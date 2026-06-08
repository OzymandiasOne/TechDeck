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
from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import Qt, QTimer, QPoint, QRectF
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics

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
    """A themed speech bubble that types a 3-line haiku out one letter at a time.

    The box is sized to the FULL text up front (so it never resizes), but only a
    growing prefix of the characters is painted, advanced by a timer.
    """

    PAD = 9
    RADIUS = 8
    REVEAL_MS = 55          # per-character typing speed

    def __init__(self, text: str, fg: QColor, bg: QColor, border: QColor, parent=None):
        super().__init__(parent)
        self._fg, self._bg, self._border = fg, bg, border
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._font = QFont()
        self._font.setPointSize(8)          # small text -> small box that fits it
        self._font.setItalic(True)
        self._fm = QFontMetrics(self._font)
        fm = self._fm
        self._lines = text.split("\n")
        self._lh = fm.height()
        tw = max((fm.horizontalAdvance(ln) for ln in self._lines), default=40)
        self._w = tw + self.PAD * 2
        self._h = self._lh * len(self._lines) + self.PAD * 2
        self.setFixedSize(self._w, self._h)

        # Typewriter reveal: count visible chars across all lines.
        self._revealed = 0
        self._total = sum(len(ln) for ln in self._lines)
        self._reveal_timer = QTimer(self)
        self._reveal_timer.setInterval(self.REVEAL_MS)
        self._reveal_timer.timeout.connect(self._reveal_step)
        self._reveal_timer.start()

    def _reveal_step(self):
        self._revealed += 1
        if self._revealed >= self._total:
            self._reveal_timer.stop()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(self._border)
        p.setBrush(self._bg)
        p.drawRoundedRect(QRectF(0.75, 0.75, self._w - 1.5, self._h - 1.5),
                          self.RADIUS, self.RADIUS)
        p.setPen(self._fg)
        p.setFont(self._font)
        remaining = self._revealed
        for i, line in enumerate(self._lines):
            take = max(0, min(len(line), remaining))
            remaining -= len(line)
            if take <= 0:
                continue
            # Draw the revealed prefix LEFT-aligned at the spot where the full
            # (centered) line begins, so letters type in left-to-right and land
            # in their final centered positions.
            lw = self._fm.horizontalAdvance(line)
            x0 = (self._w - lw) / 2.0
            p.drawText(
                QRectF(x0, self.PAD + i * self._lh, lw, self._lh),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line[:take])
        p.end()


class MothWidget(QWidget):
    """
    Frameless, translucent pixel-art moth painted in the theme colour. Flies to a
    global point, perches, and flutters occasionally; shows haikus on a delay.
    """

    CELL = 2                                  # px per pixel-art cell
    SIZE_W = _GRID_W * CELL
    SIZE_H = _GRID_H * CELL

    FLY_SEQ = [0, 1, 2, 1]                    # wing frames cycled while flying
    FLUTTER_SEQ = [1, 2, 1, 0, 1, 2, 1, 0]    # one idle flutter burst
    FLAP_MS = 70                              # per-frame step during a flutter
    IDLE_MIN_MS, IDLE_MAX_MS = 2600, 7000     # gap between idle flutters
    HAIKU_FIRST_MS = 30_000                   # first haiku after landing
    HAIKU_EVERY_MS = 600_000                  # then every 10 minutes
    HAIKU_VISIBLE_MS = 12_000                 # how long a bubble lingers

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

        # Haiku state
        self._haiku_provider = None
        self._bubble_colors: tuple[QColor, QColor, QColor] | None = None
        self._bubble: HaikuBubble | None = None

        # Movement during flight
        self._move_timer = QTimer(self)
        self._move_timer.setInterval(16)
        self._move_timer.timeout.connect(self._tick)

        # Idle flutter: a burst sequence stepped by _flap_timer, scheduled by _idle_timer
        self._flap_queue: list[int] = []
        self._flap_timer = QTimer(self)
        self._flap_timer.setInterval(self.FLAP_MS)
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

        dx, dy = target.x() - self.x(), target.y() - self.y()
        dist = math.hypot(dx, dy)
        if dist < 3:
            self.move(target)
            self._move_timer.stop()
            self._flying = False
            self._frame_idx = 0
            if not self._landed:
                self._landed = True
                self._on_landed()
        else:
            speed = min(dist * 0.08, 12)
            nx = self.x() + dx / dist * speed + random.uniform(-1, 1)
            ny = self.y() + dy / dist * speed + random.uniform(-1, 1)
            self.move(int(nx), int(ny))
        self.update()

    def _on_landed(self):
        self._idle_timer.start(random.randint(self.IDLE_MIN_MS, self.IDLE_MAX_MS))
        self._haiku_first.start(self.HAIKU_FIRST_MS)

    # ── idle flutter ────────────────────────────────────────────────────────
    def _start_flutter(self):
        self._flap_queue = list(self.FLUTTER_SEQ)
        self._flap_timer.start()

    def _flap_step(self):
        if self._flap_queue:
            self._frame_idx = self._flap_queue.pop(0)
            self.update()
        else:
            self._flap_timer.stop()
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
        fg, bg, border = self._bubble_colors
        self._hide_bubble()
        self._bubble = HaikuBubble(text, fg, bg, border)
        self._bubble.show()
        self._bubble.move(self._bubble_pos())
        self._bubble.raise_()
        self._bubble_hide.start(self.HAIKU_VISIBLE_MS)
        if not self._haiku_repeat.isActive():
            self._haiku_repeat.start()

    def _bubble_pos(self) -> QPoint:
        """Place the bubble beside the moth, clamped on-screen."""
        screen = QApplication.primaryScreen().availableGeometry()
        bw, bh = self._bubble.width(), self._bubble.height()
        bx = self.x() + self.SIZE_W + 8
        if bx + bw > screen.right():
            bx = self.x() - bw - 8
        by = self.y() + self.SIZE_H // 2 - bh // 2
        bx = max(screen.left() + 4, min(bx, screen.right() - bw - 4))
        by = max(screen.top() + 4, min(by, screen.bottom() - bh - 4))
        return QPoint(bx, by)

    def _hide_bubble(self):
        self._bubble_hide.stop()
        if self._bubble is not None:
            self._bubble.close()
            self._bubble = None

    def _cancel_idle_and_haiku(self):
        for t in (self._idle_timer, self._flap_timer, self._haiku_first,
                  self._haiku_repeat, self._bubble_hide):
            t.stop()
        self._flap_queue = []

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
