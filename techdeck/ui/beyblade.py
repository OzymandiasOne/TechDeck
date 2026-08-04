"""Beyblade parts — three swappable layers the player mixes into their own.

Every beyblade ships as THREE separate sprites, never a flattened one:

    TOP     the attack ring   — silhouette, milled body, accent blades
    BOTTOM  the weight disk   — shows through the top's grooves and windows
    CENTER  the bit chip      — ring colour, face colour, creature icon

A player who owns two beyblades can wear one's top over another's bottom with a
third's chip. That only works because the parts stay separate files all the way
from authoring to render — flattening at any point kills the feature, so the
composite is always derived here at runtime and never stored.

Parts live in `assets/sprites/beyblade/<design>_<kind>.tdart` and each declares
`"symmetry": 2`, because these are 180 degree designs and the spinner engine
would otherwise force them 4-fold and shred them.
"""
from __future__ import annotations

import sys
from pathlib import Path

from techdeck.ui import pixel_art

KINDS = ("bottom", "top", "center")     # composite order: bottom first
DESIGNS = ("classic", "silver_fang", "tidewing", "verdanox", "nightspur",
           "forgeheart", "ironclad")

DISPLAY = {
    "classic": "Storm Drake",
    "silver_fang": "Silver Fang",
    "tidewing": "Tidewing",
    "verdanox": "Thorn Crown",
    "nightspur": "Night Spur",
    "forgeheart": "Forge Heart",
    "ironclad": "Ironclad",
}

DEFAULT = {"bottom": "classic", "top": "classic", "center": "classic"}


def parts_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets" / "sprites" / "beyblade"
    return Path(__file__).resolve().parents[2] / "assets" / "sprites" / "beyblade"


def part_path(design: str, kind: str) -> Path:
    return parts_dir() / f"{design}_{kind}.tdart"


def has_part(design: str, kind: str) -> bool:
    return part_path(design, kind).exists()


def load_part(design: str, kind: str) -> dict | None:
    fn = part_path(design, kind)
    if not fn.exists():
        return None
    try:
        return pixel_art.load(fn)
    except Exception:
        return None


def normalize_choice(choice: dict | None) -> dict:
    """Fill in a partial/unknown selection from the default, so a saved combo
    referencing a removed design still renders instead of blanking out."""
    out = dict(DEFAULT)
    for kind in KINDS:
        want = (choice or {}).get(kind)
        if want in DESIGNS and has_part(want, kind):
            out[kind] = want
    return out


def compose(choice: dict | None = None) -> dict | None:
    """Flatten a parts selection into one sprite dict for rendering.

    Palettes are merged by CHAR. Parts share the tone vocabulary by design
    (accent ramp x/R/r/L, body 2/4/5/6/7, chip c/y/g/w/k/b), but two designs
    paint those keys different colours — so a later part's palette must not
    silently repaint an earlier one's pixels. Each part therefore gets its own
    char namespace when its colours differ.
    """
    choice = normalize_choice(choice)
    merged: dict[str, str] = {}
    rows: list[list[str]] = []
    size = None

    for kind in KINDS:
        data = load_part(choice[kind], kind)
        if data is None:
            continue
        pal, src = data["palette"], data["rows"]
        if size is None:
            size = (max((len(r) for r in src), default=0), len(src))
            rows = [["." for _ in range(size[0])] for _ in range(size[1])]
        remap = {}
        for ch, hexv in pal.items():
            if merged.get(ch) == hexv:
                remap[ch] = ch
                continue
            free = ch if ch not in merged else next(
                (c for c in _POOL if c not in merged), None)
            if free is None:
                remap[ch] = ch          # out of chars; last resort
                continue
            merged[free] = hexv
            remap[ch] = free
        for y, row in enumerate(src):
            if y >= len(rows):
                break
            for x, ch in enumerate(row):
                if x < len(rows[y]) and ch not in pixel_art.TRANSPARENT_CHARS:
                    rows[y][x] = remap.get(ch, ch)

    if size is None:
        return None
    used = set("".join("".join(r) for r in rows))
    return {"palette": {k: v for k, v in merged.items() if k in used},
            "rows": ["".join(r) for r in rows],
            "symmetry": 2}


_POOL = ("abdefhijlmnopqstuvzABCDEFGHIJKMNOPQSTUVWXYZ0139"
         "!#$%&*+=?@~")


VARIANT_PREFIX = "beyblade:"


def variant_id(choice: dict | None) -> str:
    """Encode a parts selection as an equipped-spinner id.

    The combination travels INSIDE the existing `equipped_spinner` string
    ("beyblade:<bottom>/<top>/<center>") rather than in a new settings field, so
    equipping, persistence and the store's "is this equipped?" checks all keep
    working untouched.
    """
    c = normalize_choice(choice)
    return VARIANT_PREFIX + "/".join(c[k] for k in KINDS)


# Catalog item id -> the design it sells. The original store item keeps its id
# so existing purchases and equips survive its rebuild into three layers.
ITEM_DESIGN = {"spinner_beyblade": "classic",
               **{f"bey_{d}": d for d in DESIGNS if d != "classic"}}


def parse_variant(variant: str | None) -> dict | None:
    """Decode an equipped-spinner id into a parts selection, or None if it is
    not a beyblade.

    Accepts a mixed combination ("beyblade:bottom/top/centre") AND a plain
    catalog item id, which resolves to that design's stock trio — so buying and
    equipping from the store needs no special case, and a save from before the
    rebuild still points at real art.
    """
    if not variant:
        return None
    if variant in ITEM_DESIGN:
        d = ITEM_DESIGN[variant]
        return normalize_choice({k: d for k in KINDS})
    if not variant.startswith(VARIANT_PREFIX):
        return None
    bits = variant[len(VARIANT_PREFIX):].split("/")
    return normalize_choice(dict(zip(KINDS, bits)))


def owned_designs(is_unlocked) -> list[str]:
    """Designs whose parts the player may mix, given an unlock predicate."""
    return [d for d in DESIGNS if is_unlocked(d)]
