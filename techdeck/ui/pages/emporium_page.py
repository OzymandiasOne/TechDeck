"""
Woogy's Emporium — the ticket redemption counter.

A pixel-art shop scene (wall + counter + Woogy, all .tdart sprites) with a grid
of purchasable tiles laid over it. Earn tickets by running apps / sending
feedback; spend them here. This page has its OWN fixed arcade palette and does
NOT follow the user's theme.

Sprites live in assets/sprites/*.tdart and are editable in tools/pixel_editor.py.
"""

import math
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QFrame, QMessageBox,
)
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QColor, QFont

from techdeck.ui import pixel_art


def _sprites_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets" / "sprites"
    return Path(__file__).resolve().parents[3] / "assets" / "sprites"


# Fixed arcade palette — independent of the active theme.
EMP = {
    "wall": "#b98a6e", "banner": "#8e3fa8", "banner_text": "#ffffff",
    "tile_bg": "#f3ede2", "tile_border": "#2a1a12", "tile_text": "#2a1a12",
    "buy": "#d8402e", "buy_text": "#ffffff", "owned": "#3f9c54",
    "speech_bg": "#101014", "speech_text": "#f4f4ec", "ticket": "#f4c430",
}

# Catalog of redeemable items.
CATALOG = [
    {"id": "spinner_beyblade", "name": "Beyblade Spinner",
     "sprite": "spinner_beyblade.tdart", "cost": 60, "kind": "spinner"},
    {"id": "spinner_shuriken", "name": "Shuriken Spinner",
     "sprite": "spinner_shuriken.tdart", "cost": 100, "kind": "spinner"},
    {"id": "steeltube_game", "name": "Steel Tube Op",
     "sprite": "cartridge_steeltube.tdart", "cost": 250, "kind": "game"},
]


def _load_pixmap(name: str, target: int):
    """Render assets/sprites/<name> to a crisp pixmap whose long edge ~= target."""
    try:
        data = pixel_art.load(_sprites_dir() / name)
    except Exception:
        return None
    w, h = pixel_art.dimensions(data)
    scale = max(1, math.ceil(target / max(w, h, 1)))
    return pixel_art.render(data, scale=scale)


class StoreTile(QFrame):
    """One purchasable tile: icon + name + cost + a Buy/Equip/Owned button."""

    SIZE = 140  # matches HomePage HOME_TILE_W/H

    def __init__(self, item, page):
        super().__init__()
        self.item = item
        self.page = page
        self.setFixedWidth(self.SIZE)
        self.setStyleSheet(
            f"StoreTile {{ background:{EMP['tile_bg']}; "
            f"border:2px solid {EMP['tile_border']}; border-radius:8px; }}"
        )
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
            f"color:{EMP['tile_text']}; font-weight:600; font-size:12px; "
            "background: transparent; border: none;")
        lay.addWidget(name)
        lay.addStretch()
        self.refresh()

    def refresh(self):
        s = self.page.settings
        owned = s.is_unlocked(self.item["id"])
        if not owned:
            cost = self.item["cost"]
            self.action_btn.setText(f"BUY  {cost} \U0001F3AB")
            afford = s.get_tickets() >= cost
            self.action_btn.setEnabled(afford)
            self.action_btn.setStyleSheet(
                f"QPushButton {{ background:{EMP['buy']}; color:{EMP['buy_text']}; "
                f"border:none; border-radius:4px; padding:2px 8px; font-weight:700; }}"
                f"QPushButton:disabled {{ background:#b8b0a4; color:#efe9df; }}")
        elif self.item["kind"] == "spinner":
            equipped = s.get_equipped_spinner() == self.item["id"]
            self.action_btn.setText("EQUIPPED" if equipped else "EQUIP")
            self.action_btn.setEnabled(not equipped)
            self.action_btn.setStyleSheet(
                f"QPushButton {{ background:{EMP['owned']}; color:#fff; border:none; "
                f"border-radius:4px; padding:2px 8px; font-weight:700; }}"
                f"QPushButton:disabled {{ background:{EMP['owned']}; color:#dff5e4; }}")
        else:
            self.action_btn.setText("OWNED")
            self.action_btn.setEnabled(False)
            self.action_btn.setStyleSheet(
                f"QPushButton {{ background:{EMP['owned']}; color:#dff5e4; border:none; "
                f"border-radius:4px; padding:2px 8px; font-weight:700; }}")

    def _on_action(self):
        self.page.handle_tile_action(self.item)


class EmporiumPage(QWidget):
    """The redemption-counter scene + the catalog grid."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._bg = _load_pixmap("emporium_background.tdart", 128)
        self._counter = _load_pixmap("emporium_counter.tdart", 128)
        self._woogy = _load_pixmap("woogy.tdart", 230)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        # Banner with ticket balance.
        bar = QHBoxLayout()
        banner = QLabel("WOOGY'S EMPORIUM")
        banner.setStyleSheet(
            f"background:{EMP['banner']}; color:{EMP['banner_text']}; "
            "font-size:22px; font-weight:800; padding:8px 18px; border-radius:6px;")
        bar.addWidget(banner)
        bar.addStretch()
        self.balance_lbl = QLabel()
        self.balance_lbl.setStyleSheet(
            f"background:{EMP['banner']}; color:{EMP['ticket']}; font-size:18px; "
            "font-weight:800; padding:8px 16px; border-radius:6px;")
        bar.addWidget(self.balance_lbl)
        root.addLayout(bar)

        # Tile grid (transparent so the scene shows behind).
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

        self.refresh()

    def refresh(self):
        self.balance_lbl.setText(f"\U0001F3AB {self.settings.get_tickets()}")
        for t in self.tiles:
            t.refresh()

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
        p.fillRect(self.rect(), QColor(EMP["wall"]))
        w, h = self.width(), self.height()
        if self._bg is not None:
            p.drawPixmap(QRect(0, 0, w, h), self._bg)
        # counter across the bottom third
        if self._counter is not None:
            ch = int(h * 0.30)
            p.drawPixmap(QRect(0, h - ch, w, ch), self._counter)
        # Woogy behind the counter, centred
        if self._woogy is not None:
            ww = self._woogy.width()
            wh = self._woogy.height()
            x = (w - ww) // 2
            y = h - int(h * 0.30) - wh + 30   # overlap the counter slightly
            p.drawPixmap(x, max(y, int(h * 0.32)), self._woogy)
        # speech bubble
        self._draw_speech(p, w, h)
        p.end()

    def _draw_speech(self, p, w, h):
        bw, bh = 360, 70
        x, y = 40, h - 96
        p.fillRect(x, y, bw, bh, QColor(EMP["speech_bg"]))
        p.setPen(QColor(EMP["speech_text"]))
        f = QFont()
        f.setPointSize(11)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRect(x + 14, y, bw - 24, bh),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   "WOOGY: WHAT'LL IT BE, FELLAS?")
