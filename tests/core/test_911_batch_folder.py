"""sdk.request_911_batch_folder — the one 911 batch-entry flow.

The 911 twin of `request_922_batch_folder`, added 2026-09-23 when the folder
audit found 911 Setup and the Batch Auditor still TYPING the batch and then
hunting the root for its folder. Same contract: family-cache hit first, else a
folder pick whose NAME carries the batch, seeding the cache for the rest of the
queued run. Cancel = the run's cancel flag set + None returned.

Where it deliberately differs from the 922 helper: validation is STRUCTURAL,
not by name shape. A 911 QTDR root holds 305 folders of wildly different
spellings (V060, GX030, WJ244, D259570025, "9FANIV 41-49 QC FINAL"), so there
is no batch-name pattern to enforce — only the root itself and the root's own
housekeeping folders are refused.
"""

import threading
from pathlib import Path

import pytest

from techdeck.core import plugin_sdk as sdk


@pytest.fixture
def root(tmp_path):
    """A fake '911 QTDR' root: two batches plus the housekeeping folders the
    real root carries."""
    for name in ("V060", "GX030", "01 - WIP Packages", "02 - Complete Packages",
                 "_ASA PROGRAM DIRECTORY"):
        (tmp_path / name).mkdir()
    return tmp_path


class _PickingConsole:
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


def _params(console=None, shared_state=None, log=None):
    return {
        "log": log or (lambda *_: None),
        "console": console,
        "shared_state": shared_state,
        "cancel_event": threading.Event(),
        "plugin_id": "911_setup",
        "plugin_family": "911",
    }


def test_pick_returns_batch_and_seeds_the_cache(root):
    shared = {"911": {}, "922": {}, "General": {}}
    console = _PickingConsole(root / "V060")
    params = _params(console, shared)

    result = sdk.request_911_batch_folder(params, base_override=str(root))

    assert result == ("V060", root / "V060")
    assert shared["911"]["batch_number"] == "V060"
    assert console.calls == 1
    assert not params["cancel_event"].is_set()


def test_cache_hit_skips_the_picker_entirely(root):
    shared = {"911": {"batch_number": "GX030"}}
    console = _PickingConsole(root / "V060")        # would pick the WRONG one
    params = _params(console, shared)

    batch, batch_path = sdk.request_911_batch_folder(
        params, base_override=str(root))

    assert batch == "GX030"
    assert batch_path == root / "GX030"
    assert console.calls == 0


def test_cached_batch_with_vanished_folder_is_user_facing(root):
    params = _params(_PickingConsole(root / "V060"),
                     {"911": {"batch_number": "ZZ999"}})
    with pytest.raises(sdk.UserFacingError):
        sdk.request_911_batch_folder(params, base_override=str(root))


def test_cancelled_pick_flags_the_run_and_returns_none(root):
    console = _CancellingConsole()
    params = _params(console, {"911": {}})

    assert sdk.request_911_batch_folder(params, base_override=str(root)) is None
    assert params["cancel_event"].is_set(), (
        "a backed-out pick must never let the run score as a success")


def test_picking_the_root_itself_is_refused(root):
    """A user really did pick the 911 QTDR root once, and 911 Inspection
    Dimensions started a run across every order under it."""
    params = _params(_PickingConsole(root), {"911": {}})
    with pytest.raises(sdk.UserFacingError):
        sdk.request_911_batch_folder(params, base_override=str(root))


@pytest.mark.parametrize("name", ["01 - WIP Packages", "02 - Complete Packages",
                                  "_ASA PROGRAM DIRECTORY"])
def test_the_roots_own_housekeeping_folders_are_refused(root, name):
    params = _params(_PickingConsole(root / name), {"911": {}})
    with pytest.raises(sdk.UserFacingError):
        sdk.request_911_batch_folder(params, base_override=str(root))


def test_an_unusual_batch_name_is_ACCEPTED_with_a_note(root):
    """The point of the picker is that the user can SEE what they chose.

    Refusing on a name shape would be the same mistake as judging a work packet
    by what it is NOT: 222 folders match the usual V060/GX030 pattern today and
    the next naming scheme is not obliged to. So an odd name is accepted and
    merely noted.
    """
    odd = root / "9FANIV 41-49 QC FINAL"
    odd.mkdir()
    lines = []
    params = _params(_PickingConsole(odd), {"911": {}}, log=lines.append)

    batch, batch_path = sdk.request_911_batch_folder(
        params, base_override=str(root))

    assert batch == "9FANIV 41-49 QC FINAL"
    assert batch_path == odd
    assert any("doesn't look like the usual batch name" in ln for ln in lines)


def test_a_normal_batch_name_gets_no_note(root):
    lines = []
    params = _params(_PickingConsole(root / "GX030"), {"911": {}},
                     log=lines.append)
    sdk.request_911_batch_folder(params, base_override=str(root))
    assert not any("doesn't look like" in ln for ln in lines)


def test_missing_root_is_user_facing(tmp_path):
    params = _params(_PickingConsole(tmp_path))
    with pytest.raises(sdk.UserFacingError):
        sdk.request_911_batch_folder(
            params, base_override=str(tmp_path / "does_not_exist"))


def test_headless_no_shared_state_still_works(root):
    """Standalone/CLI runs pass shared_state=None — pick works, no crash."""
    params = _params(_PickingConsole(root / "V060"), shared_state=None)
    result = sdk.request_911_batch_folder(params, base_override=str(root))
    assert result == ("V060", root / "V060")


def test_picker_gets_the_root_as_start_dir(root):
    seen = {}

    class _Spy:
        def request_directory(self, title, start_dir="", style=None):
            seen["title"] = title
            seen["start_dir"] = start_dir
            return str(root / "V060")

    params = _params(_Spy(), {"911": {}})
    sdk.request_911_batch_folder(params, base_override=str(root))
    assert seen["title"] == "Select the 911 batch folder"
    assert Path(seen["start_dir"]) == root


def test_a_file_picked_instead_of_a_folder_is_user_facing(root):
    stray = root / "notes.txt"
    stray.write_text("not a folder", encoding="utf-8")
    params = _params(_PickingConsole(stray), {"911": {}})
    with pytest.raises(sdk.UserFacingError):
        sdk.request_911_batch_folder(params, base_override=str(root))
