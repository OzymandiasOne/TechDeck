"""Schedule exports.

The .ics is the one with a hard contract, it has to survive Outlook's
importer, which means CRLF line endings, escaped text, and folded long lines.
The markdown/text exports just have to be complete.
"""

from datetime import date, datetime

import pytest

from techdeck.core.assistant import exporters, scheduler
from techdeck.core.assistant.models import SchedulePrefs, TaskItem


@pytest.fixture
def schedule():
    return scheduler.build_schedule(scheduler.ScheduleRequest(
        tasks=[
            TaskItem(title="Fix the PO sheet", estimate_min=45,
                     priority="critical", notes="Header row moved again"),
            TaskItem(title="Safety meeting", estimate_min=30,
                     fixed_start="2026-08-11T09:00:00"),
            TaskItem(title="Review drawings", estimate_min=12 * 60),
        ],
        start_day=date(2026, 8, 11), end_day=date(2026, 8, 11),
        prefs=SchedulePrefs.from_dict({"buffer_pct": 0}),
        label="Today", now=datetime(2026, 8, 11, 6, 0)))


# ── ics ──────────────────────────────────────────────────────────────────────

def test_ics_is_well_formed(schedule):
    text = exporters.to_ics(schedule)
    assert text.startswith("BEGIN:VCALENDAR\r\n")
    assert text.rstrip().endswith("END:VCALENDAR")
    assert text.count("BEGIN:VEVENT") == text.count("END:VEVENT")
    assert "\r\n" in text


def test_ics_uses_crlf_everywhere(schedule):
    text = exporters.to_ics(schedule)
    # A bare LF anywhere breaks strict importers.
    assert "\n" not in text.replace("\r\n", "")


def test_ics_skips_breaks_by_default(schedule):
    assert "Lunch" not in exporters.to_ics(schedule)
    assert "Lunch" in exporters.to_ics(schedule, include_breaks=True)


def test_ics_times_are_floating_local_not_utc(schedule):
    """A plan means '7am wherever you are'. A trailing Z would shift every
    block by the timezone offset on import."""
    starts = [line for line in exporters.to_ics(schedule).splitlines()
              if line.startswith("DTSTART:")]
    assert starts
    assert all(not line.endswith("Z") for line in starts)


def test_ics_escapes_special_characters():
    from techdeck.core.assistant.models import DaySchedule, Schedule, ScheduleBlock
    plan = Schedule(range_label="x", days=[DaySchedule(day="2026-08-11", blocks=[
        ScheduleBlock(start="2026-08-11T07:00:00", end="2026-08-11T08:00:00",
                      kind="task", title="Cut; drill, then deburr",
                      note="line one\nline two")])])
    text = exporters.to_ics(plan)
    assert r"Cut\; drill\, then deburr" in text
    assert r"line one\nline two" in text


def test_ics_folds_long_lines():
    from techdeck.core.assistant.models import DaySchedule, Schedule, ScheduleBlock
    plan = Schedule(range_label="x", days=[DaySchedule(day="2026-08-11", blocks=[
        ScheduleBlock(start="2026-08-11T07:00:00", end="2026-08-11T08:00:00",
                      kind="task", title="A" * 300)])])
    for line in exporters.to_ics(plan).split("\r\n"):
        assert len(line) <= 76


def test_ics_uids_are_unique(schedule):
    uids = [line for line in exporters.to_ics(schedule).splitlines()
            if line.startswith("UID:")]
    assert len(uids) == len(set(uids))


# ── markdown / text ──────────────────────────────────────────────────────────

def test_markdown_covers_the_plan_and_the_leftovers(schedule):
    text = exporters.to_markdown(schedule)
    assert "Fix the PO sheet" in text
    assert "Safety meeting" in text
    assert "Didn't fit" in text


def test_text_export_matches_the_terminal_digest(schedule):
    assert exporters.to_text(schedule) == scheduler.summarize(schedule)


def test_tasks_to_markdown_marks_done_and_lists_links():
    tasks = [TaskItem(title="Done thing", done=True),
             TaskItem(title="Open thing", links=["https://example.com"])]
    text = exporters.tasks_to_markdown(tasks)
    assert "- [x] Done thing" in text
    assert "- [ ] Open thing" in text
    assert "<https://example.com>" in text


# ── filenames ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw", [
    'Today -> Tomorrow', 'a/b\\c:d*e?f"g<h>i|j', "   ", "." * 10,
])
def test_safe_filename_is_windows_safe(raw):
    name = exporters.safe_filename(raw, "fallback")
    assert name
    assert not set(name) & set('\\/:*?"<>|')
    assert len(name) <= 60
    assert not name.startswith(".")
