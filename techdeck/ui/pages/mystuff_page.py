"""
My Stuff — the player's inventory / locker.

Shows everything bought at Woogy's Emporium and lets you EQUIP the selectable
items (right now: fidget spinners — pick which one /fidget pops). Same fixed
arcade palette + UFO50 sprite font + 9-slice word-bubble chrome as the Emporium,
so the two read as one world.

Extensible by design: items are grouped into category SECTIONS keyed off the
catalog's "kind". New equippable categories slot in here — e.g. the planned
"friends" (summoned with /friend) — and a future "My House" tab will read the
same owned-items list to place decorations.
"""

from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QFrame, QScrollArea,
)
from PySide6.QtCore import Qt, QPoint, QRect
from PySide6.QtGui import QPainter, QColor, QIcon, QPixmap, QImage

from techdeck.ui.sprite_font import font as _sf
from techdeck.ui.pages.emporium_page import (
    EMP, CATALOG, _draw_bubble, _load_pixmap, _load_art, _trim_v,
    _tile_ring, _equipped_badge,
)

# The diagonal-stripe wall, as a SEAMLESS tile so it fills the whole page (and
# repeats as the locker scrolls) instead of the old stretched art whose solid
# "floor" band showed through the bottom. Colours sampled from the Emporium wall.
_WALL_BASE = EMP["wall"]      # "#272273"
_WALL_STRIPE = "#3b34c0"


def _wall_tile(scale=8):
    """A P*scale square that tiles seamlessly: a 1px diagonal line every P px.
    ((x+y) % P) is phase-stable across tile borders, so drawTiledPixmap is gapless."""
    P, lw = 12, 1
    img = QImage(P, P, QImage.Format.Format_RGB32)
    img.fill(QColor(_WALL_BASE))
    stripe = QColor(_WALL_STRIPE)
    for y in range(P):
        for x in range(P):
            if (x + y) % P < lw:
                img.setPixelColor(x, y, stripe)
    return QPixmap.fromImage(img).scaled(
        P * scale, P * scale, Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.FastTransformation)

# Default (themed) spinner thumbnail — drawn in EMP colours so the card matches
# the arcade palette even though /fidget recolours it to the live theme.
_DEFAULT_SPINNER = {
    "body": EMP["frame_a"], "wing": EMP["frame_b"], "ring": "#f0f0ff",
    "highlight": "#ffffff", "outline": "#0c0a1e",
}
# The "use the plain themed spinner" entry — id None clears the equipped variant.
DEFAULT_SPINNER_ITEM = {"id": None, "name": "Default", "kind": "spinner",
                        "sprite": None}
# The free default wallpaper (sLibraryBG_4) — always available to re-equip.
DEFAULT_BACKGROUND_ITEM = {"id": "bg_default", "name": "Red Check",
                           "kind": "background", "sprite": "sLibraryBG_4.png"}


def _default_spinner_icon(target=72):
    try:
        from techdeck.ui.widgets.fidget_spinner import _render_spinner_pixmap
        pm = _render_spinner_pixmap(_DEFAULT_SPINNER)
        return pm.scaled(target, target, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.FastTransformation)
    except Exception:
        return None


class _HeaderBox(QWidget):
    """A full-width, opaque STICKY header. It paints the wall across its width (so
    it's invisible against the page wall) with the MY STUFF box on the left, and
    sits above the scroll — so locker content cleanly disappears under it as you
    scroll, instead of tiles overlapping/peeking beside the box. Sized to leave
    the vertical scrollbar exposed so it still starts at the top."""

    box_w = 0
    box_h = 0

    def __init__(self, page, title_pm):
        super().__init__(page)
        self.page = page
        self._title = title_pm
        self.box_w = title_pm.width() + 44
        self.box_h = title_pm.height() + 22

    def paintEvent(self, _e):
        p = QPainter(self)
        wall = self.page._wall
        if wall is not None:
            # Continue the page's wall tiling in phase, so it reads as one wall.
            p.drawTiledPixmap(self.rect(), wall,
                              QPoint(self.x() % wall.width(), self.y() % wall.height()))
        else:
            p.fillRect(self.rect(), QColor(_WALL_BASE))
        box = QRect(16, 0, self.box_w, self.box_h)
        _draw_bubble(p, box.adjusted(0, 0, -1, -1),
                     self.page._bubbles["banner"], shadow=EMP["shadow"])
        p.drawPixmap(box.x() + (self.box_w - self._title.width()) // 2,
                     box.y() + (self.box_h - self._title.height()) // 2, self._title)
        p.end()


class InventoryTile(QFrame):
    """One owned item: icon + name + an EQUIP/EQUIPPED (or OWNED) action. Mirrors
    the Emporium StoreTile look so the locker feels like the same shelf."""

    SIZE = 150
    HEIGHT = 200
    GAP = 16
    NAME_H = 52
    NAME_W = 126

    def __init__(self, item, page):
        super().__init__()
        self.item = item
        self.page = page
        self.equipped = False
        self.setFixedSize(self.SIZE, self.HEIGHT)
        self.setStyleSheet("InventoryTile { background: transparent; }")

        if item["sprite"]:
            self._icon = _load_pixmap(item["sprite"], 72)
        else:
            self._icon = _default_spinner_icon(72)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(0)

        self.action_btn = QPushButton()
        self.action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action_btn.setFixedHeight(30)
        self.action_btn.clicked.connect(self._on_action)

        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon.setStyleSheet("background: transparent; border: none;")
        self.icon.setFixedHeight(76)
        if self._icon is not None:
            self.icon.setPixmap(self._icon)

        self.name = QLabel()
        self.name.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.name.setStyleSheet("background: transparent; border: none;")
        self.name.setFixedHeight(self.NAME_H)

        lay.addStretch(1)
        lay.addWidget(self.action_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(self.GAP)
        lay.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(self.GAP)
        lay.addWidget(self.name, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(1)
        self.refresh()

    def paintEvent(self, _e):
        p = QPainter(self)
        rect = self.rect().adjusted(0, 0, -5, -5)
        _draw_bubble(p, rect, self.page._bubbles["tile"], shadow=EMP["shadow"])
        _tile_ring(p, rect, EMP["ring"])     # the ring now frames every tile
        if self.equipped:                    # equipped -> gold star badge
            _equipped_badge(p, rect)
        p.end()

    def _btn_qss(self, bg, edge):
        return (f"QPushButton {{ background:{bg}; border:2px solid {edge}; "
                f"border-radius:5px; padding:3px 10px; }}"
                f"QPushButton:disabled {{ background:#37335a; border-color:#4a466e; }}")

    def _set_btn(self, label, bg, edge, enabled):
        pm = _sf().render(label, 2, EMP["btn_text"])
        self.action_btn.setText("")
        self.action_btn.setIcon(QIcon(pm))
        self.action_btn.setIconSize(pm.size())
        self.action_btn.setEnabled(enabled)
        self.action_btn.setStyleSheet(self._btn_qss(bg, edge))

    def _is_equipped(self, s):
        k = self.item["kind"]
        if k == "spinner":
            return (s.get_equipped_spinner() or None) == self.item["id"]
        if k == "background":
            return s.get_equipped_background() == self.item["sprite"]
        return False

    def refresh(self):
        s = self.page.settings
        self.name.setPixmap(_sf().render_wrapped(self.item["name"].upper(), 2,
                                                EMP["tile_text"], max_width=self.NAME_W))
        if self.item["kind"] in ("spinner", "background"):
            self.equipped = self._is_equipped(s)
            if self.equipped:
                self._set_btn("EQUIPPED", EMP["equip"], "#7af0a0", False)
            else:
                self._set_btn("EQUIP", EMP["buy"], EMP["buy_lit_edge"], True)
        else:
            self.equipped = False
            self._set_btn("OWNED", EMP["owned"], EMP["owned"], False)
        self.update()

    def mousePressEvent(self, e):
        if self.item["kind"] in ("spinner", "background") and not self.equipped:
            self.page.equip(self.item)
        super().mousePressEvent(e)

    def _on_action(self):
        if self.item["kind"] in ("spinner", "background") and not self.equipped:
            self.page.equip(self.item)


class MyStuffPage(QWidget):
    """The locker: a header + per-category grids of owned items."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._wall = _wall_tile()
        self._bubbles = {"tile": _load_art("bubble_tile.tdart"),
                         "banner": _load_art("bubble_banner.tdart")}
        self._title = _trim_v(_sf().render("MY STUFF", 4, EMP["neon_on"]))

        # Scroll fills the whole page so its scrollbar runs from the very top,
        # aligned with the MY STUFF box; the banner floats over the top-left.
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 14, 0, 0)
        root.setSpacing(0)

        self._banner_h = self._title.height() + 22
        # Opaque sticky header floating over the top-left of the scroll.
        self.banner = _HeaderBox(self, self._title)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.scroll.viewport().setStyleSheet("background: transparent;")
        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._vbox = QVBoxLayout(self._content)
        # Top margin clears the floating banner; sections start just below it.
        self._vbox.setContentsMargins(20, self._banner_h + 18, 20, 14)
        self._vbox.setSpacing(10)
        self.scroll.setWidget(self._content)
        root.addWidget(self.scroll, 1)

        self.tiles = []
        self._build()

    # ---- build / refresh -----------------------------------------------------
    def _section_header(self, text):
        lbl = QLabel()
        lbl.setStyleSheet("background: transparent; border: none;")
        lbl.setPixmap(_trim_v(_sf().render(text.upper(), 3, EMP["ticket"])))
        return lbl

    def _grid(self, items):
        host = QWidget()
        host.setStyleSheet("background: transparent;")
        grid = QGridLayout(host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        cols = 5
        for i, item in enumerate(items):
            tile = InventoryTile(item, self)
            self.tiles.append(tile)
            grid.addWidget(tile, i // cols, i % cols,
                           Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        grid.setColumnStretch(cols, 1)
        return host

    def _hint(self, text):
        lbl = QLabel()
        lbl.setStyleSheet("background: transparent; border: none;")
        lbl.setPixmap(_sf().render_wrapped(text.upper(), 2, EMP["tile_dim"],
                                          max_width=520))
        return lbl

    def _build(self):
        # Clear any previous build (rebuilt when ownership changes).
        while self._vbox.count():
            item = self._vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.tiles = []

        s = self.settings
        owned_spinners = [c for c in CATALOG
                          if c["kind"] == "spinner" and s.is_unlocked(c["id"])]
        owned_games = [c for c in CATALOG
                       if c["kind"] == "game" and s.is_unlocked(c["id"])]

        # Fidget spinners (always: the Default option + any you own).
        self._vbox.addWidget(self._section_header("Fidget Spinners"))
        self._vbox.addWidget(self._grid([DEFAULT_SPINNER_ITEM] + owned_spinners))
        if not owned_spinners:
            self._vbox.addWidget(self._hint(
                "Buy spinners at Woogy's Emporium to add them here."))

        # Games (owned only).
        if owned_games:
            self._vbox.addWidget(self._section_header("Games"))
            self._vbox.addWidget(self._grid(owned_games))

        owned_furniture = [c for c in CATALOG
                           if c["kind"] == "furniture" and s.is_unlocked(c["id"])]
        owned_friends = [c for c in CATALOG
                         if c["kind"] == "friends" and s.is_unlocked(c["id"])]

        # Furniture (decorations you've bought for My House).
        self._vbox.addWidget(self._section_header("Furniture"))
        if owned_furniture:
            self._vbox.addWidget(self._grid(owned_furniture))
        else:
            self._vbox.addWidget(self._hint(
                "Buy furniture at Woogy's Emporium (Decorations) to fill your house."))

        # Backgrounds (the free default + any bought) — equip sets the My House
        # wallpaper.
        owned_backgrounds = [c for c in CATALOG
                             if c["kind"] == "background" and s.is_unlocked(c["id"])]
        self._vbox.addWidget(self._section_header("Backgrounds"))
        self._vbox.addWidget(self._grid([DEFAULT_BACKGROUND_ITEM] + owned_backgrounds))

        # Friends (none yet — the category is Coming Soon at Woogy's).
        self._vbox.addWidget(self._section_header("Friends"))
        if owned_friends:
            self._vbox.addWidget(self._grid(owned_friends))
        else:
            self._vbox.addWidget(self._hint(
                "Friends are coming soon to Woogy's Emporium!"))

        self._vbox.addStretch(1)

    def refresh(self):
        # Ownership can change (a purchase in the Emporium), so rebuild the grids.
        self._build()

    # ---- equip ---------------------------------------------------------------
    def equip(self, item):
        if item["kind"] == "background":
            self.settings.set_equipped_background(item["sprite"])
        else:
            self.settings.set_equipped_spinner(item["id"])
        for t in self.tiles:
            t.refresh()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # Full-width sticky header at the scroll's top, but stop short of the
        # vertical scrollbar so it stays exposed and starts at the top too.
        sb_w = self.scroll.verticalScrollBar().sizeHint().width()
        self.banner.setGeometry(0, 14, max(self.banner.box_w + 16, self.width() - sb_w),
                                self.banner.box_h)
        self.banner.raise_()

    # ---- background ----------------------------------------------------------
    def paintEvent(self, _evt):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(_WALL_BASE))
        # Tiled diagonal wall fills the whole page and repeats as the locker
        # scrolls — no more solid "floor" band at the bottom. (The MY STUFF box
        # paints itself as an opaque sticky header — see _HeaderBox.)
        if self._wall is not None:
            p.drawTiledPixmap(self.rect(), self._wall)
        p.end()
