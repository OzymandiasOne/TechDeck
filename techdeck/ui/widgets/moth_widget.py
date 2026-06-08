"""
TechDeck Moth Widget
A small PIXEL-ART moth that flies in from a random screen edge to a random empty
spot (never onto a button), then perches and flutters its wings occasionally.
About 30s after it lands it shows a manufacturing haiku in a themed speech
bubble, and again every ~10 minutes after. Coloured to the active theme.
/moth sends it somewhere new. Double-click to shoo it away entirely.
"""

import math
import random
import sys
from pathlib import Path
from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import Qt, QTimer, QPoint, QRectF
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics, QFontDatabase


# ── Haiku font (FOT Bokutoh Pro, bundled in assets/fonts) ───────────────────
# Drop the FOT Bokutoh Pro .otf/.ttf into assets/fonts/ and it's picked up here;
# until then the bubble falls back to a default italic face. Resolved once.
_HAIKU_FAMILY: str | None = None
_HAIKU_FONT_RESOLVED = False


def _assets_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets"
    return Path(__file__).resolve().parents[3] / "assets"


def haiku_font(point_size: int) -> QFont:
    """Return the FOT Bokutoh Pro font if bundled, else a default italic fallback."""
    global _HAIKU_FAMILY, _HAIKU_FONT_RESOLVED
    if not _HAIKU_FONT_RESOLVED:
        _HAIKU_FONT_RESOLVED = True
        fonts_dir = _assets_dir() / "fonts"
        families: list[str] = []
        if fonts_dir.is_dir():
            for f in sorted(fonts_dir.iterdir()):
                if f.suffix.lower() in (".otf", ".ttf", ".ttc"):
                    fid = QFontDatabase.addApplicationFont(str(f))
                    if fid != -1:
                        families += QFontDatabase.applicationFontFamilies(fid)
        _HAIKU_FAMILY = next(
            (fam for fam in families if "bokutoh" in fam.lower()),
            families[0] if families else None)
    if _HAIKU_FAMILY:
        font = QFont(_HAIKU_FAMILY)
    else:
        font = QFont()
        font.setItalic(True)
    font.setPointSize(point_size)
    return font

# ── Moth sound pool ────────────────────────────────────────────────────────────
# Module-level so the pool persists across /moth invocations (new MothWidget
# instances). Exhausts all 11 voices before cycling; never repeats back-to-back.

_MOTH_SOUND_IDS = [f"moth_voice_{i}" for i in range(1, 12)]
_moth_pool: list = []
_moth_last: str | None = None


def _next_moth_sound() -> str:
    global _moth_pool, _moth_last
    if not _moth_pool:
        _moth_pool = [s for s in _MOTH_SOUND_IDS if s != _moth_last]
        if not _moth_pool:           # safety: only 1 sound registered
            _moth_pool = list(_MOTH_SOUND_IDS)
        random.shuffle(_moth_pool)
    sound = _moth_pool.pop()
    _moth_last = sound
    return sound


# ── Pixel-art wing-flutter frames (generated via tools/_scratch_moth.py) ─────
# 19x14 grids; "X" = a filled cell painted in the theme colour. Frame 0 = wings
# spread (rest), 2 = wings raised; cycling them animates a flutter.
MOTH_FRAMES = [
    [
        ".....X.......X.....",
        "......X.....X......",
        "......XX...XX......",
        "........X.X........",
        "....XX..XXX..XX....",
        "..XXXXXXXXXXXXXXX..",
        ".XXXXXXXXXXXXXXXXX.",
        ".XXXXXXXXXXXXXXXXX.",
        "..XXXXXXXXXXXXXXX..",
        "........XXX........",
        "....XXXXXXXXXXX....",
        "....XXXXXXXXXXX....",
        "....XXXX.X.XXXX....",
        ".....XXX.X.XXX.....",
    ],
    [
        ".....X.......X.....",
        "......X.....X......",
        "......XX...XX......",
        "........X.X........",
        "....XXX.XXX.XXX....",
        "...XXXXXXXXXXXXX...",
        "...XXXXXXXXXXXXX...",
        "...XXXXXXXXXXXXX...",
        "....XXXXXXXXXXX....",
        "........XXX........",
        ".....XXXXXXXXX.....",
        ".....XXXXXXXXX.....",
        ".....XXXXXXXXX.....",
        ".....XXX.X.XXX.....",
    ],
    [
        "......X.....X......",
        ".......X...X.......",
        "........X.X........",
        "...................",
        ".....XXXXXXXXX.....",
        "....XXXXXXXXXXX....",
        "....XXXXXXXXXXX....",
        "....XXXXXXXXXXX....",
        ".....XXXXXXXXX.....",
        "........XXX........",
        "......XXXXXXX......",
        "......XXXXXXX......",
        "......XXXXXXX......",
        "......XX.X.XX......",
    ],
]
_GRID_W = len(MOTH_FRAMES[0][0])
_GRID_H = len(MOTH_FRAMES[0])


class HaikuBubble(QWidget):
    """A PIXEL-ART speech bubble (Animal-Crossing-style) that types a 3-line haiku
    out one letter at a time.

    Drawn on a cell grid: a soft rounded box (pixel-stepped corners) with a
    downward (or upward) pixel arrow pointing at the moth. Filled with the theme
    surface, outlined + arrowed in the theme accent, text in the theme text
    colour. Sized to the FULL text up front (so it never resizes / cuts off);
    only a growing prefix is painted, advanced by a timer.
    """

    CELL = 4                # px per pixel-art cell
    PAD_PX = 11             # interior breathing room around the text
    RADIUS = 5              # rounded-corner radius in cells
    ARROW_W = 5             # arrow base width in cells (odd)
    ARROW_H = 3             # arrow height in cells
    REVEAL_MS = 55          # per-character typing speed
    FONT_PT = 11

    def __init__(self, text: str, fg: QColor, bg: QColor, frame: QColor,
                 tail_dir: str = "down", parent=None):
        super().__init__(parent)
        self._fg, self._bg, self._frame = fg, bg, frame
        self._tail_dir = tail_dir            # "down" = bubble above the moth
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._font = haiku_font(self.FONT_PT)
        self._fm = QFontMetrics(self._font)
        self._lines = text.split("\n")
        self._lh = self._fm.height()
        # Width via tight ink bounds (handles italic/brush overhang) + padding.
        tw = max((self._fm.boundingRect(ln).width() for ln in self._lines), default=40)
        th = self._lh * len(self._lines)

        S = self.CELL
        self._cols = math.ceil((tw + self.PAD_PX * 2) / S) + 2   # +2 = frame
        self._rows = math.ceil((th + self.PAD_PX * 2) / S) + 2
        self._arrow_col = self._cols // 2                        # points at moth
        self.setFixedSize(self._cols * S, (self._rows + self.ARROW_H) * S)

        # Typewriter reveal across all lines.
        self._revealed = 0
        self._total = sum(len(ln) for ln in self._lines)
        self._reveal_timer = QTimer(self)
        self._reveal_timer.setInterval(self.REVEAL_MS)
        self._reveal_timer.timeout.connect(self._reveal_step)
        self._reveal_timer.start()

    def set_tail(self, direction: str, arrow_x_px: int):
        """direction 'down'/'up'; arrow_x_px = where the arrow should point (px from
        the bubble's left edge), so it aims at the moth even when clamped."""
        self._tail_dir = direction
        lo, hi = self.ARROW_W // 2, self._cols - 1 - self.ARROW_W // 2
        self._arrow_col = max(lo, min(round(arrow_x_px / self.CELL), hi))
        self.update()

    def _reveal_step(self):
        self._revealed += 1
        if self._revealed >= self._total:
            self._reveal_timer.stop()
        self.update()

    def _inside(self, cx, cy) -> bool:
        """Rounded-rectangle membership test for the box cell (cx, cy)."""
        R, cols, rows = self.RADIUS, self._cols, self._rows
        px, py = cx + 0.5, cy + 0.5
        qx = R if px < R else (cols - R if px > cols - R else px)
        qy = R if py < R else (rows - R if py > rows - R else py)
        return (px - qx) ** 2 + (py - qy) ** 2 <= R * R + 0.25

    def paintEvent(self, event):
        p = QPainter(self)
        p.setPen(Qt.PenStyle.NoPen)
        S = self.CELL
        cols, rows = self._cols, self._rows
        boy = 0 if self._tail_dir == "down" else self.ARROW_H   # box y-offset (cells)

        # Rounded box: surface fill, accent border (a cell whose 4-neighbour is
        # outside the rounded shape, or on the grid edge).
        for cy in range(rows):
            for cx in range(cols):
                if not self._inside(cx, cy):
                    continue
                border = (cx == 0 or cy == 0 or cx == cols - 1 or cy == rows - 1
                          or not self._inside(cx - 1, cy) or not self._inside(cx + 1, cy)
                          or not self._inside(cx, cy - 1) or not self._inside(cx, cy + 1))
                p.fillRect(cx * S, (boy + cy) * S, S, S,
                           self._frame if border else self._bg)

        # Pixel arrow toward the moth, in the accent colour.
        ac = self._arrow_col
        for k in range(self.ARROW_H):
            if self._tail_dir == "down":            # below the box, tip at bottom
                half = (self.ARROW_W // 2) - k
                ry = rows + k
            else:                                   # above the box, tip at top
                half = k
                ry = k
            if half < 0:
                continue
            for cx in range(ac - half, ac + half + 1):
                p.fillRect(cx * S, ry * S, S, S, self._frame)

        # Typewriter text, centered in the interior; prefix drawn left-aligned at
        # the full line's centered start so it types left-to-right.
        p.setPen(self._fg)
        p.setFont(self._font)
        iw = (cols - 2) * S
        interior_h = (rows - 2) * S
        ty = boy * S + S + (interior_h - self._lh * len(self._lines)) / 2.0
        remaining = self._revealed
        for i, line in enumerate(self._lines):
            take = max(0, min(len(line), remaining))
            remaining -= len(line)
            if take <= 0:
                continue
            lw = self._fm.boundingRect(line).width()
            x0 = S + (iw - lw) / 2.0
            p.drawText(QRectF(x0, ty + i * self._lh, lw + 6, self._lh),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       line[:take])
        p.end()


class MothWidget(QWidget):
    """
    Frameless, translucent pixel-art moth painted in the theme colour. Flies to a
    global point, perches, and flutters occasionally; shows haikus on a delay.
    """

    CELL = 2                                  # px per pixel-art cell
    SIZE_W = _GRID_W * CELL
    SIZE_H = _GRID_H * CELL

    FLY_SEQ = [0, 1, 2, 1]                    # fast flutter while in flight
    MAX_FLY_TICKS = 240                       # ~3.8s fail-safe: always land by then
    # On landing: a couple of flaps that visibly SLOW DOWN (per-frame delay ramps
    # up) so the moth eases to a graceful, still stop. (frame, ms-until-next).
    SETTLE = [(1, 90), (2, 110), (1, 135), (0, 165),
              (1, 205), (2, 255), (1, 320), (0, 400)]
    IDLE_FLAP_MS = 165                        # slow, gentle beat for idle flutters
    IDLE_FLAPS = (1, 3)                        # "just a few" on each random flutter
    IDLE_MIN_MS, IDLE_MAX_MS = 5000, 15000    # long stills between flutters
    HAIKU_FIRST_MIN_MS, HAIKU_FIRST_MAX_MS = 20_000, 50_000  # first within a minute
    HAIKU_EVERY_MS = 600_000                  # then every 10 minutes
    HAIKU_VISIBLE_MS = 13_000                 # how long a bubble lingers

    def __init__(self, color: QColor | None = None, parent=None):
        super().__init__(parent)
        self._color = color if color is not None else QColor(30, 30, 30, 230)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.SIZE_W, self.SIZE_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._frame_idx = 0
        self._fly_tick = 0
        self._flying = False
        self._target_point: QPoint | None = None
        self._landed = False
        self._fx = 0.0           # true float position (window pos is rounded)
        self._fy = 0.0

        # Haiku state
        self._haiku_provider = None
        self._bubble_colors: tuple[QColor, QColor, QColor] | None = None
        self._bubble: HaikuBubble | None = None

        # Movement during flight
        self._move_timer = QTimer(self)
        self._move_timer.setInterval(16)
        self._move_timer.timeout.connect(self._tick)

        # Flutter: a (frame, delay) sequence stepped by a single-shot timer whose
        # delay is re-set per step (so flaps can slow down); scheduled by _idle_timer.
        self._flap_seq: list[tuple[int, int]] = []
        self._flap_timer = QTimer(self)
        self._flap_timer.setSingleShot(True)
        self._flap_timer.timeout.connect(self._flap_step)
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._start_flutter)

        # Haiku timers
        self._haiku_first = QTimer(self)
        self._haiku_first.setSingleShot(True)
        self._haiku_first.timeout.connect(self._do_haiku)
        self._haiku_repeat = QTimer(self)
        self._haiku_repeat.setInterval(self.HAIKU_EVERY_MS)
        self._haiku_repeat.timeout.connect(self._do_haiku)
        self._bubble_hide = QTimer(self)
        self._bubble_hide.setSingleShot(True)
        self._bubble_hide.timeout.connect(self._hide_bubble)

    # ── public API ──────────────────────────────────────────────────────────
    def set_color(self, color: QColor):
        """Re-theme the moth (e.g. on a later /moth after a theme switch)."""
        self._color = color
        self.update()

    def configure_haiku(self, provider, fg: QColor, bg: QColor, border: QColor):
        """provider() -> haiku str; fg/bg/border colour the bubble."""
        self._haiku_provider = provider
        self._bubble_colors = (fg, bg, border)

    def fly_to(self, point: QPoint):
        """Set a new global target point and start flying."""
        self._hide_bubble()
        self._cancel_idle_and_haiku()
        self._target_point = QPoint(point)
        self._flying = True
        self._landed = False
        self._fly_tick = 0
        self._fx, self._fy = float(self.x()), float(self.y())
        self._move_timer.start()
        self.show()
        self.raise_()

    def spawn_from_edge(self, point: QPoint):
        """Pick a random screen edge, start there, then fly to the point."""
        screen = QApplication.primaryScreen().geometry()
        edge = random.choice(["top", "bottom", "left", "right"])
        if edge == "top":
            x, y = random.randint(screen.left(), screen.right()), screen.top() - self.SIZE_H
        elif edge == "bottom":
            x, y = random.randint(screen.left(), screen.right()), screen.bottom() + self.SIZE_H
        elif edge == "left":
            x, y = screen.left() - self.SIZE_W, random.randint(screen.top(), screen.bottom())
        else:
            x, y = screen.right() + self.SIZE_W, random.randint(screen.top(), screen.bottom())
        self.move(x, y)
        self.fly_to(point)

    # ── flight ──────────────────────────────────────────────────────────────
    def _target_top_left(self) -> QPoint | None:
        if self._target_point is None:
            return None
        return self._target_point - QPoint(self.SIZE_W // 2, self.SIZE_H // 2)

    def _tick(self):
        target = self._target_top_left()
        if target is None:
            self._move_timer.stop()
            return

        # flap while flying
        self._fly_tick += 1
        self._frame_idx = self.FLY_SEQ[(self._fly_tick // 3) % len(self.FLY_SEQ)]

        # Track the true position in floats so sub-pixel steering accumulates
        # (rounding the window pos each tick would stall the drift near the target
        # and it would never reach the threshold). Fail-safe lands a stuck flight.
        dx, dy = target.x() - self._fx, target.y() - self._fy
        dist = math.hypot(dx, dy)
        if dist < 3 or self._fly_tick > self.MAX_FLY_TICKS:
            self.move(target)
            self._fx, self._fy = float(target.x()), float(target.y())
            self._move_timer.stop()
            self._flying = False
            self._frame_idx = 0
            if not self._landed:
                self._landed = True
                self._on_landed()
        else:
            speed = min(dist * 0.085, 12.0)
            wander = min(1.0, dist / 26.0)   # calm the wobble as it nears
            self._fx += dx / dist * speed + random.uniform(-1, 1) * wander
            self._fy += dy / dist * speed + random.uniform(-1, 1) * wander
            self.move(round(self._fx), round(self._fy))
        self.update()

    def _on_landed(self):
        # Ease to a stop with a couple of decelerating flaps, then go still; the
        # flutter's completion schedules the next occasional flutter.
        self._settle()
        self._haiku_first.start(
            random.randint(self.HAIKU_FIRST_MIN_MS, self.HAIKU_FIRST_MAX_MS))

    # ── flutter (slow & graceful, then still) ───────────────────────────────
    def _play_flaps(self, seq):
        """Play a (frame, delay-ms) sequence; _flap_step goes still after."""
        self._flap_seq = list(seq)
        if not self._flap_timer.isActive():
            self._flap_step()

    def _settle(self):
        """The decelerating landing flutter -> graceful, still stop."""
        self._play_flaps(self.SETTLE)

    def _start_flutter(self):
        """An occasional gentle idle flutter: a few slow, even-paced beats."""
        n = random.randint(*self.IDLE_FLAPS)
        self._play_flaps([(f, self.IDLE_FLAP_MS) for _ in range(n) for f in (1, 2, 1, 0)])

    def _flap_step(self):
        if self._flap_seq:
            frame, delay = self._flap_seq.pop(0)
            self._frame_idx = frame
            self.update()
            self._flap_timer.start(delay)
        else:
            self._frame_idx = 0
            self.update()
            self._idle_timer.start(random.randint(self.IDLE_MIN_MS, self.IDLE_MAX_MS))

    # ── haiku ───────────────────────────────────────────────────────────────
    def _do_haiku(self):
        if self._haiku_provider is None or self._bubble_colors is None:
            return
        try:
            text = self._haiku_provider()
        except Exception:
            return
        fg, bg, frame = self._bubble_colors
        self._hide_bubble()
        self._bubble = HaikuBubble(text, fg, bg, frame)
        pos, direction, arrow_x = self._bubble_place()
        self._bubble.set_tail(direction, arrow_x)
        self._bubble.show()
        self._bubble.move(pos)
        self._bubble.raise_()
        self._bubble_hide.start(self.HAIKU_VISIBLE_MS)
        if not self._haiku_repeat.isActive():
            self._haiku_repeat.start()

    def _bubble_place(self):
        """Position the bubble over the moth (clamped); return (pos, dir, arrow_x).

        Prefer ABOVE the moth (arrow points down at it); flip below if there's no
        room above. The arrow aims at the moth's horizontal centre.
        """
        screen = QApplication.primaryScreen().availableGeometry()
        bw, bh = self._bubble.width(), self._bubble.height()
        moth_cx = self.x() + self.SIZE_W // 2
        direction = "down"
        by = self.y() - bh + 6                       # bubble above; arrow tip into moth top
        if by < screen.top() + 4:
            direction = "up"
            by = self.y() + self.SIZE_H - 6          # bubble below; arrow tip into moth base
        bx = moth_cx - bw // 2
        bx = max(screen.left() + 4, min(bx, screen.right() - bw - 4))
        by = max(screen.top() + 4, min(by, screen.bottom() - bh - 4))
        return QPoint(bx, by), direction, moth_cx - bx

    def _hide_bubble(self):
        self._bubble_hide.stop()
        if self._bubble is not None:
            self._bubble.close()
            self._bubble = None

    def _cancel_idle_and_haiku(self):
        for t in (self._idle_timer, self._flap_timer, self._haiku_first,
                  self._haiku_repeat, self._bubble_hide):
            t.stop()
        self._flap_seq = []

    # ── interaction / teardown ──────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            from techdeck.core.audio_manager import get_audio_manager
            get_audio_manager().play(_next_moth_sound())
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.dismiss()

    def dismiss(self):
        """Stop everything and remove the moth (and its bubble)."""
        self._move_timer.stop()
        self._cancel_idle_and_haiku()
        self._flying = False
        self._target_point = None
        self._hide_bubble()
        self.close()

    # ── paint ───────────────────────────────────────────────────────────────
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        c = self.CELL
        for y, row in enumerate(MOTH_FRAMES[self._frame_idx]):
            for x, ch in enumerate(row):
                if ch != ".":
                    painter.fillRect(x * c, y * c, c, c, self._color)
        painter.end()
