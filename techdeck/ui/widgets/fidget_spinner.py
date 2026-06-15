"""
TechDeck Fidget Spinner

A standalone, frameless, always-on-top fidget spinner drawn as HAND-EDITABLE
PIXEL ART, exactly like the moth (`MOTH_FRAMES`): edit the `SPINNER_ART` grid
below cell by cell. Colours come from the active theme palette so it fits the
theme. The grid is rendered to a pixmap once; spinning just rotates that pixmap
with smoothing OFF, so the pixels stay hard-edged at every angle.

Editing the art — each cell is one character:
    .  transparent (a dark OUTLINE is auto-traced around every filled cell,
       and around the bearing holes, just like the moth's silhouette outline)
    B  body  -> theme accent        (the hub + the arms)
    W  wing  -> theme accent_two     (the three lobes / "wings")
    R  ring  -> theme text           (the bright bearing rings)
    H  highlight -> a light accent   (optional shading; place by hand)
    o  outline tone                  (optional hand-drawn dark detail)

The spinner rotates about the GRID CENTRE, so keep the hub centred and keep all
art within the inscribed circle (radius = half the grid) or it clips as it
spins. A square grid keeps the centre easy to find.

  - Click anywhere on it to add spin (and drag to move it).
  - It does NOT close on double-click (that fought with clicking to spin);
    `/clear` puts it away (see CommandHandler.stop_session_effects).

Tip: preview edits without launching the whole app with
`python tools/preview_spinner.py`.
"""

import math

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QColor, QPixmap


# ── Hand-editable pixel art (legend in the module docstring above) ───────────
SPINNER_ART = [
    ".................................",
    "................W................",
    "..............WWRWW..............",
    ".............WRRRRRW.............",
    "............WRR...RRW............",
    "............WR.....RW............",
    "............WR.....RW............",
    "............WRR...RRW............",
    ".............WRRRRRW.............",
    ".............WWRRRWW.............",
    "..............BWWWB..............",
    "..............BBBBB..............",
    ".............BBBBBBB.............",
    "............BBRRRRRBB............",
    "............BRR...RRB............",
    "............BR.....RB............",
    "...........BBR.....RBB...........",
    "......WWWBBBBR.....RBBBBWWW......",
    "....WWRRRWWBBRR...RRBBWWRRRWW....",
    "...WWRR.RRWWBBRRRRRBBWWRR.RRWW...",
    "...WRR...RRWBBBBBBBBBWRR...RRW...",
    "...WR.....RWB...B...BWR.....RW...",
    "...WR.....RW.........WR.....RW...",
    "...WRR...RRW.........WRR...RRW...",
    "....WRRRRRW...........WRRRRRW....",
    ".....WWWWW.............WWWWW.....",
    ".................................",
    ".................................",
    ".................................",
    ".................................",
    ".................................",
    ".................................",
    ".................................",
]

CELL = 9                                 # px per art cell
_ART_H = len(SPINNER_ART)
_ART_W = max(len(r) for r in SPINNER_ART)


def _render_spinner_pixmap(colors: dict) -> QPixmap:
    """Render SPINNER_ART to a pixmap: auto-trace a dark outline around the art
    (and the holes), then paint each cell in its themed colour."""
    cmap = {"B": colors["body"], "W": colors["wing"], "R": colors["ring"],
            "H": colors["highlight"], "o": colors["outline"]}
    rows = SPINNER_ART

    def filled(x, y):
        return 0 <= y < _ART_H and 0 <= x < len(rows[y]) and rows[y][x] != "."

    pm = QPixmap(_ART_W * CELL, _ART_H * CELL)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setPen(Qt.PenStyle.NoPen)
    # Outline pass: every empty cell touching a filled cell (silhouette + holes).
    for y in range(_ART_H):
        for x in range(_ART_W):
            if filled(x, y):
                continue
            if any(filled(x + dx, y + dy)
                   for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy):
                p.fillRect(x * CELL, y * CELL, CELL, CELL, colors["outline"])
    # Body pass: each art cell in its colour.
    for y in range(_ART_H):
        row = rows[y]
        for x in range(len(row)):
            ch = row[x]
            if ch == ".":
                continue
            p.fillRect(x * CELL, y * CELL, CELL, CELL, cmap.get(ch, colors["body"]))
    p.end()
    return pm


class FidgetSpinnerWindow(QWidget):
    """Frameless, always-on-top pixel-art tri-spinner. Click to add spin, drag to
    move. Closed via /clear (no double-click-to-close)."""

    WINDOW_SIZE = max(_ART_H, _ART_W) * CELL

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
        """Colours from the active theme palette so the spinner fits the theme:
        body (hub/arms) = primary accent, wings = secondary accent_two (the CTA
        slot — where cyberpunk's red/pink lives), bearing rings = text, outline =
        a darkened accent, highlight = a lighter accent_two."""
        try:
            from techdeck.ui.theme_manager import get_theme_manager
            pal = get_theme_manager().get_current_palette()
            body, wing = QColor(pal.accent), QColor(pal.accent_two)
            ring = QColor(pal.text)
        except Exception:
            body, wing, ring = QColor(0x28, 0x78, 0xA8), QColor(0xF5, 0xA6, 0x23), QColor(0xEC, 0xEC, 0xEC)
        return {
            "body": body,
            "wing": wing,
            "ring": ring,
            "outline": body.darker(300),
            "highlight": wing.lighter(150),
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
