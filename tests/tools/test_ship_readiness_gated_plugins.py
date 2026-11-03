"""A plugin whose gate is SHUT must not fail the ship-readiness check.

This turned the public main red immediately after the v0.8.9 tag, and it was
green on every dev machine. The Puppet Master's gate became the halloween
THEME on 2026-11-03, so `gate_enabled("puppet_master")` now depends on MACHINE
STATE: a CI runner has no settings and therefore no theme, so the loader
correctly skips `game_puppet_master`, and `load_all_plugins` called that
"present on disk but NOT discovered" - an error. Anyone wearing the theme,
which included the maintainer, saw 31 plugins and a clean PASS.

That is exactly the "passes locally, fails only on CI" class this script
exists to catch, with the script itself producing it. The rule: a shut gate is
the gate working, so it is a NOTE. A plugin that names no gate, or names one
that is open, must still be a hard error when it fails to load - otherwise a
malformed plugin.json would ship silently, which is the thing the check is for.
"""
import json

import pytest

from tools import check_ship_readiness as csr


@pytest.fixture
def fake_plugins(tmp_path, monkeypatch):
    """A plugins dir we control, with the loader and gate stubbed."""
    monkeypatch.setattr(csr, "PLUGINS_DIR", tmp_path)

    def _make(plugins, discovered, open_gates=()):
        for pid, gate in plugins.items():
            d = tmp_path / pid
            d.mkdir()
            manifest = {"id": pid, "name": pid, "version": "1.0.0"}
            if gate:
                manifest["gate"] = gate
            (d / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")

        class _Plugin:
            def __init__(self, pid):
                self.id = pid

        class _Loader:
            def __init__(self, *_a, **_k):
                pass

            def discover_plugins(self):
                return [_Plugin(p) for p in discovered]

            def validate_plugin(self, _pid):
                return True, ""

        import techdeck.core.plugin_loader as pl
        import techdeck.core.constants as consts
        monkeypatch.setattr(pl, "PluginLoader", _Loader)
        monkeypatch.setattr(consts, "gate_enabled",
                            lambda name: name in open_gates)
        errors, warnings = [], []
        loaded = csr.load_all_plugins(errors, warnings)
        return loaded, errors, warnings

    return _make


def test_a_shut_gate_is_a_note_not_an_error(fake_plugins):
    """THE REGRESSION. Green on a machine wearing the theme, red on CI."""
    loaded, errors, warnings = fake_plugins(
        plugins={"game_puppet_master": "puppet_master", "922_setup": ""},
        discovered=["922_setup"],
        open_gates=())
    assert errors == [], errors
    assert loaded == 1
    assert len(warnings) == 1
    assert "game_puppet_master" in warnings[0]
    assert "gate is shut" in warnings[0]


def test_an_open_gate_that_still_fails_to_load_is_an_error(fake_plugins):
    """The gate is open, so something really is wrong with the folder."""
    _, errors, warnings = fake_plugins(
        plugins={"game_puppet_master": "puppet_master"},
        discovered=[],
        open_gates=("puppet_master",))
    assert warnings == []
    assert len(errors) == 1
    assert "present on disk but NOT discovered" in errors[0]


def test_an_ungated_plugin_that_fails_to_load_is_still_an_error(fake_plugins):
    """The original purpose of the check: a malformed plugin.json must never
    ship quietly just because gated plugins got an exemption."""
    _, errors, warnings = fake_plugins(
        plugins={"911_setup": ""},
        discovered=[],
        open_gates=())
    assert warnings == []
    assert len(errors) == 1
    assert "911_setup" in errors[0]


def test_a_gated_plugin_that_loads_is_simply_counted(fake_plugins):
    loaded, errors, warnings = fake_plugins(
        plugins={"game_puppet_master": "puppet_master"},
        discovered=["game_puppet_master"],
        open_gates=("puppet_master",))
    assert (errors, warnings) == ([], [])
    assert loaded == 1


def test_the_real_check_passes_with_no_theme_at_all(tmp_path, monkeypatch):
    """End to end against the REAL plugins dir under CI's conditions.

    A runner has no settings file, so no theme, so the Puppet Master's gate is
    shut. Before the fix this printed `RESULT: FAIL (1 error(s))` here and
    `PASS` on the maintainer's machine.
    """
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("TECHDECK_PUPPET_MASTER", raising=False)
    errors, warnings = [], []
    csr.load_all_plugins(errors, warnings)
    assert errors == [], errors
