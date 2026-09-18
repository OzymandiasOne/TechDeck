"""Java Tutor lesson names.

`history.py` reads Claude Code's transcripts and owns no storage, so a rename
cannot be written where the title normally comes from. Names live in a sidecar
(`titles.py`) and win over Claude's ai-title. The rules worth pinning:

- a rename sticks, and nothing ever re-applies a plan name over it;
- a lesson PLANNED before the tutor is open leaves a `pending` name that the
  next new session claims exactly once;
- resuming an old lesson must NOT eat that pending name;
- a corrupt sidecar degrades to automatic names instead of taking the tutor down.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.devkit.java_tutor import titles as titles_mod  # noqa: E402
from tools.devkit.java_tutor import history as history_mod  # noqa: E402


@pytest.fixture
def store(tmp_path):
    return titles_mod.TitleStore(tmp_path / "java_tutor_titles.json")


# --- renaming ---------------------------------------------------------------

def test_rename_round_trips_through_disk(store):
    store.rename("abc123", "  COS 285   L2 -  Efficiency ")
    # whitespace is collapsed, not preserved verbatim
    assert store.get("abc123") == "COS 285 L2 - Efficiency"
    assert titles_mod.TitleStore(store.path).get("abc123") == "COS 285 L2 - Efficiency"


def test_empty_rename_clears_back_to_the_automatic_name(store):
    store.rename("abc123", "Something")
    store.rename("abc123", "   ")
    assert store.get("abc123") == ""
    assert "abc123" not in titles_mod.TitleStore(store.path).titles


def test_unreadable_sidecar_does_not_raise(tmp_path):
    p = tmp_path / "java_tutor_titles.json"
    p.write_text("{ this is not json", encoding="utf-8")
    s = titles_mod.TitleStore(p)          # must not raise
    assert s.titles == {} and s.pending == ""


# --- the planned-lesson handoff --------------------------------------------

def test_pending_is_claimed_once_by_the_next_new_session(store):
    store.set_pending("COS 285 L2 - Efficiency & Big-O")
    assert store.claim_pending("session-1") == "COS 285 L2 - Efficiency & Big-O"
    assert store.get("session-1") == "COS 285 L2 - Efficiency & Big-O"
    assert store.pending == ""
    # a second new session must not inherit the same plan
    assert store.claim_pending("session-2") == ""
    assert store.get("session-2") == ""


def test_resuming_a_named_lesson_does_not_eat_the_pending_name(store):
    """session_ready also fires when an OLD lesson is resumed. If that claimed
    the pending name, the planned lesson would lose its title to whatever the
    user happened to reopen first."""
    store.rename("old-session", "Last week's recursion lesson")
    store.set_pending("COS 285 L2 - Efficiency & Big-O")

    assert store.claim_pending("old-session") == ""
    assert store.get("old-session") == "Last week's recursion lesson"
    assert store.pending == "COS 285 L2 - Efficiency & Big-O"   # still waiting

    assert store.claim_pending("brand-new") == "COS 285 L2 - Efficiency & Big-O"


def test_a_user_rename_is_never_overwritten_by_a_later_plan(store):
    store.set_pending("Planned name")
    store.claim_pending("s1")
    store.rename("s1", "My own name")
    store.set_pending("A different plan")
    assert store.claim_pending("s1") == ""          # already named
    assert store.get("s1") == "My own name"


# --- precedence in the sidebar ---------------------------------------------

def _transcript(tmp_path, session_id, *, ai_title=None, first="hello there"):
    p = tmp_path / f"{session_id}.jsonl"
    lines = []
    if ai_title:
        lines.append({"type": "ai-title", "aiTitle": ai_title})
    lines.append({"type": "user", "timestamp": "2026-09-02T10:00:00Z",
                  "message": {"role": "user", "content": first}})
    lines.append({"type": "assistant", "timestamp": "2026-09-02T10:00:05Z",
                  "message": {"role": "assistant", "content": "sure"}})
    p.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    return p


def test_chosen_name_beats_claude_ai_title(tmp_path):
    p = _transcript(tmp_path, "s1", ai_title="Claude's own title")
    convo = history_mod._summarise(p, {"s1": "The name I typed"})
    assert convo is not None
    assert convo.title == "The name I typed"
    assert convo.custom is True


def test_ai_title_used_when_there_is_no_chosen_name(tmp_path):
    p = _transcript(tmp_path, "s1", ai_title="Claude's own title")
    convo = history_mod._summarise(p, {})
    assert convo is not None
    assert convo.title == "Claude's own title"
    assert convo.custom is False


def test_first_message_used_when_there_is_neither(tmp_path):
    p = _transcript(tmp_path, "s1", first="how do generics work")
    convo = history_mod._summarise(p, None)
    assert convo is not None
    assert convo.title == "how do generics work"
    assert convo.custom is False


def test_list_conversations_threads_the_names_through(tmp_path, monkeypatch):
    _transcript(tmp_path, "s1", ai_title="auto")
    monkeypatch.setattr(history_mod, "transcript_dir", lambda _cwd: tmp_path)
    got = history_mod.list_conversations(Path("ignored"), {"s1": "chosen"})
    assert [c.title for c in got] == ["chosen"]
