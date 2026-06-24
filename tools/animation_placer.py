"""
Animation placer — dial in where Buddy's interaction sprite sits at each yard item.

Run:  python tools/animation_placer.py

Shows the closed-house yard with every interactive item (hot tub, picnic, easel,
garden plot, jump rope, lily pad) drawn at its PLACEMENT spot, and Buddy's matching
interaction sprite (first frame) laid over each one as a DRAGGABLE piece. Drag /
arrow-key-nudge each Buddy sprite until it lines up with its item, then click
"Export coords" to write BUDDY_ACT_PLACEMENT to tools/placement_export.py — paste
that back into garden_scene.

Pieces start at the same computed default the scene uses (centred over the item,
feet at its base) unless garden_scene.BUDDY_ACT_PLACEMENT already overrides them.

Not shipped; a tuning aid only.
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QWidget, QLabel, QPushButton
from PySide6.QtGui import QPixmap, QPainter, QColor
from PySide6.QtCore import Qt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
GARDEN = ROOT / "assets" / "garden"
NATIVE_W, NATIVE_H = 384, 216
SCALE = 3
BAR_H = 56

from techdeck.ui.widgets.garden_scene import (        # noqa: E402
    PLACEMENT, BUDDY_INTERACTIONS, BUDDY_ACT_PLACEMENT)
from techdeck.ui.pages.emporium_page import CATALOG    # noqa: E402

_CAT = {c["id"]: c for c in CATALOG}


def _act_sprite(item_id):
    return f"sPet_Buddy{BUDDY_INTERACTIONS[item_id]['anim']}_0.png"


def _default_pos(item_id, act_pm):
    """Mirror garden_scene._act_pos default: centred over the item, feet at base."""
    item_pm = QPixmap(str(GARDEN / _CAT[item_id]["sprite"]))
    ix, iy = PLACEMENT[item_id]
    return (ix + item_pm.width() // 2 - act_pm.width() // 2,
            iy + item_pm.height() - act_pm.height())


class Act(QLabel):
    """One draggable Buddy interaction sprite (snaps to native px)."""

    def __init__(self, placer, item_id):
        super().__init__(placer)
        self.placer = placer
        self.item_id = item_id
        pm = QPixmap(str(GARDEN / _act_sprite(item_id)))
        self.nw, self.nh = pm.width(), pm.height()
        nx, ny = BUDDY_ACT_PLACEMENT.get(item_id) or _default_pos(item_id, pm)
        self.nx, self.ny = nx, ny
        self.setPixmap(pm.scaled(pm.width() * SCALE, pm.height() * SCALE,
                                 Qt.AspectRatioMode.IgnoreAspectRatio,
                                 Qt.TransformationMode.FastTransformation))
        self.adjustSize()
        self.setToolTip(f"{item_id} -> Buddy{BUDDY_INTERACTIONS[item_id]['anim']}")
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._grab = None
        self.reposition()

    def reposition(self):
        self.move(self.nx * SCALE, self.ny * SCALE)

    def set_native(self, nx, ny):
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
        g = self.pos() + (e.position().toPoint() - self._grab)
        self.set_native(round(g.x() / SCALE), round(g.y() / SCALE))

    def mouseReleaseEvent(self, _e):
        self._grab = None


class Placer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("My House — animation placer  (drag; arrows nudge; Export)")
        self.setFixedSize(NATIVE_W * SCALE, NATIVE_H * SCALE + BAR_H)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._bg = QPixmap(str(GARDEN / "sPet_BG_0.png"))
        self._facade = QPixmap(str(GARDEN / "sPet_HouseFG_0.png"))
        self._tree = QPixmap(str(GARDEN / "sPet_Tree_5.png"))
        self._wall = QPixmap(str(GARDEN / "sLibraryBG_4.png")).scaled(
            NATIVE_W * SCALE, NATIVE_H * SCALE, Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation)
        # Item sprites drawn as static context (so you can line Buddy up to them).
        self._items = [(item_id, QPixmap(str(GARDEN / _CAT[item_id]["sprite"])),
                        PLACEMENT[item_id])
                       for item_id in BUDDY_INTERACTIONS if item_id in PLACEMENT]
        self.selected = None
        self.acts = [Act(self, item_id) for item_id in BUDDY_INTERACTIONS
                     if item_id in PLACEMENT]

        self.status = QLabel("Drag a Buddy sprite onto its item (or click it, then "
                             "nudge with arrow keys).", self)
        self.status.setStyleSheet("color:#eee; font: 13px 'Consolas';")
        self.status.setGeometry(10, NATIVE_H * SCALE + 8, NATIVE_W * SCALE - 180, 40)

        btn = QPushButton("Export coords", self)
        btn.setGeometry(NATIVE_W * SCALE - 160, NATIVE_H * SCALE + 12, 150, 32)
        btn.clicked.connect(self.export)

    def show_status(self, act):
        self.status.setText(f"{act.item_id:<16} x={act.nx}  y={act.ny}")

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
        t = self._tree
        p.drawPixmap(26 * SCALE, -8 * SCALE, t.width() * SCALE, t.height() * SCALE, t)
        p.drawPixmap(0, 0, NATIVE_W * SCALE, NATIVE_H * SCALE, self._facade)
        # The interactive items, at their real spots, as alignment context.
        for _id, pm, (ix, iy) in self._items:
            p.drawPixmap(ix * SCALE, iy * SCALE, pm.width() * SCALE, pm.height() * SCALE, pm)
        p.end()

    def export(self):
        lines = ["BUDDY_ACT_PLACEMENT = {"]
        for a in sorted(self.acts, key=lambda i: i.item_id):
            lines.append(f'    "{a.item_id}": ({a.nx}, {a.ny}),')
        lines.append("}")
        out = ROOT / "tools" / "placement_export.py"
        out.write_text("\n".join(lines), encoding="utf-8")
        self.status.setText(f"Exported {len(self.acts)} positions -> {out}")
        print("\n".join(lines))
        print(f"\nWrote {out}")


def main():
    app = QApplication(sys.argv)
    w = Placer()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
