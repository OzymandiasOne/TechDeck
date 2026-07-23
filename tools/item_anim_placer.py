"""
Item animation placer — preview each animated item's clip playing in-scene and
confirm it registers against the item's default (catalog) sprite.

Run:  python tools/item_anim_placer.py

Reads ITEM_ANIM_FRAMES from garden_scene: item id -> ordered list of sprite files
that play as one animation while Buddy interacts with the item. The catalog base
sprite is drawn FIXED at the item's PLACEMENT and tinted magenta (the "ghost") as
an alignment reference; the moving clip is drawn on top at its own origin
(ITEM_ANIM_PLACEMENT, defaulting to PLACEMENT). For same-canvas clips (chest, tub,
TV, stove) the two coincide and nothing needs moving. For a bigger-canvas clip
(the telescope, whose zoom frames are 64x80 over a 16x32 still) you DRAG the clip
until its item portion sits exactly over the magenta ghost.

Controls:
  * Click a clip to select it; drag, or arrow-nudge, to set its origin.
  * Tab toggles INTERIOR (open cutaway house) / EXTERIOR (closed yard) view.
  * Space pauses/resumes; , / . step one frame while paused.
  * [ / ] slow down / speed up playback.
  * G toggles the magenta base-sprite ghost.
  * Export writes the ITEM_ANIM_PLACEMENT overrides to tools/placement_export.py.

Ping-pong clips (ITEM_ANIM_PINGPONG) preview as 0 1 2 3 4 3 2 1 0, matching how
they play in-scene. Not shipped; a tuning aid only.
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QWidget, QLabel, QPushButton
from PySide6.QtGui import QPixmap, QPainter, QColor, QImage
from PySide6.QtCore import Qt, QTimer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
GARDEN = ROOT / "assets" / "garden"
NATIVE_W, NATIVE_H = 384, 216
SCALE = 4
BAR_H = 64

from techdeck.ui.widgets.garden_scene import (        # noqa: E402
    PLACEMENT, EXTERIOR, ITEM_ANIM_FRAMES, ITEM_ANIM_PLACEMENT, ITEM_ANIM_PINGPONG,
    ITEM_ANIM_PEAK_HOLD_S, AMBIENT_ANIM)
from techdeck.ui.pages.emporium_page import CATALOG    # noqa: E402

_CAT = {c["id"]: c for c in CATALOG}


def _ghost(pm):
    """A faint magenta-tinted copy of a pixmap, for the base-sprite underlay."""
    img = pm.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    for y in range(img.height()):
        for x in range(img.width()):
            if img.pixelColor(x, y).alpha() > 0:
                img.setPixelColor(x, y, QColor(255, 0, 200, 160))
    return QPixmap.fromImage(img)


def _pingpong(n, peak_holds=1):
    """Frame index order for an n-frame ping-pong: 0..n-1, then the apex frame
    repeated `peak_holds` times (the dwell), then n-2..1."""
    if n <= 1:
        return [0]
    return list(range(n)) + [n - 1] * (peak_holds - 1) + list(range(n - 2, 0, -1))


class AnimItem:
    """One animated item: its frame clip, base-sprite ghost (at PLACEMENT), and
    its own draggable clip origin."""

    def __init__(self, item_id):
        self.item_id = item_id
        self.interior = item_id not in EXTERIOR
        self.frames = [QPixmap(str(GARDEN / f)) for f in ITEM_ANIM_FRAMES[item_id]]
        self.frames = [p for p in self.frames if not p.isNull()]
        self.nw = max((p.width() for p in self.frames), default=16)
        self.nh = max((p.height() for p in self.frames), default=24)
        # Fixed base-sprite ghost at the item's PLACEMENT.
        base_name = _CAT.get(item_id, {}).get("sprite")
        base = QPixmap(str(GARDEN / base_name)) if base_name else QPixmap()
        self.ghost = _ghost(base) if not base.isNull() else None
        self.base_xy = PLACEMENT.get(item_id, (0, 0))
        # Draggable clip origin (its own override, else the item placement).
        self.cx, self.cy = ITEM_ANIM_PLACEMENT.get(item_id, self.base_xy)
        self.pingpong = item_id in ITEM_ANIM_PINGPONG
        self.peak_hold_s = ITEM_ANIM_PEAK_HOLD_S.get(item_id, 0.0)
        self.order = list(range(len(self.frames)))
        self.step = 0

    def rebuild_order(self, interval_ms):
        """Recompute the play order for the current frame interval so the apex
        dwell stays ~peak_hold_s of wall-clock time regardless of playback speed."""
        n = len(self.frames)
        if self.pingpong:
            holds = max(1, round(self.peak_hold_s * 1000 / max(interval_ms, 1)))
            self.order = _pingpong(n, holds)
        else:
            self.order = list(range(n))

    @property
    def frame_idx(self):
        return self.order[self.step % len(self.order)]

    def contains(self, nx, ny):
        return self.cx <= nx < self.cx + self.nw and self.cy <= ny < self.cy + self.nh


class Placer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Item animation placer  (click/drag; arrows nudge; "
                            "Space; ,/. step; [ ] speed; G ghost; Tab; Export)")
        self.setFixedSize(NATIVE_W * SCALE, NATIVE_H * SCALE + BAR_H)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._bg = QPixmap(str(GARDEN / "sPet_BG_0.png"))
        self._facade = QPixmap(str(GARDEN / "sPet_HouseFG_0.png"))
        self._tree = QPixmap(str(GARDEN / "sPet_Tree_5.png"))
        self.mode = "interior"     # the animated items so far all live inside
        self.playing = True
        self.show_ghost = True
        self.interval = 360
        self.items = [AnimItem(i) for i in ITEM_ANIM_FRAMES if i in PLACEMENT]
        for a in self.items:
            a.rebuild_order(self.interval)
        self.selected = next((a for a in self.items if a.interior), None) \
            or (self.items[0] if self.items else None)
        self._grab = None

        self.status = QLabel("", self)
        self.status.setStyleSheet("color:#eee; font: 13px 'Consolas';")

        # Width from font metrics — a fixed 150px clips the label in the
        # app theme's wider font (DevKit embed).
        self.mode_btn = QPushButton("View: Interior  (Tab)", self)
        bw = max(self.mode_btn.fontMetrics().horizontalAdvance(t) for t in (
            "View: Interior  (Tab)", "View: Exterior  (Tab)")) + 28
        self.mode_btn.setGeometry(NATIVE_W * SCALE - 180 - bw,
                                  NATIVE_H * SCALE + 16, bw, 32)
        self.status.setGeometry(10, NATIVE_H * SCALE + 8,
                                NATIVE_W * SCALE - 200 - bw, 48)
        self.mode_btn.clicked.connect(self.toggle_mode)
        btn = QPushButton("Export coords", self)
        btn.setGeometry(NATIVE_W * SCALE - 170, NATIVE_H * SCALE + 16, 160, 32)
        btn.clicked.connect(self.export)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(self.interval)
        self._update_status()

    # ---- playback ------------------------------------------------------------
    def _tick(self):
        if not self.playing:
            return
        self._step(+1)

    def _step(self, d):
        for a in self.items:
            a.step += d
        self.update()

    # ---- input ---------------------------------------------------------------
    def _to_native(self, pos):
        return round(pos.x() / SCALE), round(pos.y() / SCALE)

    def mousePressEvent(self, e):
        nx, ny = self._to_native(e.position())
        interior = self.mode == "interior"
        for a in self.items:
            if a.interior == interior and a.contains(nx, ny):
                self.selected = a
                self._grab = (nx - a.cx, ny - a.cy)
                self._update_status()
                self.update()
                return

    def mouseMoveEvent(self, e):
        if self._grab is None or self.selected is None:
            return
        nx, ny = self._to_native(e.position())
        self._set_pos(nx - self._grab[0], ny - self._grab[1])

    def mouseReleaseEvent(self, _e):
        self._grab = None

    def _set_pos(self, cx, cy):
        a = self.selected
        a.cx = max(-a.nw + 4, min(NATIVE_W - 4, cx))
        a.cy = max(-a.nh + 4, min(NATIVE_H - 4, cy))
        self._update_status()
        self.update()

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key.Key_Tab:
            self.toggle_mode()
        elif k == Qt.Key.Key_Space:
            self.playing = not self.playing
            self._update_status()
        elif k == Qt.Key.Key_G:
            self.show_ghost = not self.show_ghost
            self.update()
        elif k == Qt.Key.Key_Comma:
            self.playing = False
            self._step(-1)
            self._update_status()
        elif k == Qt.Key.Key_Period:
            self.playing = False
            self._step(+1)
            self._update_status()
        elif k in (Qt.Key.Key_BracketLeft, Qt.Key.Key_BracketRight):
            self.interval = max(60, min(1200, self.interval
                                        + (60 if k == Qt.Key.Key_BracketRight else -60)))
            self.timer.start(self.interval)
            for a in self.items:            # keep the apex dwell ~constant in seconds
                a.rebuild_order(self.interval)
            self._update_status()
        elif self.selected is not None:
            dx = (k == Qt.Key.Key_Right) - (k == Qt.Key.Key_Left)
            dy = (k == Qt.Key.Key_Down) - (k == Qt.Key.Key_Up)
            if dx or dy:
                self._set_pos(self.selected.cx + dx, self.selected.cy + dy)

    def toggle_mode(self):
        self.mode = "exterior" if self.mode == "interior" else "interior"
        self.mode_btn.setText(f"View: {'Interior' if self.mode == 'interior' else 'Exterior'}  (Tab)")
        interior = self.mode == "interior"
        if self.selected is None or self.selected.interior != interior:
            self.selected = next((a for a in self.items if a.interior == interior), None)
        self._update_status()
        self.update()

    def _update_status(self):
        a = self.selected
        play = "PLAY" if self.playing else "PAUSE"
        if a is None:
            self.status.setText(f"[{play} {self.interval}ms]  no animated item in this view")
            return
        moved = (a.cx, a.cy) != a.base_xy
        tag = "  (clip origin != placement)" if moved else ""
        trig = "ambient" if a.item_id in AMBIENT_ANIM else "buddy"
        self.status.setText(
            f"[{play} {self.interval}ms]  {a.item_id:<14} <{trig}> clip=({a.cx},{a.cy}) "
            f"base={a.base_xy}{tag}\n"
            f"frame {a.frame_idx} ({a.nw}x{a.nh})   "
            f"magenta ghost = catalog still; line the clip's item up over it")

    # ---- rendering -----------------------------------------------------------
    def _blit(self, p, pm, nx, ny):
        p.drawPixmap(nx * SCALE, ny * SCALE, pm.width() * SCALE,
                     pm.height() * SCALE, pm)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.fillRect(self.rect(), QColor("#15151f"))
        self._blit(p, self._bg, 0, 0)
        self._blit(p, self._tree, 26, -8)
        interior = self.mode == "interior"
        for a in self.items:
            if a.interior != interior or not a.frames:
                continue
            if self.show_ghost and a.ghost is not None:
                self._blit(p, a.ghost, a.base_xy[0], a.base_xy[1])
            self._blit(p, a.frames[a.frame_idx], a.cx, a.cy)
            if a is self.selected:
                p.setPen(QColor("#39d0ff"))
                p.drawRect(a.cx * SCALE, a.cy * SCALE, a.nw * SCALE, a.nh * SCALE)
        if not interior:
            self._blit(p, self._facade, 0, 0)
        p.fillRect(0, NATIVE_H * SCALE, self.width(), BAR_H, QColor("#15151f"))
        p.end()

    def export(self):
        lines = ["# ITEM_ANIM_PLACEMENT overrides (paste into garden_scene; only the",
                 "# clips whose origin differs from the item PLACEMENT are needed)",
                 "ITEM_ANIM_PLACEMENT = {"]
        for a in sorted(self.items, key=lambda i: i.item_id):
            if (a.cx, a.cy) != a.base_xy:
                lines.append(f'    "{a.item_id}": ({a.cx}, {a.cy}),')
        lines.append("}")
        out = ROOT / "tools" / "placement_export.py"
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.status.setText(f"Exported overrides -> {out}")
        print("\n".join(lines))
        print(f"\nWrote {out}")


def main():
    app = QApplication(sys.argv)
    w = Placer()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
