"""sdk.request_922_batch_folder — the one 922 batch-entry flow.

Replaces the typed request_batch_number dance that six plugins hand-copied
(and drifted on). Contract: family-cache hit first, else a folder pick whose
NAME carries the batch number, seeding the cache for the rest of the queued
run. Cancel = the run's cancel flag set + None returned (never a SUCCESS —
extends the cancel-is-never-a-success invariant).
"""

import threading
from pathlib import Path

import pytest

from techdeck.core import plugin_sdk as sdk


@pytest.fixture
def root(tmp_path):
    """A fake '922 QTDR Production Packages' root with one live batch and one
    archived batch."""
    (tmp_path / "Batch 473").mkdir()
    (tmp_path / "1 - Completed" / "Batch 401").mkdir(parents=True)
    return tmp_path


class _PickingConsole:
    """A console whose user picks the given folder."""
    def __init__(self, picked):
        self.picked = str(picked)
        self.calls = 0

    def request_directory(self, title, start_dir="", style=None):
        self.calls += 1
        return self.picked


class _CancellingConsole:
    def __init__(self):
        self.calls = 0

    def request_directory(self, title, start_dir="", style=None):
        self.calls += 1
        return ""


def _params(console=None, shared_state=None):
    return {
        "log": lambda *_: None,
        "console": console,
        "shared_state": shared_state,
        "cancel_event": threading.Event(),
        "plugin_id": "922_kitting",
        "plugin_family": "922",
    }


def test_pick_returns_batch_and_seeds_the_cache(root):
    shared = {"911": {}, "922": {}, "General": {}}
    console = _PickingConsole(root / "Batch 473")
    params = _params(console, shared)

    result = sdk.request_922_batch_folder(params, base_override=str(root))

    assert result == ("473", root / "Batch 473")
    assert shared["922"]["batch_number"] == "473"
    assert console.calls == 1
    assert not params["cancel_event"].is_set()


def test_cache_hit_skips_the_picker_entirely(root):
    shared = {"922": {"batch_number": "401"}}
    console = _PickingConsole(root / "Batch 473")   # would pick the WRONG one
    params = _params(console, shared)

    batch_no, batch_path = sdk.request_922_batch_folder(
        params, base_override=str(root))

    assert batch_no == "401"
    # Found through the '1 - Completed' archive fallback, no dialog shown.
    assert batch_path == root / "1 - Completed" / "Batch 401"
    assert console.calls == 0


def test_cached_batch_with_vanished_folder_is_user_facing(root):
    params = _params(_PickingConsole(root), {"922": {"batch_number": "999"}})
    with pytest.raises(sdk.UserFacingError):
        sdk.request_922_batch_folder(params, base_override=str(root))


def test_cancelled_pick_flags_the_run_and_returns_none(root):
    console = _CancellingConsole()
    params = _params(console, {"922": {}})

    assert sdk.request_922_batch_folder(params, base_override=str(root)) is None
    assert params["cancel_event"].is_set(), (
        "a backed-out pick must never let the run score as a success")


def test_non_batch_folder_name_is_user_facing(root):
    somewhere_else = root / "1 - Completed"          # a real dir, wrong name
    params = _params(_PickingConsole(somewhere_else), {"922": {}})
    with pytest.raises(sdk.UserFacingError):
        sdk.request_922_batch_folder(params, base_override=str(root))


def test_missing_root_is_user_facing(tmp_path):
    params = _params(_PickingConsole(tmp_path))
    with pytest.raises(sdk.UserFacingError):
        sdk.request_922_batch_folder(
            params, base_override=str(tmp_path / "does_not_exist"))


def test_headless_no_shared_state_still_works(root):
    """Standalone/CLI runs pass shared_state=None — pick works, no crash."""
    params = _params(_PickingConsole(root / "Batch 473"), shared_state=None)
    result = sdk.request_922_batch_folder(params, base_override=str(root))
    assert result == ("473", root / "Batch 473")


def test_picker_gets_the_root_as_start_dir(root):
    seen = {}

    class _Spy:
        def request_directory(self, title, start_dir="", style=None):
            seen["title"] = title
            seen["start_dir"] = start_dir
            return str(root / "Batch 473")

    params = _params(_Spy(), {"922": {}})
    sdk.request_922_batch_folder(params, base_override=str(root))
    assert seen["title"] == "Select the 922 batch folder"
    assert Path(seen["start_dir"]) == root
