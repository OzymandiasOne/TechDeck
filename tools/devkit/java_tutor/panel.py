"""The DevKit entry for the Java Tutor.

Deliberately not an embed. The tutor is a full application window (its own
splitter, lesson sidebar and streaming transcript) and it long predates the
DevKit host; squeezing it into the tool canvas would mean reworking its
layout. So this panel is just a launcher: a Run button that opens the real
window, exactly as the plugin tile used to.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from techdeck.ui.theme_manager import get_theme_manager


class JavaTutorLauncher(QWidget):
    """Run button + one line of status. Opens (or re-focuses) the tutor."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Held on the instance, not a module global: the DevKit page caches
        # this panel for the app's lifetime, so the reference lives exactly as
        # long as it needs to and a second DevKit page would get its own.
        self._window = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(12)
        layout.addStretch()

        self._heading = QLabel("Java Tutor")
        heading_font = QFont()
        heading_font.setPointSize(16)
        heading_font.setBold(True)
        self._heading.setFont(heading_font)
        self._heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._heading)

        self._blurb = QLabel(
            "Opens the coaching window: streaming answers, Java-coloured code "
            "blocks,\nand a searchable history of past lessons.\n\n"
            "Needs Claude Code on this machine. Read-only by construction — "
            "it never writes your files.")
        self._blurb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._blurb)

        self._button = QPushButton("Run")
        self._button.setMinimumSize(140, 38)
        self._button.clicked.connect(self._launch)
        layout.addWidget(self._button, 0, Qt.AlignmentFlag.AlignCenter)

        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status)
        layout.addStretch()

        self._restyle()
        get_theme_manager().theme_changed.connect(lambda _n: self._restyle())

    def _restyle(self):
        pal = get_theme_manager().get_current_palette()
        self._blurb.setStyleSheet(f"color: {pal.text_secondary}; font-size: 13px;")
        self._status.setStyleSheet(f"color: {pal.text_secondary}; font-size: 12px;")

    def _launch(self):
        # Already open? Raise it rather than stacking a second window with a
        # second Claude session against the same 5-hour usage window.
        if self._window is not None and self._window.isVisible():
            self._window.raise_()
            self._window.activateWindow()
            return

        # Imported here, not at module import: the tutor pulls in the whole
        # chat stack, and a broken import must not take the DevKit registry
        # down with it (same reason every other tool lazy-imports).
        from tools.devkit.java_tutor import run as tutor

        # Take claude_session OFF the run module rather than importing it
        # directly. run.py loads its siblings by PATH under private names
        # ("techdeck_java_tutor_session"), so `from ... import claude_session`
        # would build a SECOND, unrelated module object - and its
        # ClaudeUnavailable would be a different class than the one the tutor
        # raises, which this except clause would then silently fail to catch.
        claude_session = tutor.claude_session

        try:
            exe = claude_session.find_claude()
        except claude_session.ClaudeUnavailable as exc:
            QMessageBox.warning(
                self, "Java Tutor",
                f"{exc}\n\nInstall Claude Code, then press Run again.")
            return

        self._window = tutor.JavaTutorWindow()
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()
        self._status.setText(f"Open — using Claude Code at {exe}")
