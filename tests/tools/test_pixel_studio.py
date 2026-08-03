"""Tests for Pixel Studio helpers + the DevKit registry."""


def test_presets_have_expected_sizes():
    from tools.devkit.pixel_studio import _PRESETS
    assert _PRESETS["Default"] is None
    assert len(_PRESETS["PICO-8"]) == 16
    assert len(_PRESETS["Sweetie-16"]) == 16
    assert all(v is None or all(h.startswith("#") for h in v)
               for v in _PRESETS.values())


def test_preview_themes_exclude_professional():
    from tools.devkit.pixel_studio import _preview_themes
    themes = _preview_themes()
    assert "professional" not in themes
    assert {"dark", "matrix"} <= set(themes)
    assert len(themes) == 6


def test_recolor_tones_returns_valid_hex_for_every_theme():
    from tools.devkit.pixel_studio import _recolor_tones, _preview_themes
    tones = {"k": "#101018", "w": "#f4f4f8", "r": "#d83f3f"}
    for theme in _preview_themes():
        rc = _recolor_tones(tones, theme)
        assert set(rc) == set(tones)
        assert all(len(v) == 7 and v.startswith("#") for v in rc.values())


def test_svg_icon_renders_non_null(qapp):
    from tools.devkit.pixel_studio import _svg_icon, _TOOL_ICONS, _NAV_ICONS
    for spec in list(_TOOL_ICONS.values()) + list(_NAV_ICONS.values()):
        assert not _svg_icon(spec, "#ffffff").isNull()


def test_registry_exposes_pixel_studio():
    from tools.devkit.registry import DEV_TOOLS, ToolSpec
    assert any(t.key == "pixel_studio" for t in DEV_TOOLS)
    for t in DEV_TOOLS:
        assert isinstance(t, ToolSpec)
        assert t.label and callable(t.build)


def test_studio_builds_all_three_modes(qapp):
    from tools.devkit.pixel_studio import (
        PixelStudio, _SpritePanel, _TileIconPanel, _PlacementPanel)
    s = PixelStudio()
    assert s.stack.count() == 3
    assert isinstance(s.stack.widget(0), _SpritePanel)
    assert isinstance(s.stack.widget(1), _TileIconPanel)
    assert isinstance(s.stack.widget(2), _PlacementPanel)
    # Tile Icon starts at 32x32 and renders a preview tile per theme.
    icon = s.stack.widget(1)
    assert icon.canvas.grid_size() == (32, 32)
    assert len(icon._preview_labels) == 6


def test_sprite_mode_has_layers_tile_icon_does_not(qapp):
    """Layers belong to whole-sprite authoring. Tile Icon edits ONE 32x32 grid
    written back into a generator script, so a stack has nothing to save into."""
    from tools.devkit.pixel_studio import _SpritePanel, _TileIconPanel
    sp = _SpritePanel()
    assert sp.SHOW_LAYERS is True
    assert hasattr(sp, "layer_list")
    ti = _TileIconPanel()
    assert ti.SHOW_LAYERS is False
    assert not hasattr(ti, "layer_list")


def test_sprite_layer_rail_tracks_the_stack(qapp):
    from tools.devkit.pixel_studio import _SpritePanel
    sp = _SpritePanel()
    sp.canvas.add_layer("second")
    sp.canvas.add_layer("third")
    sp._refresh_layers()
    # the list shows the stack reversed — topmost first
    assert [sp.layer_list.item(r).text()
            for r in range(sp.layer_list.count())] == ["third", "second", "Layer 1"]
    sp.layer_list.setCurrentRow(2)          # click the bottom row
    assert sp.canvas.layer.name == "Layer 1"


def test_sprite_layer_visibility_toggle(qapp):
    from PySide6.QtCore import Qt
    from tools.devkit.pixel_studio import _SpritePanel
    sp = _SpritePanel()
    sp.canvas.add_layer("second")
    sp._refresh_layers()
    sp.layer_list.item(0).setCheckState(Qt.CheckState.Unchecked)
    assert sp.canvas.layers[1].visible is False


def test_set_active_does_not_signal_a_stack_change(qapp):
    """Regression: set_active used to emit layers_changed, which made the panel
    rebuild the whole list. An internal-move drop fires currentRowChanged
    mid-drop, so that rebuild UNDID the drop the user just made."""
    from tools.pixel_editor import Canvas
    c = Canvas(4, 4)
    c.add_layer("second")
    fired = []
    c.layers_changed.connect(lambda: fired.append("stack"))
    c.set_active(0)
    assert fired == []


def test_layer_list_reports_drops_via_dropevent(qapp):
    """Regression: QListWidget implements InternalMove as remove + insert, so
    model().rowsMoved NEVER fires. Hooking it gave a list that reordered
    visually while the stack stayed put."""
    from PySide6.QtWidgets import QListWidgetItem
    from tools.devkit.pixel_studio import _LayerList
    lw = _LayerList()
    for n in ("c", "b", "a"):
        lw.addItem(QListWidgetItem(n))
    moved = []
    lw.model().rowsMoved.connect(lambda *a: moved.append("rowsMoved"))
    assert hasattr(lw, "reordered")          # the signal we actually rely on
    assert moved == []                       # and the one we must not


def test_drag_reorder_syncs_the_stack(qapp):
    from tools.devkit.pixel_studio import _SpritePanel
    sp = _SpritePanel()
    sp.canvas.add_layer("middle")
    sp.canvas.add_layer("top")
    sp._refresh_layers()
    # what Qt's InternalMove does on a drop, then what dropEvent emits
    item = sp.layer_list.takeItem(0)
    sp.layer_list.insertItem(2, item)
    sp.layer_list.setCurrentRow(2)
    sp.layer_list.reordered.emit()

    names = [sp.layer_list.item(r).text() for r in range(sp.layer_list.count())]
    assert names == ["middle", "Layer 1", "top"]          # drop not undone
    assert [l.name for l in sp.canvas.layers] == list(reversed(names))
    assert sp.canvas.layer.name == "top"                  # follows the drag


def test_no_up_down_buttons(qapp):
    """Reordering is drag-and-drop only."""
    from PySide6.QtWidgets import QPushButton
    from tools.devkit.pixel_studio import _SpritePanel
    sp = _SpritePanel()
    labels = {b.text() for b in sp.findChildren(QPushButton)}
    assert "Up" not in labels and "Down" not in labels
    assert {"+ Open", "+ New", "Dupe", "Delete"} <= labels


def test_palette_and_layers_share_one_rail(qapp):
    """Palette above, layers below — one column, not two side-by-side rails."""
    from tools.devkit.pixel_studio import _SpritePanel
    sp = _SpritePanel()
    rail = sp.layer_list
    while rail.parent() is not None and rail.parent() is not sp:
        rail = rail.parent()
    # the swatch host must live under the same top-level rail as the layer list
    host = sp.swatch_host
    while host.parent() is not None and host.parent() is not sp:
        host = host.parent()
    assert rail is host
