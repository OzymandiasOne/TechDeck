"""Which reminders are due right now.

Pure logic: given a saved plan, the task list, the clock, and what has already
been sent, work out what the user should be told. No Qt, no tray icon, no
timers. The Qt side (``techdeck/ui/notifier.py``) only knows how to put a
string on screen.

**The rules that keep this from being annoying**, which is the entire design
problem with reminders:

* **Never fire late.** A block that already started is not a reminder, it is a
  reproach. The window is ``[now, now + lead]``, so opening TechDeck at 10am
  after it was shut all morning produces silence, not eight stale popups.
* **Never fire twice.** Every notification carries a stable key, and the keys
  already sent are persisted. Restarting the app does not replay the day.
* **Never fire outside the working day.** Optional, on by default. Nobody
  wants a work reminder at 9pm.
* **Never fire for finished work.** Ticking a block off silences it.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, date, time, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from techdeck.core.assistant.models import (
    BLOCK_FIXED, BLOCK_TASK, Schedule, SchedulePrefs, TaskItem,
    fmt_duration, fmt_time, parse_hhmm,
)

KIND_STARTING = "starting"
KIND_DIGEST = "digest"
KIND_OVERDUE = "overdue"

# Keys of already-sent reminders are kept in the store. Bounded so a heavy user
# doesn't grow the settings document forever; the oldest simply fall off, and
# re-firing a reminder from days ago is impossible anyway (the time window has
# long passed).
MAX_SENT_KEYS = 400


@dataclass
class Notification:
    """One thing to put on screen."""
    key: str
    title: str
    body: str
    kind: str = KIND_STARTING


@dataclass
class NotifyPrefs:
    """Reminder settings. Off by default is tempting, but a schedule you have
    to remember to go and look at is a schedule you stop making, so this ships
    on with a conservative lead time."""
    enabled: bool = True
    lead_minutes: int = 10
    # A morning "here's the plan" ping, so the day starts with the plan in
    # front of you rather than in a tab you forgot to open.
    daily_digest: bool = True
    digest_at: str = "07:00"
    overdue: bool = True
    quiet_outside_hours: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> "NotifyPrefs":
        base = cls()
        if not isinstance(data, dict):
            return base
        for key in base.to_dict():
            if key in data and data[key] is not None:
                setattr(base, key, data[key])
        base.enabled = bool(base.enabled)
        base.daily_digest = bool(base.daily_digest)
        base.overdue = bool(base.overdue)
        base.quiet_outside_hours = bool(base.quiet_outside_hours)
        try:
            base.lead_minutes = max(0, min(120, int(base.lead_minutes)))
        except (TypeError, ValueError):
            base.lead_minutes = 10
        return base

    def digest_time(self) -> time:
        return parse_hhmm(self.digest_at, time(7, 0))


def in_working_hours(now: datetime, prefs: SchedulePrefs,
                     lead_minutes: int = 0) -> bool:
    """Is ``now`` inside the day reminders are allowed to speak in?

    The window opens ``lead_minutes`` EARLY. "Stay quiet outside my working
    hours" must not mean "never warn me about the first thing of the day":
    with a 07:00 start and a 10 minute lead, that warning falls at 06:50, and
    a naive check swallowed the single most useful reminder there is.
    """
    start, end = prefs.start_time(), prefs.end_time()
    opens = (datetime.combine(now.date(), start)
             - timedelta(minutes=max(0, lead_minutes))).time()
    return opens <= now.time() <= end


def due_notifications(
    schedule: Optional[Schedule],
    tasks: Sequence[TaskItem],
    prefs: SchedulePrefs,
    notify: NotifyPrefs,
    now: datetime,
    already_sent: Iterable[str] = (),
) -> List[Notification]:
    """Everything that should be shown at ``now``, newest concern first."""
    if not notify.enabled:
        return []
    if notify.quiet_outside_hours and not in_working_hours(
            now, prefs, notify.lead_minutes):
        return []

    sent: Set[str] = set(already_sent or ())
    today = now.date()
    out: List[Notification] = []
    done_ids = {t.id for t in tasks if t.done}
    by_id = {t.id: t for t in tasks}

    # --- blocks about to start ----------------------------------------------
    if schedule is not None:
        horizon = now + timedelta(minutes=notify.lead_minutes)
        for block in schedule.all_blocks():
            if block.kind not in (BLOCK_TASK, BLOCK_FIXED):
                continue
            start = block.start_dt()
            if start is None or not (now <= start <= horizon):
                continue
            if block.task_id and block.task_id in done_ids:
                continue
            key = f"{KIND_STARTING}:{block.task_id or block.title}:{block.start}"
            if key in sent:
                continue
            minutes = max(0, int((start - now).total_seconds() // 60))
            lead = "now" if minutes <= 0 else f"in {minutes} min"
            part = ""
            if block.part and block.part_count > 1:
                part = f" (part {block.part} of {block.part_count})"
            body = (f"{fmt_time(start)}, {fmt_duration(block.minutes())}"
                    f"{part}\nStarting {lead}.")
            task = by_id.get(block.task_id or "")
            if task is not None and task.notes:
                body += f"\n{task.notes.splitlines()[0][:90]}"
            out.append(Notification(key=key, title=block.title, body=body,
                                    kind=KIND_STARTING))

    # --- overdue ------------------------------------------------------------
    # Once per task per day. A deadline that slipped is worth one mention each
    # morning, not one every thirty seconds until it is dealt with.
    if notify.overdue:
        late = [t for t in tasks
                if not t.done and t.deadline_date() and t.deadline_date() < today]
        for task in late:
            key = f"{KIND_OVERDUE}:{task.id}:{today.isoformat()}"
            if key in sent:
                continue
            due = task.deadline_date()
            days = (today - due).days if due else 0
            when = "yesterday" if days == 1 else f"{days} days ago"
            out.append(Notification(
                key=key, title="Past its date",
                body=f"{task.label()} was due {when}.", kind=KIND_OVERDUE))

    # --- morning digest -----------------------------------------------------
    if notify.daily_digest and schedule is not None:
        key = f"{KIND_DIGEST}:{today.isoformat()}"
        if key not in sent and now.time() >= notify.digest_time():
            body = _digest_body(schedule, done_ids, today)
            if body:
                out.append(Notification(key=key, title="Today's plan",
                                        body=body, kind=KIND_DIGEST))

    return out


def _digest_body(schedule: Schedule, done_ids: Set[str],
                 today: date) -> Optional[str]:
    """The morning summary, or None when there is nothing planned today."""
    for day_plan in schedule.days:
        if day_plan.date_obj() != today:
            continue
        blocks = [b for b in day_plan.blocks
                  if b.kind in (BLOCK_TASK, BLOCK_FIXED)
                  and not (b.task_id and b.task_id in done_ids)]
        if not blocks:
            return None
        total = sum(b.minutes() for b in blocks)
        names: List[str] = []
        for block in blocks:
            if block.title not in names:
                names.append(block.title)
        lines = [f"{len(names)} thing{'s' if len(names) != 1 else ''}, "
                 f"{fmt_duration(total)} of work."]
        for name in names[:3]:
            lines.append(f"  {name}")
        if len(names) > 3:
            lines.append(f"  and {len(names) - 3} more")
        return "\n".join(lines)
    return None


def prune_sent(keys: Iterable[str], limit: int = MAX_SENT_KEYS) -> List[str]:
    """Keep the newest ``limit`` keys, preserving order."""
    out = list(keys or [])
    return out[-limit:]
