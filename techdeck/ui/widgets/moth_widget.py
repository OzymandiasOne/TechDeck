"""
TechDeck Moth Widget
A small moth that flies from a random screen edge toward a random empty point
(never onto a button), then shows a haiku in a themed speech bubble.
/moth sends it somewhere new with a fresh haiku. Double-click to shoo it away.
Outline-only style, no fill; coloured to the active theme.
"""

import math
import random
from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import Qt, QTimer, QPointF, QPoint, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath, QFont, QFontMetrics


class HaikuBubble(QWidget):
    """A small themed speech bubble showing a 3-line haiku next to the moth."""

    PAD = 11
    RADIUS = 9

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
        self._font.setPointSize(9)
        self._font.setItalic(True)
        fm = QFontMetrics(self._font)
        self._lines = text.split("\n")
        self._lh = fm.height()
        tw = max((fm.horizontalAdvance(ln) for ln in self._lines), default=40)
        self._w = tw + self.PAD * 2
        self._h = self._lh * len(self._lines) + self.PAD * 2
        self.setFixedSize(self._w, self._h)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(self._border, 1.5))
        p.setBrush(self._bg)
        p.drawRoundedRect(QRectF(0.75, 0.75, self._w - 1.5, self._h - 1.5),
                          self.RADIUS, self.RADIUS)
        p.setPen(self._fg)
        p.setFont(self._font)
        for i, line in enumerate(self._lines):
            p.drawText(
                QRectF(self.PAD, self.PAD + i * self._lh, self._w - 2 * self.PAD, self._lh),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, line)
        p.end()

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


class MothWidget(QWidget):
    """
    Translucent, frameless moth drawn with QPainter — outlines only, no fill.
    Animates toward a target QWidget. Flaps wings in flight.
    Half the original size (28x28 window, drawn at 56x56 then scaled 0.5).
    Pass a QColor to override the outline color (default near-black).
    """

    SIZE = 28

    def __init__(self, color: QColor | None = None, parent=None):
        super().__init__(parent)
        self._OUTLINE = color if color is not None else QColor(30, 30, 30, 220)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._wing_phase = 0.0
        self._flying = False
        self._target_point: QPoint | None = None   # global point to fly to
        self._landed = False

        # Pending haiku + themed bubble colors, shown once the moth lands.
        self._haiku: str | None = None
        self._bubble_colors: tuple[QColor, QColor, QColor] | None = None
        self._bubble: HaikuBubble | None = None

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def set_color(self, color: QColor):
        """Re-theme the moth outline (e.g. on a later /moth after a theme switch)."""
        self._OUTLINE = color
        self.update()

    def set_haiku(self, text: str, fg: QColor, bg: QColor, border: QColor):
        """Stash the haiku + themed bubble colors to show on landing."""
        self._haiku = text
        self._bubble_colors = (fg, bg, border)

    def fly_to(self, point: QPoint):
        """Set a new global target point and start animating."""
        self._hide_bubble()
        self._target_point = QPoint(point)
        self._flying = True
        self._landed = False
        self._timer.start()
        self.show()
        self.raise_()

    def spawn_from_edge(self, point: QPoint):
        """Pick a random screen edge, start there, then fly to the point."""
        screen = QApplication.primaryScreen().geometry()
        edge = random.choice(["top", "bottom", "left", "right"])
        if edge == "top":
            x = random.randint(screen.left(), screen.right())
            y = screen.top() - self.SIZE
        elif edge == "bottom":
            x = random.randint(screen.left(), screen.right())
            y = screen.bottom() + self.SIZE
        elif edge == "left":
            x = screen.left() - self.SIZE
            y = random.randint(screen.top(), screen.bottom())
        else:
            x = screen.right() + self.SIZE
            y = random.randint(screen.top(), screen.bottom())

        self.move(x, y)
        self.fly_to(point)

    def _target_top_left(self) -> QPoint | None:
        if self._target_point is None:
            return None
        return self._target_point - QPoint(self.SIZE // 2, self.SIZE // 2)

    def _tick(self):
        self._wing_phase += 0.35

        target = self._target_top_left()
        if target is None:
            self._timer.stop()
            return

        dx = target.x() - self.x()
        dy = target.y() - self.y()
        dist = math.hypot(dx, dy)

        if dist < 3:
            self.move(target)
            self._flying = False
            if not self._landed:
                self._landed = True
                self._show_bubble()
        else:
            speed = min(dist * 0.08, 12)
            nx = self.x() + dx / dist * speed + random.uniform(-1, 1)
            ny = self.y() + dy / dist * speed + random.uniform(-1, 1)
            self.move(int(nx), int(ny))
            if self._bubble is not None:
                self._bubble.move(self._bubble_pos())

        self.update()

    # ── haiku bubble ────────────────────────────────────────────────────────
    def _show_bubble(self):
        if not self._haiku or self._bubble_colors is None:
            return
        self._hide_bubble()
        fg, bg, border = self._bubble_colors
        self._bubble = HaikuBubble(self._haiku, fg, bg, border)
        self._bubble.show()
        self._bubble.move(self._bubble_pos())
        self._bubble.raise_()

    def _bubble_pos(self) -> QPoint:
        """Place the bubble beside the moth, clamped on-screen."""
        screen = QApplication.primaryScreen().availableGeometry()
        bw, bh = self._bubble.width(), self._bubble.height()
        # Prefer to the right of the moth; flip left if it would clip.
        bx = self.x() + self.SIZE + 8
        if bx + bw > screen.right():
            bx = self.x() - bw - 8
        by = self.y() + self.SIZE // 2 - bh // 2
        bx = max(screen.left() + 4, min(bx, screen.right() - bw - 4))
        by = max(screen.top() + 4, min(by, screen.bottom() - bh - 4))
        return QPoint(bx, by)

    def _hide_bubble(self):
        if self._bubble is not None:
            self._bubble.close()
            self._bubble = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            from techdeck.core.audio_manager import get_audio_manager
            get_audio_manager().play(_next_moth_sound())
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.dismiss()

    def dismiss(self):
        """Stop animating and remove the moth (programmatic shoo, e.g. on /clear)."""
        self._timer.stop()
        self._flying = False
        self._target_point = None
        self._hide_bubble()
        self.close()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw in 56x56 space, scaled down to 28x28
        painter.scale(0.5, 0.5)

        pen = QPen(self._OUTLINE, 1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        cx = 28.0   # center of 56x56 space
        cy = 32.0

        flap = math.sin(self._wing_phase) * 0.15 if self._flying else 0.0

        # Left upper wing
        path = QPainterPath()
        path.moveTo(cx, cy - 8)
        path.cubicTo(
            cx - 8 - flap * 30, cy - 26,
            cx - 22 - flap * 10, cy - 18,
            cx - 16, cy + 2,
        )
        path.cubicTo(cx - 9, cy + 4, cx - 3, cy - 2, cx, cy - 4)
        path.closeSubpath()
        painter.drawPath(path)

        # Right upper wing
        path = QPainterPath()
        path.moveTo(cx, cy - 8)
        path.cubicTo(
            cx + 8 + flap * 30, cy - 26,
            cx + 22 + flap * 10, cy - 18,
            cx + 16, cy + 2,
        )
        path.cubicTo(cx + 9, cy + 4, cx + 3, cy - 2, cx, cy - 4)
        path.closeSubpath()
        painter.drawPath(path)

        # Left lower wing
        path = QPainterPath()
        path.moveTo(cx - 2, cy - 2)
        path.cubicTo(
            cx - 14 - flap * 20, cy + 6,
            cx - 14, cy + 18,
            cx - 6, cy + 16,
        )
        path.cubicTo(cx - 3, cy + 12, cx - 1, cy + 6, cx - 1, cy + 2)
        path.closeSubpath()
        painter.drawPath(path)

        # Right lower wing
        path = QPainterPath()
        path.moveTo(cx + 2, cy - 2)
        path.cubicTo(
            cx + 14 + flap * 20, cy + 6,
            cx + 14, cy + 18,
            cx + 6, cy + 16,
        )
        path.cubicTo(cx + 3, cy + 12, cx + 1, cy + 6, cx + 1, cy + 2)
        path.closeSubpath()
        painter.drawPath(path)

        # Body
        painter.drawEllipse(QPointF(cx, cy + 2), 4, 12)

        # Head
        painter.drawEllipse(QPointF(cx, cy - 10), 4, 4)

        # Antennae
        thin_pen = QPen(self._OUTLINE, 1.0)
        thin_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(thin_pen)
        painter.drawLine(QPointF(cx - 1.5, cy - 13), QPointF(cx - 10, cy - 24))
        painter.drawLine(QPointF(cx + 1.5, cy - 13), QPointF(cx + 10, cy - 24))

        # Antennae tips
        painter.setPen(pen)
        painter.drawEllipse(QPointF(cx - 10.5, cy - 25), 2.2, 2.2)
        painter.drawEllipse(QPointF(cx + 10.5, cy - 25), 2.2, 2.2)

        painter.end()
