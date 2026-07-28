"""Tests for the source-only DevKit gate + persisted toggle state.

The dev-mode singleton persists its state through SettingsManager; these
tests wire it to an in-memory stub so they never touch the real
settings.json, and reset the singleton so each test sees a fresh launch.
"""

import sys

import pytest

import techdeck.core.settings as settings_mod
import techdeck.ui.dev_mode as dev_mode


class _StubSettings:
    """Just the dev-mode accessors, backed by a plain dict."""

    def __init__(self, store):
        self._store = store

    def get_dev_mode_enabled(self):
        return bool(self._store.get("dev_mode", False))

    def set_dev_mode_enabled(self, enabled):
        self._store["dev_mode"] = bool(enabled)


@pytest.fixture
def store(monkeypatch):
    """Fresh dev-mode singleton wired to an in-memory settings store."""
    data = {}
    monkeypatch.setattr(settings_mod, "SettingsManager",
                        lambda *a, **k: _StubSettings(data))
    monkeypatch.setattr(dev_mode, "_instance", None)
    yield data
    dev_mode._instance = None


def test_is_dev_build_true_from_source():
    # The test suite runs from source, never frozen.
    assert dev_mode.is_dev_build() is True


def test_defaults_off(store):
    assert dev_mode.get_dev_mode().is_active() is False


def test_toggle_and_signal(store):
    dm = dev_mode.get_dev_mode()
    events = []
    dm.changed.connect(events.append)
    assert dm.is_active() is False
    dm.set_active(True)
    assert dm.is_active() is True
    dm.set_active(True)     # idempotent — no duplicate signal
    dm.set_active(False)
    assert dm.is_active() is False
    assert events == [True, False]


def test_set_active_persists(store):
    dev_mode.get_dev_mode().set_active(True)
    assert store["dev_mode"] is True
    dev_mode.get_dev_mode().set_active(False)
    assert store["dev_mode"] is False


def test_restores_persisted_state_on_new_instance(store):
    dev_mode.get_dev_mode().set_active(True)
    dev_mode._instance = None                    # simulate a fresh launch
    assert dev_mode.get_dev_mode().is_active() is True


def test_frozen_build_is_inert_even_with_persisted_true(store, monkeypatch):
    store["dev_mode"] = True
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    dev_mode._instance = None
    dm = dev_mode.get_dev_mode()
    assert dev_mode.is_dev_build() is False
    assert dm.is_active() is False
    dm.set_active(True)     # must refuse to activate in a frozen build
    assert dm.is_active() is False
    assert store["dev_mode"] is True   # and must not clobber settings


def test_unreadable_settings_never_block_launch(monkeypatch):
    def boom(*a, **k):
        raise OSError("settings unreadable")
    monkeypatch.setattr(settings_mod, "SettingsManager", boom)
    monkeypatch.setattr(dev_mode, "_instance", None)
    assert dev_mode.get_dev_mode().is_active() is False
    dev_mode._instance = None
