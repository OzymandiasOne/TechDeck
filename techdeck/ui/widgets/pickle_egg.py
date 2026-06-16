"""
TechDeck Pickle Easter Egg
A frameless popup that shows a hidden photo when the user clicks the
"TechDeck" wordmark in the sidebar header. Click anywhere on it (or press
Esc) to dismiss. Only one shows at a time.
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap


def _assets_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets"
    return Path(__file__).resolve().parents[3] / "assets"


def _egg_image_path() -> Path:
    return _assets_dir() / "easter_egg" / "pickled.jpg"


# Module-level handle so Qt doesn't garbage-collect the popup (it has no
# parent) and so only one is ever on screen at a time.
_active_popup: "PickleEgg | None" = None


class PickleEgg(QWidget):
    """Frameless, always-on-top photo popup. Click or Esc to dismiss."""

    MAX_SIDE = 480  # cap the long edge so it never fills the screen

    def __init__(self, anchor: QWidget | None = None):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel(self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix = QPixmap(str(_egg_image_path()))
        if not pix.isNull():
            pix = pix.scaled(
                self.MAX_SIDE, self.MAX_SIDE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            label.setPixmap(pix)
        else:
            label.setText("they're pickling me at work tomorrow")
            label.setStyleSheet("color: #fff; background: #222; padding: 40px;")
        layout.addWidget(label)

        self.adjustSize()
        self._center_on(anchor)

    def _center_on(self, anchor: QWidget | None):
        """Center over the host window, or the screen if there's none."""
        if anchor is not None and anchor.window().isVisible():
            geo = anchor.window().geometry()
        else:
            screen = QApplication.primaryScreen()
            geo = screen.availableGeometry() if screen else None
        if geo is not None:
            self.move(
                geo.center().x() - self.width() // 2,
                geo.center().y() - self.height() // 2,
            )

    def mousePressEvent(self, event):
        self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)


def show_pickle_egg(anchor: QWidget | None = None):
    """Show the pickle popup, replacing any popup already on screen."""
    global _active_popup
    if _active_popup is not None:
        try:
            _active_popup.close()
        except RuntimeError:
            pass
        _active_popup = None
    _active_popup = PickleEgg(anchor)
    _active_popup.show()
    _active_popup.raise_()
    _active_popup.activateWindow()
