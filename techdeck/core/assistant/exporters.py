"""Turn a Schedule into something the user can take somewhere else.

Three targets, each earning its place:

* **Markdown** — pasteable into Teams or a shared doc, still readable raw.
* **Plain text** — the terminal digest (``scheduler.summarize``), re-exported
  here so callers have one import for "give me the file contents".
* **iCalendar** — the one that actually matters day to day: Outlook imports a
  ``.ics``, so a plan built here lands on the real calendar in two clicks
  instead of being retyped.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional

from techdeck.core.assistant.models import (
    BLOCK_BREAK, BLOCK_FIXED, BLOCK_LUNCH, BLOCK_TASK,
    Note, Schedule, TaskItem, fmt_day, fmt_duration,
)
from techdeck.core.assistant.scheduler import summarize

__all__ = ["to_markdown", "to_text", "to_ics", "notes_to_markdown",
           "tasks_to_markdown", "safe_filename"]


def to_text(schedule: Schedule) -> str:
    return summarize(schedule)


def to_markdown(schedule: Schedule) -> str:
    stats = schedule.stats or {}
    lines: List[str] = [f"# Schedule — {schedule.range_label}", ""]
    created = schedule.created_at.replace("T", " ")
    lines.append(f"*Built {created} · {stats.get('tasks_placed', 0)} tasks · "
                 f"{fmt_duration(stats.get('work_minutes', 0))} of work · "
                 f"estimates padded {stats.get('buffer_pct', 0)}%*")
    lines.append("")

    for day_plan in schedule.days:
        planned = [b for b in day_plan.blocks
                   if b.kind in (BLOCK_TASK, BLOCK_FIXED)]
        if not planned:
            continue
        day_date = day_plan.date_obj()
        lines.append(f"## {fmt_day(day_date) if day_date else day_plan.day}")
        lines.append("")
        lines.append("| Time | | What |")
        lines.append("|---|---|---|")
        for block in day_plan.blocks:
            icon = {BLOCK_TASK: "☐", BLOCK_FIXED: "📌",
                    BLOCK_LUNCH: "🍽", BLOCK_BREAK: "☕"}.get(block.kind, "☐")
            title = block.title
            if block.part and block.part_count > 1:
                title += f" *(part {block.part} of {block.part_count})*"
            lines.append(f"| {block.time_range()} | {icon} | {title} |")
        lines.append("")

    if schedule.unscheduled:
        lines.append("## Didn't fit")
        lines.append("")
        for item in schedule.unscheduled:
            lines.append(f"- **{item.get('title', '')}** — {item.get('reason', '')}")
        lines.append("")

    if schedule.warnings:
        lines.append("## Heads up")
        lines.append("")
        for warning in schedule.warnings:
            lines.append(f"- {warning}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ── iCalendar ────────────────────────────────────────────────────────────────

def _ics_escape(text: str) -> str:
    """RFC 5545 §3.3.11 text escaping."""
    return (str(text).replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))


def _fold(line: str) -> str:
    """RFC 5545 §3.1 line folding at 75 octets. Outlook is forgiving about
    long lines; other importers are not, and a note field easily runs long."""
    if len(line) <= 75:
        return line
    out = [line[:75]]
    rest = line[75:]
    while rest:
        out.append(" " + rest[:74])
        rest = rest[74:]
    return "\r\n".join(out)


def _ics_stamp(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def to_ics(schedule: Schedule, include_breaks: bool = False,
           calendar_name: str = "TechDeck Plan") -> str:
    """Build an importable calendar.

    Times are written **floating** (no timezone, no trailing Z) on purpose: the
    plan is "07:00 wherever you are", and floating times import into Outlook as
    local without needing a VTIMEZONE block that would have to be right about
    US DST rules to be worth having.
    """
    now = datetime.now()
    lines: List[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//TechDeck//Assistant//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_ics_escape(calendar_name)}",
    ]

    kinds = {BLOCK_TASK, BLOCK_FIXED}
    if include_breaks:
        kinds |= {BLOCK_BREAK, BLOCK_LUNCH}

    seq = 0
    for day_plan in schedule.days:
        for block in day_plan.blocks:
            if block.kind not in kinds:
                continue
            start, end = block.start_dt(), block.end_dt()
            if not start or not end:
                continue
            seq += 1
            title = block.title
            if block.part and block.part_count > 1:
                title += f" ({block.part}/{block.part_count})"
            lines.append("BEGIN:VEVENT")
            lines.append(f"UID:{schedule.id}-{seq}@techdeck")
            lines.append(f"DTSTAMP:{_ics_stamp(now)}")
            lines.append(f"DTSTART:{_ics_stamp(start)}")
            lines.append(f"DTEND:{_ics_stamp(end)}")
            lines.append(_fold(f"SUMMARY:{_ics_escape(title)}"))
            if block.note:
                lines.append(_fold(f"DESCRIPTION:{_ics_escape(block.note)}"))
            if block.kind in (BLOCK_BREAK, BLOCK_LUNCH):
                lines.append("TRANSP:TRANSPARENT")
            lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    # CRLF is required by the spec and by Outlook's importer.
    return "\r\n".join(lines) + "\r\n"


# ── Notes / tasks ────────────────────────────────────────────────────────────

def notes_to_markdown(notes: Iterable[Note]) -> str:
    lines: List[str] = ["# Personal Notes", ""]
    for note in notes:
        lines.append(f"## {note.title}")
        stamp = note.updated_at.replace("T", " ")
        pin = " · 📌 pinned" if note.pinned else ""
        lines.append(f"*Updated {stamp}{pin}*")
        lines.append("")
        lines.append(note.body.rstrip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def tasks_to_markdown(tasks: Iterable[TaskItem], title: str = "Tasks") -> str:
    lines: List[str] = [f"# {title}", ""]
    for task in tasks:
        box = "x" if task.done else " "
        bits = [f"{fmt_duration(task.estimate_min)}", task.priority]
        if task.deadline:
            bits.append(f"due {task.deadline}")
        lines.append(f"- [{box}] {task.label()}  *({' · '.join(bits)})*")
        for link in task.links:
            lines.append(f"    - <{link}>")
        for note_line in (task.notes or "").splitlines():
            if note_line.strip():
                lines.append(f"    > {note_line.strip()}")
    return "\n".join(lines).rstrip() + "\n"


def safe_filename(text: str, fallback: str = "techdeck") -> str:
    """Windows-safe file stem. Every reserved character goes, and the result is
    length-capped so a long range label can't blow the 260-char path limit."""
    cleaned = "".join(c if c.isalnum() or c in " -_" else "_" for c in str(text))
    cleaned = " ".join(cleaned.split()).strip(" ._-")
    return (cleaned or fallback)[:60]
