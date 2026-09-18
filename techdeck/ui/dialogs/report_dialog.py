"""
TechDeck Plugin Report Dialog
=============================
The pop-up a plugin shows when its result is something a person has to READ,
not a file they have to go and find. Opened through ``sdk.show_report``.

Why it exists: 911 Inspection Dimensions used to end by writing a .txt into the
nest folder and printing the path to the console. The report is the whole point
of that app -- an inspector works down it with the drawing in hand -- and it was
landing somewhere they had to go dig for, in a folder tree deep enough to be
awkward. Now the run ends by putting it on the screen, and saving is a button
they press if they want the copy.

Contract:
  * MODELESS on purpose. The run is finished by the time this opens; blocking the
    worker thread would leave the app looking busy while somebody reads.
  * The caller keeps it alive. Qt garbage-collects a parentless dialog the moment
    the last Python reference drops (CLAUDE.md Hard Rule 4) -- the console holds
    the reference, and the dialog clears it on close.
  * ``save_path`` is where the Save button writes, chosen by the caller so the
    file lands next to the work it describes.
"""

import os

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QFrame,
)
from PySide6.QtCore import Qt

from techdeck.ui.theme_manager import get_theme_manager


class ReportDialog(QDialog):
    """A plugin's finished report, on screen, with a Save-as-.txt button."""

    def __init__(self, title: str, subtitle: str, body: str,
                 save_path: str = "", parent=None):
        super().__init__(parent)
        self.theme = get_theme_manager().get_current_palette()
        self._body = body
        self._save_path = save_path
        self._saved_to = ""

        self.setWindowTitle(title)
        self.setModal(False)
        self.setMinimumSize(620, 460)
        self.resize(860, 760)

        t = self.theme
        self.setStyleSheet(f"QDialog {{ background-color: {t.background}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        header = QLabel(title)
        header.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {t.text};")
        layout.addWidget(header)

        if subtitle:
            sub = QLabel(subtitle)
            sub.setWordWrap(True)
            sub.setStyleSheet(f"color: {t.text_secondary}; font-size: 12px;")
            layout.addWidget(sub)

        # The report is column-aligned plain text, so it needs a fixed-pitch font
        # and NO wrapping - wrapping would shuffle the number columns out of line.
        view = QPlainTextEdit()
        view.setPlainText(body)
        view.setReadOnly(True)
        view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        view.setFrameShape(QFrame.Shape.NoFrame)
        # The font MUST come from this widget's own stylesheet, not setFont(): the
        # app-level sheet sets font-family on QWidget, and QSS beats setFont(), so a
        # setFont() monospace silently renders proportional - which lines the ruled
        # dividers and number columns up wrong (caught on the first render).
        view.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {t.surface}; color: {t.text};
                border: 1px solid {t.border}; border-radius: 6px; padding: 10px;
                font-family: Consolas, "Cascadia Mono", "Courier New", monospace;
                font-size: 12px;
            }}
            QScrollBar:vertical, QScrollBar:horizontal {{
                background: transparent; width: 10px; height: 10px; margin: 0;
            }}
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
                background: {t.border_strong}; border-radius: 5px; min-height: 30px;
            }}
            QScrollBar::add-line, QScrollBar::sub-line {{
                height: 0; width: 0; background: none;
            }}
        """)
        layout.addWidget(view, stretch=1)

        self._status = QLabel(self._where_it_will_go())
        self._status.setWordWrap(True)
        self._status.setStyleSheet(f"color: {t.text_secondary}; font-size: 11px;")
        layout.addWidget(self._status)

        row = QHBoxLayout()
        row.addStretch()
        if save_path:
            self._save_btn = QPushButton("Save as .txt")
            self._save_btn.setMinimumHeight(34)
            self._save_btn.setMinimumWidth(140)
            self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._save_btn.setStyleSheet(self._button_css(primary=True))
            self._save_btn.clicked.connect(self._save)
            row.addWidget(self._save_btn)

        close_btn = QPushButton("Close")
        close_btn.setMinimumHeight(34)
        close_btn.setMinimumWidth(110)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(self._button_css(primary=not save_path))
        close_btn.clicked.connect(self.accept)
        row.addWidget(close_btn)
        layout.addLayout(row)

    # ------------------------------------------------------------------ #

    def _button_css(self, primary: bool) -> str:
        t = self.theme
        if primary:
            return f"""
                QPushButton {{
                    background-color: {t.accent}; color: {t.accent_text};
                    border: none; border-radius: 6px; font-weight: 600;
                }}
                QPushButton:hover {{ background-color: {t.accent_hover}; }}
                QPushButton:pressed {{ background-color: {t.accent_pressed}; }}
            """
        return f"""
            QPushButton {{
                background-color: transparent; color: {t.text};
                border: 1px solid {t.border_strong}; border-radius: 6px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {t.surface}; }}
        """

    def _where_it_will_go(self) -> str:
        if not self._save_path:
            return "Nothing to save - this report is on screen only."
        return "Save puts it in:  %s" % os.path.dirname(self._save_path)

    def _save(self):
        """Write the report next to the work it describes."""
        from techdeck.core import plugin_sdk as sdk

        try:
            path = sdk.long_path(self._save_path)      # Hard Rule 14
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self._body)
        except OSError as exc:
            self._status.setText("Could not save it: %s" % exc)
            self._status.setStyleSheet(
                f"color: {self.theme.error}; font-size: 11px;")
            return
        self._saved_to = self._save_path
        self._status.setText("Saved:  %s" % self._save_path)
        self._save_btn.setText("Saved")

    @property
    def saved_to(self) -> str:
        """Where the user saved it, or "" if they never pressed the button."""
        return self._saved_to
