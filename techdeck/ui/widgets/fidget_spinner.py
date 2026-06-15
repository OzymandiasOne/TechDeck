"""
TechDeck Fidget Spinner

A standalone, frameless, always-on-top fidget spinner drawn as PIXEL ART in the
moth's theme-coloured style, but with more detail: a darker outline, a beveled
highlight along the top-left rim, bright bearing rings, and three lobes tinted
to three hues of the theme accent (so it reads multicoloured and blurs into a
colour wheel when it spins fast).

The shape is generated procedurally (a centre hub, three arms, three lobes, all
ONE connected piece so the "wings" are attached to the body) and rendered to a
pixmap once; spinning just rotates that pixmap with smoothing OFF so the pixels
stay hard-edged at every angle. Friction is low, so a flick keeps it turning.

  - Click anywhere on it to add spin (and drag to move it).
  - It does NOT close on double-click (that fought with clicking to spin);
    `/clear` puts it away (see CommandHandler.stop_session_effects).
"""

import math

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QColor, QPixmap


# Pixel grid: each cell is CELL px. GRID is sized so the spinner's content
# radius (lobe distance + lobe radius + 1 outline cell) fits with a 1-cell
# margin, which is also the rotation radius — so nothing clips as it spins.
GRID = 43
CELL = 7
_CENTER = GRID / 2.0

# Geometry, in grid cells.
_HUB_R = 6.5          # centre hub radius
_HUB_HOLE = 3.0       # centre bearing hole
_LOBE_DIST = 13.5     # hub centre -> lobe centre
_LOBE_R = 6.0         # lobe radius
_LOBE_HOLE = 3.0      # lobe bearing hole
_ARM_HW = 3.5         # half-width of each arm (connects hub to lobe)
_RING_W = 1.6         # bright bearing ring just outside each hole
_LOBE_ANGLES_DEG = (-90.0, 30.0, 150.0)   # one lobe up, two below; 120 apart

# base codes: 0 empty, 1 hub/arm, 2/3/4 the three lobes
# deco codes: 0 none, 1 outline (on empty), 2 bearing ring, 3 highlight bevel
_HUB, _LOBE0, _LOBE1, _LOBE2 = 1, 2, 3, 4
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
    """Build (base, deco) grids for the spinner.

    base tags each solid cell as hub/arm or one of the three lobes; deco layers
    the outline (traced around the silhouette and every hole), the bright
    bearing ring just outside each hole, and a highlight bevel on the cells that
    sit against the outer (top-left) background."""
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
            lobe_idx = next((i for i, (lx, ly) in enumerate(lobes)
                             if math.hypot(px - lx, py - ly) <= _LOBE_R), -1)
            if lobe_idx >= 0:
                base[gy][gx] = _LOBE0 + lobe_idx
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
                # Outline: empty cell touching any solid cell (outer rim + holes).
                if any(solid(gx + dx, gy + dy)
                       for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy):
                    deco[gy][gx] = _OUTLINE
                continue
            # Highlight bevel: solid cell against the outer background up/left.
            if (outer[gy - 1][gx] or outer[gy][gx - 1] or outer[gy - 1][gx - 1]):
                deco[gy][gx] = _HILITE
            # Bearing ring: solid cell in the band just outside a hole.
            elif any(hr < math.hypot(px - hx, py - hy) <= hr + _RING_W
                     for hx, hy, hr in holes):
                deco[gy][gx] = _RING
    return base, deco


# Built once at import; theme colour is applied per-instance when rendering.
_SPINNER_BASE, _SPINNER_DECO = _build_spinner_grids()


def _render_spinner_pixmap(colors: dict) -> QPixmap:
    """Render the (base, deco) grids to a pixmap using the colour set."""
    part = {_HUB: colors["hub"],
            _LOBE0: colors["lobes"][0],
            _LOBE1: colors["lobes"][1],
            _LOBE2: colors["lobes"][2]}
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
    """Frameless, always-on-top pixel-art tri-spinner. Click to add spin, drag to
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
        """A colour set drawn from the active theme palette so the spinner fits the
        theme: the hub/arms are the accent, the three wings are all one uniform
        colour — the accent's complement (hue + 180, same saturation/value) — and
        the bearing rings are the text colour over a darkened-accent outline."""
        try:
            from techdeck.ui.theme_manager import get_theme_manager
            pal = get_theme_manager().get_current_palette()
            accent = QColor(pal.accent)
            hub, ring = QColor(pal.accent_pressed), QColor(pal.text)
        except Exception:
            accent = QColor(0x28, 0x78, 0xA8)
            hub, ring = accent.darker(130), QColor(245, 246, 238)

        h, s, v, a = accent.getHsv()
        if h < 0:                       # achromatic accent -> give it a hue first
            h, s = 200, 140
        comp = QColor.fromHsv((h + 180) % 360, s, v, a)

        return {
            "outline": accent.darker(300),
            "hub": hub,
            "lobes": [comp, comp, comp],
            "ring": ring,
        }

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
