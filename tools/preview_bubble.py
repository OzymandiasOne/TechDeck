"""Live preview for the /moth speech bubble so you can redesign it fast.

Edit the BUBBLE_CORNER / BUBBLE_TAIL grids (and SpeechBubble) in
techdeck/ui/widgets/moth_widget.py, then RE-RUN this script to see the result --
no need to launch the whole app.

    python tools/preview_bubble.py [theme] [corner] [text]

  theme  : dark | light | blue | cherry_blossom | cyberpunk | matrix   (default light)
  corner : bl | br | tl | tr                                           (default bl)
  text   : custom text; use \\n for line breaks   (default: a sample haiku)

Press a number key 1-6 to cycle themes, b/r/t/y to cycle the corner, Esc to quit.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication, QWidget, QLabel
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt, QPoint

from techdeck.ui.theme_manager import get_theme_manager
from techdeck.ui.widgets.moth_widget import SpeechBubble

THEMES = ["light", "dark", "blue", "cherry_blossom", "cyberpunk", "matrix"]
CORNERS = ["bl", "br", "tl", "tr"]
SAMPLE = "steel meets the laser\nsparks dance on the cutting bed\nproduction hums on"


def colors(pal):
    """Match command_handler: surface fill, accent frame, warm distinct text."""
    bg, frame = QColor(pal.surface), QColor(pal.accent)
    lum = 0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()
    fg = QColor("#3A2A14") if lum > 150 else QColor("#F3EAD2")
    return fg, bg, frame


class Preview(QWidget):
    def __init__(self, theme, corner, text):
        super().__init__()
        self.setWindowTitle("Speech bubble preview — keys: 1-6 theme, b/r/t/y corner, Esc quit")
        self.resize(720, 440)
        self._theme_i = THEMES.index(theme) if theme in THEMES else 0
        self._corner = corner if corner in CORNERS else "bl"
        self._text = text or SAMPLE
        self._bubble = None
        self._hint = QLabel(self)
        self._hint.move(12, 8)
        self._render()

    def _render(self):
        tm = get_theme_manager()
        tm.set_theme(THEMES[self._theme_i])
        pal = tm.get_current_palette()
        self.setStyleSheet(f"background-color: {pal.background};")
        self._hint.setStyleSheet(f"color: {pal.text_secondary}; font-size: 12px;")
        self._hint.setText(f"theme={THEMES[self._theme_i]}  corner={self._corner}  "
                           f"(1-6 theme · b/r/t/y corner · Esc quit)")
        self._hint.adjustSize()
        if self._bubble is not None:
            self._bubble.close()
        fg, bg, frame = colors(pal)
        b = SpeechBubble(self._text, fg, bg, frame, corner=self._corner, parent=self)
        b.set_tail(self._corner)
        b._revealed = b._total                       # show it fully (skip the typing)
        b.move((self.width() - b.width()) // 2, (self.height() - b.height()) // 2)
        b.show()
        self._bubble = b

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key.Key_Escape:
            self.close()
        elif Qt.Key.Key_1 <= k <= Qt.Key.Key_6:
            self._theme_i = k - Qt.Key.Key_1
            self._render()
        elif k in (Qt.Key.Key_B, Qt.Key.Key_R, Qt.Key.Key_T, Qt.Key.Key_Y):
            self._corner = {Qt.Key.Key_B: "bl", Qt.Key.Key_R: "br",
                            Qt.Key.Key_T: "tl", Qt.Key.Key_Y: "tr"}[k]
            self._render()


def main():
    argv = sys.argv[1:]
    theme = argv[0] if len(argv) > 0 else "light"
    corner = argv[1] if len(argv) > 1 else "bl"
    text = argv[2].replace("\\n", "\n") if len(argv) > 2 else None
    app = QApplication(sys.argv)
    w = Preview(theme, corner, text)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
