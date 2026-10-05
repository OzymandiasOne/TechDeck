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

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QAbstractScrollArea, QWidget

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


def draw_new_sticker(p: QPainter, right: float, top: float, scale: int = 2, tilt: float = 9.0):
    """A red pixel box reading NEW!, tilted high-left to low-right, its top-right
    corner near (right, top)."""
    w, h = sticker_box(scale)
    draw_new_sticker_centered(p, right - w * 0.55, top + h * 0.55, scale, tilt)


def draw_new_sticker_centered(p: QPainter, cx: float, cy: float, scale: int = 2, tilt: float = 9.0):
    """The same sticker, its centre at (cx, cy)."""
    from techdeck.ui.arcade_chrome import EMP
    from techdeck.ui.sprite_font import font as _sf
    txt = _sf().render("NEW!", scale, "#ffffff")
    pad_x, pad_y = 5 * scale, 3 * scale
    w, h = txt.width() + 2 * pad_x, txt.height() + 2 * pad_y
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    p.translate(cx, cy)
    p.rotate(tilt)
    box = QRectF(-w / 2, -h / 2, w, h)
    p.fillRect(box.translated(scale, scale), QColor(10, 6, 15, 180))       # the drop shadow
    p.fillRect(box, QColor(EMP["buy"]))
    p.setPen(QPen(QColor("#2a0a0f"), scale)); p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(box)
    p.drawPixmap(int(-txt.width() / 2), int(-txt.height() / 2), txt)
    p.restore()


def sticker_box(scale: int = 2) -> tuple[int, int]:
    """The unrotated box's size for this scale (from the real text width)."""
    from techdeck.ui.sprite_font import font as _sf
    txt = _sf().render("NEW!", scale, "#ffffff")
    return txt.width() + 10 * scale, txt.height() + 6 * scale


class NewSticker(QWidget):
    """An overlay that wears the sticker, centred, with room for its tilt;
    parents place it by its centre."""

    def __init__(self, parent, scale: int = 2, tilt: float = 9.0):
        super().__init__(parent)
        import math
        self.scale, self.tilt = scale, tilt
        w, h = sticker_box(scale)
        c, s_ = math.cos(math.radians(tilt)), math.sin(math.radians(tilt))
        self.W = int(w * c + h * s_) + 12                  # the rotated box, plus a margin all round
        self.H = int(h * c + w * s_) + 12
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedSize(self.W, self.H)
        self.hide()

    def place_center(self, cx: int, cy: int):
        self.move(cx - self.W // 2, cy - self.H // 2)
        self.raise_()

    def paintEvent(self, _e):
        p = QPainter(self)
        draw_new_sticker_centered(p, self.W / 2, self.H / 2, self.scale, self.tilt)
        p.end()


class NewOverlay(QWidget):
    """Stickers for the tiles under one HOST - the scroll view's viewport (or the
    page), not the tile grid - drawn a layer above everything in it, so a
    sticker can hang off a tile's corner and only ever clips at the view's edge.
    Tiles register with `attach_sticker` and answer `wants_new_sticker()`."""

    def __init__(self, host):
        super().__init__(host)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.tiles: list = []
        host.installEventFilter(self)
        self.setGeometry(host.rect())
        area = host.parentWidget()
        if isinstance(area, QAbstractScrollArea) and area.viewport() is host:
            area.verticalScrollBar().valueChanged.connect(lambda _v: self.update())
            area.horizontalScrollBar().valueChanged.connect(lambda _v: self.update())
        self.show()

    def watch(self, tile):
        if tile not in self.tiles:
            self.tiles.append(tile)
        self.raise_()
        self.update()

    def eventFilter(self, obj, event):
        if obj is self.parentWidget() and event.type() in (QEvent.Type.Resize, QEvent.Type.LayoutRequest):
            self.setGeometry(obj.rect())
            self.raise_()
        return False

    def paintEvent(self, _e):
        host = self.parentWidget()
        p = QPainter(self)
        for t in self.tiles:
            try:
                if not t.isVisible() or not t.wants_new_sticker():
                    continue
                g = QRect(t.mapTo(host, QPoint(0, 0)), t.size())
                draw_new_sticker(p, g.right() + 18, g.top() - 2, 2, tilt=22.0)   # off the corner, clear of the button
            except RuntimeError:
                continue                                  # a tile Qt has already deleted
        p.end()


def _sticker_host(widget):
    """The scroll view's viewport the widget sits in, else its top-most ancestor."""
    w = widget.parentWidget()
    while w is not None:
        par = w.parentWidget()
        if par is None or (isinstance(par, QAbstractScrollArea) and par.viewport() is w):
            return w
        w = par
    return None


def attach_sticker(tile):
    """Give the tile's view an overlay (once) and register the tile on it. A
    tile registered earlier on a lower host (its grid box, before the box was
    parented into the view) moves up to the view's overlay."""
    host = _sticker_host(tile)
    if host is None:
        return None
    overlay = getattr(host, "_new_overlay", None)
    if overlay is None:
        overlay = NewOverlay(host)
        host._new_overlay = overlay
    old = getattr(tile, "_new_overlay_owner", None)
    if old is not None and old is not overlay:
        try:
            old.tiles.remove(tile); old.update()
        except (ValueError, RuntimeError):
            pass
    tile._new_overlay_owner = overlay
    overlay.watch(tile)
    return overlay
