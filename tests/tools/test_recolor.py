"""Tests for the tile-icon recolor pipeline (generate_tile_icons_32) and the
Pixel Studio's live preview, which must reproduce it exactly."""

import pytest

from tools.generate_tile_icons_32 import (
    _hex, _lum, _build_map, _unique_colors, _recolor, _new, _draw_grid,
    THEME_PALETTES, THEME_SUBSTITUTIONS, PICO8,
)


def test_hex_parses_with_and_without_hash():
    assert _hex("#ff0000") == (255, 0, 0)
    assert _hex("00ff00") == (0, 255, 0)
    assert _hex("#ffffff") == (255, 255, 255)


def test_lum_orders_black_below_white():
    assert _lum((0, 0, 0)) == 0
    assert _lum((255, 255, 255)) == pytest.approx(255, abs=1)
    assert _lum((10, 10, 10)) < _lum((200, 200, 200))


def test_build_map_is_monotonic_by_luminance():
    """Darker source colors must map to darker palette colors — the property the
    whole recolor scheme relies on (outline stays darkest, highlight lightest)."""
    src = [(240, 240, 240), (10, 10, 10), (120, 120, 120)]  # deliberately unsorted
    palette = [_hex(PICO8[n]) for n in ("black", "dgrey", "lgrey", "white", "red")]
    mapping = _build_map(src, palette)
    ordered = sorted(src, key=_lum)
    mapped_lums = [_lum(mapping[c]) for c in ordered]
    assert mapped_lums == sorted(mapped_lums)          # non-decreasing
    assert len(set(mapping.values())) == len(src)      # distinct targets preserved


def test_build_map_covers_every_theme_palette():
    src = [(16, 16, 24), (128, 128, 128), (240, 240, 232)]
    for theme, names in THEME_PALETTES.items():
        palette = [_hex(h) for h in names]
        mapping = _build_map(src, palette)
        assert set(mapping.keys()) == set(src)
        assert all(c in palette for c in mapping.values()), theme


def test_studio_preview_matches_generator_render():
    """The Pixel Studio preview (_recolor_tones) must equal the actual pixels the
    generator produces for the same grid, in every theme (incl. substitutions)."""
    from tools.devkit.pixel_studio import _recolor_tones
    tones = {"a": "#101018", "b": "#808080", "c": "#f0f0f0"}
    grid = ["abc" + "." * 29] + ["." * 32] * 31  # a,b,c at (0,0),(1,0),(2,0)

    for theme in THEME_PALETTES:
        im, d = _new()
        _draw_grid(d, grid, tones)
        palette = [_hex(h) for h in THEME_PALETTES[theme]]
        mapping = _build_map(_unique_colors(im), palette)
        subs = {_hex(x): _hex(y)
                for x, y in THEME_SUBSTITUTIONS.get(theme, {}).items()}
        if subs:
            mapping = {k: subs.get(v, v) for k, v in mapping.items()}
        _recolor(im, mapping)
        px = im.load()
        expected = {"a": px[0, 0][:3], "b": px[1, 0][:3], "c": px[2, 0][:3]}

        studio = _recolor_tones(tones, theme)
        for ch, rgb in expected.items():
            assert studio[ch] == "#%02x%02x%02x" % rgb, (theme, ch)


def test_recolor_tones_empty_is_empty():
    from tools.devkit.pixel_studio import _recolor_tones
    assert _recolor_tones({}, "dark") == {}
