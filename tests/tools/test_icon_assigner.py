"""Tests for the DevKit Icon Assigner (gallery discovery + source patcher +
staging/save flow)."""

import ast
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.devkit.icon_assigner import (
    ICON_MODULE_PATH, IconAssigner, MONOGRAM_LABEL, available_icon_keys,
    patch_icon_keys_source, render_key_pixmap,
)
from techdeck.ui import plugin_icon as pi


def _extract_dict(path: Path) -> dict:
    """Parse PLUGIN_ICON_KEYS out of a plugin_icon.py file via ast."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign)
                and any(getattr(t, "id", "") == "PLUGIN_ICON_KEYS"
                        for t in node.targets)):
            return ast.literal_eval(node.value)
    raise AssertionError("PLUGIN_ICON_KEYS not found")


@pytest.fixture
def icon_module_copy(tmp_path):
    dest = tmp_path / "plugin_icon.py"
    shutil.copy(ICON_MODULE_PATH, dest)
    return dest


# ---------------------------------------------------------------------------
# available_icon_keys / render_key_pixmap
# ---------------------------------------------------------------------------

def test_gallery_discovers_assigned_keys(qapp):
    keys = {k for k, _set in available_icon_keys()}
    # every currently-assigned key must be offered (else the tool can't
    # round-trip existing assignments)
    for pid, key in pi.PLUGIN_ICON_KEYS.items():
        assert key in keys, f"{pid}'s key {key!r} missing from the gallery"
    # eye-follow directional variants are not assignable keys
    assert "mr_beans" in keys
    assert "mr_beans_up" not in keys
    # no duplicates
    listed = [k for k, _ in available_icon_keys()]
    assert len(listed) == len(set(listed))


def test_render_key_pixmap_both_sets(qapp):
    assert render_key_pixmap("repeat", 48) is not None          # themed
    assert render_key_pixmap("futurama_bender", 48) is not None  # pack
    assert render_key_pixmap("no_such_key_xyz", 48) is None


# ---------------------------------------------------------------------------
# patch_icon_keys_source
# ---------------------------------------------------------------------------

def test_patch_replaces_adds_removes(icon_module_copy):
    before = _extract_dict(icon_module_copy)
    assert "dxf_offset_tool" not in before
    patch_icon_keys_source(
        {"922_setup": "stamp",            # replace
         "dxf_offset_tool": "blueprint",  # add
         "qr_code_generator": None},      # remove
        path=icon_module_copy)
    after = _extract_dict(icon_module_copy)
    assert after["922_setup"] == "stamp"
    assert after["dxf_offset_tool"] == "blueprint"
    assert "qr_code_generator" not in after
    # everything else untouched
    for pid, key in before.items():
        if pid not in ("922_setup", "qr_code_generator"):
            assert after[pid] == key


def test_patch_preserves_untouched_lines_and_comments(icon_module_copy):
    original = icon_module_copy.read_text(encoding="utf-8").splitlines()
    patch_icon_keys_source({"922_setup": "stamp"}, path=icon_module_copy)
    patched = icon_module_copy.read_text(encoding="utf-8").splitlines()
    # same line count (one line replaced in place)
    assert len(patched) == len(original)
    diffs = [i for i, (a, b) in enumerate(zip(original, patched)) if a != b]
    assert len(diffs) == 1
    assert '"922_setup"' in patched[diffs[0]]
    # the 911_lst_organizer inline comment survives
    assert any("# recolored variant (blue body)" in ln for ln in patched)


def test_patch_replace_keeps_trailing_comment(icon_module_copy):
    patch_icon_keys_source({"911_lst_organizer": "badge"},
                           path=icon_module_copy)
    text = icon_module_copy.read_text(encoding="utf-8")
    line = next(ln for ln in text.splitlines() if '"911_lst_organizer"' in ln)
    assert '"badge"' in line
    assert "# recolored variant (blue body)" in line


def test_patch_remove_then_readd_roundtrip(icon_module_copy):
    patch_icon_keys_source({"922_setup": None}, path=icon_module_copy)
    assert "922_setup" not in _extract_dict(icon_module_copy)
    patch_icon_keys_source({"922_setup": "icons8-toolbox"},
                           path=icon_module_copy)
    assert _extract_dict(icon_module_copy)["922_setup"] == "icons8-toolbox"


def test_patch_missing_block_raises(tmp_path):
    bad = tmp_path / "not_it.py"
    bad.write_text("nothing here\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        patch_icon_keys_source({"x": "y"}, path=bad)


# ---------------------------------------------------------------------------
# IconAssigner widget flow
# ---------------------------------------------------------------------------

def _row_for_id(w, plugin_id):
    from PySide6.QtCore import Qt
    return next(
        i for i in range(w.plugin_list.count())
        if w.plugin_list.item(i).data(Qt.ItemDataRole.UserRole).id == plugin_id)


def _fake_plugins():
    return [
        SimpleNamespace(id="911_setup", name="911 Setup", family="911",
                        icon=None, path="."),
        SimpleNamespace(id="dxf_offset_tool", name="DXF Offset Tool",
                        family="General", icon=None, path="."),
    ]


def test_widget_stages_and_reverts(qapp):
    w = IconAssigner(plugins=_fake_plugins())
    assert w.plugin_list.count() == 2
    assert w.gallery.count() > 1
    assert w.gallery.item(0).text() == MONOGRAM_LABEL

    # select the DXF Offset Tool row (no saved key) and stage an icon
    # (list text is the display name only — the id lives in UserRole/tooltip)
    row = _row_for_id(w, "dxf_offset_tool")
    w.plugin_list.setCurrentRow(row)
    target = next(w.gallery.item(i) for i in range(w.gallery.count())
                  if w.gallery.item(i).text() == "blueprint")
    w._on_icon_picked(target)
    assert w._staged == {"dxf_offset_tool": "blueprint"}
    assert w._save_btn.isEnabled()
    assert "1 unsaved" in w._pending_label.text()

    # picking the already-saved key un-stages
    w._revert()
    assert w._staged == {}
    assert not w._save_btn.isEnabled()


def test_widget_save_writes_source_and_syncs(qapp, icon_module_copy,
                                             monkeypatch):
    import tools.devkit.icon_assigner as ia
    monkeypatch.setattr(ia, "ICON_MODULE_PATH", icon_module_copy)
    w = IconAssigner(plugins=_fake_plugins())
    row = _row_for_id(w, "dxf_offset_tool")
    w.plugin_list.setCurrentRow(row)
    target = next(w.gallery.item(i) for i in range(w.gallery.count())
                  if w.gallery.item(i).text() == "blueprint")
    w._on_icon_picked(target)
    try:
        w._save()
        assert _extract_dict(icon_module_copy)["dxf_offset_tool"] == "blueprint"
        assert pi.PLUGIN_ICON_KEYS.get("dxf_offset_tool") == "blueprint"
        assert w._staged == {}
        assert "Saved" in w._pending_label.text()
    finally:
        pi.PLUGIN_ICON_KEYS.pop("dxf_offset_tool", None)
