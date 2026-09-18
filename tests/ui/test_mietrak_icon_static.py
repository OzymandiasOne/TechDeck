"""The MieTrak Tools tile icon is BRAND art: it must always render in its own
colors, never the theme's (user's requirement, 2026-09-17).

Static icons live in the pack set (tools/generate_pack_icons.py -> "TechDeck
pack pixel"); the loader only theme-recolors keys that exist in the
"TechDeck pixel 32" set. So the guard is: the key resolves to a pack PNG, no
themed copy exists, and the PNG's opaque pixels are the logo red + orange.
"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
TILES = ROOT / "assets" / "icons" / "tile icons"


def test_mietrak_key_points_at_the_pack_set():
    from techdeck.ui.plugin_icon import PLUGIN_ICON_KEYS, _pack_icon_path
    key = PLUGIN_ICON_KEYS["mietrak_tools"]
    assert _pack_icon_path(key) is not None, "mietrak icon must be a pack (static) icon"
    themed = list((TILES / "TechDeck pixel 32").glob(f"*/{key}.png"))
    assert not themed, f"a themed copy would be recolored per theme: {themed}"


def test_mietrak_png_keeps_brand_colors():
    from techdeck.ui.plugin_icon import PLUGIN_ICON_KEYS, _pack_icon_path
    path = _pack_icon_path(PLUGIN_ICON_KEYS["mietrak_tools"])
    im = Image.open(path).convert("RGBA")
    colors = {px[:3] for px in im.getdata() if px[3] > 0}
    assert colors == {(0xE4, 0x1E, 0x2F), (0xF0, 0x8F, 0x06)}, colors
