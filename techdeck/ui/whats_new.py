"""The "NEW!" stickers - how a player discovers what has quietly appeared.

One function decides WHERE a sticker shows (`new_badges`), from the settings
and the season, so every page asks the same question:

    account      the sidebar's My Account entry - until My Stuff has been opened
    my_stuff     the My Stuff tab                - until the Puppet Master's table has been played
    puppet       the Puppet Master cartridge     - until the table has been played
    decorations  the Emporium's Decorations tab  - until the Ghost is bought
    ghost        the Ghost on the shelf          - until the Ghost is bought

The sticker itself is drawn by `draw_new_sticker` (a tilted red pixel box, white
"NEW!" in the sprite font) and worn by `NewSticker`, a mouse-transparent overlay
for widgets that are not custom-painted (a tab bar, a sidebar button).
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from techdeck.core.constants import halloween_active, puppet_master_enabled

PUPPET_ID = "game_puppet_master"
GHOST_ID = "deco_ghost"

ACCOUNT, MY_STUFF, PUPPET, DECORATIONS, GHOST = "account", "my_stuff", "puppet", "decorations", "ghost"


def new_badges(settings) -> set[str]:
    """Which NEW! stickers show right now."""
    out: set[str] = set()
    puppet_new = puppet_master_enabled() and not settings.is_unlocked(PUPPET_ID)
    ghost_new = halloween_active(settings=settings) and not settings.is_unlocked(GHOST_ID)
    if puppet_new:
        out |= {MY_STUFF, PUPPET}
    if ghost_new:
        out |= {DECORATIONS, GHOST}
    if (puppet_new or ghost_new) and not settings.has_seen_my_stuff():
        out.add(ACCOUNT)
    return out


def draw_new_sticker(p: QPainter, right: float, top: float, scale: int = 2, tilt: float = -9.0):
    """A tilted red pixel box reading NEW!, its top-right corner near (right, top)."""
    from techdeck.ui.arcade_chrome import EMP
    from techdeck.ui.sprite_font import font as _sf
    txt = _sf().render("NEW!", scale, "#ffffff")
    pad_x, pad_y = 5 * scale, 3 * scale
    w, h = txt.width() + 2 * pad_x, txt.height() + 2 * pad_y
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    p.translate(right - w * 0.55, top + h * 0.55)
    p.rotate(tilt)
    box = QRectF(-w / 2, -h / 2, w, h)
    p.fillRect(box.translated(scale, scale), QColor(10, 6, 15, 180))       # the drop shadow
    p.fillRect(box, QColor(EMP["buy"]))
    p.setPen(QPen(QColor("#2a0a0f"), scale)); p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(box)
    p.drawPixmap(int(-txt.width() / 2), int(-txt.height() / 2), txt)
    p.restore()


class NewSticker(QWidget):
    """An overlay that wears the sticker at its own top-right; parents place it."""

    def __init__(self, parent, scale: int = 2):
        super().__init__(parent)
        self.scale = scale
        self.W, self.H = 34 * scale + 14, 14 * scale + 10
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedSize(self.W, self.H)
        self.hide()

    def place(self, right: int, top: int):
        self.move(right - self.W, top)
        self.raise_()

    def paintEvent(self, _e):
        p = QPainter(self)
        draw_new_sticker(p, self.W - 4, 4, self.scale)
        p.end()
