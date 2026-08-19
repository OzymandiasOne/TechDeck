"""Backing out of a prompt must report CANCELLED — never SUCCESS.

Reported 2026-08-10: closing 911 Setup's master toggle window still played the
success chime and paid out tickets. The executor decides SUCCESS vs CANCELLED
from exactly one thing — whether ``cancel_event`` is set when ``run()`` returns
(plugin_executor ~line 559) — and a plugin that closed a dialog and simply
``return``ed never set it.

Three plugins had the identical hole (911 Setup's toggle window, Baked Beans'
folder pick, SSPO Invoicing Prep's file pick) while three others happened to
set the flag by hand. That split is the tell: it was a convention, not a
mechanism. The fix moved the flag into the SDK prompts themselves
(``sdk._user_cancelled``), so these tests assert the MECHANISM — every
cancellable prompt flags the run — rather than re-checking each call site.
"""

import threading

import pytest

from techdeck.core import plugin_sdk as sdk


def _params():
    return {"cancel_event": threading.Event(), "console": None}


class _CancellingConsole:
    """A console where the user closes/cancels every prompt."""
    def request_directory(self, *a, **k):
        return ""

    def request_file(self, *a, **k):
        return ""

    def request_choice(self, *a, **k):
        return None

    def request_grouped_toggles(self, *a, **k):
        return None


class _AnsweringConsole:
    """A console where the user answers everything."""
    def request_directory(self, *a, **k):
        return r"C:\some\folder"

    def request_file(self, *a, **k):
        return r"C:\some\file.xlsx"

    def request_choice(self, title, prompt, options):
        return options[0]

    def request_grouped_toggles(self, groups, **k):
        return {g["key"]: {"enabled": True, "options": {}} for g in groups}


GROUPS = [{"key": "stage_a", "label": "Stage A", "checked": True, "children": []}]

# (name, callable) for every prompt a user can back out of.
PROMPTS = [
    ("request_directory", lambda p: sdk.request_directory(p, "Pick a folder")),
    ("request_file", lambda p: sdk.request_file(p, "Pick a file")),
    ("request_choice", lambda p: sdk.request_choice(p, "T", "Pick", ["a", "b"])),
    ("request_grouped_toggles",
     lambda p: sdk.request_grouped_toggles(p, GROUPS)),
]


@pytest.mark.parametrize("name,call", PROMPTS, ids=[n for n, _ in PROMPTS])
def test_cancelling_a_prompt_flags_the_run_as_cancelled(name, call):
    """THE regression test for the reported bug: cancel -> the executor's one
    signal is set, so the run cannot be scored as a success."""
    params = _params()
    params["console"] = _CancellingConsole()
    assert call(params) is None, f"{name} should report the cancel as None"
    assert params["cancel_event"].is_set(), (
        f"{name} let a user cancel look like a completed run — the success "
        f"chime plays and tickets are awarded")


@pytest.mark.parametrize("name,call", PROMPTS, ids=[n for n, _ in PROMPTS])
def test_answering_a_prompt_leaves_the_run_alone(name, call):
    """The other half: a normal answer must NOT poison the run. A flag set here
    would abort the next raise_if_cancelled loop mid-work."""
    params = _params()
    params["console"] = _AnsweringConsole()
    assert call(params) is not None
    assert not params["cancel_event"].is_set(), (
        f"{name} flagged a cancel on a successful answer")


def test_the_toggle_window_remembers_nothing_when_cancelled():
    """Cancel must not become the new default (pairs with the sticky-toggle
    work — 'not this time' is not 'always skip this')."""
    params = _params()
    params["console"] = _CancellingConsole()
    calls = []
    original = sdk.save_toggle_memory
    sdk.save_toggle_memory = lambda k, v: calls.append(k)   # noqa: E731
    try:
        assert sdk.request_grouped_toggles(
            params, GROUPS, remember_as="some_plugin") is None
    finally:
        sdk.save_toggle_memory = original
    assert calls == []
    assert params["cancel_event"].is_set()


def test_a_missing_cancel_event_never_crashes():
    """Headless runs, CLI tests and older executors pass no event. Flagging a
    cancel must degrade to a no-op, never an AttributeError mid-prompt."""
    params = {"console": _CancellingConsole()}          # no cancel_event
    for _name, call in PROMPTS:
        assert call(params) is None


def test_a_broken_cancel_event_never_crashes():
    class _Hostile:
        def set(self):
            raise RuntimeError("boom")

    params = {"console": _CancellingConsole(), "cancel_event": _Hostile()}
    for _name, call in PROMPTS:
        assert call(params) is None


# ── the executor's contract, restated so the link can't silently break ──────
def test_the_executor_still_scores_success_off_the_cancel_flag():
    """These tests are only meaningful while cancel_event is what the executor
    reads. If that ever changes, fail HERE rather than silently letting every
    test above pass while cancelled runs pay out again."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[2]
           / "techdeck" / "core" / "plugin_executor.py").read_text(
        encoding="utf-8")
    assert "if cancel_event.is_set():" in src
    assert "PluginStatus.CANCELLED" in src
