"""
Furniture placer — a standalone dev tool for dialing in My House furniture spots.

Run:  python tools/furniture_placer.py

Shows the open house (wallpaper + BG_0 interior, no facade) scaled up, with every
furniture sprite loaded at its CURRENT PLACEMENT position. Drag items where they
belong; nudge the selected item 1 native px at a time with the arrow keys. Click
"Export coords" to write the exact native (x,y) for each item to
tools/placement_export.py — paste that back into garden_scene.PLACEMENT.

Not shipped; a tuning aid only.
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QWidget, QLabel, QPushButton
from PySide6.QtGui import QPixmap, QPainter, QColor
from PySide6.QtCore import Qt, QPoint

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
GARDEN = ROOT / "assets" / "garden"
NATIVE_W, NATIVE_H = 384, 216
SCALE = 3                       # bump to 4 if your screen is big enough
BAR_H = 56

from techdeck.ui.widgets.garden_scene import PLACEMENT          # noqa: E402
from techdeck.ui.pages.emporium_page import CATALOG             # noqa: E402

_CAT = {c["id"]: c for c in CATALOG}


def _name(item_id):
    c = _CAT.get(item_id)
    return c["name"] if c else item_id


class Item(QLabel):
    """One draggable, pixel-snapping furniture sprite."""

    def __init__(self, placer, item_id, sprite, nx, ny):
        super().__init__(placer)
        self.placer = placer
        self.item_id = item_id
        self.nx, self.ny = nx, ny
        pm = QPixmap(str(GARDEN / sprite))
        self.setPixmap(pm.scaled(pm.width() * SCALE, pm.height() * SCALE,
                                 Qt.AspectRatioMode.IgnoreAspectRatio,
                                 Qt.TransformationMode.FastTransformation))
        self.adjustSize()
        self.setToolTip(f"{_name(item_id)} ({item_id})")
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._grab = None
        self.reposition()

    def reposition(self):
        self.move(self.nx * SCALE, self.ny * SCALE)

    def set_native(self, nx, ny):
        self.nx = max(0, min(NATIVE_W - 1, nx))
        self.ny = max(0, min(NATIVE_H - 1, ny))
        self.reposition()
        self.placer.show_status(self)

    def mousePressEvent(self, e):
        self._grab = e.position().toPoint()
        self.raise_()
        self.placer.selected = self
        self.placer.show_status(self)

    def mouseMoveEvent(self, e):
        if self._grab is None:
            return
        delta = e.position().toPoint() - self._grab
        g = self.pos() + delta
        self.set_native(round(g.x() / SCALE), round(g.y() / SCALE))

    def mouseReleaseEvent(self, _e):
        self._grab = None


class Placer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("My House — furniture placer  (drag; arrows nudge; Export)")
        self.setFixedSize(NATIVE_W * SCALE, NATIVE_H * SCALE + BAR_H)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._bg = QPixmap(str(GARDEN / "sPet_BG_0.png"))
        self._wall = QPixmap(str(GARDEN / "sLibraryBG_4.png")).scaled(
            NATIVE_W * SCALE, NATIVE_H * SCALE, Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation)
        self.selected = None

        self.items = []
        for item_id, (x, y) in PLACEMENT.items():
            if item_id in _CAT:
                it = Item(self, item_id, _CAT[item_id]["sprite"], x, y)
                it.show()
                self.items.append(it)

        self.status = QLabel("Drag a piece (or click it, then nudge with arrow keys).",
                             self)
        self.status.setStyleSheet("color:#eee; font: 13px 'Consolas';")
        self.status.setGeometry(10, NATIVE_H * SCALE + 8, NATIVE_W * SCALE - 180, 40)

        btn = QPushButton("Export coords", self)
        btn.setGeometry(NATIVE_W * SCALE - 160, NATIVE_H * SCALE + 12, 150, 32)
        btn.clicked.connect(self.export)

    def show_status(self, item):
        self.status.setText(f"{_name(item.item_id):<14} {item.item_id:<16} "
                            f"x={item.nx}  y={item.ny}")

    def keyPressEvent(self, e):
        if self.selected is None:
            return
        k = e.key()
        dx = (k == Qt.Key.Key_Right) - (k == Qt.Key.Key_Left)
        dy = (k == Qt.Key.Key_Down) - (k == Qt.Key.Key_Up)
        if dx or dy:
            self.selected.set_native(self.selected.nx + dx, self.selected.ny + dy)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.drawTiledPixmap(0, 0, NATIVE_W * SCALE, NATIVE_H * SCALE, self._wall)
        p.fillRect(0, NATIVE_H * SCALE, self.width(), BAR_H, QColor("#15151f"))
        p.drawPixmap(0, 0, NATIVE_W * SCALE, NATIVE_H * SCALE, self._bg)
        p.end()

    def export(self):
        lines = ["PLACEMENT = {"]
        for it in sorted(self.items, key=lambda i: i.item_id):
            lines.append(f'    "{it.item_id}": ({it.nx}, {it.ny}),')
        lines.append("}")
        out = ROOT / "tools" / "placement_export.py"
        out.write_text("\n".join(lines), encoding="utf-8")
        self.status.setText(f"Exported {len(self.items)} items -> {out}")
        print("\n".join(lines))
        print(f"\nWrote {out}")


def main():
    app = QApplication(sys.argv)
    w = Placer()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
