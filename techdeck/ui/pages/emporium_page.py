"""
Woogy's Emporium — the ticket redemption counter.

A pixel-art arcade prize-counter scene (wall + kiosk + Woogy + an animated
arcade cabinet) with a grid of purchasable tiles laid over it. Earn tickets by
running apps / sending feedback; spend them here. Fixed arcade palette (does NOT
follow the user theme), with motion (marquee chase lights + neon flicker on the
sign, animated cabinet screen) and a typewriter dialogue box.

ALL text uses the UFO50 sprite font (techdeck.ui.sprite_font), rendered to
tinted pixmaps — labels/buttons carry pixmaps, painted text blits directly.
Chrome (sign, balance, tiles, dialogue) is drawn as chunky pixel-art panels.
"""

import math
import random
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QFrame, QMessageBox,
)
from PySide6.QtCore import Qt, QRect, QTimer, QPoint
from PySide6.QtGui import QPainter, QColor, QPolygon, QIcon

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
    "tile_text": "#f0f0ff",
    # bevel + depth tones (light = top-left, dark = bottom-right)
    "cyan_hi": "#9af6ff", "cyan_lo": "#1f6e78",
    "mag_hi": "#f2a0d8", "mag_lo": "#7a1f5a",
    "gold_hi": "#ffe9a0", "gold_lo": "#9a7a1a",
    "white": "#f4f4ec", "shadow": "#05030f",
}

CATALOG = [
    {"id": "spinner_beyblade", "name": "Beyblade Spinner",
     "sprite": "spinner_beyblade.tdart", "cost": 60, "kind": "spinner"},
    {"id": "spinner_shuriken", "name": "Shuriken Spinner",
     "sprite": "spinner_shuriken.tdart", "cost": 100, "kind": "spinner"},
    {"id": "steeltube_game", "name": "Steel Tube Op",
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


def _round_prof(r):
    """Pixel-art quarter-circle corner: the inset (in px) for each of the top
    `r` rows (mirrored top/bottom). Trailing zeros are harmless."""
    c = r - 0.5
    prof = []
    for y in range(r):
        ins = r
        for x in range(r):
            if (c - x) ** 2 + (c - y) ** 2 <= r * r:
                ins = x
                break
        prof.append(ins)
    return prof


def _round_fill(p, x, y, w, h, prof, color):
    """Fill a rounded-corner rectangle one scanline at a time (crisp, no AA)."""
    if w <= 0 or h <= 0:
        return
    col = QColor(color)
    n = len(prof)
    for row in range(h):
        if row < n:
            ins = prof[row]
        elif row >= h - n:
            ins = prof[h - 1 - row]
        else:
            ins = 0
        if w - 2 * ins > 0:
            p.fillRect(x + ins, y + row, w - 2 * ins, 1, col)


def _panel(p, rect, *, fill, border, outline="#0c0a1e", hi=None, lo=None,
           radius=4, thickness=2, shadow=None):
    """SNES-style rounded panel: a crisp dark silhouette, a colored border with
    an optional top-left highlight / bottom-right shadow bevel for depth, a
    filled interior, and an optional drop shadow to lift it off the background."""
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    prof = _round_prof(radius)
    if shadow is not None:
        sc = QColor(shadow)
        sc.setAlpha(115)
        _round_fill(p, x + 3, y + 4, w, h, prof, sc)
    ox = 0
    if outline is not None:
        _round_fill(p, x, y, w, h, prof, outline)
        ox = 1
    _round_fill(p, x + ox, y + ox, w - 2 * ox, h - 2 * ox,
                [max(0, v - ox) for v in prof], border)
    t = ox + thickness
    _round_fill(p, x + t, y + t, w - 2 * t, h - 2 * t,
                [max(0, v - t) for v in prof], fill)
    # bevel along the straight edges (skip the rounded corners)
    bw = max(1, thickness - 1)
    if hi is not None:
        hc = QColor(hi)
        p.fillRect(x + radius, y + ox, w - 2 * radius, bw, hc)
        p.fillRect(x + ox, y + radius, bw, h - 2 * radius, hc)
    if lo is not None:
        lc = QColor(lo)
        p.fillRect(x + radius, y + h - ox - bw, w - 2 * radius, bw, lc)
        p.fillRect(x + w - ox - bw, y + radius, bw, h - 2 * radius, lc)


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


class StoreTile(QFrame):
    """One purchasable tile drawn as a pixel-art box: icon + name + button."""

    SIZE = 150

    def __init__(self, item, page):
        super().__init__()
        self.item = item
        self.page = page
        self.setFixedWidth(self.SIZE)
        self.setStyleSheet("StoreTile { background: transparent; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(3)

        self.action_btn = QPushButton()
        self.action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action_btn.clicked.connect(self._on_action)
        lay.addWidget(self.action_btn, 0, Qt.AlignmentFlag.AlignHCenter)

        icon = QLabel()
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix = _load_pixmap(item["sprite"], 72)
        if pix is not None:
            icon.setPixmap(pix)
        icon.setStyleSheet("background: transparent; border: none;")
        icon.setFixedHeight(76)
        lay.addWidget(icon)

        name = QLabel()
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet("background: transparent; border: none;")
        name.setPixmap(_sf().render_wrapped(item["name"].upper(), 2,
                                            EMP["tile_text"], max_width=126))
        lay.addWidget(name, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch()
        self.refresh()

    def paintEvent(self, _e):
        p = QPainter(self)
        # Inset so the drop shadow has room — makes the card read as raised,
        # sitting on top of the banner/wall rather than blending into it.
        _panel(p, self.rect().adjusted(0, 0, -5, -5),
               fill=EMP["tile_bg"], border=EMP["frame_a"],
               hi=EMP["cyan_hi"], lo=EMP["cyan_lo"], radius=5, thickness=2,
               shadow=EMP["shadow"])
        p.end()

    def _btn_qss(self, bg, edge):
        return (f"QPushButton {{ background:{bg}; border:2px solid {edge}; "
                f"border-radius:5px; padding:3px 10px; }}"
                f"QPushButton:disabled {{ background:#3a3560; border-color:#3a3560; }}")

    def _set_btn(self, label, bg, edge, enabled):
        pm = _sf().render(label, 2, EMP["btn_text"])
        self.action_btn.setText("")
        self.action_btn.setIcon(QIcon(pm))
        self.action_btn.setIconSize(pm.size())
        self.action_btn.setEnabled(enabled)
        self.action_btn.setStyleSheet(self._btn_qss(bg, edge))

    def refresh(self):
        s = self.page.settings
        if not s.is_unlocked(self.item["id"]):
            self._set_btn(f"BUY {self.item['cost']}", EMP["buy"],
                          EMP["buy_edge"], s.get_tickets() >= self.item["cost"])
        elif self.item["kind"] == "spinner":
            equipped = s.get_equipped_spinner() == self.item["id"]
            self._set_btn("EQUIPPED" if equipped else "EQUIP",
                          EMP["equip"], "#7af0a0", not equipped)
        else:
            self._set_btn("OWNED", EMP["owned"], "#b97fe0", False)

    def _on_action(self):
        self.page.handle_tile_action(self.item)


class EmporiumPage(QWidget):
    """The redemption-counter scene + the catalog grid, with arcade animation."""

    DIALOGUE = "WOOGY: WHAT'LL IT BE, FELLAS?"

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._phase = 0
        self._reveal = 0
        self._neon_bright = True
        self._bg = _load_pixmap("emporium_background.tdart", 128)
        self._counter = _load_pixmap("emporium_counter.tdart", 128)
        self._woogy = _load_pixmap("woogy.tdart", 230)
        self._cabinet = _load_pixmap("arcade_cabinet.tdart", 64)
        # Pre-render the neon sign (bright + dim) once.
        self._sign_on = _sf().render("WOOGY'S EMPORIUM", 4, EMP["neon_on"])
        self._sign_off = _sf().render("WOOGY'S EMPORIUM", 4, EMP["neon_off"])

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

    def _set_banner_bright(self, bright):
        self._neon_bright = bright
        self.banner.setPixmap(self._sign_on if bright else self._sign_off)

    def refresh(self):
        bal = _sf().render(f"{self.settings.get_tickets()} TIX", 3, EMP["ticket"])
        self.balance_lbl.setFixedSize(max(150, bal.width() + 28),
                                      self._sign_on.height() + 18)
        self.balance_lbl.setPixmap(bal)
        for t in self.tiles:
            t.refresh()

    # ---- animation -----------------------------------------------------------
    def showEvent(self, e):
        super().showEvent(e)
        self._reveal = 0
        self._timer.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._timer.stop()

    def _tick(self):
        self._phase += 1
        if self._reveal < len(self.DIALOGUE):
            self._reveal = min(len(self.DIALOGUE), self._reveal + 2)
        bright = random.random() > 0.12
        if bright != self._neon_bright:
            self._set_banner_bright(bright)
        self.update()

    # ---- purchase / equip ----------------------------------------------------
    def handle_tile_action(self, item):
        s = self.settings
        if not s.is_unlocked(item["id"]):
            if not s.spend_tickets(item["cost"]):
                QMessageBox.information(
                    self, "Not enough tickets",
                    f"\"{item['name']}\" costs {item['cost']} tickets. "
                    f"You have {s.get_tickets()}. Run more apps to earn more!")
                return
            s.unlock_item(item["id"])
            if item["kind"] == "spinner":
                s.set_equipped_spinner(item["id"])
                msg = (f"Woogy slides \"{item['name']}\" across the counter. "
                       "It's equipped — pop it with /fidget!")
            elif item["kind"] == "game":
                msg = (f"\"{item['name']}\" is yours! Find it in your Library "
                       "(Games) and add it to a kit to play.")
            else:
                msg = f"Woogy slides \"{item['name']}\" across the counter. Enjoy!"
            QMessageBox.information(self, "Woogy's Emporium", msg)
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
        _panel(p, self.banner.geometry(), fill=EMP["panel"],
               border=EMP["frame_b"], hi=EMP["mag_hi"], lo=EMP["mag_lo"],
               radius=5, shadow=EMP["shadow"])
        _marquee(p, self.banner.geometry(), self._phase)
        _panel(p, self.balance_lbl.geometry(), fill=EMP["panel"],
               border=EMP["ticket"], hi=EMP["gold_hi"], lo=EMP["gold_lo"],
               radius=5, shadow=EMP["shadow"])
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
        rect = QRect(40, h - 104, 380, 78)
        # UFO50-style: black box, thick white rounded border, soft drop shadow.
        _panel(p, rect, fill=EMP["dialogue"], border=EMP["white"],
               outline="#0c0a1e", lo="#c4c4d0", radius=6, thickness=3,
               shadow=EMP["shadow"])
        text_pm = _sf().render_wrapped(self.DIALOGUE[:self._reveal], 3,
                                       EMP["dialogue_text"], max_width=rect.width() - 28)
        p.drawPixmap(rect.x() + 14, rect.y() + 12, text_pm)
        if self._reveal >= len(self.DIALOGUE) and (self._phase // 3) % 2 == 0:
            ax, ay = rect.center().x(), rect.bottom() - 12
            tri = QPolygon([QPoint(ax - 5, ay), QPoint(ax + 5, ay), QPoint(ax, ay + 6)])
            p.setBrush(QColor(EMP["neon_on"]))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPolygon(tri)
