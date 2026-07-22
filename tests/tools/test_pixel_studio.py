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
