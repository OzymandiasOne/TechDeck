"""The clock and the time report.

The feature is only worth having if the numbers are honest, so these are the
tests about honesty: one clock at a time, a mis-click is not work, a timer left
running overnight does not claim the night, and a session counts on the day it
started.
"""

from datetime import date, datetime, timedelta

import pytest

from techdeck.core.assistant import timelog
from techdeck.core.assistant.models import (
    MAX_OPEN_SESSION_MIN, TaskItem, WorkSession,
)
from techdeck.core.assistant.store import AssistantStore

MONDAY = datetime(2026, 10, 12, 9, 0)


@pytest.fixture
def store(tmp_path):
    return AssistantStore(tmp_path / "assistant")


# ── the clock ────────────────────────────────────────────────────────────────

def test_clocking_in_and_out_logs_the_minutes(store):
    task = store.add_task(TaskItem(title="Fix the PO sheet"))
    store.clock_in(task.id, MONDAY)
    store.clock_out(task.id, MONDAY + timedelta(minutes=45))
    assert store.get_task(task.id).logged_minutes() == 45


def test_only_one_task_is_ever_on_the_clock(store):
    """A person cannot be in two places, and a log that says otherwise is
    worse than no log."""
    first = store.add_task(TaskItem(title="First"))
    second = store.add_task(TaskItem(title="Second"))
    store.clock_in(first.id, MONDAY)
    store.clock_in(second.id, MONDAY + timedelta(minutes=20))

    assert store.get_task(first.id).logged_minutes() == 20
    assert not store.get_task(first.id).is_running
    assert store.get_task(second.id).is_running
    assert store.running_task().title == "Second"


def test_clocking_in_twice_on_the_same_task_is_a_no_op(store):
    task = store.add_task(TaskItem(title="Fix the PO sheet"))
    store.clock_in(task.id, MONDAY)
    store.clock_in(task.id, MONDAY + timedelta(minutes=5))
    assert len(store.get_task(task.id).sessions) == 1


def test_a_misclick_is_not_logged(store):
    """In and straight back out again is a mis-click, not work, so it leaves
    nothing behind to explain later."""
    task = store.add_task(TaskItem(title="Fix the PO sheet"))
    store.clock_in(task.id, MONDAY)
    store.clock_out(task.id, MONDAY + timedelta(seconds=20))
    assert store.get_task(task.id).sessions == []


def test_clock_out_with_no_id_stops_whatever_is_running(store):
    task = store.add_task(TaskItem(title="Fix the PO sheet"))
    store.clock_in(task.id, MONDAY)
    store.clock_out(now=MONDAY + timedelta(minutes=30))
    assert store.running_task() is None


def test_a_running_session_counts_up_to_now(store):
    task = store.add_task(TaskItem(title="Fix the PO sheet"))
    store.clock_in(task.id, MONDAY)
    assert store.get_task(task.id).logged_minutes(
        MONDAY + timedelta(minutes=12)) == 12


def test_time_can_be_logged_by_hand(store):
    task = store.add_task(TaskItem(title="Fix the PO sheet"))
    store.log_time(task.id, 90, when=MONDAY, note="forgot to clock")
    logged = store.get_task(task.id)
    assert logged.logged_minutes() == 90
    assert logged.sessions[0].note == "forgot to clock"


# ── a clock left running ─────────────────────────────────────────────────────

def test_a_clock_left_running_overnight_is_capped_and_marked(store):
    """The honest answer to "how long was that?" is not sixteen hours, and
    the cap has to be visible rather than silently applied."""
    task = store.add_task(TaskItem(title="Fix the PO sheet"))
    store.clock_in(task.id, MONDAY)
    store.close_stale_sessions(now=MONDAY + timedelta(days=1))

    session = store.get_task(task.id).sessions[0]
    assert not session.running
    assert session.minutes() == MAX_OPEN_SESSION_MIN
    assert "auto-closed" in session.note


def test_todays_running_clock_is_left_alone(store):
    task = store.add_task(TaskItem(title="Fix the PO sheet"))
    store.clock_in(task.id, MONDAY)
    store.close_stale_sessions(now=MONDAY + timedelta(hours=2))
    assert store.get_task(task.id).is_running


def test_a_stale_clock_is_closed_on_the_way_back_in(store):
    """The cap runs on load, so reopening TechDeck the next morning never
    shows a timer that has been going all night."""
    task = store.add_task(TaskItem(title="Fix the PO sheet"))
    yesterday = datetime.now() - timedelta(days=1)
    task.sessions.append(WorkSession(start=yesterday.isoformat()))
    store.update_task(task)

    reloaded = AssistantStore(store.dir)
    assert reloaded.running_task() is None


def test_a_session_with_an_unreadable_start_is_discarded(store):
    task = store.add_task(TaskItem(title="Fix the PO sheet"))
    task.sessions.append(WorkSession(start="nonsense"))
    store.update_task(task)
    store.close_stale_sessions(now=MONDAY + timedelta(days=1))
    assert store.get_task(task.id).sessions == []


# ── the report ───────────────────────────────────────────────────────────────

def _logged(title, minutes, when, estimate=0):
    task = TaskItem(title=title, estimate_min=estimate or 30)
    task.sessions.append(WorkSession(
        start=when.isoformat(),
        end=(when + timedelta(minutes=minutes)).isoformat()))
    return task


def test_the_report_ranks_the_biggest_cost_first():
    tasks = [_logged("Small", 20, MONDAY), _logged("Huge", 200, MONDAY),
             _logged("Middling", 60, MONDAY)]
    report = timelog.build_report(tasks, "week", MONDAY)
    assert [row.title for row in report.rows] == ["Huge", "Middling", "Small"]
    assert report.total_minutes == 280


def test_a_range_excludes_what_falls_outside_it():
    tasks = [_logged("This week", 60, MONDAY),
             _logged("Last month", 60, MONDAY - timedelta(days=40))]
    report = timelog.build_report(tasks, "week", MONDAY)
    assert [row.title for row in report.rows] == ["This week"]
    everything = timelog.build_report(tasks, "all", MONDAY)
    assert len(everything.rows) == 2


def test_a_session_counts_on_the_day_it_started():
    """Splitting one across midnight would be more precise and less true:
    nobody working at 11:50pm thinks of it as two days' work."""
    late = datetime(2026, 10, 12, 23, 50)
    report = timelog.build_report([_logged("Late one", 30, late)], "all", late)
    assert report.per_day == [(date(2026, 10, 12), 30)]


def test_over_estimate_is_reported_and_nothing_else_happens():
    task = _logged("Ran long", 120, MONDAY, estimate=60)
    row = timelog.build_report([task], "all", MONDAY).rows[0]
    assert row.over_estimate
    # The estimate itself is untouched: changing it behind the user would make
    # their next plan a stranger.
    assert task.estimate_min == 60


def test_the_week_runs_monday_to_sunday():
    start, end, label = timelog.resolve_range("week", date(2026, 10, 14))
    assert (start, end) == (date(2026, 10, 12), date(2026, 10, 18))
    assert label == "This week"


def test_everything_has_no_bounds():
    assert timelog.resolve_range("all") == (None, None, "Everything")


def test_an_empty_report_says_so_rather_than_drawing_nothing():
    text = timelog.digest([], "week", MONDAY)
    assert "Nothing clocked" in text
    assert "/clockin" in text


def test_the_digest_names_the_running_task():
    task = TaskItem(title="Fix the PO sheet")
    task.sessions.append(WorkSession(start=MONDAY.isoformat()))
    text = timelog.digest([task], "week", MONDAY + timedelta(minutes=30))
    assert "Fix the PO sheet" in text and "running now" in text


# ── the CSV ──────────────────────────────────────────────────────────────────

def test_the_csv_has_one_row_per_session():
    """Session level, not a roll-up: a PivotTable can summarise rows, and
    nothing can un-summarise a total."""
    task = _logged("Fix the PO sheet", 45, MONDAY, estimate=30)
    task.sessions.append(WorkSession(
        start=(MONDAY + timedelta(hours=2)).isoformat(),
        end=(MONDAY + timedelta(hours=3)).isoformat()))
    csv_text = timelog.to_csv([task], "all", MONDAY)
    lines = [line for line in csv_text.split("\r\n") if line]
    assert lines[0].startswith("Date,Task,Priority")
    assert len(lines) == 3
    assert "0.75" in lines[1]          # 45 minutes as hours


def test_the_csv_keeps_crlf_endings_for_excel():
    task = _logged("Fix the PO sheet", 45, MONDAY)
    assert "\r\n" in timelog.to_csv([task], "all", MONDAY)


def test_a_comma_in_a_task_name_survives_the_csv():
    task = _logged("Pull drawings, then scribe", 30, MONDAY)
    csv_text = timelog.to_csv([task], "all", MONDAY)
    assert '"Pull drawings, then scribe"' in csv_text
