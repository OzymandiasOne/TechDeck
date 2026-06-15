"""
TechDeck Fidget Spinner

A standalone, frameless, always-on-top fidget spinner drawn as PIXEL ART in the
moth's theme-coloured style. The shape is generated procedurally — a centre hub,
N arms, N lobes, all ONE connected piece — and rendered to a pixmap once;
spinning just rotates that pixmap with smoothing OFF so the pixels stay
hard-edged at every angle.

It has FOUR arms at 0/90/180/270 degrees. On a square pixel grid a 4-fold shape
is perfectly symmetric (a 90-degree rotation maps cells exactly onto cells),
which 3 arms can never be.

Reshape it by editing the geometry constants below (all in grid cells). Bump
GRID for more resolution; keep the content radius (_LOBE_DIST + _LOBE_R + 1)
inside GRID/2 so nothing clips as it spins. Preview edits without launching the
app via `python tools/preview_spinner.py`.

  - Click anywhere on it to add spin (and drag to move it).
  - It does NOT close on double-click (that fought with clicking to spin);
    `/clear` puts it away (see CommandHandler.stop_session_effects).
"""

import math

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QColor, QPixmap


# Pixel grid: each cell is CELL px. GRID is sized so the content radius fits with
# a margin (also the rotation radius, so nothing clips while it spins).
GRID = 51
CELL = 6
_CENTER = GRID / 2.0

# Geometry, in grid cells.
_HUB_R = 7.5          # centre hub radius
_HUB_HOLE = 3.5       # centre bearing hole
_LOBE_DIST = 16.0     # hub centre -> lobe centre
_LOBE_R = 7.0         # lobe radius
_LOBE_HOLE = 3.5      # lobe bearing hole
_ARM_HW = 4.0         # half-width of each arm (connects hub to lobe)
_RING_W = 1.8         # bright bearing ring just outside each hole
_LOBE_ANGLES_DEG = (-90.0, 0.0, 90.0, 180.0)   # four arms, 90 apart -> symmetric

# base codes: 0 empty, 1 hub/arm, 2 wing (lobe). deco codes: 0 none,
# 1 outline (on empty), 2 bearing ring, 3 highlight bevel.
_HUB, _WING = 1, 2
_OUTLINE, _RING, _HILITE = 1, 2, 3


def _seg_dist(px, py, ax, ay, bx, by):
    """Distance from point P to segment AB (for the connecting arms)."""
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 == 0.0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _build_spinner_grids():
    """Build (base, deco) grids: hub/arm vs wing for each solid cell, plus the
    outline (traced around the silhouette and every hole), the bright ring just
    outside each hole, and a highlight bevel on cells against the outer rim."""
    lobes = [(_CENTER + _LOBE_DIST * math.cos(math.radians(a)),
              _CENTER + _LOBE_DIST * math.sin(math.radians(a)))
             for a in _LOBE_ANGLES_DEG]
    holes = [(_CENTER, _CENTER, _HUB_HOLE)] + [(lx, ly, _LOBE_HOLE) for lx, ly in lobes]

    base = [[0] * GRID for _ in range(GRID)]
    for gy in range(GRID):
        for gx in range(GRID):
            px, py = gx + 0.5, gy + 0.5
            if any(math.hypot(px - hx, py - hy) <= hr for hx, hy, hr in holes):
                continue  # bearing hole -> empty
            if any(math.hypot(px - lx, py - ly) <= _LOBE_R for lx, ly in lobes):
                base[gy][gx] = _WING
            elif (math.hypot(px - _CENTER, py - _CENTER) <= _HUB_R or
                  any(_seg_dist(px, py, _CENTER, _CENTER, lx, ly) <= _ARM_HW
                      for lx, ly in lobes)):
                base[gy][gx] = _HUB

    solid = lambda gx, gy: 0 <= gx < GRID and 0 <= gy < GRID and base[gy][gx] != 0

    # Flood the outer (background) empties from the border, so the highlight bevel
    # only lights the OUTER rim, not the inner bearing-hole rims.
    outer = [[False] * GRID for _ in range(GRID)]
    stack = [(x, y) for x in range(GRID) for y in (0, GRID - 1) if base[y][x] == 0]
    stack += [(x, y) for y in range(GRID) for x in (0, GRID - 1) if base[y][x] == 0]
    while stack:
        gx, gy = stack.pop()
        if outer[gy][gx]:
            continue
        outer[gy][gx] = True
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = gx + dx, gy + dy
            if 0 <= nx < GRID and 0 <= ny < GRID and not outer[ny][nx] and base[ny][nx] == 0:
                stack.append((nx, ny))

    deco = [[0] * GRID for _ in range(GRID)]
    for gy in range(GRID):
        for gx in range(GRID):
            px, py = gx + 0.5, gy + 0.5
            if base[gy][gx] == 0:
                if any(solid(gx + dx, gy + dy)
                       for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy):
                    deco[gy][gx] = _OUTLINE
                continue
            if (outer[gy - 1][gx] or outer[gy][gx - 1] or outer[gy - 1][gx - 1]):
                deco[gy][gx] = _HILITE
            elif any(hr < math.hypot(px - hx, py - hy) <= hr + _RING_W
                     for hx, hy, hr in holes):
                deco[gy][gx] = _RING
    return base, deco


# Built once at import; theme colour is applied per-instance when rendering.
_SPINNER_BASE, _SPINNER_DECO = _build_spinner_grids()


def _render_spinner_pixmap(colors: dict) -> QPixmap:
    """Render the (base, deco) grids to a pixmap using the colour set."""
    part = {_HUB: colors["hub"], _WING: colors["wing"]}
    pm = QPixmap(GRID * CELL, GRID * CELL)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setPen(Qt.PenStyle.NoPen)
    for gy in range(GRID):
        for gx in range(GRID):
            b, d = _SPINNER_BASE[gy][gx], _SPINNER_DECO[gy][gx]
            if b == 0:
                if d == _OUTLINE:
                    p.fillRect(gx * CELL, gy * CELL, CELL, CELL, colors["outline"])
                continue
            col = part[b]
            if d == _HILITE:
                col = col.lighter(155)
            elif d == _RING:
                col = colors["ring"]
            p.fillRect(gx * CELL, gy * CELL, CELL, CELL, col)
    p.end()
    return pm


class FidgetSpinnerWindow(QWidget):
    """Frameless, always-on-top pixel-art spinner. Click to add spin, drag to
    move. Closed via /clear (no double-click-to-close)."""

    WINDOW_SIZE = GRID * CELL

    FRICTION = 0.9985     # per ~60fps frame — low, so a flick keeps it spinning
    CLICK_IMPULSE = 3.0   # radians/sec added per click

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0.0      # radians
        self._velocity = 1.0   # radians/sec
        self._pixmap = _render_spinner_pixmap(self._theme_colors())

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.WINDOW_SIZE, self.WINDOW_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60fps
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        self._drag_pos = None

    @staticmethod
    def _theme_colors() -> dict:
        """The original theme-palette colour set: hub/arms = pressed accent, wings
        = secondary accent_two (the CTA slot — where cyberpunk's red/pink lives),
        bearing rings = text, outline = a darkened accent. The highlight bevel is
        a lighter shade of each part, computed at render time."""
        try:
            from techdeck.ui.theme_manager import get_theme_manager
            pal = get_theme_manager().get_current_palette()
            hub, wing = QColor(pal.accent_pressed), QColor(pal.accent_two)
            ring, outline = QColor(pal.text), QColor(pal.accent).darker(300)
        except Exception:
            hub, wing = QColor(0x1F, 0x67, 0x90), QColor(0xF5, 0xC5, 0x18)
            ring, outline = QColor(0xEC, 0xEC, 0xEC), QColor(0x10, 0x28, 0x38)
        return {"hub": hub, "wing": wing, "ring": ring, "outline": outline}

    def _tick(self):
        self._velocity *= self.FRICTION
        self._angle += self._velocity * 0.016  # 16ms frame
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._velocity += self.CLICK_IMPULSE
            self._drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def paintEvent(self, event):
        painter = QPainter(self)
        # Smoothing OFF keeps the pixels hard-edged at every rotation angle.
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.translate(self.WINDOW_SIZE / 2.0, self.WINDOW_SIZE / 2.0)
        painter.rotate(math.degrees(self._angle))
        painter.drawPixmap(-self._pixmap.width() // 2,
                           -self._pixmap.height() // 2, self._pixmap)
        painter.end()
