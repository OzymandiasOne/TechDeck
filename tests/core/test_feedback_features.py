"""Tests for the dynamic Submit-Feedback "Which Feature?" option list.

The list is built live from the installed plugin roster (so it never goes
stale), keeps LOCKED plugins visible (users report on things they haven't
unlocked), and retires vanished plugins as "(RETIRED)" until they've ridden
out PURGE_AFTER_UPDATES version bumps. State persists in SettingsManager, so
every test uses settings_dir=tmp_path for an isolated store.
"""

from pathlib import Path

from techdeck.core import feedback_features as ff
from techdeck.core.plugin_loader import Plugin
from techdeck.core.settings import SettingsManager


class _FakeLoader:
    """Stub PluginLoader returning a controllable roster of Plugin objects."""

    def __init__(self, names_families, locked=()):
        self._plugins = [
            Plugin(id=n.lower().replace(" ", "_"), name=n, description="",
                   version="1.0.0", author="", path=Path("."), family=f,
                   locked=(n in locked))
            for n, f in names_families
        ]

    def get_all_plugins(self):
        return list(self._plugins)


_BASE = [("911 Setup", "911"), ("922 Setup", "922"), ("QR Code Generator", "General")]


def _opts(settings, loader):
    return ff.get_feature_options(settings, loader)


def test_first_run_seeds_from_live_roster(tmp_path):
    s = SettingsManager(settings_dir=tmp_path)
    opts = _opts(s, _FakeLoader(_BASE))
    assert opts[0] == "TechDeck (General)"
    assert opts[-2:] == ["New - Suggestion Box", "Other"]
    for name in ("911 Setup", "922 Setup", "QR Code Generator"):
        assert name in opts
    # Nothing is retired on first sight.
    assert s.get_feedback_feature_state()["retired"] == {}


def test_locked_plugin_is_included(tmp_path):
    s = SettingsManager(settings_dir=tmp_path)
    loader = _FakeLoader(_BASE + [("ASA: The Video Game", "Games")],
                         locked=("ASA: The Video Game",))
    assert "ASA: The Video Game" in _opts(s, loader)


def test_new_plugin_auto_appears(tmp_path):
    s = SettingsManager(settings_dir=tmp_path)
    _opts(s, _FakeLoader(_BASE))
    opts = _opts(s, _FakeLoader(_BASE + [("New Cool App", "General")]))
    assert "New Cool App" in opts


def test_removed_plugin_is_retired_with_suffix(tmp_path):
    s = SettingsManager(settings_dir=tmp_path)
    _opts(s, _FakeLoader(_BASE))
    less = [("911 Setup", "911"), ("QR Code Generator", "General")]
    opts = _opts(s, _FakeLoader(less))
    assert "922 Setup (RETIRED)" in opts
    assert "922 Setup" not in opts            # the plain name is gone
    # Retired entries sit after the actives, before the fixed catch-alls.
    assert opts.index("922 Setup (RETIRED)") < opts.index("New - Suggestion Box")


def test_retired_plugin_purged_after_five_updates(tmp_path, monkeypatch):
    s = SettingsManager(settings_dir=tmp_path)
    _opts(s, _FakeLoader(_BASE))
    less = [("911 Setup", "911"), ("QR Code Generator", "General")]
    monkeypatch.setattr(ff, "APP_VERSION", "1.0.0")
    _opts(s, _FakeLoader(less))               # retire at v1.0.0 (updates=0)
    # Visible across the next four version bumps...
    for i in range(1, 5):
        monkeypatch.setattr(ff, "APP_VERSION", f"1.0.{i}")
        assert "922 Setup (RETIRED)" in _opts(s, _FakeLoader(less)), i
    # ...purged on the fifth.
    monkeypatch.setattr(ff, "APP_VERSION", "1.0.5")
    opts = _opts(s, _FakeLoader(less))
    assert not any("922 Setup" in o for o in opts)
    assert s.get_feedback_feature_state()["retired"] == {}


def test_same_version_reopen_does_not_advance_clock(tmp_path, monkeypatch):
    s = SettingsManager(settings_dir=tmp_path)
    _opts(s, _FakeLoader(_BASE))
    less = [("911 Setup", "911"), ("QR Code Generator", "General")]
    monkeypatch.setattr(ff, "APP_VERSION", "2.0.0")
    for _ in range(4):                         # reopened 4x on the SAME version
        _opts(s, _FakeLoader(less))
    assert s.get_feedback_feature_state()["retired"]["922 Setup"]["updates"] == 0


def test_reinstated_plugin_is_unretired(tmp_path, monkeypatch):
    s = SettingsManager(settings_dir=tmp_path)
    _opts(s, _FakeLoader(_BASE))
    less = [("911 Setup", "911"), ("QR Code Generator", "General")]
    monkeypatch.setattr(ff, "APP_VERSION", "3.0.0")
    _opts(s, _FakeLoader(less))
    assert "922 Setup" in s.get_feedback_feature_state()["retired"]
    opts = _opts(s, _FakeLoader(_BASE))        # 922 Setup comes back
    assert "922 Setup" in opts
    assert "922 Setup (RETIRED)" not in opts
    assert s.get_feedback_feature_state()["retired"] == {}


def test_empty_roster_keeps_last_known_list(tmp_path):
    s = SettingsManager(settings_dir=tmp_path)
    _opts(s, _FakeLoader(_BASE))
    opts = _opts(s, _FakeLoader([]))           # discovery hiccup
    assert "911 Setup" in opts and "922 Setup" in opts
    assert s.get_feedback_feature_state()["retired"] == {}   # nothing retired


def test_no_settings_builds_unpersisted_list():
    opts = ff.get_feature_options(None, _FakeLoader(_BASE))
    assert opts[0] == "TechDeck (General)"
    assert "922 Setup" in opts
