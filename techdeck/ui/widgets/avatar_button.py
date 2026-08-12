"""A clickable profile picture, the Office 365 way.

Shows the avatar; on hover it dims and puts a camera on top, which is the
whole affordance. No "Choose image…" button, no explanatory paragraph: the
picture IS the button, and the tooltip says the rest.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal, QRectF, QSize
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap

# How dark the picture goes under the camera. Enough to read a white glyph
# against a photo of anything, including a white wall.
_SCRIM = QColor(0, 0, 0, 140)


class AvatarButton(QWidget):
    """Click to change the picture. Emits :attr:`clicked`."""

    clicked = Signal()

    def __init__(self, size: int = 72, parent=None):
        super().__init__(parent)
        self._size = size
        self._pixmap: Optional[QPixmap] = None
        self._hover = False
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Change or add profile picture")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def sizeHint(self) -> QSize:
        return QSize(self._size, self._size)

    def set_pixmap(self, pixmap: QPixmap):
        self._pixmap = pixmap
        self.update()

    # -- interaction ---------------------------------------------------------

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
                event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(event)

    # -- painting ------------------------------------------------------------

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if self._pixmap is not None and not self._pixmap.isNull():
            painter.drawPixmap(0, 0, self._pixmap.scaled(
                self._size, self._size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))

        if not self._hover:
            return

        # The avatar is already a circle, so the scrim has to be one too or it
        # paints over the corners the picture deliberately left empty.
        circle = QPainterPath()
        circle.addEllipse(0, 0, self._size, self._size)
        painter.fillPath(circle, _SCRIM)
        _draw_camera(painter, self._size)


def _draw_camera(painter: QPainter, size: int):
    """A camera glyph, centred, drawn rather than shipped as an asset so it
    stays crisp at whatever size the avatar is."""
    glyph = size * 0.42
    left = (size - glyph) / 2.0
    top = (size - glyph * 0.78) / 2.0
    white = QColor("#FFFFFF")

    body = QRectF(left, top, glyph, glyph * 0.78)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(white)

    # Viewfinder bump on top of the body, offset left like a real camera.
    bump = QRectF(left + glyph * 0.18, top - glyph * 0.14,
                  glyph * 0.30, glyph * 0.18)
    painter.drawRoundedRect(bump, glyph * 0.05, glyph * 0.05)
    painter.drawRoundedRect(body, glyph * 0.14, glyph * 0.14)

    # Punch the lens back out of the body so the glyph reads at 20px as well
    # as at 100. A filled lens turns into a white blob when it is small.
    painter.setCompositionMode(
        QPainter.CompositionMode.CompositionMode_DestinationOut)
    centre = body.center()
    radius = glyph * 0.23
    painter.setBrush(QColor(0, 0, 0, 255))
    painter.drawEllipse(centre, radius, radius)
    painter.setCompositionMode(
        QPainter.CompositionMode.CompositionMode_SourceOver)
