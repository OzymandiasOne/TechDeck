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

from techdeck.ui.widgets.garden_scene import (PLACEMENT, EXTERIOR,   # noqa: E402
                                              TREE_PLACEMENT)
from techdeck.ui.pages.emporium_page import CATALOG                  # noqa: E402

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
        self.nw, self.nh = pm.width(), pm.height()   # native size, for clamping
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
        # Allow items to extend off any edge (large sprites like the tree need to
        # sit partly off-screen); keep at least ~8px on-canvas so it stays grabbable.
        self.nx = max(-self.nw + 8, min(NATIVE_W - 8, nx))
        self.ny = max(-self.nh + 8, min(NATIVE_H - 8, ny))
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
        self._facade = QPixmap(str(GARDEN / "sPet_HouseFG_0.png"))
        self._tree = QPixmap(str(GARDEN / "sPet_Tree_5.png"))   # full-grown
        self._wall = QPixmap(str(GARDEN / "sLibraryBG_4.png")).scaled(
            NATIVE_W * SCALE, NATIVE_H * SCALE, Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation)
        self.selected = None
        # "interior" (open house) | "exterior" (closed + yard) | "tree" (one stage)
        self.mode = "interior"
        self.tree_sel = 5        # start on the full tree — place it first

        self.items = []
        for item_id, (x, y) in PLACEMENT.items():
            if item_id in _CAT:
                it = Item(self, item_id, _CAT[item_id]["sprite"], x, y)
                self.items.append(it)
        # One draggable widget per tree growth stage (1..5), aligned so they all
        # share a root point. The full tree is drawn faint as a reference.
        self.tree_items = [Item(self, f"tree_{n}", f"sPet_Tree_{n}.png",
                                *TREE_PLACEMENT[n]) for n in range(1, 6)]

        self.status = QLabel("Drag a piece (or click it, then nudge with arrow keys).",
                             self)
        self.status.setStyleSheet("color:#eee; font: 13px 'Consolas';")

        # Size the view button to its widest label in the ACTUAL font (the
        # app theme's font is wider than the standalone default — a fixed
        # 145px clipped the text when embedded in the DevKit).
        self.mode_btn = QPushButton("View: Interior  (Tab)", self)
        bw = max(self.mode_btn.fontMetrics().horizontalAdvance(t) for t in (
            "View: Interior  (Tab)", "View: Exterior  (Tab)",
            "View: Tree 5/5  ([ ])")) + 28
        self.mode_btn.setGeometry(NATIVE_W * SCALE - 170 - bw,
                                  NATIVE_H * SCALE + 12, bw, 32)
        self.status.setGeometry(10, NATIVE_H * SCALE + 8,
                                NATIVE_W * SCALE - 190 - bw, 40)
        self.mode_btn.clicked.connect(self.toggle_mode)

        btn = QPushButton("Export coords", self)
        btn.setGeometry(NATIVE_W * SCALE - 160, NATIVE_H * SCALE + 12, 150, 32)
        btn.clicked.connect(self.export)
        self.apply_mode()

    def show_status(self, item):
        self.status.setText(f"{_name(item.item_id):<14} {item.item_id:<16} "
                            f"x={item.nx}  y={item.ny}")

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Tab:
            self.toggle_mode()
            return
        if self.mode == "tree" and e.key() in (Qt.Key.Key_BracketLeft,
                                               Qt.Key.Key_BracketRight):
            step = 1 if e.key() == Qt.Key.Key_BracketRight else -1
            self.tree_sel = max(1, min(5, self.tree_sel + step))
            self.apply_mode()
            return
        if self.selected is None:
            return
        k = e.key()
        dx = (k == Qt.Key.Key_Right) - (k == Qt.Key.Key_Left)
        dy = (k == Qt.Key.Key_Down) - (k == Qt.Key.Key_Up)
        if dx or dy:
            self.selected.set_native(self.selected.nx + dx, self.selected.ny + dy)

    def toggle_mode(self):
        order = ["interior", "exterior", "tree"]
        self.mode = order[(order.index(self.mode) + 1) % len(order)]
        self.apply_mode()

    def apply_mode(self):
        """Show only the items for the current view. Exterior closes the house
        (facade); Tree shows one growth stage at a time over a faint full tree."""
        m = self.mode
        for it in self.items:
            it.setVisible(m != "tree" and (it.item_id in EXTERIOR) == (m == "exterior"))
        for i, it in enumerate(self.tree_items, start=1):
            it.setVisible(m == "tree" and i == self.tree_sel)
        if m == "tree":
            self.mode_btn.setText(f"View: Tree {self.tree_sel}/5  ([ ])")
        else:
            self.mode_btn.setText(
                f"View: {'Exterior' if m == 'exterior' else 'Interior'}  (Tab)")
        self.selected = None
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.drawTiledPixmap(0, 0, NATIVE_W * SCALE, NATIVE_H * SCALE, self._wall)
        p.fillRect(0, NATIVE_H * SCALE, self.width(), BAR_H, QColor("#15151f"))
        p.drawPixmap(0, 0, NATIVE_W * SCALE, NATIVE_H * SCALE, self._bg)
        tw, th = self._tree.width() * SCALE, self._tree.height() * SCALE
        # The full tree follows ITS OWN (stage-5) placement, so it's the live
        # reference for the smaller stages and for tree-side furniture.
        t5 = self.tree_items[4]
        tx, ty = t5.nx * SCALE, t5.ny * SCALE
        if self.mode == "tree":
            if self.tree_sel != 5:   # ghost the placed full tree to align against
                p.setOpacity(0.30)
                p.drawPixmap(tx, ty, tw, th, self._tree)
                p.setOpacity(1.0)
        else:
            p.drawPixmap(tx, ty, tw, th, self._tree)   # solid, for furniture context
            if self.mode == "exterior":   # close the house so the facade/roof shows
                p.drawPixmap(0, 0, NATIVE_W * SCALE, NATIVE_H * SCALE, self._facade)
        p.end()

    def export(self):
        lines = ["PLACEMENT = {"]
        for it in sorted(self.items, key=lambda i: i.item_id):
            lines.append(f'    "{it.item_id}": ({it.nx}, {it.ny}),')
        lines.append("}")
        lines.append("")
        lines.append("TREE_PLACEMENT = {")
        for i, it in enumerate(self.tree_items, start=1):
            lines.append(f"    {i}: ({it.nx}, {it.ny}),")
        lines.append("}")
        out = ROOT / "tools" / "placement_export.py"
        out.write_text("\n".join(lines), encoding="utf-8")
        self.status.setText(f"Exported {len(self.items)} items + tree -> {out}")
        print("\n".join(lines))
        print(f"\nWrote {out}")


def main():
    app = QApplication(sys.argv)
    w = Placer()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
