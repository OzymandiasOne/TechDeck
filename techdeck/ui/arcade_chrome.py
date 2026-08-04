"""
Arcade chrome — the shared pixel-art look of the ticket-economy pages.

The Emporium, Achievements, and My Stuff pages all draw the same arcade-prize-
counter chrome: the EMP palette, 9-slice word-bubble panels, inset tile rings,
the equipped-star badge, marquee bulbs, sprite-font pixmap helpers, and the
frameless PixelDialog message box. This module is that shared layer — pages
import it instead of reaching into each other's privates.

Sprites are editable .tdart files (assets/sprites/, repaintable in the Pixel
Studio or tools/pixel_editor.py); PNG furniture/backgrounds live in
assets/garden.
"""

import math
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QDialog,
)
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QPainter, QColor, QPolygon, QIcon, QPixmap, QImage

from techdeck.ui import pixel_art
from techdeck.ui.sprite_font import font as _sf


def _sprites_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets" / "sprites"
    return Path(__file__).resolve().parents[2] / "assets" / "sprites"


def _garden_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets" / "garden"
    return Path(__file__).resolve().parents[2] / "assets" / "garden"


EMP = {
    "panel": "#2a1644", "neon_on": "#7ef9ff", "neon_off": "#2b6b73",
    "frame_a": "#37c9da", "frame_b": "#cf3597", "ticket": "#f4c430",
    "tile_bg": "#1c1850", "buy": "#c42a34", "buy_edge": "#ff7a3f",
    "equip": "#2bb04a", "owned": "#7a3fb0", "screen": "#0a0a18",
    "wall": "#272273", "bulb_on": "#fff07a", "bulb_off": "#6a5a1a",
    "dialogue": "#0a0a12", "dialogue_text": "#f4f4ec", "btn_text": "#ffffff",
    "tile_text": "#f0f0ff", "shadow": "#05030f",
    # BUY button: lit (affordable) vs dim (can't afford yet)
    "buy_lit_edge": "#ffb14a", "buy_dim": "#46202a", "buy_dim_edge": "#6e3038",
    "buy_dim_text": "#9c8088",
    # purchased/owned look
    "tile_dim": "#6a6488", "sold_band": "#0a060f",
    # default inset ring that frames every item tile (store + My Stuff)
    "ring": "#2bb04a",
}


def _load_pixmap(name: str, target: int):
    # PNG sprites (Garden furniture + backgrounds) load straight from assets/garden;
    # .tdart sprites go through pixel_art.
    if name.lower().endswith(".png"):
        pm = QPixmap(str(_garden_dir() / name))
        if pm.isNull():
            return None
        w, h = pm.width(), pm.height()
        if max(w, h) >= 200:   # a full 384x216 background -> small thumbnail swatch
            return pm.scaledToWidth(112, Qt.TransformationMode.SmoothTransformation)
        if max(w, h) > target:  # bigger than the icon (e.g. the tree) -> fit by height
            return pm.scaledToHeight(target, Qt.TransformationMode.SmoothTransformation)
        scale = max(1, round(target / max(w, h, 1)))   # tiny furniture -> upscale crisp
        return pm.scaled(w * scale, h * scale,
                         Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.FastTransformation)
    # "beyblade/<design>" is not a file: a beyblade ships as three separate
    # part sprites and its preview is composed from them, so the store never
    # needs a flattened copy of art that exists only as layers.
    if name.startswith("beyblade/"):
        from techdeck.ui import beyblade as _bb
        design = name.split("/", 1)[1]
        data = _bb.compose({k: design for k in _bb.KINDS})
        if data is None:
            return None
        w, h = pixel_art.dimensions(data)
        return pixel_art.render(data, scale=max(1, math.ceil(target / max(w, h, 1))))
    try:
        data = pixel_art.load(_sprites_dir() / name)
    except Exception:
        return None
    w, h = pixel_art.dimensions(data)
    scale = max(1, math.ceil(target / max(w, h, 1)))
    return pixel_art.render(data, scale=scale)


# The plain themed fidget spinner (EMP palette) — used as the Toys category icon.
_DEFAULT_SPINNER_COLORS = {
    "body": EMP["frame_a"], "wing": EMP["frame_b"], "ring": "#f0f0ff",
    "highlight": "#ffffff", "outline": "#0c0a1e",
}


def _default_spinner_pixmap(target):
    try:
        from techdeck.ui.widgets.fidget_spinner import _render_spinner_pixmap
        pm = _render_spinner_pixmap(_DEFAULT_SPINNER_COLORS)
        return pm.scaled(target, target, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.FastTransformation)
    except Exception:
        return None


def _brighten(pm, factor=1.3):
    """Lighten a pixmap's colours (multiply RGB, clamped) — leaves alpha alone."""
    if pm is None:
        return None
    img = pm.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha() == 0:
                continue
            c.setRed(min(255, int(c.red() * factor)))
            c.setGreen(min(255, int(c.green() * factor)))
            c.setBlue(min(255, int(c.blue() * factor)))
            img.setPixelColor(x, y, c)
    return QPixmap.fromImage(img)


def _trim_v(pm):
    """Crop fully-transparent rows off the top/bottom of a text pixmap. The
    sprite font renders into a fixed 8px cell, so the letter ink sits low in the
    pixmap; trimming lets AlignCenter actually centre the visible text."""
    img = pm.toImage()
    w, h = img.width(), img.height()
    if w == 0 or h == 0:
        return pm

    def row_empty(y):
        return all((img.pixel(x, y) >> 24) == 0 for x in range(w))

    top = 0
    while top < h and row_empty(top):
        top += 1
    bot = h - 1
    while bot > top and row_empty(bot):
        bot -= 1
    if top == 0 and bot == h - 1:
        return pm
    return pm.copy(0, top, w, bot - top + 1)


def _ascii(s):
    """Map the few smart-punctuation chars we use to ASCII the sprite font has
    glyphs for, then drop anything else (em-dash etc. has no glyph)."""
    for a, b in (("—", "-"), ("–", "-"), ("’", "'"),
                 ("‘", "'"), ("“", '"'), ("”", '"')):
        s = s.replace(a, b)
    return s.encode("ascii", "ignore").decode()


def _greyed(pm):
    """A desaturated, dimmed copy of a pixmap — the 'already bought' look."""
    if pm is None:
        return None
    img = pm.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha() == 0:
                continue
            g = int(0.30 * c.red() + 0.59 * c.green() + 0.11 * c.blue())
            g = min(255, int(g * 0.55 + 45))   # desaturate + dim
            img.setPixelColor(x, y, QColor(g, g, g, int(c.alpha() * 0.85)))
    return QPixmap.fromImage(img)


def _load_art(name):
    """Load a .tdart sprite dict (for 9-slice bubbles); None if missing."""
    try:
        return pixel_art.load(_sprites_dir() / name)
    except Exception:
        return None


def _draw_bubble(p, rect, sprite, *, shadow=None, offset=(3, 4), alpha=0.45):
    """Render a 9-slice word-bubble sprite to fit `rect` (corners crisp, middle
    stretched), under an optional soft drop shadow taken from the bubble's own
    silhouette — so the shadow always matches whatever the .tdart is repainted
    to. Bubbles live in assets/sprites/bubble_*.tdart and are editable in the
    pixel editor."""
    if sprite is None:
        return
    pix = pixel_art.render_nine_slice(sprite, rect.width(), rect.height())
    if shadow is not None:
        sh = QPixmap(pix.size())
        sh.fill(Qt.GlobalColor.transparent)
        qp = QPainter(sh)
        qp.drawPixmap(0, 0, pix)
        qp.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        qp.fillRect(sh.rect(), QColor(shadow))
        qp.end()
        prev = p.opacity()
        p.setOpacity(alpha)
        p.drawPixmap(rect.x() + offset[0], rect.y() + offset[1], sh)
        p.setOpacity(prev)
    p.drawPixmap(rect.x(), rect.y(), pix)


def _tile_ring(p, rect, color, inset=4, thick=2):
    """The crisp inset rectangular ring that frames every item tile (store + My
    Stuff). Drawn just inside the bubble border for a clean arcade-cabinet look."""
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    c = QColor(color)
    p.fillRect(x + inset, y + inset, w - 2 * inset, thick, c)
    p.fillRect(x + inset, y + h - inset - thick, w - 2 * inset, thick, c)
    p.fillRect(x + inset, y + inset, thick, h - 2 * inset, c)
    p.fillRect(x + w - inset - thick, y + inset, thick, h - 2 * inset, c)


def _equipped_badge(p, rect):
    """The 'this one is equipped' marker: a gold star medallion in the
    bottom-right corner (clear of the wide action button up top). Distinct from
    the default tile ring (which now frames every tile)."""
    cx = rect.x() + rect.width() - 17
    cy = rect.y() + rect.height() - 17
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#0c0a1e"))
    p.drawEllipse(QPoint(cx, cy), 12, 12)
    p.setBrush(QColor(EMP["equip"]))
    p.drawEllipse(QPoint(cx, cy), 10, 10)
    pts = []
    for i in range(10):
        r = 8 if i % 2 == 0 else 3.4
        a = -math.pi / 2 + i * math.pi / 5
        pts.append(QPoint(int(round(cx + r * math.cos(a))),
                          int(round(cy + r * math.sin(a)))))
    p.setBrush(QColor(EMP["ticket"]))
    p.drawPolygon(QPolygon(pts))


def _marquee(p, rect, phase):
    """Chasing marquee bulbs evenly spaced just inside the rect perimeter."""
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    pts, step = [], 13
    for bx in range(x + 7, x + w - 6, step):
        pts.append((bx, y + 4)); pts.append((bx, y + h - 5))
    for by in range(y + 12, y + h - 10, step):
        pts.append((x + 4, by)); pts.append((x + w - 5, by))
    for idx, (bx, by) in enumerate(pts):
        on = (idx - phase) % 3 == 0
        p.fillRect(bx - 1, by - 1, 3, 3,
                   QColor(EMP["bulb_on"] if on else EMP["bulb_off"]))


class _SoldStamp(QWidget):
    """A diagonal 'SOLD' banner drawn ON TOP of a purchased tile (the icon and
    name underneath are greyed by the tile)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()

    def paintEvent(self, _e):
        p = QPainter(self)
        w, h = self.width() - 5, self.height() - 5   # stay within the card
        txt = _trim_v(_sf().render("SOLD", 4, "#ffffff"))
        p.translate(w / 2, h / 2)
        p.rotate(-28)
        band = txt.height() + 14
        p.fillRect(-w, -band // 2, 2 * w, band, QColor(10, 6, 15, 175))
        p.fillRect(-w, -band // 2, 2 * w, 3, QColor(EMP["buy"]))
        p.fillRect(-w, band // 2 - 3, 2 * w, 3, QColor(EMP["buy"]))
        p.drawPixmap(-txt.width() // 2, -txt.height() // 2, txt)
        p.end()


class PixelDialog(QDialog):
    """A small frameless pixel-art message box — a dialogue bubble with text in
    the UFO50 sprite font and a pixel OK button. Used instead of QMessageBox so
    the arcade aesthetic isn't broken. Call PixelDialog.show_message(...)."""

    WIDTH = 440

    def __init__(self, parent, title, body, ok_label="OK"):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self._bubble = _load_art("bubble_dialogue.tdart")

        pad = 24
        inner = self.WIDTH - 2 * pad
        self._title_pm = (_trim_v(_sf().render(_ascii(title).upper(), 3, EMP["neon_on"]))
                          if title else None)
        self._body_pm = _sf().render_wrapped(_ascii(body).upper(), 2,
                                             EMP["dialogue_text"], max_width=inner)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(pad, pad, pad, 18)
        lay.setSpacing(0)
        self._title_gap = 12
        text_h = self._body_pm.height()
        if self._title_pm is not None:
            text_h += self._title_pm.height() + self._title_gap
        lay.addSpacing(text_h)
        lay.addSpacing(16)
        btn = QPushButton()
        bpm = _sf().render(ok_label, 2, EMP["btn_text"])
        btn.setIcon(QIcon(bpm)); btn.setIconSize(bpm.size()); btn.setText("")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(30)
        btn.setStyleSheet(
            f"QPushButton {{ background:{EMP['buy']}; border:2px solid "
            f"{EMP['buy_lit_edge']}; border-radius:5px; padding:3px 18px; }}")
        btn.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(); row.addWidget(btn); row.addStretch()
        lay.addLayout(row)
        self.setFixedWidth(self.WIDTH)

    def paintEvent(self, _e):
        p = QPainter(self)
        _draw_bubble(p, self.rect().adjusted(0, 0, -1, -1), self._bubble,
                     shadow=EMP["shadow"])
        y = 24
        if self._title_pm is not None:
            p.drawPixmap((self.width() - self._title_pm.width()) // 2, y, self._title_pm)
            y += self._title_pm.height() + self._title_gap
        p.drawPixmap((self.width() - self._body_pm.width()) // 2, y, self._body_pm)
        p.end()

    def showEvent(self, e):
        super().showEvent(e)
        par = self.parent()
        if par is not None:
            c = par.window().geometry().center()
            self.move(c.x() - self.width() // 2, c.y() - self.height() // 2)

    @classmethod
    def show_message(cls, parent, title, body, ok_label="OK"):
        cls(parent, title, body, ok_label).exec()
