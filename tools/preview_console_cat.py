"""Render the Cheshire Cat face to a PNG contact sheet for visual review.

Usage:
    python tools/preview_console_cat.py [--out PATH]

Draws a grid of face variants (gaze positions, mouth frames, blink) exactly as
the compositor produces them — monospace cells, phosphor tier colors, a cheap
4-tap halo behind bright cells to approximate the glow. Headless (offscreen
platform); default output is console_cat_preview.png beside the repo.
"""

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import (  # noqa: E402
    QGuiApplication, QImage, QPainter, QColor, QFont, QFontDatabase,
    QFontMetrics,
)

from techdeck.ui.widgets.console_cat import (  # noqa: E402
    FACE_ART as FACE_GRID, PHOSPHOR, compose_face, summon_frame,
)

BG = "#070B07"
LABEL = "#2FA84F"
HALO_TIERS = {"bright", "peak"}

VARIANTS = [
    ("center / closed", dict(iris=(2, 1), mouth=0)),
    ("gaze left-up / closed", dict(iris=(0, 0), mouth=0)),
    ("gaze right-down / closed", dict(iris=(4, 2), mouth=0)),
    ("blink", dict(blink=True)),
    ("speaking / half", dict(iris=(2, 1), mouth=1)),
    ("speaking / open", dict(iris=(2, 1), mouth=2)),
]

# lids · eyes opening · open wide · seed points · early flower · mid flower
# · late flower · brightening · done
SUMMON_STAGES = [0.10, 0.22, 0.36, 0.42, 0.52, 0.65, 0.78, 0.90, 1.0]
SUMMON_SEED = 7


def render(panels, out_path: Path):
    """panels: list of (label, composed cells) drawn in a 3-wide grid."""
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841
    # The offscreen platform on Windows has no system font lookup — load
    # Consolas straight from the Windows fonts folder or the glyphs render
    # as tofu boxes.
    family = "Consolas"
    consola = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "consola.ttf"
    if consola.is_file():
        font_id = QFontDatabase.addApplicationFont(str(consola))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            family = families[0]
    font = QFont(family, 14)
    font.setStyleHint(QFont.StyleHint.Monospace)
    fm = QFontMetrics(font)
    cw = fm.horizontalAdvance("M")
    chh = fm.height()

    rows, cols = len(FACE_GRID), len(FACE_GRID[0])
    pad = 16
    label_h = 24
    panel_w = cols * cw + pad * 2
    panel_h = rows * chh + pad * 2 + label_h
    grid_cols = 3
    grid_rows = (len(panels) + grid_cols - 1) // grid_cols

    img = QImage(panel_w * grid_cols, panel_h * grid_rows,
                 QImage.Format.Format_RGB32)
    img.fill(QColor(BG))
    p = QPainter(img)
    p.setFont(font)

    for i, (label, cells) in enumerate(panels):
        ox = (i % grid_cols) * panel_w + pad
        oy = (i // grid_cols) * panel_h + pad
        p.setPen(QColor(LABEL))
        p.drawText(ox, oy + fm.ascent(), label)
        oy += label_h
        for r, row in enumerate(cells):
            for c, (ch, tier) in enumerate(row):
                if tier is None:
                    continue
                x = ox + c * cw
                y = oy + r * chh + fm.ascent()
                if tier in HALO_TIERS:
                    halo = QColor(PHOSPHOR[tier])
                    halo.setAlpha(70)
                    p.setPen(halo)
                    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        p.drawText(x + dx, y + dy, ch)
                p.setPen(QColor(PHOSPHOR[tier]))
                p.drawText(x, y, ch)
    p.end()

    img.save(str(out_path))
    print(f"Wrote {out_path} ({img.width()}x{img.height()})")


def main():
    parser = argparse.ArgumentParser(
        description="Render the console cat face variants (and the summon "
                    "compile stages) to PNGs.")
    parser.add_argument("--out", type=Path,
                        default=ROOT / "console_cat_preview.png")
    parser.add_argument("--summon-out", type=Path,
                        default=ROOT / "console_cat_summon.png")
    args = parser.parse_args()
    render([(label, compose_face(**kwargs)) for label, kwargs in VARIANTS],
           args.out)
    final = compose_face()
    render([(f"summon {int(p * 100)}%",
             summon_frame(final, p, seed=SUMMON_SEED))
            for p in SUMMON_STAGES], args.summon_out)


if __name__ == "__main__":
    main()
