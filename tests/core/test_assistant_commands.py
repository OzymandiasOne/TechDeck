"""The terminal's brain, one typed line in, a reply plus an action out.

The brain is Qt-free on purpose, so the entire command surface is testable
without a window. Anything the page does on the brain's behalf shows up here as
a named ``action``.
"""

from datetime import datetime, date, timedelta

import pytest

from techdeck.core.assistant.commands import (
    ACT_CLEAR, ACT_EDIT_NOTE, ACT_EXPORT, ACT_GOTO, ACT_OPEN_WIZARD,
    AssistantBrain,
)
from techdeck.core.assistant.models import Schedule, TaskItem
from techdeck.core.assistant.store import AssistantStore


NOW = datetime(2026, 8, 11, 6, 30)


@pytest.fixture
def brain(tmp_path):
    return AssistantBrain(AssistantStore(tmp_path / "assistant"))


def _text(reply) -> str:
    return "\n".join(line for _role, line in reply.lines)


# ── talking (the default) ────────────────────────────────────────────────────

@pytest.mark.parametrize("said", [
    "this PO sheet is a nightmare",
    "onedrive ate the file AGAIN",
    "order the 4130 tube",
    "i need to get out of here",
    "just thinking out loud",
])
def test_free_text_files_absolutely_nothing(brain, said):
    """The contract. Someone venting at 6:40am must not end the morning with a
    to-do list made of their own complaints."""
    reply = brain.handle(said, NOW)
    assert brain.store.tasks == []
    assert brain.store.notes == []
    assert reply.dirty is False
    assert reply.lines                      # but it DOES answer


def test_talking_gets_a_reply_and_nothing_else(brain):
    """One line in, one line out. No disclaimer riding along underneath."""
    reply = brain.handle("what a morning", NOW)
    assert len(reply.lines) == 1
    assert reply.lines[0][0] == "deck"


def test_an_explicit_ask_still_captures(brain):
    reply = brain.handle("/task fix the PO sheet 45m urgent due today", NOW)
    assert reply.dirty
    task = brain.store.tasks[0]
    assert task.title == "fix the PO sheet"
    assert task.priority == "critical"
    assert task.estimate_min == 45
    assert task.deadline == "2026-08-11"


def test_remind_me_to_is_an_explicit_ask(brain):
    brain.handle("remind me to call Dan at 9am", NOW)
    assert brain.store.tasks[0].title == "call Dan"


def test_a_bare_task_command_promotes_the_last_thing_said(brain):
    brain.handle("order the 4130 tube", NOW)
    assert brain.store.tasks == []
    brain.handle("/task", NOW)
    assert brain.store.tasks[0].title == "order the 4130 tube"


def test_promoting_twice_does_not_file_it_twice(brain):
    brain.handle("order the 4130 tube", NOW)
    brain.handle("/task", NOW)
    brain.handle("/task", NOW)
    assert len(brain.store.tasks) == 1


def test_a_bare_task_command_with_nothing_said_asks_for_input(brain):
    assert "Give me something to do" in _text(brain.handle("/task", NOW))


def test_an_actionable_line_is_OFFERED_not_filed(brain):
    reply = brain.handle("call Dan about the rev C", NOW)
    assert reply.offer_task is True
    assert brain.store.tasks == []


@pytest.mark.parametrize("vent", [
    "this printer is garbage",
    "i hate this spreadsheet",
    "WHY WON'T IT SYNC",
    "so tired today",
])
def test_venting_is_never_offered_as_a_task(brain, vent):
    """A complaint is full of verbs. Offering to add "this printer is garbage"
    to someone's to-do list is the exact joke the goblin exists to prevent."""
    assert brain.handle(vent, NOW).offer_task is False


def test_the_goblin_takes_the_users_side_never_the_other_way(brain):
    """Cheap but load-bearing: the goblin absorbs abuse, it never returns it."""
    reply = _text(brain.handle("this is completely broken and I hate it", NOW)).lower()
    for insult in ("you're", "your fault", "you are", "user error", "skill issue"):
        assert insult not in reply



def test_note_prefix_files_a_note(brain):
    reply = brain.handle("note: gate code is 4417", NOW)
    assert reply.dirty
    assert brain.store.notes[0].title == "gate code is 4417"
    assert brain.store.tasks == []


def test_a_multi_line_paste_becomes_one_note_with_a_title(brain):
    brain.handle("Shutdown checklist\n- lock out the saw\n  - tag it", NOW)
    note = brain.store.notes[0]
    assert note.title == "Shutdown checklist"
    assert "lock out the saw" in note.body


def test_an_empty_line_does_nothing(brain):
    assert brain.handle("   ", NOW).lines == []


# ── tasks ────────────────────────────────────────────────────────────────────

def test_done_by_partial_title(brain):
    brain.handle("/task fix the PO sheet 45m", NOW)
    reply = brain.handle("/done fix the po", NOW)
    assert brain.store.tasks[0].done is True
    assert "Done" in _text(reply)


def test_done_with_an_ambiguous_match_asks_rather_than_guessing(brain):
    brain.handle("/task fix the PO sheet", NOW)
    brain.handle("/task fix the PO header", NOW)
    reply = brain.handle("/done fix the po", NOW)
    assert "matches 2 tasks" in _text(reply)
    assert not any(t.done for t in brain.store.tasks)


def test_done_with_no_match_says_so(brain):
    reply = brain.handle("/done nothing like this", NOW)
    assert "No open task" in _text(reply)


def test_undone_reopens(brain):
    brain.handle("/task fix the PO sheet", NOW)
    brain.handle("/done fix the po", NOW)
    brain.handle("/undone fix the po", NOW)
    assert brain.store.tasks[0].done is False


def test_remove_deletes(brain):
    brain.handle("/task fix the PO sheet", NOW)
    brain.handle("/rm fix the po", NOW)
    assert brain.store.tasks == []


def test_tasks_lists_the_most_worth_doing_first(brain):
    brain.handle("/task slow job 3h", NOW)
    brain.handle("/task quick win 15m urgent", NOW)
    listing = _text(brain.handle("/tasks", NOW))
    assert listing.index("quick win") < listing.index("slow job")


# ── scheduling ───────────────────────────────────────────────────────────────

def test_schedule_opens_the_builder(brain):
    reply = brain.handle("/schedule", NOW)
    assert reply.action == ACT_OPEN_WIZARD


def test_schedule_passes_a_range_word_through(brain):
    reply = brain.handle("/schedule tomorrow", NOW)
    assert reply.payload["range"] == "tomorrow"


def test_natural_language_opens_the_builder_too(brain):
    assert brain.handle("build me a schedule", NOW).action == ACT_OPEN_WIZARD


def test_replan_needs_something_to_plan(brain):
    assert "Nothing open" in _text(brain.handle("/replan", NOW))


def test_replan_builds_from_the_current_task_list(brain):
    brain.handle("/task fix the PO sheet 45m", NOW)
    reply = brain.handle("/replan", NOW)
    assert reply.action == ACT_GOTO
    assert brain.store.latest_schedule() is not None


def test_today_reads_the_saved_plan_without_inventing_one(brain):
    assert "No plan saved yet" in _text(brain.handle("/today", NOW))


# ── notes ────────────────────────────────────────────────────────────────────

def test_note_command_starts_one_and_opens_it(brain):
    reply = brain.handle("/note Shutdown checklist", NOW)
    assert reply.action == ACT_EDIT_NOTE
    assert reply.payload["note_id"] == brain.store.notes[0].id


def test_notes_command_jumps_to_the_tab(brain):
    assert brain.handle("/notes", NOW).action == ACT_GOTO


# ── search ───────────────────────────────────────────────────────────────────

def test_find_searches_both_tasks_and_notes(brain):
    brain.handle("/task recut the rev C plate", NOW)
    brain.handle("note: rev C came in late", NOW)
    found = _text(brain.handle("/find rev c", NOW))
    assert "Tasks:" in found
    assert "Notes:" in found


def test_find_with_no_hits_says_so(brain):
    assert "Nothing matching" in _text(brain.handle("/find unicorns", NOW))


# ── preferences ──────────────────────────────────────────────────────────────

def test_set_updates_a_preference(brain):
    brain.handle("/set start 06:30", NOW)
    assert brain.store.prefs.day_start == "06:30"


def test_set_clamps_an_absurd_value_instead_of_poisoning_every_future_plan(brain):
    brain.handle("/set buffer 900", NOW)
    assert brain.store.prefs.buffer_pct == 100


def test_set_rejects_an_unknown_key(brain):
    assert "Don't know the setting" in _text(brain.handle("/set wibble 3", NOW))


# ── export ───────────────────────────────────────────────────────────────────

def test_export_needs_a_plan_first(brain):
    assert "No plan to export" in _text(brain.handle("/export ics", NOW))


def test_export_asks_the_page_for_a_save_dialog(brain):
    brain.store.add_schedule(Schedule(range_label="Today"))
    reply = brain.handle("/export ics", NOW)
    assert reply.action == ACT_EXPORT
    assert reply.payload["format"] == "ics"


def test_export_accepts_friendly_format_names(brain):
    brain.store.add_schedule(Schedule(range_label="Today"))
    assert brain.handle("/export outlook", NOW).payload["format"] == "ics"
    assert brain.handle("/export markdown", NOW).payload["format"] == "md"


# ── misc ─────────────────────────────────────────────────────────────────────

def test_clear_asks_the_page_to_wipe_the_view(brain):
    assert brain.handle("/clear", NOW).action == ACT_CLEAR


def test_an_unknown_command_suggests_the_nearest_one(brain):
    assert "Did you mean /schedule?" in _text(brain.handle("/schedul", NOW))


def test_an_unrecognisable_command_points_at_help(brain):
    assert "/help" in _text(brain.handle("/zzzz", NOW))


def test_help_is_reachable_both_ways(brain):
    assert "/schedule" in _text(brain.handle("/help", NOW))
    assert "/schedule" in _text(brain.handle("help", NOW))


@pytest.mark.parametrize("asked", [
    "/about", "what is this", "what is this?", "what does this do",
    "what am i looking at", "how does this work",
])
def test_asking_what_this_is_explains_the_page(brain, asked):
    """It used to shrug. The answer has to actually say what the page is, name
    the parts, and repeat the promise that talking files nothing."""
    said = _text(brain.handle(asked, NOW))
    assert "Assistant" in said
    for part in ("Tasks", "Schedule", "Personal Notes", "/help"):
        assert part in said, part
    assert brain.store.tasks == []


def test_the_page_tour_drops_woogy_in_the_professional_theme(tmp_path):
    brain = AssistantBrain(AssistantStore(tmp_path / "a"), professional=True)
    said = _text(brain.handle("what is this", NOW))
    assert "Woogy" not in said
    assert "Personal Notes" in said and "/help" in said
