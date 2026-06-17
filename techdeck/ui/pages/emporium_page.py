"""
Woogy's Emporium — the ticket redemption counter.

A pixel-art arcade prize-counter scene (wall + kiosk + Woogy + an animated
arcade cabinet) with a grid of purchasable tiles laid over it. Earn tickets by
running apps / sending feedback; spend them here. Fixed arcade palette (does NOT
follow the user theme), with motion (marquee chase lights + neon flicker on the
sign, animated cabinet screen) and a typewriter dialogue box.

Chrome (sign, balance, tiles, dialogue) is drawn as chunky pixel-art panels in
code; the scene sprites are editable .tdart in assets/sprites/.
"""

import math
import random
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QFrame, QMessageBox,
)
from PySide6.QtCore import Qt, QRect, QTimer
from PySide6.QtGui import QPainter, QColor, QFont, QPolygon
from PySide6.QtCore import QPoint

from techdeck.ui import pixel_art


def _sprites_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets" / "sprites"
    return Path(__file__).resolve().parents[3] / "assets" / "sprites"


def _arcade_family() -> str:
    try:
        from techdeck.ui.widgets.moth_widget import haiku_font
        return haiku_font(12).family()
    except Exception:
        return ""


EMP = {
    "panel": "#2a1644", "neon_on": "#7ef9ff", "neon_off": "#2b6b73",
    "frame_a": "#37c9da", "frame_b": "#cf3597", "ticket": "#f4c430",
    "tile_bg": "#1c1850", "buy": "#c42a34", "buy_edge": "#ff7a3f",
    "equip": "#2bb04a", "owned": "#7a3fb0", "screen": "#0a0a18",
    "wall": "#272273", "bulb_on": "#fff07a", "bulb_off": "#6a5a1a",
    "dialogue": "#101018", "dialogue_text": "#f4f4ec",
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


def _pixel_panel(p, rect, fill, c_outer, c_inner):
    """Chunky 2-tone pixel-art border around a filled rect (no anti-aliasing)."""
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    p.fillRect(x, y, w, h, QColor(fill))
    o, i = QColor(c_outer), QColor(c_inner)
    p.fillRect(x, y, w, 2, o); p.fillRect(x, y + h - 2, w, 2, o)
    p.fillRect(x, y, 2, h, o); p.fillRect(x + w - 2, y, 2, h, o)
    p.fillRect(x + 2, y + 2, w - 4, 2, i); p.fillRect(x + 2, y + h - 4, w - 4, 2, i)
    p.fillRect(x + 2, y + 2, 2, h - 4, i); p.fillRect(x + w - 4, y + 2, 2, h - 4, i)


def _marquee(p, rect, phase):
    """Chasing marquee bulbs evenly spaced just inside the rect perimeter."""
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    pts, step = [], 13
    for bx in range(x + 7, x + w - 6, step):
        pts.append((bx, y + 4)); pts.append((bx, y + h - 5))
    for by in range(y + 12, y + h - 10, step):
        pts.append((x + 4, by)); pts.append((x + w - 5, by))
    for idx, (bx, by) in enumerate(pts):
        on = (idx - phase) % 3 == 0       # chase
        p.fillRect(bx - 1, by - 1, 3, 3,
                   QColor(EMP["bulb_on"] if on else EMP["bulb_off"]))


class StoreTile(QFrame):
    """One purchasable tile drawn as a pixel-art box: icon + name + button."""

    SIZE = 150

    def __init__(self, item, page):
        super().__init__()
        self.item = item
        self.page = page
        fam = page.family
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

        name = QLabel(item["name"])
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setWordWrap(True)
        name.setStyleSheet(
            f"color:#f0f0ff; font-family:'{fam}'; font-size:12px; "
            "background: transparent; border: none;")
        lay.addWidget(name)
        lay.addStretch()
        self.refresh()

    def paintEvent(self, _e):
        p = QPainter(self)
        _pixel_panel(p, self.rect().adjusted(0, 0, -1, -1),
                     EMP["tile_bg"], EMP["frame_a"], EMP["frame_b"])
        p.end()

    def _btn_qss(self, bg, edge):
        return (f"QPushButton {{ background:{bg}; color:#fff; "
                f"border:2px solid {edge}; border-radius:0px; padding:2px 10px; "
                f"font-family:'{self.page.family}'; font-weight:700; }}"
                f"QPushButton:disabled {{ background:#3a3560; color:#9a96c0; "
                f"border-color:#3a3560; }}")

    def refresh(self):
        s = self.page.settings
        if not s.is_unlocked(self.item["id"]):
            self.action_btn.setText(f"BUY  {self.item['cost']} TIX")
            self.action_btn.setEnabled(s.get_tickets() >= self.item["cost"])
            self.action_btn.setStyleSheet(self._btn_qss(EMP["buy"], EMP["buy_edge"]))
        elif self.item["kind"] == "spinner":
            equipped = s.get_equipped_spinner() == self.item["id"]
            self.action_btn.setText("EQUIPPED" if equipped else "EQUIP")
            self.action_btn.setEnabled(not equipped)
            self.action_btn.setStyleSheet(self._btn_qss(EMP["equip"], "#7af0a0"))
        else:
            self.action_btn.setText("OWNED")
            self.action_btn.setEnabled(False)
            self.action_btn.setStyleSheet(self._btn_qss(EMP["owned"], "#b97fe0"))

    def _on_action(self):
        self.page.handle_tile_action(self.item)


class EmporiumPage(QWidget):
    """The redemption-counter scene + the catalog grid, with arcade animation."""

    DIALOGUE = "WOOGY: WHAT'LL IT BE, FELLAS?"

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.family = _arcade_family()
        self._phase = 0
        self._reveal = 0
        self._neon_bright = True
        self._bg = _load_pixmap("emporium_background.tdart", 128)
        self._counter = _load_pixmap("emporium_counter.tdart", 128)
        self._woogy = _load_pixmap("woogy.tdart", 230)
        self._cabinet = _load_pixmap("arcade_cabinet.tdart", 64)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        bar = QHBoxLayout()
        self.banner = QLabel("WOOGY'S EMPORIUM")
        self.banner.setFixedSize(372, 52)
        self.banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bar.addWidget(self.banner)
        bar.addStretch()
        self.balance_lbl = QLabel()
        self.balance_lbl.setFixedSize(132, 48)
        self.balance_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.balance_lbl.setStyleSheet(
            f"background: transparent; border: none; color:{EMP['ticket']}; "
            f"font-family:'{self.family}'; font-size:18px; font-weight:800;")
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
        self.banner.setStyleSheet(
            f"background: transparent; border: none; "
            f"color:{EMP['neon_on'] if bright else EMP['neon_off']}; "
            f"font-family:'{self.family}'; font-size:22px; font-weight:800;")

    def refresh(self):
        self.balance_lbl.setText(f"{self.settings.get_tickets()} TIX")
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
            QMessageBox.information(
                self, "Woogy's Emporium",
                f"Woogy slides \"{item['name']}\" across the counter. Enjoy!")
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
        # chrome panels behind the text widgets
        _pixel_panel(p, self.banner.geometry(), EMP["panel"],
                     EMP["frame_b"], EMP["frame_a"])
        _marquee(p, self.banner.geometry(), self._phase)
        _pixel_panel(p, self.balance_lbl.geometry(), EMP["panel"],
                     EMP["frame_a"], EMP["frame_b"])
        self._draw_dialogue(p, w, h)
        p.end()

    def _draw_cabinet(self, p, w, h):
        pix = self._cabinet
        if pix is None:
            return
        scale = max(2, round(0.40 * h / 64))
        cw, ch = 40 * scale, 64 * scale
        cx = w - cw - 24
        cy = max((h - int(h * 0.30)) - ch + 10 * scale, int(0.08 * h))
        p.drawPixmap(QRect(cx, cy, cw, ch), pix)
        sx, sy, sw, sh = cx + 9 * scale, cy + 14 * scale, 22 * scale, 15 * scale
        p.fillRect(sx, sy, sw, sh, QColor(EMP["screen"]))
        bars = ["#37c9da", "#cf3597", "#3b34c0", "#e8841f"]
        bh = max(1, sh // 4)
        for i in range(4):
            c = QColor(bars[(self._phase + i) % 4])
            c.setAlpha(150)
            p.fillRect(sx, sy + i * bh, sw, bh, c)
        by = sy + (self._phase * scale) % max(1, sh)
        p.fillRect(sx, by, sw, max(1, scale), QColor("#f0f0ff"))
        for j, mx in enumerate(range(9, 31, 3)):
            on = (self._phase + j) % 3 != 0
            p.fillRect(cx + mx * scale, cy + 5 * scale, scale, scale,
                       QColor("#7ef9ff" if on else "#1a4a52"))

    def _draw_dialogue(self, p, w, h):
        rect = QRect(40, h - 104, 380, 78)
        _pixel_panel(p, rect, EMP["dialogue"], EMP["frame_a"], EMP["frame_b"])
        f = QFont(self.family) if self.family else QFont()
        f.setPointSize(12)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(EMP["dialogue_text"]))
        p.drawText(rect.adjusted(14, 10, -14, -10),
                   Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
                   | Qt.TextFlag.TextWordWrap,
                   self.DIALOGUE[:self._reveal])
        # blinking down-arrow once fully revealed
        if self._reveal >= len(self.DIALOGUE) and (self._phase // 3) % 2 == 0:
            ax, ay = rect.center().x(), rect.bottom() - 12
            tri = QPolygon([QPoint(ax - 5, ay), QPoint(ax + 5, ay),
                            QPoint(ax, ay + 6)])
            p.setBrush(QColor(EMP["neon_on"]))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPolygon(tri)
