"""
TechDeck Splash Screen
======================
Frameless splash window shown at app startup. The window's size matches the
native frame size of assets/images/splash.gif, which is played full-bleed
via QMovie. A status caption is overlaid centered on top of the GIF with a
drop-shadow for readability.

Call `update_caption(text)` between heavy init steps to repaint and pump
the event loop. The QMovie animates whenever Qt is processing events.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QMovie, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QLabel,
    QWidget,
)


_CAPTION_COLOR = "#FFFFFF"
_CAPTION_POINT_SIZE = 14
_SHADOW_BLUR = 40
_SHADOW_OFFSET_Y = 4
_SHADOW_ALPHA = 255
_CORNER_RADIUS = 16


class _RoundedMovieLabel(QLabel):
    """QLabel that clips its QMovie frame to a rounded rect with antialiasing.
    Per-frame cost is a clip-path setup (sub-microsecond) on top of the
    repaint QMovie was doing anyway — no measurable perf impact."""

    def __init__(self, radius: int, parent=None):
        super().__init__(parent)
        self._radius = radius

    def paintEvent(self, event):
        movie = self.movie()
        if movie is None:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        path = QPainterPath()
        path.addRoundedRect(self.rect(), self._radius, self._radius)
        painter.setClipPath(path)
        painter.drawPixmap(self.rect(), movie.currentPixmap())


class SplashScreen(QWidget):
    """Frameless GIF splash. Construct only when the GIF exists."""

    def __init__(self, gif_path: Path):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.SplashScreen
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Load GIF and size the window to its native frame
        self._movie = QMovie(str(gif_path))
        if not self._movie.isValid():
            raise RuntimeError(f"Invalid GIF: {gif_path}")

        # Pre-decode every frame into memory. Without this, QMovie decodes
        # each frame on demand, and any moment the main thread is blocked
        # while the next frame is needed = a missed frame. CacheAll trades
        # memory for buttery-smooth playback once the event loop ticks.
        self._movie.setCacheMode(QMovie.CacheMode.CacheAll)

        self._movie.jumpToFrame(0)
        frame_size = self._movie.currentImage().size()
        if frame_size.isEmpty():
            raise RuntimeError(f"Could not determine frame size of GIF: {gif_path}")

        self.setFixedSize(frame_size)

        # GIF label fills the window; custom subclass clips to rounded corners.
        self._gif_label = _RoundedMovieLabel(_CORNER_RADIUS, self)
        self._gif_label.setGeometry(0, 0, frame_size.width(), frame_size.height())
        self._gif_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._gif_label.setMovie(self._movie)
        self._movie.start()

        # Caption overlay — centered, drop shadow for readability
        self._caption = QLabel("Starting...", self)
        self._caption.setGeometry(0, 0, frame_size.width(), frame_size.height())
        self._caption.setAlignment(Qt.AlignmentFlag.AlignCenter)

        font = QFont(self._caption.font())
        font.setPointSize(_CAPTION_POINT_SIZE)
        font.setWeight(QFont.Weight.DemiBold)
        self._caption.setFont(font)
        self._caption.setStyleSheet(
            f"color: {_CAPTION_COLOR}; background: transparent;"
        )

        shadow = QGraphicsDropShadowEffect(self._caption)
        shadow.setBlurRadius(_SHADOW_BLUR)
        shadow.setOffset(0, _SHADOW_OFFSET_Y)
        shadow.setColor(QColor(0, 0, 0, _SHADOW_ALPHA))
        self._caption.setGraphicsEffect(shadow)
        self._caption.raise_()

        self._center_on_screen()

    def update_caption(self, text: str):
        """Update the status caption and pump the event loop so the splash
        repaints (and the GIF advances) before the next heavy step."""
        self._caption.setText(text)
        QApplication.processEvents()

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geom = screen.availableGeometry()
        x = geom.x() + (geom.width() - self.width()) // 2
        y = geom.y() + (geom.height() - self.height()) // 2
        self.move(x, y)

    def close(self):
        self._movie.stop()
        super().close()
