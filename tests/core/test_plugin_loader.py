"""PluginLoader directory resolution + basic discovery.

The resolution order is the contract that retired old Hard Rule 12 ("after
editing a plugin, copy it to BOTH locations"): dev runs now load the repo
plugins/ tree directly, frozen builds keep loading the installed copies in
%LOCALAPPDATA%\\TechDeck\\plugins, and TECHDECK_PLUGINS_DIR overrides both.
"""

import json
import sys
from pathlib import Path

from techdeck.core.plugin_loader import PluginLoader

ROOT = Path(__file__).resolve().parents[2]


# ------------------------------------------------- directory resolution

def test_dev_default_is_the_repo_tree(monkeypatch):
    """python -m techdeck from a checkout must run the code you just edited."""
    monkeypatch.delenv("TECHDECK_PLUGINS_DIR", raising=False)
    assert PluginLoader._default_plugins_dir() == ROOT / "plugins"


def test_env_override_wins(monkeypatch, tmp_path):
    override = tmp_path / "override_plugins"
    monkeypatch.setenv("TECHDECK_PLUGINS_DIR", str(override))
    assert PluginLoader._default_plugins_dir() == override


def test_frozen_build_uses_localappdata(monkeypatch, tmp_path):
    """The frozen exe ships a plugins/ tree inside _internal that would match
    the repo-tree probe — the sys.frozen branch must win before it."""
    monkeypatch.delenv("TECHDECK_PLUGINS_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert (PluginLoader._default_plugins_dir()
            == tmp_path / "TechDeck" / "plugins")


def test_explicit_plugins_dir_argument_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("TECHDECK_PLUGINS_DIR", str(tmp_path / "ignored"))
    custom = tmp_path / "custom"
    loader = PluginLoader(custom)
    assert loader.plugins_dir == custom
    assert custom.is_dir()  # created on construction


def test_shared_loader_in_dev_sees_repo_plugins(monkeypatch):
    """End-to-end: a default loader in a dev run discovers the real roster."""
    monkeypatch.delenv("TECHDECK_PLUGINS_DIR", raising=False)
    loader = PluginLoader()
    found = {p.id for p in loader.discover_plugins()}
    assert "911_setup" in found and "922_setup" in found


# ------------------------------------------------- basic discovery

def _write_plugin(root: Path, plugin_id: str) -> None:
    plugin_dir = root / plugin_id
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(json.dumps({
        "id": plugin_id,
        "name": "Test Plugin",
        "description": "test",
        "version": "1.0.0",
        "author": "tests",
        "family": "General",
    }), encoding="utf-8")
    (plugin_dir / "run.py").write_text(
        "def run(params, progress_callback, cancel_event):\n"
        "    return None\n", encoding="utf-8")


def test_discovery_finds_valid_and_skips_malformed(tmp_path):
    _write_plugin(tmp_path, "good_one")
    bad = tmp_path / "bad_one"
    bad.mkdir()
    (bad / "plugin.json").write_text("{this is not json", encoding="utf-8")
    (bad / "run.py").write_text("def run(p, c, e):\n    pass\n",
                                encoding="utf-8")

    loader = PluginLoader(tmp_path)
    found = loader.discover_plugins()
    assert [p.id for p in found] == ["good_one"]


def test_discovery_skips_folder_missing_run_py(tmp_path):
    _write_plugin(tmp_path, "complete")
    incomplete = tmp_path / "incomplete"
    incomplete.mkdir()
    (incomplete / "plugin.json").write_text(json.dumps({
        "id": "incomplete", "name": "X", "description": "x",
        "version": "1.0.0", "author": "t", "family": "General",
    }), encoding="utf-8")

    loader = PluginLoader(tmp_path)
    assert [p.id for p in loader.discover_plugins()] == ["complete"]
