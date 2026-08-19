"""Reminders.

The whole design problem with reminders is not firing them, it is not being
annoying. Every test here is one of the four rules that keep them tolerable:
never late, never twice, never outside the working day, never for finished work.
"""

from datetime import datetime, date, timedelta

import pytest

from techdeck.core.assistant import notifier, scheduler
from techdeck.core.assistant.models import SchedulePrefs, TaskItem
from techdeck.core.assistant.notifier import (
    KIND_DIGEST, KIND_OVERDUE, KIND_STARTING, NotifyPrefs, due_notifications,
)

TUESDAY = date(2026, 8, 11)


def _prefs() -> SchedulePrefs:
    return SchedulePrefs.from_dict(
        {"day_start": "07:00", "day_end": "15:30", "buffer_pct": 0,
         "focus_block_min": 0, "lunch_minutes": 0})


def _notify(**overrides) -> NotifyPrefs:
    base = {"enabled": True, "lead_minutes": 10, "daily_digest": False,
            "overdue": False, "quiet_outside_hours": True}
    base.update(overrides)
    return NotifyPrefs.from_dict(base)


def _plan(tasks, now=datetime(2026, 8, 11, 6, 0)):
    return scheduler.build_schedule(scheduler.ScheduleRequest(
        tasks=tasks, start_day=TUESDAY, end_day=TUESDAY, prefs=_prefs(),
        now=now))


def _kinds(notes):
    return [n.kind for n in notes]


# ── starting soon ────────────────────────────────────────────────────────────

def test_a_block_inside_the_lead_window_fires():
    task = TaskItem(title="Fix the PO sheet", estimate_min=45)
    plan = _plan([task])                       # starts 07:00
    out = due_notifications(plan, [task], _prefs(), _notify(),
                            datetime(2026, 8, 11, 6, 52))
    assert _kinds(out) == [KIND_STARTING]
    assert out[0].title == "Fix the PO sheet"


def test_a_block_further_out_than_the_lead_stays_quiet():
    task = TaskItem(title="Fix the PO sheet", estimate_min=45)
    plan = _plan([task])
    assert due_notifications(plan, [task], _prefs(), _notify(),
                             datetime(2026, 8, 11, 7, 0) - timedelta(minutes=40)) == []


def test_a_block_that_already_started_never_fires():
    """Opening TechDeck at 10am after it was shut all morning must produce
    silence, not eight stale popups. A late reminder is a reproach."""
    task = TaskItem(title="Fix the PO sheet", estimate_min=45)
    plan = _plan([task])
    assert due_notifications(plan, [task], _prefs(), _notify(),
                             datetime(2026, 8, 11, 10, 0)) == []


def test_a_finished_block_stays_quiet():
    task = TaskItem(title="Fix the PO sheet", estimate_min=45)
    plan = _plan([task])
    task.done = True
    assert due_notifications(plan, [task], _prefs(), _notify(),
                             datetime(2026, 8, 11, 6, 55)) == []


def test_a_reminder_already_sent_is_not_repeated():
    task = TaskItem(title="Fix the PO sheet", estimate_min=45)
    plan = _plan([task])
    now = datetime(2026, 8, 11, 6, 55)
    first = due_notifications(plan, [task], _prefs(), _notify(), now)
    assert first
    again = due_notifications(plan, [task], _prefs(), _notify(), now,
                              already_sent=[n.key for n in first])
    assert again == []


def test_the_body_says_what_and_how_soon():
    task = TaskItem(title="Fix the PO sheet", estimate_min=45)
    plan = _plan([task])
    out = due_notifications(plan, [task], _prefs(), _notify(),
                            datetime(2026, 8, 11, 6, 52))
    assert "in 8 min" in out[0].body
    assert "7:00 AM" in out[0].body


def test_a_task_note_rides_along_so_you_know_what_it_was():
    task = TaskItem(title="Fix the PO sheet", estimate_min=45,
                    notes="Header row moved again")
    plan = _plan([task])
    out = due_notifications(plan, [task], _prefs(), _notify(),
                            datetime(2026, 8, 11, 6, 52))
    assert "Header row moved again" in out[0].body


# ── switches ─────────────────────────────────────────────────────────────────

def test_disabled_means_silent():
    task = TaskItem(title="A", estimate_min=45)
    plan = _plan([task])
    assert due_notifications(plan, [task], _prefs(), _notify(enabled=False),
                             datetime(2026, 8, 11, 6, 55)) == []


def test_quiet_outside_working_hours():
    task = TaskItem(title="A", estimate_min=45)
    plan = _plan([task])
    late = datetime(2026, 8, 11, 21, 0)
    assert due_notifications(plan, [task], _prefs(), _notify(), late) == []
    # ...unless you asked it not to be.
    loud = _notify(quiet_outside_hours=False, overdue=True)
    overdue_task = TaskItem(title="late", deadline="2026-08-01")
    assert due_notifications(None, [overdue_task], _prefs(), loud, late)


def test_lead_minutes_is_clamped():
    assert NotifyPrefs.from_dict({"lead_minutes": 9999}).lead_minutes == 120
    assert NotifyPrefs.from_dict({"lead_minutes": "nonsense"}).lead_minutes == 10


# ── overdue ──────────────────────────────────────────────────────────────────

def test_overdue_fires_once_a_day():
    task = TaskItem(title="Fix the PO sheet", deadline="2026-08-10")
    now = datetime(2026, 8, 11, 8, 0)
    out = due_notifications(None, [task], _prefs(), _notify(overdue=True), now)
    assert _kinds(out) == [KIND_OVERDUE]
    assert "yesterday" in out[0].body
    assert due_notifications(None, [task], _prefs(), _notify(overdue=True), now,
                             already_sent=[out[0].key]) == []


def test_overdue_ignores_finished_and_future_work():
    tasks = [TaskItem(title="done", deadline="2026-08-01", done=True),
             TaskItem(title="later", deadline="2026-08-20"),
             TaskItem(title="no deadline")]
    assert due_notifications(None, tasks, _prefs(), _notify(overdue=True),
                             datetime(2026, 8, 11, 8, 0)) == []


# ── daily digest ─────────────────────────────────────────────────────────────

def test_the_digest_waits_until_its_time_then_fires_once():
    task = TaskItem(title="Fix the PO sheet", estimate_min=45)
    plan = _plan([task])
    prefs = _notify(daily_digest=True, digest_at="07:00", lead_minutes=0)

    early = due_notifications(plan, [task], _prefs(), prefs,
                              datetime(2026, 8, 11, 6, 30))
    assert KIND_DIGEST not in _kinds(early)

    out = due_notifications(plan, [task], _prefs(), prefs,
                            datetime(2026, 8, 11, 7, 30))
    digest = [n for n in out if n.kind == KIND_DIGEST]
    assert len(digest) == 1
    assert "Fix the PO sheet" in digest[0].body
    assert due_notifications(plan, [task], _prefs(), prefs,
                             datetime(2026, 8, 11, 8, 0),
                             already_sent=[digest[0].key]) == []


def test_no_digest_when_the_day_is_empty():
    plan = _plan([])
    assert due_notifications(plan, [], _prefs(),
                             _notify(daily_digest=True),
                             datetime(2026, 8, 11, 8, 0)) == []


def test_the_digest_ignores_work_already_ticked_off():
    task = TaskItem(title="Fix the PO sheet", estimate_min=45)
    plan = _plan([task])
    task.done = True
    out = due_notifications(plan, [task], _prefs(),
                            _notify(daily_digest=True, lead_minutes=0),
                            datetime(2026, 8, 11, 8, 0))
    assert out == []


# ── housekeeping ─────────────────────────────────────────────────────────────

def test_no_plan_at_all_is_not_an_error():
    assert due_notifications(None, [], _prefs(), _notify(),
                             datetime(2026, 8, 11, 8, 0)) == []


def test_sent_keys_are_pruned():
    keys = [str(i) for i in range(notifier.MAX_SENT_KEYS + 50)]
    pruned = notifier.prune_sent(keys)
    assert len(pruned) == notifier.MAX_SENT_KEYS
    assert pruned[-1] == keys[-1]          # the newest survive


def test_keys_are_stable_across_calls():
    """The dedupe only works if the same block yields the same key every tick."""
    task = TaskItem(title="A", estimate_min=45)
    plan = _plan([task])
    now = datetime(2026, 8, 11, 6, 55)
    a = due_notifications(plan, [task], _prefs(), _notify(), now)
    b = due_notifications(plan, [task], _prefs(), _notify(),
                          now + timedelta(seconds=30))
    assert [n.key for n in a] == [n.key for n in b]


def test_the_quiet_window_opens_early_enough_to_warn_about_the_first_block():
    """Regression found by the tests above: with a 07:00 start and a 10 minute
    lead the warning falls at 06:50, and a naive quiet-hours check swallowed
    the single most useful reminder there is."""
    task = TaskItem(title="Fix the PO sheet", estimate_min=45)
    plan = _plan([task])                       # starts 07:00
    out = due_notifications(plan, [task], _prefs(), _notify(lead_minutes=10),
                            datetime(2026, 8, 11, 6, 51))
    assert _kinds(out) == [KIND_STARTING]

    # But it does not open a whole hour early.
    assert due_notifications(plan, [task], _prefs(), _notify(lead_minutes=10),
                             datetime(2026, 8, 11, 5, 30)) == []
