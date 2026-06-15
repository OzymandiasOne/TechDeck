"""Live preview for the /fidget spinner so you can redesign its pixel art fast.

Edit the SPINNER_ART grid in techdeck/ui/widgets/fidget_spinner.py, then RE-RUN
this script to see the result spinning — no need to launch the whole app.

    python tools/preview_spinner.py [theme]

  theme : dark | light | blue | cherry_blossom | cyberpunk | matrix  (default dark)

Press a number key 1-6 to cycle themes, SPACE to pause/resume, click to flick it,
Esc to quit.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtGui import QPainter, QColor
from PySide6.QtCore import Qt, QTimer

from techdeck.ui.theme_manager import get_theme_manager
from techdeck.ui.widgets.fidget_spinner import _render_spinner_pixmap, FidgetSpinnerWindow

THEMES = ["dark", "light", "blue", "cherry_blossom", "cyberpunk", "matrix"]


class Preview(QWidget):
    def __init__(self, theme):
        super().__init__()
        self.setWindowTitle("Spinner preview — 1-6 theme · space pause · click flick · Esc quit")
        self.resize(440, 480)
        self._i = THEMES.index(theme) if theme in THEMES else 0
        self._angle = 0.0
        self._vel = 3.0
        self._spin = True
        self._render()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _render(self):
        tm = get_theme_manager()
        tm.set_theme(THEMES[self._i])
        self._pal = tm.get_current_palette()
        self._pm = _render_spinner_pixmap(FidgetSpinnerWindow._theme_colors())
        self.update()

    def _tick(self):
        if self._spin:
            self._vel *= FidgetSpinnerWindow.FRICTION
            self._angle += self._vel * 0.016
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(self._pal.background))
        p.setPen(QColor(self._pal.text))
        p.drawText(10, 20, f"theme={THEMES[self._i]}   (1-6 theme · space pause · click flick · Esc quit)")
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.translate(self.width() / 2.0, self.height() / 2.0 + 12)
        p.rotate(math.degrees(self._angle))
        p.drawPixmap(-self._pm.width() // 2, -self._pm.height() // 2, self._pm)
        p.end()

    def mousePressEvent(self, e):
        self._vel += FidgetSpinnerWindow.CLICK_IMPULSE

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key.Key_Escape:
            self.close()
        elif k == Qt.Key.Key_Space:
            self._spin = not self._spin
        elif Qt.Key.Key_1 <= k <= Qt.Key.Key_6:
            self._i = k - Qt.Key.Key_1
            self._render()


def main():
    theme = sys.argv[1] if len(sys.argv) > 1 else "dark"
    app = QApplication(sys.argv)
    w = Preview(theme)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
