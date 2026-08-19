"""The time-blocking engine.

The plan a user gets is only trustworthy if these hold: it never books the
past, it never books over lunch or an appointment, a "one sitting" task is
never chopped up, and anything that does not fit is reported rather than
quietly dropped. Each of those is a test here.
"""

from datetime import datetime, date, timedelta

import pytest

from techdeck.core.assistant.models import (
    BLOCK_BREAK, BLOCK_FIXED, BLOCK_LUNCH, BLOCK_TASK, SchedulePrefs, TaskItem,
)
from techdeck.core.assistant import scheduler


MONDAY = date(2026, 8, 10)
TUESDAY = date(2026, 8, 11)
EARLY = datetime(2026, 8, 11, 6, 0)     # before the working day starts


def _prefs(**overrides) -> SchedulePrefs:
    base = {"day_start": "07:00", "day_end": "15:30",
            "lunch_start": "11:30", "lunch_minutes": 30,
            "buffer_pct": 0, "focus_block_min": 0, "breather_min": 0}
    base.update(overrides)
    return SchedulePrefs.from_dict(base)


def _build(tasks, start=TUESDAY, end=TUESDAY, now=EARLY, **pref_overrides):
    return scheduler.build_schedule(scheduler.ScheduleRequest(
        tasks=tasks, start_day=start, end_day=end,
        prefs=_prefs(**pref_overrides), now=now))


def _task_blocks(schedule):
    return [b for b in schedule.all_blocks() if b.kind == BLOCK_TASK]


# ── basics ───────────────────────────────────────────────────────────────────

def test_a_single_task_lands_at_the_start_of_the_day():
    schedule = _build([TaskItem(title="A", estimate_min=60)])
    block = _task_blocks(schedule)[0]
    assert block.start_dt() == datetime(2026, 8, 11, 7, 0)
    assert block.end_dt() == datetime(2026, 8, 11, 8, 0)


def test_lunch_is_always_placed_and_never_worked_through():
    schedule = _build([TaskItem(title="A", estimate_min=8 * 60)])
    lunch = [b for b in schedule.all_blocks() if b.kind == BLOCK_LUNCH]
    assert len(lunch) == 1
    for block in _task_blocks(schedule):
        assert not (block.start_dt() < lunch[0].end_dt()
                    and block.end_dt() > lunch[0].start_dt())


def test_lunch_can_be_switched_off():
    schedule = _build([TaskItem(title="A", estimate_min=30)], lunch_minutes=0)
    assert not [b for b in schedule.all_blocks() if b.kind == BLOCK_LUNCH]


def test_nothing_is_scheduled_into_the_past():
    """The most user-visible rule: replanning at 10am must not book 7am."""
    mid_morning = datetime(2026, 8, 11, 10, 17)
    schedule = _build([TaskItem(title="A", estimate_min=30)], now=mid_morning)
    assert _task_blocks(schedule)[0].start_dt() >= mid_morning


def test_estimates_are_padded_by_the_buffer():
    schedule = _build([TaskItem(title="A", estimate_min=60)], buffer_pct=15)
    # 60 * 1.15 = 69 → snapped up to the 5-minute grid = 70
    assert _task_blocks(schedule)[0].minutes() == 70


# ── ordering ─────────────────────────────────────────────────────────────────

def test_a_deadline_today_beats_a_better_score():
    """Bucketing by deadline is what stops a clever score from blowing a due
    date."""
    schedule = _build([
        TaskItem(title="big-and-due", priority="low", estimate_min=120,
                 deadline=TUESDAY.isoformat()),
        TaskItem(title="quick-win", priority="critical", estimate_min=15),
    ])
    assert _task_blocks(schedule)[0].title == "big-and-due"


def test_within_a_bucket_cost_of_delay_per_minute_wins():
    """A 15-minute high beats a 3-hour critical, five quick wins shouldn't
    rot behind one big job."""
    schedule = _build([
        TaskItem(title="slow-critical", priority="critical", estimate_min=180),
        TaskItem(title="fast-high", priority="high", estimate_min=15),
    ])
    assert _task_blocks(schedule)[0].title == "fast-high"


# ── appointments ─────────────────────────────────────────────────────────────

def test_a_fixed_task_is_placed_exactly_and_worked_around():
    schedule = _build([
        TaskItem(title="meeting", estimate_min=30,
                 fixed_start="2026-08-11T09:00:00"),
        TaskItem(title="filler", estimate_min=4 * 60),
    ])
    fixed = [b for b in schedule.all_blocks() if b.kind == BLOCK_FIXED]
    assert len(fixed) == 1
    assert fixed[0].start_dt() == datetime(2026, 8, 11, 9, 0)
    for block in _task_blocks(schedule):
        assert not (block.start_dt() < fixed[0].end_dt()
                    and block.end_dt() > fixed[0].start_dt())


def test_overlapping_appointments_are_reported_not_silently_merged():
    schedule = _build([
        TaskItem(title="A", estimate_min=60, fixed_start="2026-08-11T09:00:00"),
        TaskItem(title="B", estimate_min=60, fixed_start="2026-08-11T09:30:00"),
    ])
    assert any("overlaps" in warning for warning in schedule.warnings)


def test_an_appointment_outside_the_window_is_flagged():
    schedule = _build([
        TaskItem(title="A", estimate_min=30, fixed_start="2026-09-01T09:00:00"),
    ])
    assert any("outside this schedule" in warning for warning in schedule.warnings)


# ── splitting ────────────────────────────────────────────────────────────────

def test_a_long_task_splits_around_lunch():
    schedule = _build([TaskItem(title="A", estimate_min=6 * 60)])
    parts = [b for b in _task_blocks(schedule) if b.title == "A"]
    assert len(parts) == 2
    assert parts[0].part == 1 and parts[0].part_count == 2


def test_one_sitting_is_never_chopped_up():
    # 4h fits the 7:00–11:30 morning run whole; a splittable task of the same
    # length would have been cut at lunch.
    schedule = _build([
        TaskItem(title="deep", estimate_min=4 * 60, splittable=False),
    ])
    parts = [b for b in _task_blocks(schedule) if b.title == "deep"]
    assert len(parts) == 1
    assert parts[0].minutes() == 4 * 60


def test_one_sitting_longer_than_any_gap_is_not_forced_in():
    """7:00–15:30 with lunch at 11:30 leaves no 5-hour run. Reporting that is
    the right answer; silently splitting it is not."""
    schedule = _build([
        TaskItem(title="deep", estimate_min=5 * 60, splittable=False),
    ])
    assert not _task_blocks(schedule)
    assert "unbroken block" in schedule.unscheduled[0]["reason"]


def test_one_sitting_that_cannot_fit_is_reported_with_the_reason():
    schedule = _build([
        TaskItem(title="huge", estimate_min=10 * 60, splittable=False),
    ])
    assert not _task_blocks(schedule)
    assert len(schedule.unscheduled) == 1
    assert "unbroken block" in schedule.unscheduled[0]["reason"]


def test_adjacent_slices_of_one_task_are_merged():
    """The packer works interval by interval, so a task can come out as two
    touching pieces. On paper that's one sitting and must read as one row."""
    schedule = _build([TaskItem(title="A", estimate_min=3 * 60)],
                      focus_block_min=60, breather_min=0, min_chunk_min=15)
    blocks = [b for b in _task_blocks(schedule) if b.title == "A"]
    for earlier, later in zip(blocks, blocks[1:]):
        assert earlier.end != later.start


# ── breathers ────────────────────────────────────────────────────────────────

def test_a_breather_is_inserted_after_a_focus_block():
    schedule = _build([TaskItem(title="A", estimate_min=4 * 60)],
                      focus_block_min=90, breather_min=10, min_chunk_min=25)
    assert [b for b in schedule.all_blocks() if b.kind == BLOCK_BREAK]


def test_no_breathers_when_switched_off():
    schedule = _build([TaskItem(title="A", estimate_min=4 * 60)],
                      focus_block_min=0, breather_min=0)
    assert not [b for b in schedule.all_blocks() if b.kind == BLOCK_BREAK]


# ── overflow + deadlines ─────────────────────────────────────────────────────

def test_work_that_does_not_fit_is_listed_never_dropped():
    schedule = _build([TaskItem(title=f"J{i}", estimate_min=180)
                       for i in range(5)])
    placed = {b.title for b in _task_blocks(schedule)}
    listed = {item["title"] for item in schedule.unscheduled}
    assert placed | listed == {f"J{i}" for i in range(5)}


def test_a_partially_placed_task_reports_the_remainder():
    schedule = _build([TaskItem(title="A", estimate_min=12 * 60)])
    assert schedule.unscheduled
    assert "didn't fit" in schedule.unscheduled[0]["reason"]


def test_a_missed_deadline_is_warned_about():
    schedule = _build(
        [TaskItem(title="late", estimate_min=6 * 60,
                  deadline=TUESDAY.isoformat()),
         TaskItem(title="hog", estimate_min=7 * 60,
                  deadline=TUESDAY.isoformat())],
        start=TUESDAY, end=TUESDAY + timedelta(days=1))
    assert any("due" in warning for warning in schedule.warnings)


def test_done_tasks_are_ignored():
    schedule = _build([TaskItem(title="A", estimate_min=60, done=True)])
    assert not _task_blocks(schedule)


# ── windows ──────────────────────────────────────────────────────────────────

def test_weekends_are_skipped_unless_asked_for():
    saturday, sunday = date(2026, 8, 15), date(2026, 8, 16)
    prefs = _prefs()
    assert scheduler.working_days(saturday, sunday, prefs) == []
    prefs.include_weekends = True
    assert scheduler.working_days(saturday, sunday, prefs) == [saturday, sunday]


def test_a_window_with_no_working_days_explains_itself():
    schedule = _build([TaskItem(title="A", estimate_min=30)],
                      start=date(2026, 8, 15), end=date(2026, 8, 16))
    assert schedule.warnings
    assert schedule.unscheduled


def test_resolve_range_today_and_tomorrow():
    now = datetime(2026, 8, 11, 8, 0)
    assert scheduler.resolve_range("today", now)[:2] == (TUESDAY, TUESDAY)
    tomorrow = date(2026, 8, 12)
    assert scheduler.resolve_range("tomorrow", now)[:2] == (tomorrow, tomorrow)


def test_resolve_range_custom_swaps_reversed_dates():
    start, end, _label = scheduler.resolve_range(
        "custom", anchor=date(2026, 8, 20), end_anchor=date(2026, 8, 18))
    assert start < end


# ── summary ──────────────────────────────────────────────────────────────────

def test_summarize_mentions_every_placed_task_and_every_leftover():
    schedule = _build([TaskItem(title="Alpha", estimate_min=60),
                       TaskItem(title="Omega", estimate_min=12 * 60)])
    text = scheduler.summarize(schedule)
    assert "Alpha" in text
    assert "Omega" in text
    assert "Didn't fit" in text
