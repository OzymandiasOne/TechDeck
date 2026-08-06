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
    FACE_ART as FACE_GRID, PHOSPHOR, compose_face,
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


def render(out_path: Path):
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
    grid_rows = (len(VARIANTS) + grid_cols - 1) // grid_cols

    img = QImage(panel_w * grid_cols, panel_h * grid_rows,
                 QImage.Format.Format_RGB32)
    img.fill(QColor(BG))
    p = QPainter(img)
    p.setFont(font)

    for i, (label, kwargs) in enumerate(VARIANTS):
        ox = (i % grid_cols) * panel_w + pad
        oy = (i // grid_cols) * panel_h + pad
        p.setPen(QColor(LABEL))
        p.drawText(ox, oy + fm.ascent(), label)
        oy += label_h
        cells = compose_face(**kwargs)
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
        description="Render the console cat face variants to a PNG.")
    parser.add_argument("--out", type=Path,
                        default=ROOT / "console_cat_preview.png")
    args = parser.parse_args()
    render(args.out)


if __name__ == "__main__":
    main()
