"""Meetings and other standing claims on the day.

The point of a Commitment is that the planner may not use that time. The tests
that matter are the ones proving work moves AROUND it (rather than on top of
it, or not at all), that a weekly block lands on every one of its weekdays,
and that the one place a meeting must NOT appear is the .ics export, because it
is already on the real calendar.
"""

from datetime import date, datetime

import pytest

from techdeck.core.assistant import exporters
from techdeck.core.assistant.models import (
    BLOCK_BUSY, Commitment, SchedulePrefs, TaskItem,
)
from techdeck.core.assistant.scheduler import (
    ScheduleRequest, build_schedule,
)
from techdeck.core.assistant.store import AssistantStore

# A Wednesday, so weekday() == 2 and the weekend rules stay out of the way.
WEDNESDAY = date(2026, 10, 14)
BEFORE = datetime(2026, 10, 13, 12, 0)


@pytest.fixture
def prefs():
    return SchedulePrefs.from_dict({"day_start": "07:00", "day_end": "15:30",
                                    "lunch_minutes": 0, "focus_block_min": 0})


def _plan(tasks, commitments, prefs, day=WEDNESDAY):
    return build_schedule(ScheduleRequest(
        tasks=tasks, start_day=day, end_day=day, prefs=prefs,
        now=BEFORE, commitments=commitments))


# ── the model ────────────────────────────────────────────────────────────────

def test_a_weekly_block_lands_on_each_of_its_weekdays():
    weekly = Commitment(title="Huddle", weekdays=[0, 2, 4])
    assert weekly.occurs_on(date(2026, 10, 12))      # Monday
    assert weekly.occurs_on(WEDNESDAY)               # Wednesday
    assert not weekly.occurs_on(date(2026, 10, 13))  # Tuesday


def test_a_one_off_lands_only_on_its_own_date():
    once = Commitment(title="Audit", day=WEDNESDAY.isoformat())
    assert once.occurs_on(WEDNESDAY)
    assert not once.occurs_on(date(2026, 10, 21))


def test_switched_off_means_it_claims_nothing():
    """The off switch is for a meeting that has been paused: it stays on the
    list (so it can come back) without blocking a minute."""
    paused = Commitment(title="Paused", weekdays=[2], active=False)
    assert not paused.occurs_on(WEDNESDAY)


def test_weekdays_survive_a_hand_edited_file():
    revived = Commitment.from_dict(
        {"title": "x", "weekdays": [2, "4", 99, None, 2], "minutes": "90"})
    assert revived.weekdays == [2, 4]
    assert revived.minutes == 90


# ── the engine ───────────────────────────────────────────────────────────────

def test_work_is_planned_around_a_meeting_not_through_it(prefs):
    meeting = Commitment(title="Production meeting", start="09:00",
                         minutes=60, weekdays=[2])
    schedule = _plan([TaskItem(title="Big job", estimate_min=240)],
                     [meeting], prefs)

    busy = schedule.busy_blocks()
    assert [b.title for b in busy] == ["Production meeting"]
    meeting_start, meeting_end = busy[0].start_dt(), busy[0].end_dt()
    assert meeting_start and meeting_end
    # Nothing overlaps the meeting.
    for block in schedule.task_blocks():
        start, end = block.start_dt(), block.end_dt()
        assert start and end
        assert not (start < meeting_end and meeting_start < end)


def test_a_meeting_is_not_counted_as_your_work(prefs):
    """A meeting is time you do not have, not work you did. Counting it as
    work would flatter every utilisation number on the page."""
    schedule = _plan([TaskItem(title="Job", estimate_min=60)],
                     [Commitment(title="Meeting", start="09:00", minutes=60,
                                 weekdays=[2])], prefs)
    assert schedule.stats["committed_minutes"] == 60
    # 60 padded by 15% is 69, snapped up to the 5-minute grid.
    assert schedule.stats["work_minutes"] == 70
    assert all(b.kind != BLOCK_BUSY for b in schedule.task_blocks())


def test_a_day_eaten_by_meetings_leaves_the_work_unplaced(prefs):
    """Overbooked is a real answer, and it has to be said out loud rather
    than shown as an empty day."""
    all_day = Commitment(title="Offsite", start="07:00", minutes=8 * 60,
                         weekdays=[2])
    schedule = _plan([TaskItem(title="Job", estimate_min=60)], [all_day], prefs)
    assert schedule.unscheduled
    assert schedule.unscheduled[0]["title"] == "Job"


def test_an_inactive_meeting_blocks_nothing_in_the_plan(prefs):
    schedule = _plan([TaskItem(title="Job", estimate_min=60)],
                     [Commitment(title="Paused", start="07:00",
                                 minutes=8 * 60, weekdays=[2],
                                 active=False)], prefs)
    assert schedule.busy_blocks() == []
    assert not schedule.unscheduled


# ── exports ──────────────────────────────────────────────────────────────────

def test_the_ics_export_leaves_meetings_out(prefs):
    """They were typed in BECAUSE they are already on the calendar. Writing
    them back would import a second copy of every standing meeting."""
    schedule = _plan([TaskItem(title="Job", estimate_min=60)],
                     [Commitment(title="Production meeting", start="09:00",
                                 minutes=60, weekdays=[2])], prefs)
    ics = exporters.to_ics(schedule)
    assert "Job" in ics
    assert "Production meeting" not in ics


def test_the_markdown_export_shows_meetings(prefs):
    schedule = _plan([TaskItem(title="Job", estimate_min=60)],
                     [Commitment(title="Production meeting", start="09:00",
                                 minutes=60, weekdays=[2])], prefs)
    assert "Production meeting" in exporters.to_markdown(schedule)


# ── the store ────────────────────────────────────────────────────────────────

def test_commitments_round_trip(tmp_path):
    store = AssistantStore(tmp_path / "assistant")
    store.add_commitment(Commitment(title="Huddle", weekdays=[0, 2],
                                    start="08:30", minutes=15))
    store.add_commitment(Commitment(title="Audit",
                                    day=WEDNESDAY.isoformat()))

    reloaded = AssistantStore(store.dir)
    assert {c.title for c in reloaded.commitments} == {"Huddle", "Audit"}
    assert [c.title for c in reloaded.commitments_on(WEDNESDAY)] == [
        "Huddle", "Audit"]      # start-time order: 08:30 then the 09:00 default


def test_standing_blocks_sort_before_one_offs(tmp_path):
    store = AssistantStore(tmp_path / "assistant")
    store.add_commitment(Commitment(title="Once", day="2026-10-14"))
    store.add_commitment(Commitment(title="Weekly", weekdays=[4]))
    assert [c.title for c in store.sorted_commitments()] == ["Weekly", "Once"]


# ── the 5-minute grid ────────────────────────────────────────────────────────

def test_a_meeting_off_the_grid_is_snapped_outwards(prefs):
    """Everything on this page lives on a 5-minute grid. A meeting typed as
    9:04 (one stray press of the spinner) would otherwise put a lone
    9:04-9:34 row in a plan where nothing else is off-grid.

    Outwards, not nearest: it protects a little more of the meeting, never
    less, so work can never be planned into its first minutes.
    """
    schedule = _plan([TaskItem(title="Job", estimate_min=30)],
                     [Commitment(title="Standup", start="09:04", minutes=22,
                                 weekdays=[2])], prefs)
    busy = schedule.busy_blocks()[0]
    start, end = busy.start_dt(), busy.end_dt()
    assert start and end
    assert (start.hour, start.minute) == (9, 0)
    assert start.minute % 5 == 0 and end.minute % 5 == 0
    assert busy.minutes() >= 22


def test_no_block_in_a_plan_is_ever_off_the_grid(prefs):
    schedule = _plan([TaskItem(title="Job", estimate_min=95)],
                     [Commitment(title="Standup", start="09:04", minutes=7,
                                 weekdays=[2]),
                      Commitment(title="Review", start="13:03", minutes=48,
                                 weekdays=[2])], prefs)
    for block in schedule.all_blocks():
        start, end = block.start_dt(), block.end_dt()
        assert start and end
        assert start.minute % 5 == 0, f"{block.title} starts at {block.start}"
        assert end.minute % 5 == 0, f"{block.title} ends at {block.end}"
