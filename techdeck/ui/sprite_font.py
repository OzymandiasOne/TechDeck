"""
UFO50 sprite-font renderer.

The UFO50 fonts ship as one 8x8 PNG per glyph (a GameMaker sprite font), not a
.ttf/.otf, so Qt can't load them as a QFont. This renders a string by blitting
those glyph PNGs, tinted to any colour, with proportional spacing.

Glyphs live in assets/fonts/sFontDefaultNoShadow/ as `<base>_<n>.png`, where the
frame index maps to a character by `n = ord(char) - 32` (frame 0 = space).
"""

import sys
from pathlib import Path

from PySide6.QtGui import QImage, QPixmap, QPainter, QColor
from PySide6.QtCore import Qt, QRect

GLYPH = 8           # native glyph cell size (px)
_FIRST = 32         # frame 0 == ASCII 32 (space)
_LETTER_SPACING = 1  # native px between glyphs


def _fonts_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets" / "fonts"
    return Path(__file__).resolve().parents[2] / "assets" / "fonts"


class SpriteFont:
    """Loads + caches a UFO50 sprite font and renders tinted text to pixmaps."""

    def __init__(self, base="sFontDefaultNoShadow"):
        self.base = base
        self.dir = _fonts_dir() / base
        self._glyphs: dict[int, QImage] = {}
        self._advance: dict[int, int] = {}

    def _glyph(self, ch: str):
        idx = ord(ch) - _FIRST
        if idx < 0:
            return None, GLYPH // 2
        if idx not in self._glyphs:
            im = QImage(str(self.dir / f"{self.base}_{idx}.png"))
            self._glyphs[idx] = None if im.isNull() else im
            self._advance[idx] = self._compute_advance(im, ch)
        return self._glyphs[idx], self._advance[idx]

    @staticmethod
    def _compute_advance(im: QImage, ch: str) -> int:
        """Proportional advance: width of the inked part + letter spacing.
        (No GameMaker metadata ships, so derive it from the alpha.)"""
        if im is None or im.isNull():
            return GLYPH // 2 + _LETTER_SPACING
        if ch == " ":
            return GLYPH // 2 + _LETTER_SPACING
        right = 0
        for x in range(im.width()):
            for y in range(im.height()):
                if QColor(im.pixelColor(x, y)).alpha() > 0:
                    right = max(right, x)
                    break
        return right + 1 + _LETTER_SPACING

    def text_width(self, text: str, scale: int = 1) -> int:
        return sum(self._glyph(c)[1] for c in text) * scale

    def render(self, text: str, scale: int = 3, color: str = "#ffffff") -> QPixmap:
        """Render `text` to a tinted, transparent-background pixmap."""
        w = max(1, self.text_width(text, scale))
        pm = QPixmap(w, GLYPH * scale)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        col = QColor(color)
        x = 0
        for ch in text:
            im, adv = self._glyph(ch)
            if im is not None:
                gw = im.width() * scale
                p.drawImage(QRect(x, 0, gw, im.height() * scale), im)
            x += adv * scale
        # Tint: recolour every inked pixel to `color`, preserving the alpha shape.
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        p.fillRect(pm.rect(), col)
        p.end()
        return pm


    def render_wrapped(self, text: str, scale: int = 3, color: str = "#ffffff",
                       max_width: int = 9999) -> QPixmap:
        """Render word-wrapped, horizontally-centred lines stacked vertically."""
        lines, cur = [], ""
        for word in text.split(" "):
            trial = (cur + " " + word).strip()
            if not cur or self.text_width(trial, scale) <= max_width:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        pms = [self.render(ln, scale, color) for ln in lines] or [self.render("", scale, color)]
        gap = scale
        W = max(p.width() for p in pms)
        H = sum(p.height() for p in pms) + gap * (len(pms) - 1)
        out = QPixmap(max(W, 1), max(H, 1))
        out.fill(Qt.GlobalColor.transparent)
        p = QPainter(out)
        y = 0
        for pm in pms:
            p.drawPixmap((W - pm.width()) // 2, y, pm)
            y += pm.height() + gap
        p.end()
        return out


_DEFAULT: SpriteFont | None = None


def font() -> SpriteFont:
    """Shared default sprite font (lazy)."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = SpriteFont()
    return _DEFAULT
