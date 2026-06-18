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
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QIcon, QPixmap

from techdeck.ui.sprite_font import font as _sf
from techdeck.ui.pages.emporium_page import (
    EMP, CATALOG, _draw_bubble, _load_pixmap, _load_art, _trim_v,
    _tile_ring, _equipped_badge,
)

# Default (themed) spinner thumbnail — drawn in EMP colours so the card matches
# the arcade palette even though /fidget recolours it to the live theme.
_DEFAULT_SPINNER = {
    "body": EMP["frame_a"], "wing": EMP["frame_b"], "ring": "#f0f0ff",
    "highlight": "#ffffff", "outline": "#0c0a1e",
}
# The "use the plain themed spinner" entry — id None clears the equipped variant.
DEFAULT_SPINNER_ITEM = {"id": None, "name": "Default", "kind": "spinner",
                        "sprite": None}


def _default_spinner_icon(target=72):
    try:
        from techdeck.ui.widgets.fidget_spinner import _render_spinner_pixmap
        pm = _render_spinner_pixmap(_DEFAULT_SPINNER)
        return pm.scaled(target, target, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.FastTransformation)
    except Exception:
        return None


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

    def refresh(self):
        s = self.page.settings
        self.name.setPixmap(_sf().render_wrapped(self.item["name"].upper(), 2,
                                                EMP["tile_text"], max_width=self.NAME_W))
        if self.item["kind"] == "spinner":
            self.equipped = (s.get_equipped_spinner() or None) == self.item["id"]
            if self.equipped:
                self._set_btn("EQUIPPED", EMP["equip"], "#7af0a0", False)
            else:
                self._set_btn("EQUIP", EMP["buy"], EMP["buy_lit_edge"], True)
        else:
            self.equipped = False
            self._set_btn("OWNED", EMP["owned"], EMP["owned"], False)
        self.update()

    def mousePressEvent(self, e):
        if self.item["kind"] == "spinner" and not self.equipped:
            self.page.equip(self.item)
        super().mousePressEvent(e)

    def _on_action(self):
        if self.item["kind"] == "spinner" and not self.equipped:
            self.page.equip(self.item)


class MyStuffPage(QWidget):
    """The locker: a header + per-category grids of owned items."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._bg = _load_pixmap("emporium_background.tdart", 128)
        self._bubbles = {"tile": _load_art("bubble_tile.tdart"),
                         "banner": _load_art("bubble_banner.tdart")}
        self._title = _trim_v(_sf().render("MY STUFF", 4, EMP["neon_on"]))

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        self.banner = QLabel()
        self.banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.banner.setStyleSheet("background: transparent; border: none;")
        self.banner.setFixedSize(self._title.width() + 44, self._title.height() + 22)
        self.banner.setPixmap(self._title)
        bar = QHBoxLayout()
        bar.addWidget(self.banner)
        bar.addStretch()
        root.addLayout(bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.scroll.viewport().setStyleSheet("background: transparent;")
        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._vbox = QVBoxLayout(self._content)
        self._vbox.setContentsMargins(4, 4, 4, 4)
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

        # Future: a "Friends" section (summoned with /friend) slots in here.
        self._vbox.addStretch(1)

    def refresh(self):
        # Ownership can change (a purchase in the Emporium), so rebuild the grids.
        self._build()

    # ---- equip ---------------------------------------------------------------
    def equip(self, item):
        self.settings.set_equipped_spinner(item["id"])
        for t in self.tiles:
            t.refresh()

    # ---- background ----------------------------------------------------------
    def paintEvent(self, _evt):
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(EMP["wall"]))
        if self._bg is not None:
            from PySide6.QtCore import QRect
            p.drawPixmap(QRect(0, 0, w, h), self._bg)
        _draw_bubble(p, self.banner.geometry(), self._bubbles["banner"],
                     shadow=EMP["shadow"])
        p.end()
