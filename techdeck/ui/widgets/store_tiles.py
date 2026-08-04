"""
Store widgets for Woogy's Emporium — the purchasable tile, the category box,
and the floating shop window. Extracted siblings of EmporiumPage: each takes a
`page` back-reference (the EmporiumPage) for settings, the shared 9-slice
bubble sprites, and the purchase/select handlers.
"""

from PySide6.QtWidgets import (
    QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QIcon

from techdeck.ui.arcade_chrome import (
    EMP, _SoldStamp, _draw_bubble, _equipped_badge, _greyed, _load_art,
    _load_pixmap, _tile_ring, _trim_v,
)
from techdeck.ui.sprite_font import font as _sf


class StoreTile(QFrame):
    """One purchasable tile drawn as a pixel-art box: icon + name + button. All
    tiles are a fixed size so the grid is uniform; the icon is centred with equal
    spacing to the button above and the name below."""

    SIZE = 164          # width — wide enough for a 9-letter name at scale 2
    HEIGHT = 216        # uniform height (so 1-line and 3-line names match)
    GAP = 16            # equal gap above/below the icon
    NAME_H = 52         # reserves up to 3 wrapped lines @ scale 2
    NAME_W = 148

    def __init__(self, item, page):
        super().__init__()
        self.item = item
        self.page = page
        self.owned = False
        self.equipped = False
        self.setFixedSize(self.SIZE, self.HEIGHT)
        self.setStyleSheet("StoreTile { background: transparent; }")

        self._icon_norm = _load_pixmap(item["sprite"], 72)
        self._icon_grey = _greyed(self._icon_norm)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 12, 8, 12)
        lay.setSpacing(0)

        self.action_btn = QPushButton()
        self.action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action_btn.setFixedHeight(30)
        self.action_btn.clicked.connect(self._on_action)

        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon.setStyleSheet("background: transparent; border: none;")
        self.icon.setFixedHeight(76)

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

        self.stamp = _SoldStamp(self)
        self.stamp.setGeometry(0, 0, self.SIZE, self.HEIGHT)
        self.refresh()

    def paintEvent(self, _e):
        p = QPainter(self)
        # Inset so the drop shadow has room — makes the card read as raised,
        # sitting on top of the banner/wall rather than blending into it.
        rect = self.rect().adjusted(0, 0, -5, -5)
        _draw_bubble(p, rect, self.page._bubbles["tile"], shadow=EMP["shadow"])
        _tile_ring(p, rect, EMP["ring"])
        if self.equipped:
            _equipped_badge(p, rect)
        p.end()

    def _btn_qss(self, bg, edge):
        return (f"QPushButton {{ background:{bg}; border:2px solid {edge}; "
                f"border-radius:5px; padding:3px 10px; }}"
                f"QPushButton:disabled {{ background:#37335a; border-color:#4a466e; }}")

    def _set_btn(self, label, bg, edge, enabled, text=None):
        pm = _sf().render(label, 2, text or EMP["btn_text"])
        self.action_btn.setText("")
        self.action_btn.setIcon(QIcon(pm))
        self.action_btn.setIconSize(pm.size())
        self.action_btn.setEnabled(enabled)
        self.action_btn.setStyleSheet(self._btn_qss(bg, edge))

    def _is_equipped(self, s):
        """Is this item the currently-equipped one (spinners + backgrounds)?"""
        k = self.item["kind"]
        if k == "spinner":
            return s.get_equipped_spinner() == self.item["id"]
        if k == "background":
            return s.get_equipped_background() == self.item["sprite"]
        return False

    def refresh(self):
        s = self.page.settings
        self.owned = s.is_unlocked(self.item["id"])
        self.equipped = self.owned and self._is_equipped(s)
        # icon + name dim when owned
        pm = self._icon_grey if self.owned else self._icon_norm
        if pm is not None:
            self.icon.setPixmap(pm)
        # render_fitted, not render_wrapped: a name too long for one line at
        # scale 2 shrinks a step rather than being broken mid-word or clipped.
        self.name.setPixmap(_sf().render_fitted(
            self.item["name"].upper(), 2,
            EMP["tile_dim"] if self.owned else EMP["tile_text"],
            self.NAME_W, self.NAME_H))

        if not self.owned:
            affordable = s.get_tickets() >= self.item["cost"]
            label = f"BUY {self.item['cost']}"
            if affordable:   # lit
                self._set_btn(label, EMP["buy"], EMP["buy_lit_edge"], True)
            else:            # dim until you can afford it
                self._set_btn(label, EMP["buy_dim"], EMP["buy_dim_edge"], True,
                              text=EMP["buy_dim_text"])
        elif self.item["kind"] in ("spinner", "background"):
            self._set_btn("EQUIPPED" if self.equipped else "EQUIP",
                          EMP["owned"], EMP["owned"], False)
        else:
            self._set_btn("OWNED", EMP["owned"], EMP["owned"], False)

        self.stamp.setVisible(self.owned)
        self.stamp.raise_()
        self.update()

    def mousePressEvent(self, e):
        # Owned spinners/backgrounds stay equippable: clicking the SOLD tile
        # (re)equips it.
        if self.owned and self.item["kind"] in ("spinner", "background"):
            self.page.handle_tile_action(self.item)
        super().mousePressEvent(e)

    def _on_action(self):
        self.page.handle_tile_action(self.item)


class CategoryBox(QFrame):
    """A clickable pixel-art box for a store category (representative icon +
    name). The whole box opens that category's floating window; it lights up
    (accent ring + neon name) while its window is open."""

    MIN_W = 112
    HEIGHT = 112

    def __init__(self, cat_id, label, icon_pm, page, box_w, icon_dy=0):
        super().__init__()
        self.cat_id = cat_id
        self.page = page
        self.selected = False
        self.setFixedSize(box_w, self.HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("CategoryBox { background: transparent; }")
        self._icon = icon_pm
        self._icon_dy = icon_dy   # nudge the icon down within its box
        self._name_norm = _trim_v(_sf().render(label.upper(), 2, EMP["tile_text"]))
        self._name_sel = _trim_v(_sf().render(label.upper(), 2, EMP["neon_on"]))

    def set_selected(self, sel):
        if sel != self.selected:
            self.selected = sel
            self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        rect = self.rect().adjusted(0, 0, -5, -5)
        _draw_bubble(p, rect, self.page._bubbles["tile"], shadow=EMP["shadow"])
        _tile_ring(p, rect, EMP["buy_lit_edge"] if self.selected else EMP["ring"],
                   inset=4, thick=3 if self.selected else 2)
        name = self._name_sel if self.selected else self._name_norm
        name_y = rect.y() + rect.height() - name.height() - 12
        if self._icon is not None:
            # Vertically centre the icon in the space above the name.
            top, bot = rect.y() + 8, name_y - 6
            iy = top + max(0, (bot - top - self._icon.height()) // 2) + self._icon_dy
            p.drawPixmap(rect.x() + (rect.width() - self._icon.width()) // 2,
                         iy, self._icon)
        p.drawPixmap(rect.x() + (rect.width() - name.width()) // 2, name_y, name)
        p.end()

    def mousePressEvent(self, e):
        self.page._select_category(self.cat_id)
        super().mousePressEvent(e)


class ShopWindow(QFrame):
    """A floating pixel-art panel inside the Emporium that shows one category's
    merchandise. It has a top-right X to close, and floats over the scene so it
    cleanly overlaps Woogy; closing it reveals him again. Drawn as a 9-slice
    word-bubble so it matches the arcade chrome."""

    def __init__(self, page, content):
        super().__init__(page)
        self.page = page
        self._bubble = _load_art("bubble_dialogue.tdart")

        v = QVBoxLayout(self)
        v.setContentsMargins(20, 16, 20, 18)
        v.setSpacing(10)

        header = QHBoxLayout()
        self.title_lbl = QLabel()
        self.title_lbl.setStyleSheet("background: transparent; border: none;")
        header.addWidget(self.title_lbl)
        header.addStretch()
        self.close_btn = QPushButton()
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setFixedSize(28, 28)
        xpm = _sf().render("X", 3, EMP["btn_text"])
        self.close_btn.setIcon(QIcon(xpm)); self.close_btn.setIconSize(xpm.size())
        # Transparent: just the X glyph, no button chrome, over the panel.
        self.close_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; }")
        self.close_btn.clicked.connect(page._close_window)
        header.addWidget(self.close_btn, 0, Qt.AlignmentFlag.AlignTop)
        v.addLayout(header)
        v.addWidget(content, 1)
        self.hide()

    def paintEvent(self, _e):
        p = QPainter(self)
        _draw_bubble(p, self.rect().adjusted(0, 0, -1, -1), self._bubble,
                     shadow=EMP["shadow"])
        p.end()

    def set_title(self, text):
        self.title_lbl.setPixmap(
            _trim_v(_sf().render(text.upper(), 4, EMP["neon_on"])))
