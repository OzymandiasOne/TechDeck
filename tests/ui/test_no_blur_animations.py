"""Gate: never animate a QGraphicsDropShadowEffect's SIZE — animate its COLOR.

Animating blurRadius makes Qt re-rasterize the widget into a differently-sized
rect every frame; on fractional Windows display scaling (125%/150%) the
rounding lands on different pixels frame to frame, so the widget visibly
"vibrates" (reported live on the Home Run Selected button, 2026-09-03 — the
same class also sat in the tile hover lift and running pulse). A colour/alpha
animation at constant geometry gives the identical breathe/lift effect and
repaints the same pixels every frame.

One-shot setBlurRadius calls (splash, tile_grid's drag lift) are fine — a
single discrete change is not a per-frame animation. Only ANIMATING the size
is banned.
"""

import re
from pathlib import Path

UI_DIR = Path(__file__).resolve().parents[2] / "techdeck"

# QPropertyAnimation(<target>, b"blurRadius" ...  — the property name is the
# second argument, so a source scan is unambiguous.
_BLUR_ANIM_RE = re.compile(
    r'QPropertyAnimation\([^)]*b"blurRadius"', re.DOTALL)


def test_no_blur_radius_animations_anywhere():
    offenders = []
    for py in UI_DIR.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="replace")
        if _BLUR_ANIM_RE.search(text):
            offenders.append(str(py.relative_to(UI_DIR.parent)))
    assert not offenders, (
        "QPropertyAnimation on b\"blurRadius\" found in: "
        + ", ".join(offenders)
        + " — animating a shadow's SIZE makes widgets shiver on fractional "
          "display scaling. Keep blurRadius fixed and animate the effect's "
          "b\"color\" (alpha) instead; see this test's docstring."
    )
