"""
TechDeck Fidget Spinner

A standalone, frameless, always-on-top fidget spinner drawn as PIXEL ART in the
same two-tone, theme-coloured style as the moth and the tile icons: a body tone
(the theme accent) plus an auto-traced darker outline, with the bearing holes
punched clean through.

The shape is generated procedurally (a centre hub, three arms, three lobes, all
ONE connected piece so the "wings" are attached to the body) and rendered to a
pixmap once; spinning just rotates that pixmap with smoothing OFF so the pixels
stay hard-edged at every angle.

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
_LOBE_ANGLES_DEG = (-90.0, 30.0, 150.0)   # one lobe up, two below; 120 apart


def _seg_dist(px, py, ax, ay, bx, by):
    """Distance from point P to segment AB (for the connecting arms)."""
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 == 0.0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _build_spinner_cats():
    """Build the spinner as a GRID x GRID category map: 0 empty, 1 body, 2 outline.

    A cell is BODY if it lies in the hub, in any lobe, or under any arm, AND is
    not inside a bearing hole. Every empty cell touching a body cell becomes
    OUTLINE — which traces the outer silhouette AND rings each punched hole."""
    lobes = [(_CENTER + _LOBE_DIST * math.cos(math.radians(a)),
              _CENTER + _LOBE_DIST * math.sin(math.radians(a)))
             for a in _LOBE_ANGLES_DEG]

    solid = [[False] * GRID for _ in range(GRID)]
    for gy in range(GRID):
        for gx in range(GRID):
            px, py = gx + 0.5, gy + 0.5
            s = math.hypot(px - _CENTER, py - _CENTER) <= _HUB_R
            for lx, ly in lobes:
                if math.hypot(px - lx, py - ly) <= _LOBE_R:
                    s = True
                if _seg_dist(px, py, _CENTER, _CENTER, lx, ly) <= _ARM_HW:
                    s = True
            # Punch the bearing holes back out.
            if math.hypot(px - _CENTER, py - _CENTER) <= _HUB_HOLE:
                s = False
            for lx, ly in lobes:
                if math.hypot(px - lx, py - ly) <= _LOBE_HOLE:
                    s = False
            solid[gy][gx] = s

    cats = [[1 if solid[gy][gx] else 0 for gx in range(GRID)] for gy in range(GRID)]
    for gy in range(GRID):
        for gx in range(GRID):
            if solid[gy][gx]:
                continue
            if any(0 <= gy + dy < GRID and 0 <= gx + dx < GRID and solid[gy + dy][gx + dx]
                   for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dx or dy):
                cats[gy][gx] = 2
    return cats


# Built once at import; theme colour is applied per-instance when rendering.
_SPINNER_CATS = _build_spinner_cats()


def _render_spinner_pixmap(body: QColor, outline: QColor) -> QPixmap:
    """Render the category map to a pixmap (body + outline tones, holes clear)."""
    pm = QPixmap(GRID * CELL, GRID * CELL)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setPen(Qt.PenStyle.NoPen)
    for gy in range(GRID):
        for gx in range(GRID):
            cat = _SPINNER_CATS[gy][gx]
            if cat == 0:
                continue
            p.fillRect(gx * CELL, gy * CELL, CELL, CELL,
                       body if cat == 1 else outline)
    p.end()
    return pm


class FidgetSpinnerWindow(QWidget):
    """Frameless, always-on-top pixel-art tri-spinner. Click to add spin, drag to
    move. Closed via /clear (no double-click-to-close)."""

    WINDOW_SIZE = GRID * CELL

    FRICTION = 0.995      # per ~60fps frame
    CLICK_IMPULSE = 2.5   # radians/sec added per click

    def __init__(self, body_color: QColor | None = None,
                 outline_color: QColor | None = None, parent=None):
        super().__init__(parent)
        self._angle = 0.0      # radians
        self._velocity = 1.0   # radians/sec

        if body_color is None or outline_color is None:
            body_color, outline_color = self._theme_colors()
        self._pixmap = _render_spinner_pixmap(body_color, outline_color)

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
    def _theme_colors() -> tuple[QColor, QColor]:
        """Body = theme accent, outline = a darker accent — matching the moth."""
        try:
            from techdeck.ui.theme_manager import get_theme_manager
            pal = get_theme_manager().get_current_palette()
            body = QColor(pal.accent)
            return body, body.darker(260)
        except Exception:
            return QColor(200, 205, 218), QColor(70, 72, 85)  # chrome fallback

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
