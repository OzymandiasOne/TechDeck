"""Sticky master-toggle windows (sdk.request_grouped_toggles remember_as).

A.T. 2026-08-07: Saco had to untick "Generate Teams Cards" and "Difficulty
label" on EVERY 911 Setup run before they could even reach the batch prompt.
The window now reopens with whatever was last submitted.

The merge rules are the interesting part -- they are what has to hold when a
later app update adds, removes, or renames a toggle. A remembered preference
that resurrects a dead toggle, or silently applies a state the user was never
shown, is worse than no memory at all.
"""

import pytest

from techdeck.core import plugin_sdk as sdk
from techdeck.core.settings import SettingsManager


GROUPS = [
    {"key": "teams_cards", "label": "Generate Teams Cards", "checked": False,
     "children": []},
    {"key": "folder_setup", "label": "Nest Folder Setup", "checked": True,
     "children": []},
    {"key": "pdf_stamping", "label": "PDF Stamping", "checked": True,
     "children": [{"key": "difficulty", "label": "Difficulty label",
                   "checked": True}]},
]


def _checked(groups):
    return {g["key"]: g["checked"] for g in groups}


def _child_checked(groups, gkey, ckey):
    g = next(x for x in groups if x["key"] == gkey)
    return next(c for c in g["children"] if c["key"] == ckey)["checked"]


# ── apply_toggle_memory: the merge rules ────────────────────────────────────
def test_remembered_state_wins_over_the_declared_default():
    merged = sdk.apply_toggle_memory(GROUPS, {
        "teams_cards": {"enabled": True, "options": {}},
        "folder_setup": {"enabled": False, "options": {}},
    })
    assert _checked(merged) == {"teams_cards": True, "folder_setup": False,
                                "pdf_stamping": True}


def test_child_options_are_remembered_too():
    """The exact ask: untick the difficulty label once, it stays unticked."""
    merged = sdk.apply_toggle_memory(GROUPS, {
        "pdf_stamping": {"enabled": True, "options": {"difficulty": False}},
    })
    assert _child_checked(merged, "pdf_stamping", "difficulty") is False


def test_a_toggle_added_by_an_update_takes_its_own_default():
    """Memory saved before the toggle existed must not decide it. A user who
    never saw a switch has expressed no preference about it."""
    remembered = {"folder_setup": {"enabled": True, "options": {}}}
    merged = sdk.apply_toggle_memory(GROUPS, remembered)
    assert _checked(merged)["teams_cards"] is False      # its declared default
    assert _child_checked(merged, "pdf_stamping", "difficulty") is True


def test_a_removed_toggle_is_dropped_not_resurrected():
    merged = sdk.apply_toggle_memory(GROUPS, {
        "some_stage_we_deleted": {"enabled": True, "options": {}},
        "teams_cards": {"enabled": True, "options": {}},
    })
    assert [g["key"] for g in merged] == [g["key"] for g in GROUPS]
    assert _checked(merged)["teams_cards"] is True


def test_a_disabled_child_stays_unchecked_whatever_is_remembered():
    """disabled means UNAVAILABLE, not merely off -- memory cannot turn a
    locked option back on (mirrors GroupedToggleDialog's own rule)."""
    groups = [{"key": "g", "label": "G", "checked": True, "children": [
        {"key": "locked", "label": "Locked", "checked": False,
         "disabled": True}]}]
    merged = sdk.apply_toggle_memory(
        groups, {"g": {"enabled": True, "options": {"locked": True}}})
    assert _child_checked(merged, "g", "locked") is False


def test_apply_is_pure_and_never_mutates_the_caller_spec():
    """_dialog_groups() rebuilds each call, but a shared/module-level spec must
    not be quietly rewritten by a memory overlay."""
    before = _checked(GROUPS)
    before_child = _child_checked(GROUPS, "pdf_stamping", "difficulty")
    sdk.apply_toggle_memory(GROUPS, {
        "teams_cards": {"enabled": True, "options": {}},
        "pdf_stamping": {"enabled": False, "options": {"difficulty": False}},
    })
    assert _checked(GROUPS) == before
    assert _child_checked(GROUPS, "pdf_stamping", "difficulty") is before_child


def test_empty_memory_leaves_every_declared_default_alone():
    assert _checked(sdk.apply_toggle_memory(GROUPS, {})) == _checked(GROUPS)


# ── round trip through settings.json ────────────────────────────────────────
@pytest.fixture
def store(tmp_path, monkeypatch):
    """A real SettingsManager on a throwaway dir, wired into the SDK."""
    mgr = SettingsManager.__new__(SettingsManager)
    mgr._initialized = False
    mgr.__init__(settings_dir=tmp_path)
    monkeypatch.setattr("techdeck.core.settings.SettingsManager",
                        lambda *a, **k: mgr)
    return mgr


def test_memory_survives_a_round_trip_to_disk(store):
    sdk.save_toggle_memory("911_setup", {
        "teams_cards": {"enabled": False, "options": {}},
        "pdf_stamping": {"enabled": True, "options": {"difficulty": False}},
    })
    # a fresh read of the same document -- this is the "next session" path
    assert sdk.load_toggle_memory("911_setup")["pdf_stamping"]["options"][
        "difficulty"] is False


def test_each_plugin_remembers_separately(store):
    sdk.save_toggle_memory("911_setup", {"a": {"enabled": True, "options": {}}})
    sdk.save_toggle_memory("922_setup", {"a": {"enabled": False, "options": {}}})
    assert sdk.load_toggle_memory("911_setup")["a"]["enabled"] is True
    assert sdk.load_toggle_memory("922_setup")["a"]["enabled"] is False


def test_an_unknown_key_reads_as_no_memory(store):
    assert sdk.load_toggle_memory("never_run_this") == {}


# ── request_grouped_toggles end to end (headless path) ──────────────────────
def test_headless_submit_is_remembered_and_reapplied(store):
    """Headless returns the declared defaults, so if the memory were not
    applied this test could not tell the difference -- flip one first."""
    sdk.save_toggle_memory("911_setup",
                           {"teams_cards": {"enabled": True, "options": {}}})
    result = sdk.request_grouped_toggles({}, GROUPS, remember_as="911_setup")
    assert result["teams_cards"]["enabled"] is True
    assert result["folder_setup"]["enabled"] is True


def test_a_cancel_is_never_remembered(store, monkeypatch):
    """"Not this time" must not become "make that my default"."""
    sdk.save_toggle_memory("911_setup",
                           {"teams_cards": {"enabled": True, "options": {}}})

    class _CancellingConsole:
        def request_grouped_toggles(self, groups, **kw):
            return None

    assert sdk.request_grouped_toggles(
        {"console": _CancellingConsole()}, GROUPS,
        remember_as="911_setup") is None
    assert sdk.load_toggle_memory("911_setup")["teams_cards"]["enabled"] is True


def test_without_remember_as_nothing_is_stored(store):
    sdk.request_grouped_toggles({}, GROUPS)
    assert sdk.load_toggle_memory("911_setup") == {}


def test_the_dialog_is_offered_the_remembered_state_not_the_defaults(store):
    """What the USER sees pre-ticked is the whole point -- assert on the spec
    handed to the dialog, not just on the returned result."""
    sdk.save_toggle_memory("911_setup", {
        "teams_cards": {"enabled": True, "options": {}},
        "pdf_stamping": {"enabled": True, "options": {"difficulty": False}},
    })
    seen = {}

    class _RecordingConsole:
        def request_grouped_toggles(self, groups, **kw):
            seen["groups"] = groups
            return {g["key"]: {"enabled": g["checked"],
                               "options": {c["key"]: c["checked"]
                                           for c in g.get("children", [])}}
                    for g in groups}

    sdk.request_grouped_toggles({"console": _RecordingConsole()}, GROUPS,
                                remember_as="911_setup")
    assert _checked(seen["groups"])["teams_cards"] is True
    assert _child_checked(seen["groups"], "pdf_stamping", "difficulty") is False


def test_a_broken_settings_store_never_sinks_the_run(monkeypatch):
    """Failing to remember a preference is a nuisance; failing the run over it
    is not acceptable. Both directions swallow."""
    def _boom(*a, **k):
        raise OSError("settings.json is locked")
    monkeypatch.setattr("techdeck.core.settings.SettingsManager", _boom)
    assert sdk.load_toggle_memory("911_setup") == {}
    sdk.save_toggle_memory("911_setup", {"a": {"enabled": True}})   # no raise
    assert sdk.request_grouped_toggles({}, GROUPS, remember_as="911_setup") \
        is not None


# ── remember: False — per-run mode switches (911 Setup PLATE batch) ─────────
NO_MEMORY_GROUPS = GROUPS + [
    {"key": "plate_batch", "label": "PLATE batch", "checked": False,
     "remember": False, "children": []},
]


def test_a_remember_false_group_always_opens_at_its_declared_default():
    """The PLATE toggle is a property of THIS batch, not a preference: a
    leftover PLATE tick applied to next week's shape batch would fill real
    paperwork from the wrong template. Memory must never touch it."""
    merged = sdk.apply_toggle_memory(NO_MEMORY_GROUPS, {
        "plate_batch": {"enabled": True, "options": {}},   # stale/hand-edited
        "teams_cards": {"enabled": True, "options": {}},
    })
    assert _checked(merged)["plate_batch"] is False        # declared default
    assert _checked(merged)["teams_cards"] is True         # others still merge


def test_a_remember_false_group_is_never_saved(store):
    """Belt and braces: the state is stripped on save too, so it cannot leak
    into a later run even through a stale settings.json."""

    class _PlateTickingConsole:
        def request_grouped_toggles(self, groups, **kw):
            return {g["key"]: {"enabled": True, "options": {}}
                    for g in groups}

    sdk.request_grouped_toggles({"console": _PlateTickingConsole()},
                                NO_MEMORY_GROUPS, remember_as="911_setup")
    saved = sdk.load_toggle_memory("911_setup")
    assert "plate_batch" not in saved
    assert saved["teams_cards"]["enabled"] is True
