"""
Nav editor — author the house's interior navigation graph for Buddy.

Run:  python tools/nav_editor.py

Shows the OPEN house (cutaway interior, no facade) scaled up. Drag the handles to
mark, in native pixels:
  * FLOOR lines (one per storey, ground -> attic): drag to the floor Buddy walks on.
  * STAIR ends (a lower + upper dot per staircase): drop the lower dot at the foot
    of the stairs and the upper dot where they meet the next floor.
  * the DOOR (green dot): where Buddy enters/leaves on the ground floor.

Arrow keys nudge the selected handle 1px. "Export coords" writes HOUSE_FLOORS,
HOUSE_STAIRS and HOUSE_DOOR_X to tools/placement_export.py — paste them into
garden_scene. Floors keep their full interior x-range (186..320); only Y matters
for a floor, only X matters for a stair end / the door.

Not shipped; a tuning aid only.
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QWidget, QPushButton
from PySide6.QtGui import QPainter, QColor, QPixmap, QFont
from PySide6.QtCore import Qt, QRect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
GARDEN = ROOT / "assets" / "garden"
NATIVE_W, NATIVE_H = 384, 216
SCALE = 3
BAR_H = 56
FLOOR_X0, FLOOR_X1 = 186, 320       # interior walkable x-range (fixed)

from techdeck.ui.widgets.garden_scene import (        # noqa: E402
    HOUSE_FLOORS, HOUSE_STAIRS, HOUSE_DOOR_X)

_FLOOR_NAMES = ["ground", "living", "bed/bath", "attic"]


class Handle(QWidget):
    """A draggable native-px marker. kind: 'floor' | 'stair_lo' | 'stair_hi' | 'door'."""
    COLORS = {"floor": "#ffd23f", "stair_lo": "#ff7a3f", "stair_hi": "#37c9da",
              "door": "#2bb04a"}

    def __init__(self, editor, kind, label, nx, ny):
        super().__init__(editor)
        self.editor = editor
        self.kind = kind
        self.label = label
        self.nx, self.ny = nx, ny
        self.resize(16, 16)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._grab = None
        self.reposition()

    def reposition(self):
        self.move(self.nx * SCALE - 8, self.ny * SCALE - 8)

    def set_native(self, nx, ny):
        self.nx = max(0, min(NATIVE_W, nx))
        self.ny = max(0, min(NATIVE_H, ny))
        self.reposition()
        self.editor.show_status(self)
        self.editor.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setBrush(QColor(self.COLORS[self.kind]))
        p.setPen(QColor("#0c0a1e"))
        p.drawEllipse(2, 2, 12, 12)
        p.end()

    def mousePressEvent(self, e):
        self._grab = e.position().toPoint()
        self.raise_()
        self.editor.selected = self
        self.editor.show_status(self)

    def mouseMoveEvent(self, e):
        if self._grab is None:
            return
        g = self.pos() + (e.position().toPoint() - self._grab)
        self.set_native(round((g.x() + 8) / SCALE), round((g.y() + 8) / SCALE))

    def mouseReleaseEvent(self, _e):
        self._grab = None


class Editor(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("My House — nav editor  (drag floors/stairs/door; Export)")
        self.setFixedSize(NATIVE_W * SCALE, NATIVE_H * SCALE + BAR_H)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._bg = QPixmap(str(GARDEN / "sPet_BG_0.png"))
        self._tree = QPixmap(str(GARDEN / "sPet_Tree_5.png"))
        self._wall = QPixmap(str(GARDEN / "sLibraryBG_4.png")).scaled(
            NATIVE_W * SCALE, NATIVE_H * SCALE, Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation)
        self.selected = None

        self.floors = [Handle(self, "floor", _FLOOR_NAMES[i] if i < len(_FLOOR_NAMES)
                              else f"floor{i}", FLOOR_X0 - 6, f["y"])
                       for i, f in enumerate(HOUSE_FLOORS)]
        self.stairs = []           # list of (lo_handle, hi_handle)
        for i, st in enumerate(HOUSE_STAIRS):
            lo = Handle(self, "stair_lo", f"stair{i} lo", st["x_lo"], HOUSE_FLOORS[i]["y"])
            hi = Handle(self, "stair_hi", f"stair{i} hi", st["x_hi"], HOUSE_FLOORS[i + 1]["y"])
            self.stairs.append((lo, hi))
        self.door = Handle(self, "door", "door", HOUSE_DOOR_X, HOUSE_FLOORS[0]["y"])

        for h in self._all_handles():
            h.show()

        btn = QPushButton("Export coords", self)
        btn.setGeometry(NATIVE_W * SCALE - 160, NATIVE_H * SCALE + 12, 150, 32)
        btn.clicked.connect(self.export)
        self.status_text = "Drag the floor lines, stair dots, and the door."

    def _all_handles(self):
        hs = list(self.floors) + [self.door]
        for lo, hi in self.stairs:
            hs += [lo, hi]
        return hs

    def show_status(self, h):
        self.status_text = f"{h.label:<12} x={h.nx}  y={h.ny}"
        self.update()

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
        p.drawPixmap(26 * SCALE, -8 * SCALE, self._tree.width() * SCALE,
                     self._tree.height() * SCALE, self._tree)
        # Floor lines across the interior width.
        p.setPen(QColor(255, 210, 63, 200))
        for h in self.floors:
            y = h.ny * SCALE
            p.drawLine(FLOOR_X0 * SCALE, y, FLOOR_X1 * SCALE, y)
        # Stair connectors.
        p.setPen(QColor(255, 122, 63, 220))
        for lo, hi in self.stairs:
            p.drawLine(lo.nx * SCALE, lo.ny * SCALE, hi.nx * SCALE, hi.ny * SCALE)
        p.setPen(QColor("#eee"))
        p.setFont(QFont("Consolas", 11))
        p.drawText(QRect(10, NATIVE_H * SCALE + 8, NATIVE_W * SCALE - 180, 40),
                   Qt.AlignmentFlag.AlignVCenter, self.status_text)
        p.end()

    def export(self):
        lines = ["HOUSE_FLOORS = ["]
        for h in self.floors:
            lines.append(f'    {{"y": {h.ny}, "x0": {FLOOR_X0}, "x1": {FLOOR_X1}}},')
        lines.append("]")
        lines.append("HOUSE_STAIRS = [")
        for lo, hi in self.stairs:
            lines.append(f'    {{"x_lo": {lo.nx}, "x_hi": {hi.nx}}},')
        lines.append("]")
        lines.append(f"HOUSE_DOOR_X = {self.door.nx}")
        out = ROOT / "tools" / "placement_export.py"
        out.write_text("\n".join(lines), encoding="utf-8")
        self.status_text = f"Exported nav graph -> {out}"
        self.update()
        print("\n".join(lines))
        print(f"\nWrote {out}")


def main():
    app = QApplication(sys.argv)
    w = Editor()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
