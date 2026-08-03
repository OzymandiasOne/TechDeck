"""Sentry Drone gate — ownership + per-app opt-in.

The drone is a purchasable Emporium gadget that applies PER APP. Both halves
have to be true before any picker turns into the kill-cam, and the settings
field has to stay invisible (but its value intact) until it's bought.
"""

import json

import pytest

from techdeck.core import plugin_sdk as sdk
from techdeck.core import sentry_mode
from techdeck.ui.emporium_catalog import CATALOG


class _FakeSettings:
    """Just enough SettingsManager for the gate: unlocks + plugin settings."""

    def __init__(self, unlocked=(), plugin_settings=None):
        self._unlocked = set(unlocked)
        self._plugin = plugin_settings or {}

    def is_unlocked(self, item_id):
        return item_id in self._unlocked

    def get_plugin_setting(self, plugin_id, key, default=None):
        return self._plugin.get(plugin_id, {}).get(key, default)

    def set_plugin_setting(self, plugin_id, key, value):
        self._plugin.setdefault(plugin_id, {})[key] = value


OWNED = (sentry_mode.ITEM_ID,)


# ── catalog wiring ───────────────────────────────────────────────────────────
def test_catalog_carries_the_gadget():
    item = next(c for c in CATALOG if c["id"] == sentry_mode.ITEM_ID)
    assert item["kind"] == "gadget"      # configured, not equipped
    assert item["category"] == "toys"
    assert item["cost"] > 0
    assert item["sprite"] == "sentry_drone.tdart"


def test_sprite_exists_and_is_loadable():
    from pathlib import Path
    from techdeck.ui import pixel_art
    root = Path(__file__).resolve().parents[2]
    data = pixel_art.load(root / "assets" / "sprites" / "sentry_drone.tdart")
    assert pixel_art.dimensions(data) == (44, 44)


# ── the gate ─────────────────────────────────────────────────────────────────
def test_gate_needs_both_halves():
    both = _FakeSettings(OWNED, {"922_setup": {"sentry_drone": True}})
    assert sentry_mode.is_enabled("922_setup", both)

    # Bought, but switched off for this app.
    off = _FakeSettings(OWNED, {"922_setup": {"sentry_drone": False}})
    assert not sentry_mode.is_enabled("922_setup", off)

    # Switched on, but never bought — the setting alone must not arm it.
    unbought = _FakeSettings((), {"922_setup": {"sentry_drone": True}})
    assert not sentry_mode.is_enabled("922_setup", unbought)


def test_gate_is_per_app():
    s = _FakeSettings(OWNED, {"922_setup": {"sentry_drone": True},
                              "911_lst_organizer": {"sentry_drone": False}})
    assert sentry_mode.is_enabled("922_setup", s)
    assert not sentry_mode.is_enabled("911_lst_organizer", s)
    assert not sentry_mode.is_enabled("902_dxf_prep", s)   # never set = off


def test_default_is_off_for_a_fresh_owner():
    """Buying the drone must not silently switch it on anywhere."""
    s = _FakeSettings(OWNED, {})
    for app in ("922_setup", "911_batch_repeater", "902_dxf_prep"):
        assert not sentry_mode.is_enabled(app, s)


def test_set_enabled_round_trips():
    s = _FakeSettings(OWNED, {})
    sentry_mode.set_enabled("902_dxf_prep", True, s)
    assert sentry_mode.is_enabled("902_dxf_prep", s)
    sentry_mode.set_enabled("902_dxf_prep", False, s)
    assert not sentry_mode.is_enabled("902_dxf_prep", s)


def test_style_for_matches_the_gate():
    on = _FakeSettings(OWNED, {"922_setup": {"sentry_drone": True}})
    assert sentry_mode.style_for("922_setup", on) == sentry_mode.STYLE
    assert sentry_mode.style_for("911_setup", on) is None


# ── plugin manifests ─────────────────────────────────────────────────────────
def _repo_plugins():
    from pathlib import Path
    return sorted((Path(__file__).resolve().parents[2] / "plugins").iterdir())


def _sentry_field(manifest):
    fields = (manifest.get("settings") or {}).get("fields") or []
    for f in fields:
        if f.get("key") == sentry_mode.SETTING_KEY:
            return f
    return None


def test_every_declared_field_is_off_by_default_and_hidden():
    """A plugin advertises drone support by declaring the field. Every one of
    them must default OFF and stay hidden until the gadget is bought."""
    found = 0
    for d in _repo_plugins():
        manifest = d / "plugin.json"
        if not manifest.is_file():
            continue
        field = _sentry_field(json.loads(manifest.read_text(encoding="utf-8")))
        if field is None:
            continue
        found += 1
        assert field["type"] == "boolean", d.name
        assert field["default"] is False, d.name
        assert field["hidden_unless_unlocked"] == sentry_mode.ITEM_ID, d.name
    assert found >= 8, "expected the picker plugins to declare the field"


def test_folder_picking_plugins_all_declare_it():
    """Every plugin that makes the user pick a file/folder out of Explorer is
    Sentry-compatible — that's the whole promise of the gadget."""
    expected = {
        "902_dxf_prep", "911_baked_beans_wild_ride", "911_batch_repeater",
        "911_lst_organizer", "911_sspo_award_review", "911_sspo_invoicing_prep",
        "922_setup", "customer_dxf_analysis", "qr_code_generator",
    }
    declared = set()
    for d in _repo_plugins():
        manifest = d / "plugin.json"
        if manifest.is_file() and _sentry_field(
                json.loads(manifest.read_text(encoding="utf-8"))):
            declared.add(d.name)
    assert expected <= declared, f"missing: {expected - declared}"


# ── SDK plumbing ─────────────────────────────────────────────────────────────
class _RecordingConsole:
    def __init__(self):
        self.dir_calls = []
        self.file_calls = []

    def request_directory(self, title, start_dir, style=None):
        self.dir_calls.append(style)
        return "C:/picked"

    def request_file(self, title, start_dir, name_filter, style=None):
        self.file_calls.append(style)
        return "C:/picked.xlsx"


@pytest.fixture
def console():
    return _RecordingConsole()


def test_request_directory_applies_the_drone_when_armed(console, monkeypatch):
    monkeypatch.setattr(sentry_mode, "is_enabled", lambda pid, settings=None: True)
    sdk.request_directory({"console": console, "plugin_id": "922_setup"}, "t")
    assert console.dir_calls == [sentry_mode.STYLE]


def test_request_directory_is_plain_when_not_armed(console, monkeypatch):
    monkeypatch.setattr(sentry_mode, "is_enabled", lambda pid, settings=None: False)
    sdk.request_directory({"console": console, "plugin_id": "922_setup"}, "t")
    assert console.dir_calls == [None]


def test_request_file_applies_the_drone_when_armed(console, monkeypatch):
    monkeypatch.setattr(sentry_mode, "is_enabled", lambda pid, settings=None: True)
    sdk.request_file({"console": console, "plugin_id": "customer_dxf_analysis"},
                     "t", "", "DXF (*.dxf)")
    assert console.file_calls == [sentry_mode.STYLE]


def test_explicit_empty_style_forces_the_plain_dialog(console, monkeypatch):
    """style="" is the opt-out for a prompt the drone should never touch — it
    reaches the console as the plain 2-arg call, so no style at all."""
    monkeypatch.setattr(sentry_mode, "is_enabled", lambda pid, settings=None: True)
    sdk.request_directory({"console": console, "plugin_id": "922_setup"}, "t",
                          style="")
    assert console.dir_calls == [None]


def test_sentry_style_survives_headless():
    """No SettingsManager (standalone CLI plugin testing) must not raise."""
    assert sdk.sentry_style({"plugin_id": "922_setup", "settings": {}}) in (
        None, sentry_mode.STYLE)
