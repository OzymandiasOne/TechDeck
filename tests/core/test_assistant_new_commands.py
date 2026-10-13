"""The terminal commands added for the 2026-10-09 Assistant requests.

Asserted through ``Reply`` only -- the action and the printed lines -- so the
whole command surface still tests with no window on screen.
"""

from datetime import datetime, timedelta

import pytest

from techdeck.core.assistant.commands import (
    ACT_BLOCKS, ACT_GOTO, ACT_THEME, AssistantBrain,
)
from techdeck.core.assistant.models import ChecklistItem, Commitment, TaskItem
from techdeck.core.assistant.store import AssistantStore

NOW = datetime(2026, 10, 13, 9, 0)


@pytest.fixture
def store(tmp_path):
    return AssistantStore(tmp_path / "assistant")


@pytest.fixture
def brain(store):
    return AssistantBrain(store, themes=["dark", "light", "cherry_blossom"])


def _text(reply):
    return "\n".join(line for _role, line in reply.lines)


# ── waiting ──────────────────────────────────────────────────────────────────

def test_wait_parks_a_task_and_names_the_person(brain, store):
    store.add_task(TaskItem(title="Order the 4130 tube"))
    reply = brain.handle("/wait order the 4130 tube on Dan", NOW)

    task = store.open_tasks()[0]
    assert task.waiting and task.waiting_on == "Dan"
    assert reply.dirty and "Dan" in _text(reply)


def test_wait_without_a_person_still_parks_it(brain, store):
    store.add_task(TaskItem(title="Order the tube"))
    brain.handle("/wait order the tube", NOW)
    task = store.open_tasks()[0]
    assert task.waiting and task.waiting_on == ""


def test_a_task_whose_name_contains_on_survives(brain, store):
    """The ` on <who>` tail is split off the END and only when what follows is
    short enough to be a name, so this task keeps its own words."""
    store.add_task(TaskItem(title="turn the lights on"))
    brain.handle("/wait turn the lights on", NOW)
    task = store.open_tasks()[0]
    assert task.title == "turn the lights on"
    assert task.waiting


def test_unwait_hands_it_back(brain, store):
    task = store.add_task(TaskItem(title="Order the tube"))
    store.set_waiting(task.id, True, "Dan")
    reply = brain.handle("/unwait order the tube", NOW)
    assert not store.get_task(task.id).waiting
    assert "Back on you" in _text(reply)


def test_unwait_on_something_that_was_not_parked_says_so(brain, store):
    store.add_task(TaskItem(title="Order the tube"))
    reply = brain.handle("/unwait order the tube", NOW)
    assert "wasn't waiting" in _text(reply)
    assert not reply.dirty


def test_waiting_lists_what_other_people_have(brain, store):
    first = store.add_task(TaskItem(title="Order the tube"))
    store.add_task(TaskItem(title="Mine to do"))
    store.set_waiting(first.id, True, "Dan")

    text = _text(brain.handle("/waiting", NOW))
    assert "Order the tube" in text and "Dan" in text
    assert "Mine to do" not in text


def test_an_ambiguous_name_asks_rather_than_guessing(brain, store):
    store.add_task(TaskItem(title="Order the tube"))
    store.add_task(TaskItem(title="Order the plate"))
    reply = brain.handle("/wait order", NOW)
    assert "matches 2 tasks" in _text(reply)
    assert not any(t.waiting for t in store.open_tasks())


# ── the clock ────────────────────────────────────────────────────────────────

def test_clockin_and_clockout(brain, store):
    task = store.add_task(TaskItem(title="Fix the PO sheet"))
    brain.handle("/clockin fix the po sheet", NOW)
    assert store.get_task(task.id).is_running

    reply = brain.handle("/clockout", NOW + timedelta(minutes=50))
    assert store.get_task(task.id).logged_minutes() == 50
    assert "50m" in _text(reply)


def test_clockin_elsewhere_clocks_out_of_the_first_and_says_so(brain, store):
    first = store.add_task(TaskItem(title="First job"))
    store.add_task(TaskItem(title="Second job"))
    brain.handle("/clockin first job", NOW)
    reply = brain.handle("/clockin second job", NOW + timedelta(minutes=25))

    assert store.get_task(first.id).logged_minutes() == 25
    assert "Clocked out of First job" in _text(reply)


def test_clockout_with_nothing_running_is_not_an_error(brain):
    reply = brain.handle("/clockout", NOW)
    assert "isn't running" in _text(reply)
    assert not reply.dirty


def test_a_bare_clockin_reports_what_is_already_running(brain, store):
    task = store.add_task(TaskItem(title="Fix the PO sheet"))
    store.clock_in(task.id, NOW)
    text = _text(brain.handle("/clockin", NOW + timedelta(minutes=10)))
    assert "Already on the clock" in text and "Fix the PO sheet" in text


def test_time_opens_the_tab_and_reports(brain, store):
    task = store.add_task(TaskItem(title="Fix the PO sheet"))
    store.clock_in(task.id, NOW)
    store.clock_out(task.id, NOW + timedelta(minutes=45))

    reply = brain.handle("/time week", NOW)
    assert reply.action == ACT_GOTO and reply.payload["tab"] == "time"
    assert "Fix the PO sheet" in _text(reply)


def test_time_rejects_a_range_it_does_not_know(brain):
    reply = brain.handle("/time fortnight", NOW)
    assert "Ranges:" in _text(reply)


# ── steps ────────────────────────────────────────────────────────────────────

def test_step_adds_one_parsed_like_a_task_line(brain, store):
    task = store.add_task(TaskItem(title="Weld shop rollout"))
    brain.handle("/step weld shop rollout | order the tube 20m due 2026-10-16",
                 NOW)

    step = store.get_task(task.id).checklist[0]
    assert step.text == "order the tube"
    assert step.estimate_min == 20 and step.deadline == "2026-10-16"


def test_step_without_the_divider_explains_itself(brain, store):
    store.add_task(TaskItem(title="Rollout"))
    assert "Use: /step" in _text(brain.handle("/step rollout order", NOW))


def test_steps_lists_the_checklist(brain, store):
    store.add_task(TaskItem(title="Rollout", checklist=[
        ChecklistItem(text="pull the drawings", done=True),
        ChecklistItem(text="build the kit sheet", estimate_min=45)]))
    text = _text(brain.handle("/steps rollout", NOW))
    assert "1/2 steps" in text and "build the kit sheet" in text


def test_steps_on_a_task_with_none_says_how_to_add_them(brain, store):
    store.add_task(TaskItem(title="Rollout"))
    assert "/step" in _text(brain.handle("/steps rollout", NOW))


# ── meetings ─────────────────────────────────────────────────────────────────

def test_blocks_opens_the_editor_and_lists_what_is_there(brain, store):
    store.add_commitment(Commitment(title="Production meeting", weekdays=[0]))
    reply = brain.handle("/blocks", NOW)
    assert reply.action == ACT_BLOCKS
    assert "Production meeting" in _text(reply)


def test_blocks_with_nothing_set_up_still_opens_the_editor(brain):
    reply = brain.handle("/blocks", NOW)
    assert reply.action == ACT_BLOCKS
    assert "No meetings" in _text(reply)


# ── this page's theme ────────────────────────────────────────────────────────

def test_theme_hands_the_name_to_the_page(brain):
    reply = brain.handle("/theme light", NOW)
    assert reply.action == ACT_THEME and reply.payload == {"name": "light"}


def test_theme_off_releases_the_override(brain):
    for word in ("off", "none", "app", "follow"):
        reply = brain.handle(f"/theme {word}", NOW)
        assert reply.payload == {"name": ""}


def test_theme_accepts_the_spelling_people_type(brain):
    """Cherry Blossom is two words on screen, so "cherry blossom" has to
    reach the same theme as cherry_blossom."""
    reply = brain.handle("/theme cherry blossom", NOW)
    assert reply.payload == {"name": "cherry_blossom"}


def test_an_unknown_theme_suggests_the_nearest(brain):
    reply = brain.handle("/theme lite", NOW)
    assert reply.action is None
    assert "light" in _text(reply)


def test_a_bare_theme_lists_the_choices(brain):
    text = _text(brain.handle("/theme", NOW))
    assert "light" in text and "/theme off" in text


def test_the_brain_never_imports_the_theme_list_itself(store):
    """core/ stays free of any ui/ import, so an un-injected brain simply
    does not validate and lets the page report a bad name."""
    bare = AssistantBrain(store)
    reply = bare.handle("/theme whatever", NOW)
    assert reply.action == ACT_THEME


# ── /tasks gained a filter ───────────────────────────────────────────────────

def test_tasks_can_be_filtered_by_text(brain, store):
    store.add_task(TaskItem(title="Order the 4130 tube"))
    store.add_task(TaskItem(title="Fix the PO sheet"))
    text = _text(brain.handle("/tasks tube", NOW))
    assert "Order the 4130 tube" in text and "Fix the PO sheet" not in text


def test_tasks_shows_the_new_state_on_each_line(brain, store):
    task = store.add_task(TaskItem(title="Rollout", checklist=[
        ChecklistItem(text="step one")]))
    store.set_waiting(task.id, True, "Dan")
    text = _text(brain.handle("/tasks", NOW))
    assert "waiting on Dan" in text and "0/1 steps" in text


def test_help_mentions_the_new_commands(brain):
    text = _text(brain.handle("/help", NOW))
    for command in ("/blocks", "/wait", "/clockin", "/time", "/theme"):
        assert command in text
