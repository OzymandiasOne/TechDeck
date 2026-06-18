"""
Woogy's Emporium — the ticket redemption counter.

A pixel-art arcade prize-counter scene (wall + kiosk + Woogy + an animated
arcade cabinet) with a grid of purchasable tiles laid over it. Earn tickets by
running apps / sending feedback; spend them here. Fixed arcade palette (does NOT
follow the user theme), with motion (marquee chase lights + neon flicker on the
sign, animated cabinet screen) and a typewriter dialogue box.

ALL text uses the UFO50 sprite font (techdeck.ui.sprite_font), rendered to
tinted pixmaps — labels/buttons carry pixmaps, painted text blits directly.
Chrome (sign, balance, tiles, dialogue) is drawn from editable 9-slice
word-bubble sprites (assets/sprites/bubble_*.tdart, authored by
tools/generate_bubbles.py) via pixel_art.render_nine_slice + _draw_bubble:
corners stay crisp, the middle stretches to any size, and a soft drop shadow is
taken from the bubble's own silhouette. Repaint them in the pixel editor.
"""

import math
import random
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QFrame, QDialog,
)
from PySide6.QtCore import Qt, QRect, QTimer, QPoint
from PySide6.QtGui import QPainter, QColor, QPolygon, QIcon, QPixmap, QImage

from techdeck.ui import pixel_art
from techdeck.ui.sprite_font import font as _sf


def _sprites_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets" / "sprites"
    return Path(__file__).resolve().parents[3] / "assets" / "sprites"


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

CATALOG = [
    {"id": "spinner_beyblade", "name": "Beyblade",
     "sprite": "spinner_beyblade.tdart", "cost": 60, "kind": "spinner"},
    {"id": "spinner_shuriken", "name": "Shuriken",
     "sprite": "spinner_shuriken.tdart", "cost": 100, "kind": "spinner"},
    {"id": "steeltube_game", "name": "ASA: The Video Game",
     "sprite": "cartridge_steeltube.tdart", "cost": 250, "kind": "game"},
]


def _load_pixmap(name: str, target: int):
    try:
        data = pixel_art.load(_sprites_dir() / name)
    except Exception:
        return None
    w, h = pixel_art.dimensions(data)
    scale = max(1, math.ceil(target / max(w, h, 1)))
    return pixel_art.render(data, scale=scale)


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
    to. Bubbles are authored by tools/generate_bubbles.py and editable in the
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


class StoreTile(QFrame):
    """One purchasable tile drawn as a pixel-art box: icon + name + button. All
    tiles are a fixed size so the grid is uniform; the icon is centred with equal
    spacing to the button above and the name below."""

    SIZE = 150          # width
    HEIGHT = 216        # uniform height (so 1-line and 3-line names match)
    GAP = 16            # equal gap above/below the icon
    NAME_H = 52         # reserves up to 3 wrapped lines @ scale 2
    NAME_W = 126

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

    def refresh(self):
        s = self.page.settings
        self.owned = s.is_unlocked(self.item["id"])
        self.equipped = (self.owned and self.item["kind"] == "spinner"
                         and s.get_equipped_spinner() == self.item["id"])
        # icon + name dim when owned
        pm = self._icon_grey if self.owned else self._icon_norm
        if pm is not None:
            self.icon.setPixmap(pm)
        self.name.setPixmap(_sf().render_wrapped(
            self.item["name"].upper(), 2,
            EMP["tile_dim"] if self.owned else EMP["tile_text"],
            max_width=self.NAME_W))

        if not self.owned:
            affordable = s.get_tickets() >= self.item["cost"]
            label = f"BUY {self.item['cost']}"
            if affordable:   # lit
                self._set_btn(label, EMP["buy"], EMP["buy_lit_edge"], True)
            else:            # dim until you can afford it
                self._set_btn(label, EMP["buy_dim"], EMP["buy_dim_edge"], True,
                              text=EMP["buy_dim_text"])
        elif self.item["kind"] == "spinner":
            equipped = s.get_equipped_spinner() == self.item["id"]
            self._set_btn("EQUIPPED" if equipped else "EQUIP",
                          EMP["owned"], EMP["owned"], False)
        else:
            self._set_btn("OWNED", EMP["owned"], EMP["owned"], False)

        self.stamp.setVisible(self.owned)
        self.stamp.raise_()
        self.update()

    def mousePressEvent(self, e):
        # Owned spinners stay equippable: clicking the SOLD tile (re)equips it.
        if self.owned and self.item["kind"] == "spinner":
            self.page.handle_tile_action(self.item)
        super().mousePressEvent(e)

    def _on_action(self):
        self.page.handle_tile_action(self.item)


class EmporiumPage(QWidget):
    """The redemption-counter scene + the catalog grid, with arcade animation."""

    DEFAULT_DIALOGUE = "WOOGY: WHAT'LL IT BE, FELLAS?"

    # A little something Woogy says for every item he rings up. Keyed by item id;
    # falls back to GENERIC_COMMENT for anything not listed.
    WOOGY_COMMENTS = {
        "spinner_beyblade":
            "WOOGY: A BEYBLADE! GO ON, LET IT RIP. I'LL CHEER FROM BACK HERE.",
        "spinner_shuriken":
            "WOOGY: A SHURIKEN! SO SHARP, SO COOL. PLEASE DON'T POKE OL' WOOGY.",
        "steeltube_game":
            "WOOGY: OOH, MY FAVORITE! 400 HOURS LOGGED AND I STILL STINK AT IT.",
    }
    GENERIC_COMMENT = "WOOGY: A FINE PICK! YOU'VE GOT GOOD TASTE, FRIEND."

    DIALOGUE_W = 380        # word-bubble width (px); height is fixed at 78
    LINES_PER_PAGE = 2      # lines that fit in the bubble before it paginates

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._phase = 0
        self._set_dialogue(self.DEFAULT_DIALOGUE)
        self._neon_bright = True
        self._bg = _load_pixmap("emporium_background.tdart", 128)
        self._counter = _load_pixmap("emporium_counter.tdart", 128)
        self._woogy = _load_pixmap("woogy.tdart", 230)
        self._cabinet = _load_pixmap("arcade_cabinet.tdart", 64)
        # 9-slice word-bubble panels (editable .tdart; see tools/generate_bubbles.py)
        self._bubbles = {
            "tile": _load_art("bubble_tile.tdart"),
            "banner": _load_art("bubble_banner.tdart"),
            "balance": _load_art("bubble_balance.tdart"),
            "dialogue": _load_art("bubble_dialogue.tdart"),
        }
        # Pre-render the neon sign (bright + dim) once.
        self._sign_on = _trim_v(_sf().render("WOOGY'S EMPORIUM", 4, EMP["neon_on"]))
        self._sign_off = _trim_v(_sf().render("WOOGY'S EMPORIUM", 4, EMP["neon_off"]))

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        bar = QHBoxLayout()
        self.banner = QLabel()
        self.banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.banner.setStyleSheet("background: transparent; border: none;")
        self.banner.setFixedSize(self._sign_on.width() + 44, self._sign_on.height() + 22)
        bar.addWidget(self.banner)
        bar.addStretch()
        self.balance_lbl = QLabel()
        self.balance_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.balance_lbl.setStyleSheet("background: transparent; border: none;")
        self.balance_lbl.setFixedSize(150, self._sign_on.height() + 18)
        bar.addWidget(self.balance_lbl)
        root.addLayout(bar)
        self._set_banner_bright(True)

        grid_host = QWidget()
        grid_host.setStyleSheet("background: transparent;")
        self.grid = QGridLayout(grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(12)
        self.tiles = []
        cols = 5
        for i, item in enumerate(CATALOG):
            tile = StoreTile(item, self)
            self.tiles.append(tile)
            self.grid.addWidget(tile, i // cols, i % cols,
                                 Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.grid.setColumnStretch(cols, 1)
        root.addWidget(grid_host, 0, Qt.AlignmentFlag.AlignTop)
        root.addStretch()

        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._tick)
        self.refresh()

    # ---- Woogy's word bubble (paginated typewriter) --------------------------
    def _set_dialogue(self, text):
        """Point Woogy's bubble at `text`, wrapped into pages, typed from the top."""
        self._dialogue = text
        self._lines = _sf().wrap_lines(text, 3, self.DIALOGUE_W - 28)
        self._page = 0
        self._reveal = 0

    def _dialogue_rect(self):
        return QRect(40, self.height() - 104, self.DIALOGUE_W, 78)

    def _page_lines(self):
        lpp = self.LINES_PER_PAGE
        return self._lines[self._page * lpp: self._page * lpp + lpp]

    def _page_chars(self):
        return sum(len(ln) for ln in self._page_lines())

    def _has_more_pages(self):
        return (self._page + 1) * self.LINES_PER_PAGE < len(self._lines)

    def _set_banner_bright(self, bright):
        self._neon_bright = bright
        self.banner.setPixmap(self._sign_on if bright else self._sign_off)

    def refresh(self):
        bal = _trim_v(_sf().render(f"{self.settings.get_tickets()} TICKETS", 3,
                                   EMP["ticket"]))
        self.balance_lbl.setFixedSize(max(150, bal.width() + 28),
                                      self._sign_on.height() + 18)
        self.balance_lbl.setPixmap(bal)
        for t in self.tiles:
            t.refresh()

    # ---- animation -----------------------------------------------------------
    def showEvent(self, e):
        super().showEvent(e)
        self._set_dialogue(self.DEFAULT_DIALOGUE)
        self._timer.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._timer.stop()

    def _tick(self):
        self._phase += 1
        page_chars = self._page_chars()
        if self._reveal < page_chars:
            self._reveal = min(page_chars, self._reveal + 2)
        bright = random.random() > 0.12
        if bright != self._neon_bright:
            self._set_banner_bright(bright)
        self.update()

    def mousePressEvent(self, e):
        # Click the bubble to fast-forward the typewriter, then to page through
        # the rest of Woogy's comment.
        if self._dialogue_rect().contains(e.position().toPoint()):
            if self._reveal < self._page_chars():
                self._reveal = self._page_chars()
            elif self._has_more_pages():
                self._page += 1
                self._reveal = 0
            self.update()
        super().mousePressEvent(e)

    # ---- purchase / equip ----------------------------------------------------
    def handle_tile_action(self, item):
        s = self.settings
        if not s.is_unlocked(item["id"]):
            if not s.spend_tickets(item["cost"]):
                PixelDialog.show_message(
                    self, "Not enough tickets",
                    f"{item['name']} costs {item['cost']} tickets. You have "
                    f"{s.get_tickets()}. Run more apps to earn more!")
                return
            s.unlock_item(item["id"])
            grab = (f"Woogy grabs the {item['name']} off the shelf with effort "
                    "and wobbles back to the counter. He slides it towards you "
                    "with a huff.")
            if item["kind"] == "spinner":
                s.set_equipped_spinner(item["id"])
                instr = "It's equipped! Pop it with /fidget, or switch in My Stuff."
            elif item["kind"] == "game":
                instr = ("Find it in your Library (Games) and add it to a kit "
                         "to play.")
            else:
                instr = "Enjoy!"
            PixelDialog.show_message(self, "Sold!", f"{grab} {instr}")
            # Once the SOLD! box is dismissed, Woogy pipes up in his word bubble
            # with a comment for this item (paginated + typed from the top).
            self._set_dialogue(
                self.WOOGY_COMMENTS.get(item["id"], self.GENERIC_COMMENT))
        elif item["kind"] == "spinner":
            s.set_equipped_spinner(item["id"])
        self.refresh()

    # ---- the pixel-art scene -------------------------------------------------
    def paintEvent(self, _evt):
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(EMP["wall"]))
        if self._bg is not None:
            p.drawPixmap(QRect(0, 0, w, h), self._bg)
        self._draw_cabinet(p, w, h)
        if self._woogy is not None:
            ww, wh = self._woogy.width(), self._woogy.height()
            y = h - int(h * 0.30) - wh + 30
            p.drawPixmap((w - ww) // 2, max(y, int(h * 0.32)), self._woogy)
        if self._counter is not None:
            ch = int(h * 0.30)
            p.drawPixmap(QRect(0, h - ch, w, ch), self._counter)
        _draw_bubble(p, self.banner.geometry(), self._bubbles["banner"],
                     shadow=EMP["shadow"])
        _marquee(p, self.banner.geometry(), self._phase)
        _draw_bubble(p, self.balance_lbl.geometry(), self._bubbles["balance"],
                     shadow=EMP["shadow"])
        self._draw_dialogue(p, w, h)
        p.end()

    # Native cabinet metrics (cells) — kept in sync with the .tdart art built by
    # tools/generate_arcade_cabinet.py (W x H = 48 x 76).
    _CAB_W, _CAB_H = 48, 76
    _SCREEN = (13, 21, 22, 20)        # x, y, w, h of the animated screen face
    _MARQUEE_BULBS = (range(8, 41, 4), 3)   # bulb x-cells, row

    def _draw_cabinet(self, p, w, h):
        pix = self._cabinet
        if pix is None:
            return
        scale = max(2, round(0.40 * h / self._CAB_H))
        cw, ch = self._CAB_W * scale, self._CAB_H * scale
        cx = w - cw - 24
        cy = max((h - int(h * 0.30)) - ch + 10 * scale, int(0.08 * h))
        p.drawPixmap(QRect(cx, cy, cw, ch), pix)
        scol, srow, scells_w, scells_h = self._SCREEN
        sx, sy = cx + scol * scale, cy + srow * scale
        sw, sh = scells_w * scale, scells_h * scale
        p.fillRect(sx, sy, sw, sh, QColor(EMP["screen"]))
        bars = ["#37c9da", "#cf3597", "#3b34c0", "#e8841f"]
        bh = max(1, sh // 4)
        for i in range(4):
            c = QColor(bars[(self._phase + i) % 4])
            c.setAlpha(150)
            p.fillRect(sx, sy + i * bh, sw, bh, c)
        by = sy + (self._phase * scale) % max(1, sh)
        p.fillRect(sx, by, sw, max(1, scale), QColor("#f0f0ff"))
        bulb_xs, bulb_row = self._MARQUEE_BULBS
        for j, mx in enumerate(bulb_xs):
            on = (self._phase + j) % 3 != 0
            p.fillRect(cx + mx * scale, cy + bulb_row * scale, scale, scale,
                       QColor("#7ef9ff" if on else "#1a4a52"))

    def _draw_dialogue(self, p, w, h):
        rect = self._dialogue_rect()
        # UFO50-style: black box, thick white rounded border, soft drop shadow.
        _draw_bubble(p, rect, self._bubbles["dialogue"], shadow=EMP["shadow"])
        # Reveal the current page's lines char-by-char (typewriter).
        lines = self._page_lines()
        r = self._reveal
        shown = []
        for ln in lines:
            shown.append(ln[:max(0, min(len(ln), r))])
            r -= len(ln)
        fully = self._reveal >= self._page_chars()
        has_more = self._has_more_pages()
        # When there's more to read, mark it with "..." and the blink-y down arrow.
        if fully and has_more and shown:
            shown[-1] = shown[-1] + "..."
        text_pm = _sf().render_lines(shown or [""], 3, EMP["dialogue_text"])
        p.drawPixmap(rect.x() + 14, rect.y() + 12, text_pm)
        if fully and has_more and (self._phase // 3) % 2 == 0:
            ax, ay = rect.center().x(), rect.bottom() - 12
            tri = QPolygon([QPoint(ax - 5, ay), QPoint(ax + 5, ay), QPoint(ax, ay + 6)])
            p.setBrush(QColor(EMP["neon_on"]))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPolygon(tri)
