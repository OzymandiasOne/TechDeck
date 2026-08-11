"""Terminal surface for the Assistant page: the transcript, the word-bubble
chips, and the command line.

The transcript reuses the console's visual language (monospace, role-coloured
prefixes, dark panel) so it reads as the same kind of place as Home's console —
but it is a **separate** widget with its own history file, because this one has
to survive across sessions and the plugin console deliberately does not.
"""

from __future__ import annotations

from typing import Iterable, List

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QTextEdit, QLineEdit, QPushButton, QFrame,
)
from PySide6.QtCore import Qt, Signal, QUrl, QEvent
from PySide6.QtGui import QFont, QTextCursor, QDesktopServices

from techdeck.ui.theme_aware import ThemeAware
from techdeck.ui.widgets.flow_layout import FlowLayout

# Role → colour role. 'accent' and 'text*' resolve against the live palette;
# the two literals are the same ones the plugin console uses for user input and
# errors, so the two terminals stay recognisably related across every theme.
_USER_COLOR = "#60A5FA"
_ERROR_COLOR = "#EF4444"


class TerminalView(QTextEdit, ThemeAware):
    """Read-only scrollback with clickable links."""

    MAX_BLOCKS = 4000

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.document().setMaximumBlockCount(self.MAX_BLOCKS)
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setFrameShape(QFrame.Shape.NoFrame)
        # A read-only QTextEdit renders anchors but never acts on them — same
        # filter trick the plugin console uses.
        self.viewport().installEventFilter(self)
        self.viewport().setMouseTracking(True)
        self.setup_theme_awareness()

    def apply_theme(self):
        palette = self.get_current_palette()
        self.setStyleSheet(
            f"QTextEdit {{ border: none; background: {palette.console_bg};"
            f" color: {palette.console_text}; padding: 6px; }}")

    # -- appending -----------------------------------------------------------

    def append_line(self, role: str, text: str):
        palette = self.get_current_palette()
        body = _escape(text)

        if role == "user":
            html = (f'<span style="color: {_USER_COLOR}; font-weight: bold;">'
                    f'you &rsaquo;</span> <span style="color: {palette.text};">'
                    f'{body}</span>')
        elif role == "error":
            html = f'<span style="color: {_ERROR_COLOR};">{body}</span>'
        elif role == "system":
            html = f'<span style="color: {palette.text_secondary};">{body}</span>'
        elif role == "result":
            # Blocks of structured output (agendas, lists) get the plain body
            # colour and lean on their own indentation for structure.
            html = f'<span style="color: {palette.text};">{body}</span>'
        else:  # 'deck' — the assistant speaking
            html = (f'<span style="color: {palette.accent}; font-weight: bold;">'
                    f'&#9670;</span> <span style="color: {palette.text};">'
                    f'{body}</span>')
        self.append(html)
        self._scroll_to_bottom()

    def append_separator(self, label: str):
        """A dim, centred divider — used to mark where a previous session's
        history ends and this one begins."""
        palette = self.get_current_palette()
        self.append(
            f'<div style="color: {palette.text_secondary};">'
            f'──────── {_escape(label)} ────────</div>')
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)

    # -- links ---------------------------------------------------------------

    def eventFilter(self, obj, event):
        if obj is self.viewport():
            kind = event.type()
            if kind == QEvent.Type.MouseMove:
                anchor = self.anchorAt(event.position().toPoint())
                self.viewport().setCursor(
                    Qt.CursorShape.PointingHandCursor if anchor
                    else Qt.CursorShape.IBeamCursor)
            elif (kind == QEvent.Type.MouseButtonRelease
                  and event.button() == Qt.MouseButton.LeftButton):
                anchor = self.anchorAt(event.position().toPoint())
                if anchor:
                    QDesktopServices.openUrl(QUrl(anchor))
                    return True
        return super().eventFilter(obj, event)


class ChipBar(QWidget, ThemeAware):
    """The row of pressable word bubbles above the command line.

    Chips are the discoverable half of the page: everything they do can also be
    typed, but nobody reads a help screen before they need one. They wrap
    (FlowLayout) rather than scroll, so a narrow window loses no options.
    """

    chip_clicked = Signal(str)      # emits the chip's action key

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = FlowLayout(self, margin=0, hspacing=6, vspacing=6)
        self._buttons: List[QPushButton] = []
        self.setup_theme_awareness()

    def set_chips(self, chips: Iterable[tuple]):
        """``chips`` is an iterable of ``(key, label, tooltip)``."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._buttons.clear()

        for key, label, tooltip in chips:
            button = QPushButton(label)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(tooltip)
            button.setProperty("chipKey", key)
            button.setFlat(True)
            button.clicked.connect(
                lambda _checked=False, k=key: self.chip_clicked.emit(k))
            self._buttons.append(button)
            self._layout.addWidget(button)
        self.apply_theme()

    def apply_theme(self):
        palette = self.get_current_palette()
        sheet = f"""
            QPushButton {{
                background-color: {palette.surface};
                color: {palette.text};
                border: 1px solid {palette.border};
                border-radius: 13px;
                padding: 5px 14px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {palette.surface_hover};
                border-color: {palette.accent};
                color: {palette.accent};
            }}
            QPushButton:pressed {{
                background-color: {palette.tile_selected};
            }}
        """
        for button in self._buttons:
            button.setStyleSheet(sheet)


class CommandLine(QWidget, ThemeAware):
    """The input row: a single line with Up/Down recall and a Send button."""

    submitted = Signal(str)

    HISTORY_LIMIT = 200

    def __init__(self, parent=None):
        super().__init__(parent)
        self._history: List[str] = []
        self._history_pos = 0
        self._draft = ""

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self.field = QLineEdit()
        self.field.setMinimumHeight(38)
        # The placeholder is a promise. It used to advertise task shorthand,
        # which implied that typing files things — the opposite of the rule.
        self.field.setPlaceholderText(
            "Say anything — nothing gets filed unless you ask.  /help")
        self.field.returnPressed.connect(self._submit)
        self.field.installEventFilter(self)

        self.send_btn = QPushButton("Send")
        self.send_btn.setProperty("class", "primary")
        self.send_btn.setMinimumHeight(38)
        self.send_btn.setMinimumWidth(84)
        self.send_btn.clicked.connect(self._submit)

        row.addWidget(self.field, 1)
        row.addWidget(self.send_btn, 0)
        self.setup_theme_awareness()

    def apply_theme(self):
        palette = self.get_current_palette()
        self.field.setStyleSheet(
            f"QLineEdit {{ background: {palette.console_bg}; "
            f"color: {palette.console_text}; border: 1px solid {palette.border}; "
            f"border-radius: 8px; padding: 6px 10px; "
            f"font-family: Consolas, monospace; }}"
            f"QLineEdit:focus {{ border-color: {palette.accent}; }}")

    def seed_history(self, entries: Iterable[str]):
        """Prime Up-arrow recall from the persisted transcript, so yesterday's
        commands are still one keypress away."""
        self._history = [e for e in entries if e][-self.HISTORY_LIMIT:]
        self._history_pos = len(self._history)

    def focus(self):
        self.field.setFocus()

    def set_text(self, text: str):
        self.field.setText(text)
        self.field.setCursorPosition(len(text))
        self.field.setFocus()

    def _submit(self):
        text = self.field.text().strip()
        if not text:
            return
        self.field.clear()
        if not self._history or self._history[-1] != text:
            self._history.append(text)
            del self._history[:-self.HISTORY_LIMIT]
        self._history_pos = len(self._history)
        self._draft = ""
        self.submitted.emit(text)

    def eventFilter(self, obj, event):
        if obj is self.field and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Up:
                self._recall(-1)
                return True
            if key == Qt.Key.Key_Down:
                self._recall(1)
                return True
        return super().eventFilter(obj, event)

    def _recall(self, step: int):
        if not self._history:
            return
        if self._history_pos == len(self._history) and step < 0:
            self._draft = self.field.text()
        new_pos = self._history_pos + step
        if new_pos < 0:
            new_pos = 0
        if new_pos >= len(self._history):
            self._history_pos = len(self._history)
            self.field.setText(self._draft)
            self.field.setCursorPosition(len(self._draft))
            return
        self._history_pos = new_pos
        entry = self._history[new_pos]
        self.field.setText(entry)
        self.field.setCursorPosition(len(entry))


def _escape(text: str) -> str:
    """HTML-escape and keep the line breaks + leading indentation that the
    brain's block output relies on for structure."""
    escaped = (str(text).replace("&", "&amp;").replace("<", "&lt;")
               .replace(">", "&gt;"))
    # Runs of spaces collapse in HTML; the agenda's alignment is the whole point.
    escaped = escaped.replace("\n", "<br>")
    out, run = [], 0
    for char in escaped:
        if char == " ":
            run += 1
        else:
            out.append("&nbsp;" * run if run > 1 else " " * run)
            run = 0
            out.append(char)
    out.append("&nbsp;" * run if run > 1 else " " * run)
    return "".join(out)
