"""Work that is parked on somebody else.

Two promises hold this feature up, and both are tested here:

* a waiting task is **never planned** (booking an hour for a job you cannot
  start is how a plan loses the user's trust by 9am), and
* it is **never silently dropped** either -- it comes back as a reported line
  saying who has it, and it earns a follow-up nudge once it has sat too long.
"""

from datetime import date, datetime, timedelta

import pytest

from techdeck.core.assistant import notifier
from techdeck.core.assistant.models import SchedulePrefs, TaskItem
from techdeck.core.assistant.notifier import (
    KIND_WAITING, NotifyPrefs, due_notifications,
)
from techdeck.core.assistant.scheduler import (
    ScheduleRequest, build_schedule, summarize,
)
from techdeck.core.assistant.store import AssistantStore

MONDAY = date(2026, 10, 12)
NOW = datetime(2026, 10, 12, 8, 0)


@pytest.fixture
def prefs():
    return SchedulePrefs.from_dict({"day_start": "07:00", "day_end": "15:30"})


@pytest.fixture
def store(tmp_path):
    return AssistantStore(tmp_path / "assistant")


# ── the planner ──────────────────────────────────────────────────────────────

def test_a_waiting_task_is_not_scheduled(prefs):
    parked = TaskItem(title="Order the tube", estimate_min=30,
                      waiting=True, waiting_on="Dan")
    schedule = build_schedule(ScheduleRequest(
        tasks=[parked], start_day=MONDAY, end_day=MONDAY, prefs=prefs,
        now=NOW))
    assert schedule.task_blocks() == []


def test_a_waiting_task_is_reported_not_dropped(prefs):
    parked = TaskItem(title="Order the tube", waiting=True, waiting_on="Dan")
    schedule = build_schedule(ScheduleRequest(
        tasks=[parked], start_day=MONDAY, end_day=MONDAY, prefs=prefs,
        now=NOW))
    assert len(schedule.unscheduled) == 1
    entry = schedule.unscheduled[0]
    assert entry["waiting"] is True
    assert entry["reason"] == "waiting on Dan"
    assert "waiting on Dan" in summarize(schedule)


def test_waiting_is_counted_apart_from_didnt_fit(prefs):
    """A squeeze and somebody else's turn are different problems, so adding
    them together would make both numbers meaningless."""
    schedule = build_schedule(ScheduleRequest(
        tasks=[TaskItem(title="Parked", waiting=True),
               TaskItem(title="Huge", estimate_min=20 * 60,
                        splittable=False)],
        start_day=MONDAY, end_day=MONDAY, prefs=prefs, now=NOW))
    assert schedule.stats["tasks_waiting"] == 1
    assert schedule.stats["tasks_unplaced"] == 1


def test_taking_it_back_puts_it_in_the_plan_again(prefs, store):
    task = store.add_task(TaskItem(title="Order the tube", estimate_min=30))
    store.set_waiting(task.id, True, "Dan")
    store.set_waiting(task.id, False)

    schedule = build_schedule(ScheduleRequest(
        tasks=store.open_tasks(), start_day=MONDAY, end_day=MONDAY,
        prefs=prefs, now=NOW))
    assert [b.title for b in schedule.task_blocks()] == ["Order the tube"]


# ── the flag itself ──────────────────────────────────────────────────────────

def test_the_waiting_clock_starts_once_and_is_not_restarted(store):
    """Correcting WHO you are waiting on must not reset the follow-up clock,
    or the nudge can be deferred forever by a typo fix."""
    task = store.add_task(TaskItem(title="Order the tube"))
    store.set_waiting(task.id, True, "Dan")
    first = store.get_task(task.id).waiting_since

    store.set_waiting(task.id, True, "Dan Smith")
    assert store.get_task(task.id).waiting_since == first
    assert store.get_task(task.id).waiting_on == "Dan Smith"


def test_unparking_clears_everything(store):
    task = store.add_task(TaskItem(title="Order the tube"))
    store.set_waiting(task.id, True, "Dan")
    store.set_waiting(task.id, False)
    fresh = store.get_task(task.id)
    assert (fresh.waiting, fresh.waiting_on, fresh.waiting_since) == (
        False, "", None)


def test_an_unreadable_stamp_never_fires_a_nudge():
    """waiting_days is the input to a notification, so a hand-mangled date
    has to read as 0 days rather than raise."""
    task = TaskItem(title="x", waiting=True, waiting_since="not a date")
    assert task.waiting_days(MONDAY) == 0


# ── the nudge ────────────────────────────────────────────────────────────────

def _nudges(tasks, now, prefs, **overrides):
    notify = NotifyPrefs.from_dict({"enabled": True, "daily_digest": False,
                                    **overrides})
    found = due_notifications(schedule=None, tasks=tasks, prefs=prefs,
                              notify=notify, now=now)
    return [n for n in found if n.kind == KIND_WAITING]


def test_nothing_is_nudged_before_the_threshold(prefs):
    task = TaskItem(title="Order the tube", waiting=True, waiting_on="Dan",
                    waiting_since=(NOW - timedelta(days=1)).isoformat())
    assert _nudges([task], NOW, prefs, waiting_after_days=3) == []


def test_a_long_wait_earns_one_nudge(prefs):
    task = TaskItem(title="Order the tube", waiting=True, waiting_on="Dan",
                    waiting_since=(NOW - timedelta(days=4)).isoformat())
    nudges = _nudges([task], NOW, prefs, waiting_after_days=3)
    assert len(nudges) == 1
    assert "Dan" in nudges[0].body and "4 days" in nudges[0].body


def test_the_nudge_fires_once_a_day_at_most(prefs):
    """Same rule as the overdue nudge: one mention each morning, not one
    every thirty seconds until it is dealt with."""
    task = TaskItem(title="Order the tube", waiting=True,
                    waiting_since=(NOW - timedelta(days=9)).isoformat())
    first = _nudges([task], NOW, prefs, waiting_after_days=3)
    notify = NotifyPrefs.from_dict({"daily_digest": False})
    again = due_notifications(schedule=None, tasks=[task], prefs=prefs,
                              notify=notify, now=NOW,
                              already_sent=[first[0].key])
    assert [n for n in again if n.kind == KIND_WAITING] == []


def test_a_finished_task_is_never_nudged(prefs):
    task = TaskItem(title="Order the tube", waiting=True, done=True,
                    waiting_since=(NOW - timedelta(days=30)).isoformat())
    assert _nudges([task], NOW, prefs) == []


def test_follow_ups_can_be_switched_off(prefs):
    task = TaskItem(title="Order the tube", waiting=True,
                    waiting_since=(NOW - timedelta(days=30)).isoformat())
    assert _nudges([task], NOW, prefs, waiting_followup=False) == []


def test_the_threshold_is_clamped_to_something_sane():
    assert NotifyPrefs.from_dict({"waiting_after_days": 0}).waiting_after_days == 1
    assert NotifyPrefs.from_dict({"waiting_after_days": 9999}).waiting_after_days == 60
    assert NotifyPrefs.from_dict({"waiting_after_days": "x"}).waiting_after_days == 3
