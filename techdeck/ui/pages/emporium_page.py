"""
Woogy's Emporium — the ticket redemption counter.

A pixel-art arcade prize-counter scene (wall + kiosk + Woogy + an animated
arcade cabinet, all .tdart sprites) with a grid of purchasable tiles laid over
it. Earn tickets by running apps / sending feedback; spend them here. This page
has its OWN fixed arcade palette and does NOT follow the user's theme, and adds
a little motion (flickering neon sign, animated cabinet screen, twinkles) so it
feels like a real arcade.

Sprites live in assets/sprites/*.tdart and are editable in tools/pixel_editor.py.
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
from PySide6.QtGui import QPainter, QColor

from techdeck.ui import pixel_art


def _sprites_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets" / "sprites"
    return Path(__file__).resolve().parents[3] / "assets" / "sprites"


def _arcade_family() -> str:
    """The bundled chunky retro font (Bokutoh EB), for arcade text."""
    try:
        from techdeck.ui.widgets.moth_widget import haiku_font
        return haiku_font(12).family()
    except Exception:
        return ""


# Fixed arcade palette — independent of the active theme.
EMP = {
    "banner": "#3a1640", "neon_on": "#7ef9ff", "neon_off": "#2b6b73",
    "border_on": "#ff4fd0", "border_off": "#5a1f4a", "ticket": "#f4c430",
    "tile_bg": "#1c1850", "tile_border": "#37c9da", "tile_text": "#f0f0ff",
    "buy": "#c42a34", "buy_edge": "#ff7a3f", "equip": "#2bb04a",
    "owned": "#7a3fb0", "screen": "#0a0a18", "wall": "#272273",
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


class StoreTile(QFrame):
    """One purchasable tile, arcade-styled: icon + name + Buy/Equip/Owned."""

    SIZE = 140  # matches HomePage HOME_TILE_W/H

    def __init__(self, item, page):
        super().__init__()
        self.item = item
        self.page = page
        fam = page.family
        self.setFixedWidth(self.SIZE)
        self.setStyleSheet(
            f"StoreTile {{ background:{EMP['tile_bg']}; "
            f"border:2px solid {EMP['tile_border']}; border-radius:8px; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 8)
        lay.setSpacing(2)

        self.action_btn = QPushButton()
        self.action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action_btn.clicked.connect(self._on_action)
        lay.addWidget(self.action_btn, 0, Qt.AlignmentFlag.AlignLeft)

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
            f"color:{EMP['tile_text']}; font-family:'{fam}'; font-size:12px; "
            "background: transparent; border: none;")
        lay.addWidget(name)
        lay.addStretch()
        self.refresh()

    def _btn_qss(self, bg, edge, fg="#ffffff"):
        fam = self.page.family
        return (f"QPushButton {{ background:{bg}; color:{fg}; "
                f"border:2px solid {edge}; border-radius:4px; padding:2px 8px; "
                f"font-family:'{fam}'; font-weight:700; }}"
                f"QPushButton:disabled {{ background:#3a3560; color:#9a96c0; "
                f"border-color:#3a3560; }}")

    def refresh(self):
        s = self.page.settings
        owned = s.is_unlocked(self.item["id"])
        if not owned:
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
    """The redemption-counter scene + the catalog grid, with light animation."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.family = _arcade_family()
        self._phase = 0
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
        self.banner.setStyleSheet(self._banner_qss(True))
        bar.addWidget(self.banner)
        bar.addStretch()
        self.balance_lbl = QLabel()
        self.balance_lbl.setStyleSheet(
            f"background:{EMP['banner']}; color:{EMP['ticket']}; "
            f"font-family:'{self.family}'; font-size:18px; font-weight:800; "
            f"padding:8px 16px; border:3px solid {EMP['border_off']}; "
            "border-radius:6px;")
        bar.addWidget(self.balance_lbl)
        root.addLayout(bar)

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
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._tick)
        self.refresh()

    def _banner_qss(self, bright):
        return (f"background:{EMP['banner']}; "
                f"color:{EMP['neon_on'] if bright else EMP['neon_off']}; "
                f"font-family:'{self.family}'; font-size:24px; font-weight:800; "
                f"padding:8px 20px; border-radius:6px; "
                f"border:3px solid "
                f"{EMP['border_on'] if bright else EMP['border_off']};")

    def refresh(self):
        self.balance_lbl.setText(f"{self.settings.get_tickets()} TIX")
        for t in self.tiles:
            t.refresh()

    # ---- animation -----------------------------------------------------------
    def showEvent(self, e):
        super().showEvent(e)
        self._timer.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._timer.stop()

    def _tick(self):
        self._phase += 1
        # Neon flicker: mostly on, brief random dips.
        bright = random.random() > 0.12
        if bright != self._neon_bright:
            self._neon_bright = bright
            self.banner.setStyleSheet(self._banner_qss(bright))
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
        self._draw_twinkles(p, w, h)
        self._draw_cabinet(p, w, h)
        if self._woogy is not None:
            ww, wh = self._woogy.width(), self._woogy.height()
            y = h - int(h * 0.30) - wh + 30
            p.drawPixmap((w - ww) // 2, max(y, int(h * 0.32)), self._woogy)
        if self._counter is not None:
            ch = int(h * 0.30)
            p.drawPixmap(QRect(0, h - ch, w, ch), self._counter)
        self._draw_speech(p, w, h)
        p.end()

    def _draw_twinkles(self, p, w, h):
        for i, (fx, fy) in enumerate([(0.10, 0.28), (0.90, 0.50),
                                      (0.58, 0.16), (0.30, 0.60)]):
            if (self._phase + i * 2) % 6 < 3:
                p.fillRect(int(fx * w), int(fy * h), 3, 3, QColor(EMP["ticket"]))

    def _draw_cabinet(self, p, w, h):
        pix = self._cabinet
        if pix is None:
            return
        scale = max(2, round(0.40 * h / 64))
        cw, ch = 40 * scale, 64 * scale
        cx = w - cw - 24
        cy = max((h - int(h * 0.30)) - ch + 10 * scale, int(0.08 * h))
        p.drawPixmap(QRect(cx, cy, cw, ch), pix)
        # animated screen (attract mode): cycling translucent bars + scanline
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
        # blinking marquee blips
        for j, mx in enumerate(range(9, 31, 3)):
            on = (self._phase + j) % 3 != 0
            p.fillRect(cx + mx * scale, cy + 5 * scale, scale, scale,
                       QColor("#7ef9ff" if on else "#1a4a52"))

    def _draw_speech(self, p, w, h):
        bw, bh = 360, 70
        x, y = 40, h - 96
        p.fillRect(x, y, bw, bh, QColor("#101014"))
        p.setPen(QColor("#f4f4ec"))
        from PySide6.QtGui import QFont
        f = QFont(self.family) if self.family else QFont()
        f.setPointSize(12)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRect(x + 14, y, bw - 24, bh),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   "WOOGY: WHAT'LL IT BE, FELLAS?")
