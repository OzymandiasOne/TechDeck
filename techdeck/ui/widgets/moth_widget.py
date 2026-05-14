"""
TechDeck Moth Widget
A small moth that flies from a random screen edge toward a target UI element.
/moth sends it somewhere new. Double-click to shoo it away entirely.
Outline-only style, no fill.
"""

import math
import random
from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import Qt, QTimer, QPointF, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath


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
        self._target: QWidget | None = None

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def fly_to(self, target_widget: QWidget):
        """Set a new target and start animating."""
        self._target = target_widget
        self._flying = True
        self._timer.start()
        self.show()
        self.raise_()

    def spawn_from_edge(self, target_widget: QWidget):
        """Pick a random screen edge, start there, then fly to target."""
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
        self.fly_to(target_widget)

    def _target_global_pos(self) -> QPoint | None:
        if self._target is None or not self._target.isVisible():
            return None
        center = self._target.rect().center()
        return self._target.mapToGlobal(center) - QPoint(self.SIZE // 2, self.SIZE // 2)

    def _tick(self):
        self._wing_phase += 0.35

        target = self._target_global_pos()
        if target is None:
            self._timer.stop()
            return

        dx = target.x() - self.x()
        dy = target.y() - self.y()
        dist = math.hypot(dx, dy)

        if dist < 3:
            self.move(target)
            self._flying = False
        else:
            speed = min(dist * 0.08, 12)
            nx = self.x() + dx / dist * speed + random.uniform(-1, 1)
            ny = self.y() + dy / dist * speed + random.uniform(-1, 1)
            self.move(int(nx), int(ny))

        self.update()

    def mouseDoubleClickEvent(self, event):
        self._timer.stop()
        self.hide()
        self._target = None

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
