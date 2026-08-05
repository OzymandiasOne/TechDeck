"""Tests for the ship-readiness gate's E11 Sentry Drone opt-in check.

The drone loadout menu (My Stuff -> SET UP) is discovered from plugin
manifests (sentry_mode.compatible_plugins) - there is no second list - so a
plugin that gains a file/folder picker without gaining the sentry_drone
settings field silently never appears there. E11 makes that unshippable.
"""

from __future__ import annotations

import ast
import json
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import check_ship_readiness as C  # noqa: E402


def _calls(src: str) -> list[str]:
    return C.find_drone_picker_calls(ast.parse(textwrap.dedent(src)))


def test_detects_every_picker_call_name():
    src = """
        def run(params, progress_callback, cancel_event):
            sdk.request_directory(params, "pick")
            sdk.request_file(params, "pick")
            sdk.pick_directory_gui(params, "pick")
            sdk.pick_file_gui(params, "pick")
            sdk.request_nest_targets(params, "pick", "start")
    """
    assert sorted(_calls(src)) == ["pick_directory_gui", "pick_file_gui",
                                   "request_directory", "request_file",
                                   "request_nest_targets"]


def test_style_empty_string_is_exempt():
    # style="" forces the plain dialog - that prompt never uses the drone.
    src = """
        def run(params, progress_callback, cancel_event):
            sdk.request_directory(params, "pick", style="")
    """
    assert _calls(src) == []


def test_style_none_still_counts():
    # style=None is the default "ask sentry_style(params)" path - drone-capable.
    src = """
        def run(params, progress_callback, cancel_event):
            sdk.request_directory(params, "pick", style=None)
    """
    assert _calls(src) == ["request_directory"]


def test_main_guard_harness_is_skipped():
    src = """
        if __name__ == "__main__":
            sdk.request_directory({}, "pick")
    """
    assert _calls(src) == []


def test_unrelated_calls_not_flagged():
    src = """
        def run(params, progress_callback, cancel_event):
            sdk.request_batch_number(params, "Enter batch number:")
            sdk.request_text(params, "Which line?")
    """
    assert _calls(src) == []


# --- end-to-end through check_plugin -----------------------------------------

_MANIFEST = {
    "id": "922_fake_picker",
    "name": "922 Fake Picker",
    "family": "922",
    "settings": {"fields": []},
}

_RUN = textwrap.dedent("""
    def run(params, progress_callback, cancel_event):
        sdk.request_directory(params, "Select the batch folder")
""")

_DRONE_FIELD = {
    "key": "sentry_drone",
    "type": "boolean",
    "label": "Sentry Drone mode",
    "default": False,
    "hidden_unless_unlocked": "toy_sentry_drone",
}


def _check(tmp_path: Path, manifest: dict) -> list[str]:
    plugin = tmp_path / manifest["id"]
    plugin.mkdir()
    (plugin / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (plugin / "run.py").write_text(_RUN, encoding="utf-8")
    errors: list[str] = []
    C.check_plugin(plugin, set(), set(), [], {}, errors, [])
    return [e for e in errors if "sentry_drone" in e]


def test_picker_without_drone_field_fails(tmp_path):
    assert _check(tmp_path, dict(_MANIFEST)) != []


def test_picker_with_drone_field_passes(tmp_path):
    manifest = dict(_MANIFEST)
    manifest["settings"] = {"fields": [dict(_DRONE_FIELD)]}
    assert _check(tmp_path, manifest) == []
