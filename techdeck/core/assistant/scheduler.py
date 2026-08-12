"""The time-blocking engine.

Given a pile of tasks and the shape of the user's working day, produce a real
agenda: what to do, when, and what didn't fit.

**How it decides.** Two ideas do the work, and both are explainable to the
person whose day it is:

1. *Deadline buckets.* Walking day by day, anything already due that day (or
   overdue) is placed first, no clever score is allowed to push a
   due-today task past its deadline.
2. *WSJF within a bucket.* Whatever's left competes on cost-of-delay per
   minute (``TaskItem.score``), so a 15-minute high-priority job outranks a
   3-hour one. This is what stops a single big task from eating the morning
   while five quick wins rot.

On top of that: every estimate is padded (people under-estimate), long stretches
get a breather, splittable work is sliced but never into useless slivers, and
"one sitting" tasks demand a contiguous block or don't get scheduled at all.

Pure functions over the models, no Qt, no I/O, fully unit-testable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, date, time, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from techdeck.core.assistant.models import (
    BLOCK_BREAK, BLOCK_FIXED, BLOCK_LUNCH, BLOCK_TASK,
    DaySchedule, Schedule, ScheduleBlock, SchedulePrefs, TaskItem,
    fmt_day, fmt_duration,
)

# Everything snaps to this grid. A plan full of 07:13–08:41 blocks reads as
# machine output and gets ignored; 5-minute boundaries read as a plan.
GRID = 5


def _snap_up(minutes: float) -> int:
    return int(math.ceil(minutes / GRID) * GRID)


def _snap_down(minutes: float) -> int:
    return int(math.floor(minutes / GRID) * GRID)


def _mins(t: time) -> int:
    return t.hour * 60 + t.minute


def _at(day: date, minute_of_day: int) -> datetime:
    """Minute-of-day → datetime, rolling into the next day if it overshoots."""
    return datetime.combine(day, time(0, 0)) + timedelta(minutes=int(minute_of_day))


@dataclass
class _Pending:
    """A flexible task mid-placement: how much of it is still unplaced, and how
    many pieces it has been cut into so far."""
    task: TaskItem
    remaining: int
    total: int
    parts: int = 0

    @property
    def splittable(self) -> bool:
        return self.task.splittable


@dataclass
class ScheduleRequest:
    """Everything the engine needs. Built by the wizard, the terminal, or a
    test, all three go through this one door."""
    tasks: Sequence[TaskItem]
    start_day: date
    end_day: date
    prefs: SchedulePrefs
    label: str = ""
    now: Optional[datetime] = None
    # Optional hard clamp on the first day, for "plan my afternoon".
    first_day_start: Optional[time] = None
    last_day_end: Optional[time] = None


def padded_minutes(task: TaskItem, prefs: SchedulePrefs) -> int:
    """The estimate the engine actually plans against, the user's number plus
    the optimism buffer, snapped to the grid."""
    raw = max(GRID, int(task.estimate_min or 0))
    return max(GRID, _snap_up(raw * (1.0 + prefs.buffer_pct / 100.0)))


# ── Day windows ──────────────────────────────────────────────────────────────

def working_days(start: date, end: date, prefs: SchedulePrefs) -> List[date]:
    """Every day the user is willing to work in the range, in order."""
    days: List[date] = []
    cursor = start
    guard = 0
    while cursor <= end and guard < 400:
        guard += 1
        if prefs.include_weekends or cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _free_intervals(day: date, prefs: SchedulePrefs, req: ScheduleRequest,
                    busy: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """Open stretches on ``day``, as (start_min, end_min) pairs.

    Starts from the working day, cuts out lunch and every already-committed
    block, and, on the current day, refuses to schedule into the past.
    """
    start = _mins(prefs.start_time())
    end = _mins(prefs.end_time())
    if req.first_day_start and day == req.start_day:
        start = max(start, _mins(req.first_day_start))
    if req.last_day_end and day == req.end_day:
        end = min(end, _mins(req.last_day_end))

    now = req.now or datetime.now()
    if day == now.date():
        start = max(start, _snap_up(_mins(now.time()) + 1))

    if end <= start:
        return []

    blocked = sorted(busy)
    free: List[Tuple[int, int]] = []
    cursor = start
    for b_start, b_end in blocked:
        b_start, b_end = max(b_start, start), min(b_end, end)
        if b_end <= cursor:
            continue
        if b_start > cursor:
            free.append((cursor, min(b_start, end)))
        cursor = max(cursor, b_end)
        if cursor >= end:
            break
    if cursor < end:
        free.append((cursor, end))
    return [(s, e) for s, e in free if e - s >= GRID]


# ── The engine ───────────────────────────────────────────────────────────────

def build_schedule(req: ScheduleRequest) -> Schedule:
    """Produce a Schedule for the request. Never raises on bad input, an
    impossible window yields an empty plan with a warning explaining why."""
    prefs = req.prefs
    now = req.now or datetime.now()
    today = now.date()
    schedule = Schedule(range_label=req.label or _default_label(req))

    days = working_days(req.start_day, req.end_day, prefs)
    if not days:
        schedule.warnings.append(
            "That range has no working days in it. Turn on weekends in "
            "Advanced, or pick a different range.")
        for task in req.tasks:
            if not task.done:
                schedule.unscheduled.append(
                    {"task_id": task.id, "title": task.label(),
                     "reason": "no working days in range"})
        return schedule

    active = [t for t in req.tasks if not t.done and t.label()]

    # --- 1. appointments: immovable, placed before anything else ------------
    fixed_by_day: Dict[date, List[Tuple[int, int, TaskItem]]] = {d: [] for d in days}
    for task in active:
        start_dt = task.fixed_datetime()
        if start_dt is None:
            continue
        day = start_dt.date()
        # An appointment is a commitment someone else made with you, plan the
        # raw duration, not the padded one; the buffer is for your own guesses.
        length = max(GRID, _snap_up(task.estimate_min))
        if day not in fixed_by_day:
            schedule.warnings.append(
                f"“{task.label()}” is set for {day.isoformat()}, which is "
                f"outside this schedule. Left where it is.")
            continue
        begin = _mins(start_dt.time())
        fixed_by_day[day].append((begin, begin + length, task))

    for day, items in fixed_by_day.items():
        items.sort()
        for i in range(1, len(items)):
            if items[i][0] < items[i - 1][1]:
                schedule.warnings.append(
                    f"{fmt_day(day)}: “{items[i][2].label()}” overlaps "
                    f"“{items[i - 1][2].label()}”. Both are shown. You'll have "
                    f"to move one.")

    # --- 2. the flexible pool ------------------------------------------------
    pending = [
        _Pending(task=t, remaining=padded_minutes(t, prefs),
                 total=padded_minutes(t, prefs))
        for t in active if t.fixed_datetime() is None
    ]

    # --- 3. walk the days ----------------------------------------------------
    for day in days:
        blocks: List[ScheduleBlock] = []
        busy: List[Tuple[int, int]] = []

        lunch = prefs.lunch_time()
        if lunch is not None:
            l_start = _mins(lunch)
            l_end = l_start + prefs.lunch_minutes
            busy.append((l_start, l_end))
            blocks.append(ScheduleBlock(
                start=_at(day, l_start).isoformat(), end=_at(day, l_end).isoformat(),
                kind=BLOCK_LUNCH, title="Lunch"))

        for begin, finish, task in fixed_by_day.get(day, []):
            busy.append((begin, finish))
            blocks.append(ScheduleBlock(
                start=_at(day, begin).isoformat(), end=_at(day, finish).isoformat(),
                kind=BLOCK_FIXED, title=task.label(), task_id=task.id,
                note=task.notes))

        for interval in _free_intervals(day, prefs, req, busy):
            _pack_interval(interval, day, pending, prefs, blocks, today)

        blocks.sort(key=lambda b: b.start)
        blocks = _merge_adjacent(blocks)
        # A lunch or appointment on a day where nothing else got planned is
        # still worth showing, it's why the day looks empty.
        schedule.days.append(DaySchedule(day=day.isoformat(), blocks=blocks))

    _stamp_parts(schedule)

    # --- 4. what didn't fit --------------------------------------------------
    for entry in pending:
        if entry.remaining <= 0:
            continue
        task = entry.task
        if entry.remaining == entry.total:
            reason = ("needs one unbroken block of "
                      f"{fmt_duration(entry.total)} and no gap is that long"
                      ) if not entry.splittable else "ran out of room in this range"
        else:
            reason = (f"{fmt_duration(entry.remaining)} of "
                      f"{fmt_duration(entry.total)} didn't fit")
        schedule.unscheduled.append(
            {"task_id": task.id, "title": task.label(), "reason": reason,
             "minutes": entry.remaining, "priority": task.priority,
             "deadline": task.deadline})

    _add_deadline_warnings(schedule, active, pending, days)
    schedule.stats = _stats(schedule, days, prefs)
    return schedule


def _pack_interval(interval: Tuple[int, int], day: date, pending: List[_Pending],
                   prefs: SchedulePrefs, blocks: List[ScheduleBlock],
                   today: date) -> None:
    """Fill one open stretch of the day, in place."""
    cursor, end = interval
    continuous = 0

    while cursor < end:
        window = end - cursor
        if window < GRID:
            break

        cap = window
        if prefs.focus_block_min > 0 and prefs.breather_min > 0:
            room = prefs.focus_block_min - continuous
            if room < prefs.min_chunk_min:
                # Time for a breather, but only if there is enough left after
                # it to be worth sitting back down for.
                if window >= prefs.breather_min + prefs.min_chunk_min and \
                        any(p.remaining > 0 for p in pending):
                    blocks.append(ScheduleBlock(
                        start=_at(day, cursor).isoformat(),
                        end=_at(day, cursor + prefs.breather_min).isoformat(),
                        kind=BLOCK_BREAK, title="Breather"))
                    cursor += prefs.breather_min
                    continuous = 0
                    continue
                room = window        # not worth a break; run out the clock
            cap = min(cap, max(room, prefs.min_chunk_min))

        placed = False
        for entry in _ordered(pending, day, today):
            need = entry.remaining
            if entry.splittable:
                chunk = _snap_down(min(need, cap))
                # Never leave a sliver too small to be useful, unless the
                # sliver IS the whole remainder of the task.
                if chunk < need and chunk < prefs.min_chunk_min:
                    continue
                if chunk < GRID:
                    continue
            else:
                # "One sitting" beats the focus block: it either gets its whole
                # contiguous run here or waits for a stretch that can hold it.
                if need > window:
                    continue
                chunk = need

            entry.parts += 1
            entry.remaining -= chunk
            blocks.append(ScheduleBlock(
                start=_at(day, cursor).isoformat(),
                end=_at(day, cursor + chunk).isoformat(),
                kind=BLOCK_TASK, title=entry.task.label(),
                task_id=entry.task.id, note=entry.task.notes))
            cursor += chunk
            continuous += chunk
            placed = True
            break

        if not placed:
            break


def _merge_adjacent(blocks: List[ScheduleBlock]) -> List[ScheduleBlock]:
    """Fuse back-to-back slices of the same task.

    The packer works one open stretch at a time and caps chunks at the focus
    block, so a task can end up as "part 1 of 2" immediately followed by "part 2
    of 2" with nothing between them. On paper that's two rows for one sitting, merge them so a split only ever appears where there's a real interruption.
    """
    merged: List[ScheduleBlock] = []
    for block in blocks:
        previous = merged[-1] if merged else None
        if (previous is not None and block.kind == BLOCK_TASK
                and previous.kind == BLOCK_TASK
                and block.task_id and previous.task_id == block.task_id
                and previous.end == block.start):
            previous.end = block.end
            continue
        merged.append(block)
    return merged


def _stamp_parts(schedule: Schedule) -> None:
    """Number a task's slices across the WHOLE plan, not per day, a task split
    over two afternoons is "part 1 of 2" and "part 2 of 2", not two part-1s."""
    counts: Dict[str, int] = {}
    for block in schedule.all_blocks():
        if block.kind == BLOCK_TASK and block.task_id:
            counts[block.task_id] = counts.get(block.task_id, 0) + 1
    seen: Dict[str, int] = {}
    for block in schedule.all_blocks():
        if block.kind != BLOCK_TASK or not block.task_id:
            continue
        total = counts.get(block.task_id, 1)
        if total < 2:
            block.part, block.part_count = 0, 0
            continue
        seen[block.task_id] = seen.get(block.task_id, 0) + 1
        block.part, block.part_count = seen[block.task_id], total


def _ordered(pending: List[_Pending], day: date, today: date) -> List[_Pending]:
    """Candidate order for ``day``: due-by-today's-bucket first (earliest
    deadline wins), then everything else by cost-of-delay per minute."""
    live = [p for p in pending if p.remaining > 0]
    due_now, rest = [], []
    for entry in live:
        deadline = entry.task.deadline_date()
        (due_now if deadline is not None and deadline <= day else rest).append(entry)

    due_now.sort(key=lambda p: (p.task.deadline_date() or day,
                                -p.task.score(today), p.task.created_at))
    rest.sort(key=lambda p: (-p.task.score(today),
                             p.task.deadline_date() or date.max,
                             p.task.created_at))
    return due_now + rest


def _add_deadline_warnings(schedule: Schedule, tasks: Sequence[TaskItem],
                           pending: List[_Pending], days: List[date]) -> None:
    """Flag every deadline the plan does not actually hit, the single most
    useful thing a schedule can tell you, and the easiest to miss by eye."""
    last_end: Dict[str, date] = {}
    for day_plan in schedule.days:
        day_date = day_plan.date_obj()
        for block in day_plan.blocks:
            if block.kind in (BLOCK_TASK, BLOCK_FIXED) and block.task_id and day_date:
                previous = last_end.get(block.task_id)
                if previous is None or day_date > previous:
                    last_end[block.task_id] = day_date

    unplaced = {p.task.id for p in pending if p.remaining > 0}
    window_end = days[-1] if days else None

    for task in tasks:
        due = task.deadline_date()
        if due is None:
            continue
        if task.id in unplaced:
            if window_end is not None and due <= window_end:
                schedule.warnings.append(
                    f"⚠ “{task.label()}” is due {due.isoformat()} and there is "
                    f"no room for it in this plan.")
            continue
        finish = last_end.get(task.id)
        if finish is not None and finish > due:
            schedule.warnings.append(
                f"⚠ “{task.label()}” is due {due.isoformat()} but the plan "
                f"doesn't finish it until {finish.isoformat()}.")


def _stats(schedule: Schedule, days: List[date], prefs: SchedulePrefs) -> Dict[str, Any]:
    work = sum(b.minutes() for b in schedule.task_blocks())
    breaks = sum(b.minutes() for b in schedule.all_blocks()
                 if b.kind in (BLOCK_BREAK, BLOCK_LUNCH))
    capacity = 0
    for day_plan in schedule.days:
        blocks = day_plan.blocks
        if not blocks:
            continue
        starts = [b.start_dt() for b in blocks if b.start_dt()]
        ends = [b.end_dt() for b in blocks if b.end_dt()]
        if starts and ends:
            capacity += int((max(ends) - min(starts)).total_seconds() // 60)
    task_ids = {b.task_id for b in schedule.task_blocks() if b.task_id}
    return {
        "work_minutes": work,
        "break_minutes": breaks,
        "days": len(days),
        "tasks_placed": len(task_ids),
        "tasks_unplaced": len(schedule.unscheduled),
        "utilization": round(100.0 * work / capacity, 1) if capacity else 0.0,
        "buffer_pct": prefs.buffer_pct,
    }


def _default_label(req: ScheduleRequest) -> str:
    if req.start_day == req.end_day:
        return fmt_day(req.start_day)
    return f"{fmt_day(req.start_day)} → {fmt_day(req.end_day)}"


# ── Ranges the UI offers ─────────────────────────────────────────────────────

RANGE_CHOICES = [
    ("rest_of_today", "Rest of today"),
    ("today", "Today"),
    ("tomorrow", "Tomorrow"),
    ("this_week", "Rest of this week"),
    ("next_week", "Next week"),
    ("pick_day", "A specific day"),
    ("custom", "Custom range"),
]


def resolve_range(key: str, now: Optional[datetime] = None,
                  anchor: Optional[date] = None,
                  end_anchor: Optional[date] = None) -> Tuple[date, date, str]:
    """Turn a range key from the wizard into concrete dates + a label."""
    now = now or datetime.now()
    today = now.date()
    if key == "today" or key == "rest_of_today":
        return today, today, "Today"
    if key == "tomorrow":
        day = today + timedelta(days=1)
        return day, day, "Tomorrow"
    if key == "this_week":
        end = today + timedelta(days=(4 - today.weekday()) % 7)
        if end < today:
            end = today
        return today, end, "Rest of this week"
    if key == "next_week":
        start = today + timedelta(days=7 - today.weekday())
        return start, start + timedelta(days=4), "Next week"
    if key == "pick_day":
        day = anchor or today
        return day, day, fmt_day(day)
    if key == "custom":
        start = anchor or today
        end = end_anchor or start
        if end < start:
            start, end = end, start
        return start, end, f"{fmt_day(start)} → {fmt_day(end)}"
    return today, today, "Today"


# ── Human-readable summary (used by the terminal + the wizard preview) ───────

def summarize(schedule: Schedule) -> str:
    """A compact plain-text digest of a plan."""
    stats = schedule.stats or {}
    lines = [f"{schedule.range_label}: {stats.get('tasks_placed', 0)} task(s), "
             f"{fmt_duration(stats.get('work_minutes', 0))} of planned work"]
    if stats.get("buffer_pct"):
        lines[0] += f" (estimates padded {stats['buffer_pct']}%)"
    for day_plan in schedule.days:
        day_date = day_plan.date_obj()
        planned = [b for b in day_plan.blocks if b.kind in (BLOCK_TASK, BLOCK_FIXED)]
        if not planned:
            continue
        lines.append("")
        lines.append(fmt_day(day_date) if day_date else day_plan.day)
        for block in day_plan.blocks:
            marker = {BLOCK_TASK: "•", BLOCK_FIXED: "◆",
                      BLOCK_LUNCH: "·", BLOCK_BREAK: "·"}.get(block.kind, "•")
            suffix = ""
            if block.part and block.part_count > 1:
                suffix = f"  (part {block.part} of {block.part_count})"
            lines.append(f"  {block.time_range():<20} {marker} {block.title}{suffix}")
    if schedule.unscheduled:
        lines.append("")
        lines.append("Didn't fit:")
        for item in schedule.unscheduled:
            lines.append(f"  {item['title']}: {item['reason']}")
    if schedule.warnings:
        lines.append("")
        for warning in schedule.warnings:
            lines.append(warning)
    return "\n".join(lines)
