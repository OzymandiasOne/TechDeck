"""
TechDeck Crab Widget
An ASCII art crab that walks horizontally across the screen, bouncing off
the edges. Colors cycle through a neon rainbow. Double-click to dismiss.
"""

import random
from PySide6.QtWidgets import QWidget, QLabel, QApplication
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont


class CrabWidget(QWidget):
    """
    Frameless, always-on-top ASCII dancing crab.
    Walks left/right across the screen at a fixed Y position.
    Cycles through two dance frames and a neon rainbow palette.
    """

    _FRAMES = [
        "\\(^·^)/\n [___] \n/|   |\\",
        "/(^·^)\\\n [___] \n\\|   |/",
    ]

    _COLORS = [
        "#FF2080", "#FF8000", "#FFE000",
        "#00E060", "#00CFFF", "#CC00FF",
        "#FF2080", "#48DBFB", "#FF9FF3",
    ]

    SPEED = 4       # px per tick (60fps → ~240px/sec)
    FONT_SIZE = 11

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._frame_idx = 0
        self._color_idx = 0
        self._direction = 1  # 1 = right, -1 = left
        self._tick_count = 0
        self._drag_pos = None
        self._patrol_left = 0   # left boundary of patrol range
        self._patrol_right = 0  # right boundary of patrol range

        # Label for ASCII art
        self._label = QLabel(self)
        self._label.setTextFormat(Qt.TextFormat.PlainText)
        self._label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        font = QFont("Consolas", self.FONT_SIZE)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setBold(True)
        self._label.setFont(font)

        self._label.setText(self._FRAMES[0])
        self._apply_color()
        self._label.adjustSize()
        w = self._label.width() + 6
        h = self._label.height() + 6
        self.resize(w, h)
        self._label.setGeometry(3, 3, self._label.width(), self._label.height())

        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60fps
        self._timer.timeout.connect(self._tick)

    def start(self):
        """Place at a random screen position with a local patrol range."""
        screen = QApplication.primaryScreen().geometry()

        patrol_width = random.randint(150, 350)
        center_x = random.randint(screen.left() + patrol_width // 2,
                                  screen.right() - patrol_width // 2)
        y = random.randint(int(screen.height() * 0.15),
                           int(screen.height() * 0.85))

        self._patrol_left = center_x - patrol_width // 2
        self._patrol_right = center_x + patrol_width // 2
        self._direction = random.choice([-1, 1])

        self.move(center_x, y)
        self.show()
        self.raise_()
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self.hide()

    def _tick(self):
        self._tick_count += 1

        # Switch dance frame every 8 ticks (~7.5fps)
        if self._tick_count % 8 == 0:
            self._frame_idx = (self._frame_idx + 1) % len(self._FRAMES)
            self._label.setText(self._FRAMES[self._frame_idx])

        # Cycle color every 5 ticks (~12fps)
        if self._tick_count % 5 == 0:
            self._color_idx = (self._color_idx + 1) % len(self._COLORS)
            self._apply_color()

        # Move within patrol range
        new_x = self.x() + self.SPEED * self._direction

        if new_x + self.width() > self._patrol_right:
            self._direction = -1
        elif new_x < self._patrol_left:
            self._direction = 1

        self.move(new_x, self.y())

    def _apply_color(self):
        color = self._COLORS[self._color_idx]
        self._label.setStyleSheet(
            f"color: {color}; background: transparent;"
        )

    def mouseDoubleClickEvent(self, event):
        self.stop()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
