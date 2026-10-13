"""Steps inside a task.

A long project is one thing in the backlog with a stack of work underneath it,
not eight look-alike tasks. The rules worth pinning: a step is never scheduled
on its own, a step's own date can come due long before the task's, and ticking
a step never touches the task's estimate.
"""

from datetime import date, datetime, timedelta

import pytest

from techdeck.core.assistant.models import (
    ChecklistItem, SchedulePrefs, TaskItem,
)
from techdeck.core.assistant.notifier import (
    KIND_STEP, NotifyPrefs, due_notifications,
)
from techdeck.core.assistant.scheduler import ScheduleRequest, build_schedule
from techdeck.core.assistant.store import AssistantStore

MONDAY = date(2026, 10, 12)
NOW = datetime(2026, 10, 12, 8, 0)


@pytest.fixture
def store(tmp_path):
    return AssistantStore(tmp_path / "assistant")


@pytest.fixture
def prefs():
    return SchedulePrefs.from_dict({"day_start": "07:00", "day_end": "15:30"})


def _project() -> TaskItem:
    return TaskItem(title="Weld shop rollout", estimate_min=120, checklist=[
        ChecklistItem(text="pull the drawings", estimate_min=15, done=True),
        ChecklistItem(text="build the kit sheet", estimate_min=45),
        ChecklistItem(text="walk it to QA", estimate_min=10),
    ])


# ── the model ────────────────────────────────────────────────────────────────

def test_progress_and_totals():
    task = _project()
    assert task.checklist_progress() == (1, 3)
    assert task.checklist_minutes() == 70
    nxt = task.next_step()
    assert nxt is not None and nxt.text == "build the kit sheet"


def test_the_next_step_is_the_first_one_still_open():
    task = _project()
    task.checklist[1].done = True
    nxt = task.next_step()
    assert nxt is not None and nxt.text == "walk it to QA"


def test_a_finished_checklist_has_no_next_step():
    task = _project()
    for step in task.checklist:
        step.done = True
    assert task.next_step() is None


def test_steps_round_trip_through_json():
    task = TaskItem.from_dict(_project().to_dict())
    assert [s.text for s in task.checklist] == [
        "pull the drawings", "build the kit sheet", "walk it to QA"]
    assert task.checklist[0].done


def test_junk_in_the_checklist_is_skipped_not_fatal():
    """A hand-edited file must not take the page down."""
    task = TaskItem.from_dict(
        {"title": "x", "checklist": [None, "nope", {"text": "real step"}]})
    assert [s.text for s in task.checklist] == ["real step"]


def test_a_steps_estimate_is_clamped_not_trusted():
    step = ChecklistItem.from_dict({"text": "x", "estimate_min": "-5"})
    assert step.estimate_min == 0


# ── the store ────────────────────────────────────────────────────────────────

def test_ticking_a_step_leaves_the_task_estimate_alone(store):
    """The estimate is what the person booked. Deriving it from the steps
    behind their back would make the next plan a stranger."""
    task = store.add_task(_project())
    store.set_step_done(task.id, task.checklist[1].id, True)
    fresh = store.get_task(task.id)
    assert fresh.checklist_progress() == (2, 3)
    assert fresh.estimate_min == 120
    assert not fresh.done


def test_a_step_can_be_added_and_removed(store):
    task = store.add_task(TaskItem(title="Rollout"))
    store.add_step(task.id, ChecklistItem(text="first"))
    assert store.get_task(task.id).checklist_progress() == (0, 1)

    step_id = store.get_task(task.id).checklist[0].id
    store.delete_step(task.id, step_id)
    assert store.get_task(task.id).checklist == []


def test_ticking_a_step_stamps_when(store):
    task = store.add_task(_project())
    store.set_step_done(task.id, task.checklist[1].id, True)
    assert store.get_task(task.id).checklist[1].done_at

    store.set_step_done(task.id, task.checklist[1].id, False)
    assert store.get_task(task.id).checklist[1].done_at is None


def test_the_search_box_reaches_into_the_steps(store):
    """"I know I wrote that down somewhere" has to find it wherever it was
    written."""
    store.add_task(_project())
    assert [t.title for t in store.find_tasks_text("kit sheet")] == [
        "Weld shop rollout"]


# ── the planner ──────────────────────────────────────────────────────────────

def test_the_task_stays_the_unit_the_planner_places(prefs):
    """Steps are deliberately NOT scheduled one by one, or a day's plan fills
    up with fragments nobody asked for."""
    schedule = build_schedule(ScheduleRequest(
        tasks=[_project()], start_day=MONDAY, end_day=MONDAY, prefs=prefs,
        now=NOW))
    titles = {b.title for b in schedule.task_blocks()}
    assert titles == {"Weld shop rollout"}


# ── the nudge ────────────────────────────────────────────────────────────────

def test_a_steps_own_date_can_come_due_long_before_the_task(prefs):
    """The whole point of per-step dates is the milestone you miss three weeks
    before the task itself is due."""
    task = TaskItem(title="Weld shop rollout",
                    deadline=(MONDAY + timedelta(days=21)).isoformat(),
                    checklist=[ChecklistItem(
                        text="order the tube",
                        deadline=(MONDAY - timedelta(days=2)).isoformat())])
    found = due_notifications(
        schedule=None, tasks=[task], prefs=prefs,
        notify=NotifyPrefs.from_dict({"daily_digest": False}), now=NOW)
    steps = [n for n in found if n.kind == KIND_STEP]
    assert len(steps) == 1
    assert "order the tube" in steps[0].body
    assert "Weld shop rollout" in steps[0].title


def test_a_done_step_is_never_nudged(prefs):
    task = TaskItem(title="Rollout", checklist=[ChecklistItem(
        text="order the tube", done=True,
        deadline=(MONDAY - timedelta(days=9)).isoformat())])
    found = due_notifications(
        schedule=None, tasks=[task], prefs=prefs,
        notify=NotifyPrefs.from_dict({"daily_digest": False}), now=NOW)
    assert [n for n in found if n.kind == KIND_STEP] == []


def test_a_step_nudge_fires_once_a_day_at_most(prefs):
    task = TaskItem(title="Rollout", checklist=[ChecklistItem(
        text="order the tube",
        deadline=(MONDAY - timedelta(days=4)).isoformat())])
    notify = NotifyPrefs.from_dict({"daily_digest": False})
    first = due_notifications(schedule=None, tasks=[task], prefs=prefs,
                              notify=notify, now=NOW)
    key = [n for n in first if n.kind == KIND_STEP][0].key
    again = due_notifications(schedule=None, tasks=[task], prefs=prefs,
                              notify=notify, now=NOW, already_sent=[key])
    assert [n for n in again if n.kind == KIND_STEP] == []
