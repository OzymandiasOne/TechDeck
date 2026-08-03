"""Sentry Drone UI wiring: the hidden-until-bought settings field and the
per-app loadout window.

The field and the window edit the SAME per-plugin value, so the two can never
disagree — these lock that in, plus the one way this could quietly bite: saving
Settings -> Apps while the field is hidden must not wipe the stored value.
"""

import pytest

from techdeck.core import sentry_mode
from techdeck.ui.widgets.plugin_settings_widget import PluginSettingsWidget


SCHEMA = {
    "fields": [
        {"key": "base_path", "type": "string", "label": "Base path",
         "default": ""},
        {"key": "sentry_drone", "type": "boolean", "label": "Sentry Drone mode",
         "default": False, "hidden_unless_unlocked": sentry_mode.ITEM_ID},
    ]
}


class _Unlocks:
    def __init__(self, owned):
        self._owned = bool(owned)

    def is_unlocked(self, item_id):
        return self._owned


@pytest.fixture
def own(monkeypatch):
    """Toggle ownership for the widget's SettingsManager lookup."""
    def _set(owned):
        import techdeck.core.settings as settings_mod
        monkeypatch.setattr(settings_mod, "SettingsManager",
                            lambda *a, **k: _Unlocks(owned))
    return _set


def test_field_is_hidden_until_the_drone_is_bought(qapp, own):
    own(False)
    w = PluginSettingsWidget("922_setup", SCHEMA, {"sentry_drone": True})
    assert "sentry_drone" not in w.widgets
    assert "base_path" in w.widgets


def test_field_appears_once_bought(qapp, own):
    own(True)
    w = PluginSettingsWidget("922_setup", SCHEMA, {"sentry_drone": True})
    assert "sentry_drone" in w.widgets
    assert w.get_values()["sentry_drone"] is True


def test_hidden_value_survives_a_save(qapp, own):
    """The user bought the drone, switched it on for this app, then someone
    reset the store. Saving this page must not silently clear the setting."""
    own(False)
    w = PluginSettingsWidget("922_setup", SCHEMA, {"sentry_drone": True,
                                                   "base_path": "C:/x"})
    values = w.get_values()
    assert values["sentry_drone"] is True     # carried through untouched
    assert values["base_path"] == "C:/x"


def test_all_fields_locked_shows_the_no_settings_message(qapp, own):
    own(False)
    schema = {"fields": [SCHEMA["fields"][1]]}   # sentry_drone only
    w = PluginSettingsWidget("902_dxf_prep", schema, {})
    assert not w.widgets
    labels = [lbl.text() for lbl, _ in w.secondary_labels]
    assert any("no configurable settings" in t for t in labels)


# ── the loadout window ───────────────────────────────────────────────────────
class _Settings:
    def __init__(self):
        self.plugin = {}

    def is_unlocked(self, item_id):
        return item_id == sentry_mode.ITEM_ID

    def get_plugin_setting(self, plugin_id, key, default=None):
        return self.plugin.get(plugin_id, {}).get(key, default)

    def set_plugin_setting(self, plugin_id, key, value):
        self.plugin.setdefault(plugin_id, {})[key] = value


APPS = [
    {"id": "922_setup", "name": "922 Setup", "family": "922", "enabled": False},
    {"id": "902_dxf_prep", "name": "902 DXF Prep", "family": "902",
     "enabled": True},
]


def test_loadout_window_saves_each_app_independently(qapp, monkeypatch):
    from techdeck.ui.dialogs.sentry_config_dialog import SentryConfigDialog
    monkeypatch.setattr(sentry_mode, "compatible_plugins",
                        lambda **kw: [dict(a) for a in APPS])
    s = _Settings()
    dlg = SentryConfigDialog(s)

    # Rows come back in the order compatible_plugins gave them.
    assert [r.app["id"] for r in dlg._rows] == ["922_setup", "902_dxf_prep"]
    assert [r.is_on() for r in dlg._rows] == [False, True]

    dlg._rows[0].toggle.setChecked(True)     # switch 922 Setup on
    dlg._rows[1].toggle.setChecked(False)    # switch 902 DXF Prep off
    dlg._save()

    assert sentry_mode.is_enabled("922_setup", s)
    assert not sentry_mode.is_enabled("902_dxf_prep", s)
    dlg.deleteLater()


def test_loadout_all_on_all_off(qapp, monkeypatch):
    from techdeck.ui.dialogs.sentry_config_dialog import SentryConfigDialog
    monkeypatch.setattr(sentry_mode, "compatible_plugins",
                        lambda **kw: [dict(a) for a in APPS])
    dlg = SentryConfigDialog(_Settings())
    dlg._set_all(True)
    assert dlg.enabled_count() == 2
    dlg._set_all(False)
    assert dlg.enabled_count() == 0
    dlg.deleteLater()


def test_loadout_handles_no_compatible_apps(qapp, monkeypatch):
    from techdeck.ui.dialogs.sentry_config_dialog import SentryConfigDialog
    monkeypatch.setattr(sentry_mode, "compatible_plugins", lambda **kw: [])
    dlg = SentryConfigDialog(_Settings())
    assert dlg._rows == []
    dlg._save()          # must not raise
    dlg.deleteLater()
