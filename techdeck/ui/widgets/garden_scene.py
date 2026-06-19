"""
My House — the Garden scene.

A recreation of UFO 50's "The Garden" pet/home screen, built entirely from the
ripped sprites vendored under assets/garden/ (sPet_* PNGs). The player's house +
yard; clicking the house "pulls away" the front facade to reveal the cutaway
interior, which the player slowly furnishes with items bought at Woogy's.

Rendering model
---------------
The original runs on a fixed 384x216 pixel canvas, so we compose every layer at
that NATIVE resolution into a small buffer, then blit the buffer once, scaled by
an INTEGER factor with nearest-neighbour (no smoothing) so it stays pixel-crisp
at any window size. Letterboxed + centred in whatever space the tab gives us.

Layers (back -> front):
    BG_0            yard + EMPTY house interior (floors/rooms/stairs baked in)
    tree            6-frame idle sway, standing in the left yard
    furniture       data-driven sprites placed into the interior rooms
    HouseFG_0       the closed front facade; lifts up + fades on "open"

Furniture placement is a plain data table (FURNITURE) in native pixel coords —
first-pass estimates, easy to nudge. Later this becomes owned-item driven (buy a
couch at Woogy's -> it appears in a room here).
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Qt, QRect, QTimer, QPoint
from PySide6.QtGui import QPainter, QPixmap, QColor


# Native UFO50 canvas the whole scene is authored against.
NATIVE_W, NATIVE_H = 384, 216

# House facade bounding box in native coords (the clickable "front" — the right
# portion of the canvas; the left half is transparent yard). Used for hit-test.
HOUSE_RECT = QRect(184, 6, 200, 204)

# How far (native px) the facade lifts when opened — fully off the top edge.
FACADE_LIFT = 216

# Tree stands in the left yard; its base rests near the fence line. The 6 tree
# sprites are a GROWTH sequence (0 = unplanted/empty, 5 = full grown), not a sway
# loop — so we draw a single stage. Default to full grown; later this stage can
# track house progression so the tree visibly grows as the player invests.
TREE_POS = (16, 7)
TREE_STAGE_FULL = 5

# Furniture placed into the interior rooms: (sprite filename, native_x, native_y),
# y = top-left, positioned to sit on a floor band. Empty by design — a new house
# starts bare and fills in as the player buys items at Woogy's (the next pass
# wires this to owned items). Example of the format:
#   ("sPet_ItemCouch_0.png", 300, 178)
FURNITURE = []

_TICK_MS = 16


def _garden_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets" / "garden"
    return Path(__file__).resolve().parents[3] / "assets" / "garden"


def _ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


class GardenScene(QWidget):
    """The clickable house/yard scene. Click the house to open/close the front."""

    def __init__(self, settings=None, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(NATIVE_W, NATIVE_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        d = _garden_dir()
        self._bg = self._load(d / "sPet_BG_0.png")
        self._facade = self._load(d / "sPet_HouseFG_0.png")
        self._tree = [self._load(d / f"sPet_Tree_{i}.png") for i in range(6)]
        self._tree_stage = TREE_STAGE_FULL
        self._furniture = [(self._load(d / name), x, y) for name, x, y in FURNITURE]

        # Reveal state: progress 0 = closed, 1 = fully open; animates toward target.
        self._open_progress = 0.0
        self._open_target = 0.0

        # Cached blit geometry (filled each paint) so mouse hit-test can map
        # widget coords back to native coords.
        self._scale = 1
        self._origin = QPoint(0, 0)

        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)

    # ---- assets --------------------------------------------------------------
    @staticmethod
    def _load(path: Path):
        pm = QPixmap(str(path))
        return None if pm.isNull() else pm

    # ---- lifecycle (only animate while the tab is visible) -------------------
    def showEvent(self, e):
        super().showEvent(e)
        self.update()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._timer.stop()

    # ---- animation -----------------------------------------------------------
    def _tick(self):
        # Ease the facade toward its target a step at a time; stop the timer once
        # it settles so a static scene doesn't repaint at 60fps.
        if abs(self._open_progress - self._open_target) <= 0.001:
            self._open_progress = self._open_target
            self._timer.stop()
            return
        step = 0.06
        if self._open_progress < self._open_target:
            self._open_progress = min(self._open_target, self._open_progress + step)
        else:
            self._open_progress = max(self._open_target, self._open_progress - step)
        self.update()

    def toggle_house(self):
        self._open_target = 0.0 if self._open_target > 0.5 else 1.0
        if not self._timer.isActive():
            self._timer.start()

    # ---- input ---------------------------------------------------------------
    def mousePressEvent(self, e):
        # Map the click back into native coords and toggle if it hit the house.
        if self._scale > 0:
            nx = (e.position().x() - self._origin.x()) / self._scale
            ny = (e.position().y() - self._origin.y()) / self._scale
            if HOUSE_RECT.contains(int(nx), int(ny)) or self._open_target > 0.5:
                self.toggle_house()
        super().mousePressEvent(e)

    # ---- rendering -----------------------------------------------------------
    def _compose_native(self) -> QPixmap:
        """Draw every layer at native 384x216 into one buffer."""
        buf = QPixmap(NATIVE_W, NATIVE_H)
        buf.fill(QColor("#1b1b2a"))
        p = QPainter(buf)
        if self._bg is not None:
            p.drawPixmap(0, 0, self._bg)
        if 0 <= self._tree_stage < len(self._tree) and self._tree[self._tree_stage]:
            p.drawPixmap(TREE_POS[0], TREE_POS[1], self._tree[self._tree_stage])
        for pm, x, y in self._furniture:
            if pm is not None:
                p.drawPixmap(x, y, pm)
        if self._facade is not None:
            eased = _ease_out_cubic(self._open_progress)
            if eased < 1.0:
                p.setOpacity(1.0 - eased)
                p.drawPixmap(0, -int(FACADE_LIFT * eased), self._facade)
                p.setOpacity(1.0)
        p.end()
        return buf

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#12121c"))
        # Largest integer scale that fits, centred.
        self._scale = max(1, min(self.width() // NATIVE_W, self.height() // NATIVE_H))
        dw, dh = NATIVE_W * self._scale, NATIVE_H * self._scale
        self._origin = QPoint((self.width() - dw) // 2, (self.height() - dh) // 2)
        # Pixel-perfect: no smoothing.
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.drawPixmap(QRect(self._origin.x(), self._origin.y(), dw, dh),
                     self._compose_native())
        p.end()

    def refresh(self):
        """Re-read owned furniture etc. (placeholder until purchase-driven)."""
        self.update()
