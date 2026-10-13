"""Where the time actually went.

The schedule says what the day was *supposed* to look like. This says what it
looked like: every clocked stretch of work, rolled up so the question people
actually ask -- "why did this week disappear?" -- has an answer with numbers in
it rather than a feeling.

Two deliberate limits, both of which keep the numbers honest:

* **A session counts on the day it STARTED.** Splitting one across midnight
  would be more precise and less true: nobody working at 11:50pm thinks of it
  as two days' work.
* **Estimates and logged time are reported side by side, never reconciled.**
  The app does not "correct" an estimate from the clock, and it does not grade
  anybody on the gap. It shows both and leaves the reading to the person whose
  week it was.

Pure functions over the models: no Qt, no I/O, fully unit-testable.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from techdeck.core.assistant.models import (
    TaskItem, fmt_duration, PRIORITY_LABELS,
)

# The ranges the Time tab offers, in the order it offers them.
RANGE_CHOICES = [
    ("today", "Today"),
    ("week", "This week"),
    ("last_week", "Last week"),
    ("month", "This month"),
    ("all", "Everything"),
]


@dataclass
class TaskTotal:
    """One row of the report: a task and what it has cost so far."""
    task_id: str
    title: str
    minutes: int
    sessions: int
    estimate_min: int = 0
    done: bool = False
    running: bool = False
    priority: str = "medium"

    @property
    def over_estimate(self) -> bool:
        """Has this task cost more than it was booked for?

        Reported, never acted on: a task that ran long is information, and the
        most useful thing the page can do with it is show it.
        """
        return bool(self.estimate_min) and self.minutes > self.estimate_min

    def priority_label(self) -> str:
        return PRIORITY_LABELS.get(self.priority, "Medium")


@dataclass
class TimeReport:
    """Everything the Time tab draws: the rows, the totals, and the days."""
    label: str = ""
    start: Optional[date] = None
    end: Optional[date] = None
    rows: List[TaskTotal] = field(default_factory=list)
    per_day: List[Tuple[date, int]] = field(default_factory=list)

    @property
    def total_minutes(self) -> int:
        return sum(row.minutes for row in self.rows)

    @property
    def tasks_touched(self) -> int:
        return len(self.rows)

    @property
    def busiest_day(self) -> Optional[Tuple[date, int]]:
        return max(self.per_day, key=lambda pair: pair[1]) if self.per_day else None

    def headline(self) -> str:
        """One line for the top of the tab."""
        if not self.rows:
            return "Nothing clocked in this range."
        bits = [f"{fmt_duration(self.total_minutes)} logged",
                f"{self.tasks_touched} task"
                f"{'s' if self.tasks_touched != 1 else ''}"]
        if len(self.per_day) > 1:
            average = self.total_minutes // max(1, len(self.per_day))
            bits.append(f"{fmt_duration(average)} on an average working day")
        return "  ·  ".join(bits)


def resolve_range(key: str, today: Optional[date] = None
                  ) -> Tuple[Optional[date], Optional[date], str]:
    """Range key -> (start, end, label). ``all`` returns (None, None).

    The week runs Monday to Sunday, matching the scheduler's working week and
    the way the forecast is read on the floor.
    """
    today = today or date.today()
    if key == "today":
        return today, today, "Today"
    if key == "week":
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=6), "This week"
    if key == "last_week":
        this_week = today - timedelta(days=today.weekday())
        start = this_week - timedelta(days=7)
        return start, start + timedelta(days=6), "Last week"
    if key == "month":
        start = today.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1) - timedelta(days=1)
        else:
            end = start.replace(month=start.month + 1) - timedelta(days=1)
        return start, end, "This month"
    return None, None, "Everything"


def build_report(tasks: Sequence[TaskItem], key: str = "week",
                 now: Optional[datetime] = None) -> TimeReport:
    """Roll the clocked sessions up for one range, biggest cost first."""
    now = now or datetime.now()
    start, end, label = resolve_range(key, now.date())
    report = TimeReport(label=label, start=start, end=end)

    per_day: Dict[date, int] = {}
    for task in tasks:
        minutes = 0
        count = 0
        for session in task.sessions:
            day = session.day()
            if day is None:
                continue
            if start is not None and end is not None and not (
                    start <= day <= end):
                continue
            length = session.minutes(now)
            if length <= 0:
                continue
            minutes += length
            count += 1
            per_day[day] = per_day.get(day, 0) + length
        if minutes <= 0:
            continue
        report.rows.append(TaskTotal(
            task_id=task.id, title=task.label(), minutes=minutes,
            sessions=count, estimate_min=max(0, int(task.estimate_min or 0)),
            done=task.done, running=task.is_running, priority=task.priority))

    # Biggest first: the point of the page is "what ate the week", and that is
    # the top row, not an alphabetical hunt.
    report.rows.sort(key=lambda row: (-row.minutes, row.title.lower()))
    report.per_day = sorted(per_day.items())
    return report


def digest(tasks: Sequence[TaskItem], key: str = "week",
           now: Optional[datetime] = None, limit: int = 8) -> str:
    """The plain-text version, for the terminal's ``/time``."""
    report = build_report(tasks, key, now)
    lines = [f"{report.label}: {report.headline()}"]
    if not report.rows:
        lines.append("")
        lines.append("Press ▶ on a task to start the clock, "
                     "or type /clockin <task>.")
        return "\n".join(lines)

    lines.append("")
    width = max((len(row.title) for row in report.rows[:limit]), default=10)
    width = min(44, max(16, width))
    for row in report.rows[:limit]:
        title = row.title if len(row.title) <= width else row.title[:width - 1] + "…"
        tail = fmt_duration(row.minutes)
        if row.estimate_min:
            tail += f"  (booked {fmt_duration(row.estimate_min)})"
        if row.running:
            tail += "  ← running now"
        lines.append(f"  {title:<{width}}  {tail}")
    if len(report.rows) > limit:
        rest = sum(r.minutes for r in report.rows[limit:])
        lines.append(f"  {'and ' + str(len(report.rows) - limit) + ' more':<{width}}"
                     f"  {fmt_duration(rest)}")

    if len(report.per_day) > 1:
        lines.append("")
        for day, minutes in report.per_day:
            lines.append(f"  {day.strftime('%a %b')} {day.day:<2}"
                         f"   {fmt_duration(minutes)}")
    return "\n".join(lines)


def to_csv(tasks: Sequence[TaskItem], key: str = "all",
           now: Optional[datetime] = None) -> str:
    """Every session in the range, one row each, for Excel.

    Session-level rather than summarised on purpose: a roll-up is one
    PivotTable away from the rows, and the rows cannot be recovered from a
    roll-up.
    """
    now = now or datetime.now()
    start, end, _ = resolve_range(key, now.date())
    buffer = io.StringIO()
    # QUOTE_MINIMAL plus an explicit \r\n: Excel on Windows expects CRLF, and
    # the caller writes the file with newline="" so these survive verbatim.
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(["Date", "Task", "Priority", "Start", "End", "Minutes",
                     "Hours", "Estimate (min)", "Done", "Note"])
    rows: List[list] = []
    for task in tasks:
        for session in task.sessions:
            day = session.day()
            if day is None:
                continue
            if start is not None and end is not None and not (
                    start <= day <= end):
                continue
            minutes = session.minutes(now)
            if minutes <= 0:
                continue
            begin, finish = session.start_dt(), session.end_dt()
            rows.append([
                day.isoformat(),
                task.label(),
                PRIORITY_LABELS.get(task.priority, "Medium"),
                begin.strftime("%H:%M") if begin else "",
                finish.strftime("%H:%M") if finish else "running",
                minutes,
                round(minutes / 60.0, 2),
                int(task.estimate_min or 0),
                "yes" if task.done else "no",
                session.note,
            ])
    rows.sort(key=lambda r: (r[0], r[3]))
    writer.writerows(rows)
    return buffer.getvalue()
