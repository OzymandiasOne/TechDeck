"""
TechDeck Fidget Spinner
A standalone window with a chrome fidget spinner drawn entirely in QPainter.
Click anywhere on the spinner to add angular velocity.
"""

import math
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer, QPointF, QRectF
from PySide6.QtGui import (
    QPainter, QColor, QBrush, QPen, QRadialGradient, QLinearGradient,
    QPainterPath,
)


class FidgetSpinnerWindow(QWidget):
    """
    Frameless, always-on-top fidget spinner.
    Three rounded chrome lobes 120 degrees apart around a center bearing.
    Click to add velocity; friction = 0.995 per frame at 60fps.
    """

    WINDOW_SIZE = 300
    LOBE_RADIUS = 90     # distance from center to lobe center
    LOBE_SIZE = 70       # width/height of each lobe ellipse
    BEARING_RADIUS = 22  # center hub

    FRICTION = 0.995
    CLICK_IMPULSE = 2.5  # radians/sec added per click

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0.0      # radians
        self._velocity = 1.0   # radians/sec

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

        # For dragging the window
        self._drag_pos = None

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

    def mouseDoubleClickEvent(self, event):
        self.close()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx = self.WINDOW_SIZE / 2
        cy = self.WINDOW_SIZE / 2

        # Draw the three lobes
        for i in range(3):
            lobe_angle = self._angle + i * (2 * math.pi / 3)
            lx = cx + self.LOBE_RADIUS * math.cos(lobe_angle)
            ly = cy + self.LOBE_RADIUS * math.sin(lobe_angle)
            self._draw_lobe(painter, lx, ly, lobe_angle)

        # Draw center bearing
        self._draw_bearing(painter, cx, cy)

        painter.end()

    def _draw_lobe(self, painter: QPainter, cx: float, cy: float, angle: float):
        s = self.LOBE_SIZE
        half = s / 2

        # Chrome gradient — light source from top-left
        grad = QRadialGradient(QPointF(cx - half * 0.3, cy - half * 0.3), s * 0.8)
        grad.setColorAt(0.0, QColor(240, 240, 248))   # near-white highlight
        grad.setColorAt(0.35, QColor(180, 185, 200))  # mid chrome
        grad.setColorAt(0.7, QColor(110, 115, 130))   # darker chrome
        grad.setColorAt(1.0, QColor(70, 72, 85))      # shadow edge

        painter.save()
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(QColor(55, 57, 70), 1.5))
        rect = QRectF(cx - half, cy - half, s, s)
        painter.drawEllipse(rect)

        # Specular highlight — small bright oval
        hi_grad = QRadialGradient(QPointF(cx - half * 0.25, cy - half * 0.3), half * 0.5)
        hi_grad.setColorAt(0.0, QColor(255, 255, 255, 180))
        hi_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(hi_grad))
        painter.setPen(Qt.PenStyle.NoPen)
        hi_w, hi_h = s * 0.35, s * 0.25
        painter.drawEllipse(QRectF(cx - hi_w / 2 - half * 0.1, cy - hi_h / 2 - half * 0.2, hi_w, hi_h))

        painter.restore()

    def _draw_bearing(self, painter: QPainter, cx: float, cy: float):
        r = self.BEARING_RADIUS

        # Outer ring
        outer_grad = QRadialGradient(QPointF(cx - r * 0.3, cy - r * 0.3), r * 1.4)
        outer_grad.setColorAt(0.0, QColor(210, 215, 225))
        outer_grad.setColorAt(0.5, QColor(140, 145, 158))
        outer_grad.setColorAt(1.0, QColor(80, 82, 95))
        painter.setBrush(QBrush(outer_grad))
        painter.setPen(QPen(QColor(50, 52, 65), 1.5))
        painter.drawEllipse(QPointF(cx, cy), r, r)

        # Inner ring (darker recess)
        inner_r = r * 0.55
        inner_grad = QRadialGradient(QPointF(cx + inner_r * 0.2, cy + inner_r * 0.2), inner_r * 1.2)
        inner_grad.setColorAt(0.0, QColor(60, 62, 75))
        inner_grad.setColorAt(0.6, QColor(95, 98, 112))
        inner_grad.setColorAt(1.0, QColor(150, 153, 168))
        painter.setBrush(QBrush(inner_grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx, cy), inner_r, inner_r)

        # Center dot
        dot_r = inner_r * 0.35
        painter.setBrush(QBrush(QColor(40, 42, 55)))
        painter.drawEllipse(QPointF(cx, cy), dot_r, dot_r)
