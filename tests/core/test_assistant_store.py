"""Assistant persistence.

The store holds the only copy of the user's notes. The tests that matter are
the ones about not losing them: an unreadable file must be quarantined rather
than overwritten, a torn transcript line must not take the rest of the history
with it, and a save must be atomic.
"""

import json

import pytest

from techdeck.core.assistant.models import ChatMessage, Note, SchedulePrefs, TaskItem
from techdeck.core.assistant.store import AssistantStore


@pytest.fixture
def store(tmp_path):
    return AssistantStore(tmp_path / "assistant")


def test_round_trip(store, tmp_path):
    store.add_note(Note(title="Gate code", body="- 4417"))
    store.add_task(TaskItem(title="Fix the PO sheet", estimate_min=45))
    store.save_prefs(SchedulePrefs.from_dict({"day_start": "06:30"}))

    reloaded = AssistantStore(store.dir)
    assert [n.title for n in reloaded.notes] == ["Gate code"]
    assert [t.title for t in reloaded.tasks] == ["Fix the PO sheet"]
    assert reloaded.prefs.day_start == "06:30"


def test_a_corrupt_document_is_quarantined_not_overwritten(tmp_path):
    directory = tmp_path / "assistant"
    directory.mkdir(parents=True)
    (directory / "assistant.json").write_text("{ this is not json",
                                              encoding="utf-8")

    store = AssistantStore(directory)
    assert store.notes == []
    # The bad file is kept under a .corrupt_ name so the user can rescue it.
    assert list(directory.glob("*.corrupt_*.json"))


def test_prefs_are_clamped_on_load(tmp_path):
    directory = tmp_path / "assistant"
    directory.mkdir(parents=True)
    (directory / "assistant.json").write_text(
        json.dumps({"prefs": {"buffer_pct": 9000, "min_chunk_min": 0}}),
        encoding="utf-8")
    store = AssistantStore(directory)
    assert store.prefs.buffer_pct == 100
    assert store.prefs.min_chunk_min == 5


def test_notes_sort_pinned_first_then_recent(store):
    store.add_note(Note(title="old", updated_at="2026-01-01T00:00:00"))
    store.add_note(Note(title="new", updated_at="2026-08-01T00:00:00"))
    store.add_note(Note(title="pinned", pinned=True,
                        updated_at="2025-01-01T00:00:00"))
    assert [n.title for n in store.sorted_notes()] == ["pinned", "new", "old"]


def test_find_tasks_prefers_an_exact_title(store):
    store.add_task(TaskItem(title="Fix the PO sheet"))
    store.add_task(TaskItem(title="Fix the PO sheet header row"))
    matches = store.find_tasks("fix the po sheet")
    assert [t.title for t in matches] == ["Fix the PO sheet"]


def test_find_tasks_substring(store):
    store.add_task(TaskItem(title="Fix the PO sheet"))
    store.add_task(TaskItem(title="Call Dan"))
    assert len(store.find_tasks("po")) == 1


def test_find_tasks_skips_done_by_default(store):
    task = store.add_task(TaskItem(title="Fix the PO sheet"))
    store.set_done(task.id)
    assert store.find_tasks("po") == []
    assert len(store.find_tasks("po", include_done=True)) == 1


def test_purge_done_leaves_open_work_alone(store):
    open_task = store.add_task(TaskItem(title="open"))
    done_task = store.add_task(TaskItem(title="done",
                                        done_at="2020-01-01T00:00:00"))
    store.set_done(done_task.id)
    # set_done stamps today's date, so purge with keep_days=0 removes nothing;
    # rewrite the stamp to something old to exercise the cutoff.
    done_task.done_at = "2020-01-01T00:00:00"
    store.update_task(done_task)
    assert store.purge_done(keep_days=0) == 1
    assert [t.title for t in store.tasks] == [open_task.title]


def test_chat_round_trip(store):
    store.append_chat(ChatMessage(role="user", text="hello"))
    store.append_chat(ChatMessage(role="deck", text="hi"))
    history = store.load_chat()
    assert [(m.role, m.text) for m in history] == [("user", "hello"),
                                                   ("deck", "hi")]


def test_a_torn_transcript_line_does_not_lose_the_rest(store):
    store.append_chat(ChatMessage(role="user", text="first"))
    with open(store.chat_path, "a", encoding="utf-8") as handle:
        handle.write('{"role": "user", "text": "tor\n')       # truncated JSON
    store.append_chat(ChatMessage(role="user", text="third"))
    assert [m.text for m in store.load_chat()] == ["first", "third"]


def test_clear_chat(store):
    store.append_chat(ChatMessage(role="user", text="hello"))
    store.clear_chat()
    assert store.load_chat() == []


def test_schedule_history_is_capped(store):
    from techdeck.core.assistant.models import Schedule
    from techdeck.core.assistant.store import MAX_SCHEDULES
    for i in range(MAX_SCHEDULES + 10):
        store.add_schedule(Schedule(range_label=f"plan {i}"))
    assert len(store.schedules) == MAX_SCHEDULES
    # Newest first.
    assert store.schedules[0].range_label == f"plan {MAX_SCHEDULES + 9}"


def test_no_temp_files_are_left_behind(store):
    store.add_note(Note(title="a"))
    store.add_note(Note(title="b"))
    assert not list(store.dir.glob("*.tmp"))
