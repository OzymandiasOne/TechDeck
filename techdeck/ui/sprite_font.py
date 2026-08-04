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


    def wrap_lines(self, text: str, scale: int = 3, max_width: int = 9999) -> list:
        """Word-wrap `text` into lines that each fit within max_width.

        A word longer than max_width is BROKEN rather than emitted whole. The
        old version accepted the first word of a line unconditionally, so a
        single long word overflowed and the caller's fixed-width label then
        clipped it at BOTH ends -- "FORGEHEART" rendered as "ORGEHEAR". Never
        returning an over-wide line means a label can no longer lose glyphs.
        """
        lines, cur = [], ""
        for word in text.split(" "):
            trial = (cur + " " + word).strip()
            if self.text_width(trial, scale) <= max_width:
                cur = trial
                continue
            if cur:
                lines.append(cur)
                cur = ""
            while self.text_width(word, scale) > max_width and len(word) > 1:
                cut = len(word)
                while cut > 1 and self.text_width(word[:cut], scale) > max_width:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            cur = word
        if cur:
            lines.append(cur)
        return lines or [""]

    def fits(self, text: str, scale: int, max_width: int, max_height: int) -> bool:
        """Would `text` wrap into max_width x max_height at this scale with
        every word left WHOLE? A broken word is treated as not fitting, so the
        caller can try a smaller scale before resorting to a mid-word split."""
        lines = self.wrap_lines(text, scale, max_width)
        words = [w for w in text.split(" ") if w]
        produced = [w for ln in lines for w in ln.split(" ") if w]
        if produced != words:                     # something got broken
            return False
        line_h = GLYPH * scale
        return len(lines) * line_h + scale * (len(lines) - 1) <= max_height

    def render_fitted(self, text: str, scale: int, color: str,
                      max_width: int, max_height: int) -> QPixmap:
        """Render at the largest scale up to `scale` that fits the box with
        whole words. Shrinking a too-long name beats breaking it across lines
        at an arbitrary letter ("TELES/COPE") or clipping it."""
        for sc in range(scale, 0, -1):
            if self.fits(text, sc, max_width, max_height):
                return self.render_wrapped(text, sc, color, max_width)
        return self.render_wrapped(text, 1, color, max_width)

    def render_lines(self, lines, scale: int = 3, color: str = "#ffffff") -> QPixmap:
        """Render pre-wrapped lines, horizontally-centred and stacked vertically."""
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

    def render_wrapped(self, text: str, scale: int = 3, color: str = "#ffffff",
                       max_width: int = 9999) -> QPixmap:
        """Render word-wrapped, horizontally-centred lines stacked vertically."""
        return self.render_lines(self.wrap_lines(text, scale, max_width), scale, color)


_DEFAULT: SpriteFont | None = None


def font() -> SpriteFont:
    """Shared default sprite font (lazy)."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = SpriteFont()
    return _DEFAULT
