"""Personal Notes tab, a note list beside a bullet-aware plain-text editor.

Notes are **plain text**, not rich text, and that is a deliberate choice: a
plain note stays greppable by ``/find``, exports to markdown unchanged, and
survives any future change to how it's displayed. Nesting is expressed the way
everyone already types it, two spaces per level with a ``-`` marker, and the
editor just makes that ergonomic (Enter continues the bullet, Tab nests it).
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QListWidget, QListWidgetItem,
    QLineEdit, QPushButton, QLabel, QTextEdit, QMessageBox, QFrame,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QTextCursor

from techdeck.core.assistant.models import Note
from techdeck.core.assistant.store import AssistantStore
from techdeck.ui.theme_aware import ThemeAware

INDENT = "  "          # two spaces per nesting level
BULLET = "- "


class BulletEditor(QTextEdit, ThemeAware):
    """Plain-text editor that knows about nested bullets.

    * **Enter** continues the current bullet at the same indent. On an *empty*
      bullet it outdents instead, then clears, so you walk back out of a list
      by pressing Enter, exactly like every other outliner.
    * **Tab / Shift+Tab** nest and un-nest the current line, or every line in
      the selection.
    * **Ctrl+D** duplicates the line, which is most of what list-building is.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        font = QFont("Consolas", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setTabStopDistance(28)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setup_theme_awareness()

    def apply_theme(self):
        palette = self.get_current_palette()
        self.setStyleSheet(
            f"QTextEdit {{ background: {palette.console_bg}; "
            f"color: {palette.console_text}; border: 1px solid {palette.border}; "
            f"border-radius: 8px; padding: 10px; selection-background-color: "
            f"{palette.accent}; }}")

    # -- key handling --------------------------------------------------------

    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()

        if key == Qt.Key.Key_Tab and not (modifiers & Qt.KeyboardModifier.ControlModifier):
            self._shift_indent(+1)
            return
        if key == Qt.Key.Key_Backtab or (
                key == Qt.Key.Key_Tab and modifiers & Qt.KeyboardModifier.ShiftModifier):
            self._shift_indent(-1)
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
                modifiers & Qt.KeyboardModifier.ShiftModifier):
            if self._continue_bullet():
                return
        if key == Qt.Key.Key_D and modifiers & Qt.KeyboardModifier.ControlModifier:
            self._duplicate_line()
            return
        super().keyPressEvent(event)

    def _current_line(self) -> str:
        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.LineUnderCursor)
        return cursor.selectedText()

    def _continue_bullet(self) -> bool:
        """Returns True when the Enter was handled here."""
        line = self._current_line()
        stripped = line.lstrip()
        indent = line[:len(line) - len(stripped)]

        if not stripped.startswith(("- ", "* ", "• ")) and stripped not in ("-", "*", "•"):
            return False

        marker = stripped[:2] if len(stripped) > 1 else stripped + " "
        content = stripped[len(marker):].strip()

        cursor = self.textCursor()
        if not content:
            # Empty bullet: step out one level, or drop the bullet entirely at
            # the outer level. This is how you end a list without reaching for
            # the mouse.
            cursor.select(QTextCursor.SelectionType.LineUnderCursor)
            if len(indent) >= len(INDENT):
                cursor.insertText(indent[:-len(INDENT)] + marker)
            else:
                cursor.insertText("")
            self.setTextCursor(cursor)
            return True

        cursor.insertText("\n" + indent + marker)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
        return True

    def _shift_indent(self, direction: int):
        cursor = self.textCursor()
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        cursor.beginEditBlock()

        cursor.setPosition(start)
        first_block = cursor.blockNumber()
        cursor.setPosition(end)
        last_block = cursor.blockNumber()

        block = self.document().findBlockByNumber(first_block)
        while block.isValid() and block.blockNumber() <= last_block:
            text = block.text()
            edit = QTextCursor(block)
            edit.select(QTextCursor.SelectionType.BlockUnderCursor)
            if direction > 0:
                new_text = INDENT + text
            else:
                new_text = text[len(INDENT):] if text.startswith(INDENT) \
                    else text.lstrip(" ")
            # BlockUnderCursor selects the leading newline too on every block
            # after the first, replace only the text and keep the break.
            edit.setPosition(block.position())
            edit.setPosition(block.position() + len(text),
                             QTextCursor.MoveMode.KeepAnchor)
            edit.insertText(new_text)
            block = block.next()

        cursor.endEditBlock()

    def _duplicate_line(self):
        cursor = self.textCursor()
        line = self._current_line()
        cursor.movePosition(QTextCursor.MoveOperation.EndOfLine)
        cursor.insertText("\n" + line)
        self.setTextCursor(cursor)

    def add_bullet(self):
        """Toolbar action: turn the current line into a bullet, or start one."""
        cursor = self.textCursor()
        line = self._current_line()
        stripped = line.lstrip()
        if stripped.startswith(("- ", "* ", "• ")):
            return
        indent = line[:len(line) - len(stripped)]
        cursor.select(QTextCursor.SelectionType.LineUnderCursor)
        cursor.insertText(indent + BULLET + stripped)
        self.setTextCursor(cursor)
        self.setFocus()


class NotesPanel(QWidget, ThemeAware):
    """The Personal Notes tab: list on the left, editor on the right."""

    changed = Signal()

    AUTOSAVE_MS = 700

    def __init__(self, store: AssistantStore, parent=None):
        super().__init__(parent)
        self.store = store
        self._current: Optional[Note] = None
        self._loading = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)

        # --- left: search + list + actions -----------------------------------
        left = QWidget()
        left_box = QVBoxLayout(left)
        left_box.setContentsMargins(0, 0, 8, 0)
        left_box.setSpacing(6)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter notes…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _t: self.refresh(keep_selection=True))
        left_box.addWidget(self.search)

        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._on_selected)
        left_box.addWidget(self.list, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.new_btn = QPushButton("New")
        self.new_btn.clicked.connect(lambda: self.create_note())
        self.pin_btn = QPushButton("Pin")
        self.pin_btn.clicked.connect(self._toggle_pin)
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self._delete_current)
        for button in (self.new_btn, self.pin_btn, self.delete_btn):
            button.setMinimumHeight(30)
            buttons.addWidget(button)
        left_box.addLayout(buttons)

        # --- right: title + editor -------------------------------------------
        right = QWidget()
        right_box = QVBoxLayout(right)
        right_box.setContentsMargins(8, 0, 0, 0)
        right_box.setSpacing(8)

        self.title_field = QLineEdit()
        self.title_field.setPlaceholderText("Note title")
        self.title_field.setMinimumHeight(34)
        self.title_field.textEdited.connect(self._touch)
        right_box.addWidget(self.title_field)

        tools = QHBoxLayout()
        tools.setSpacing(6)
        self.bullet_btn = QPushButton("• Bullet")
        self.bullet_btn.setToolTip("Turn this line into a bullet")
        self.bullet_btn.clicked.connect(lambda: self.editor.add_bullet())
        self.indent_btn = QPushButton("→ Indent")
        self.indent_btn.setToolTip("Nest this bullet (Tab)")
        self.indent_btn.clicked.connect(lambda: self.editor._shift_indent(+1))
        self.outdent_btn = QPushButton("← Outdent")
        self.outdent_btn.setToolTip("Un-nest this bullet (Shift+Tab)")
        self.outdent_btn.clicked.connect(lambda: self.editor._shift_indent(-1))
        for button in (self.bullet_btn, self.indent_btn, self.outdent_btn):
            button.setMinimumHeight(28)
            tools.addWidget(button)
        tools.addStretch()
        self.status = QLabel("")
        tools.addWidget(self.status)
        right_box.addLayout(tools)

        self.editor = BulletEditor()
        self.editor.textChanged.connect(self._touch)
        right_box.addWidget(self.editor, 1)

        self.splitter.addWidget(left)
        self.splitter.addWidget(right)
        self.splitter.setSizes([260, 620])
        outer.addWidget(self.splitter)

        self._autosave = QTimer(self)
        self._autosave.setSingleShot(True)
        self._autosave.setInterval(self.AUTOSAVE_MS)
        self._autosave.timeout.connect(self._save_current)

        self.setup_theme_awareness()
        self.refresh()

    # -- theme ---------------------------------------------------------------

    def apply_theme(self):
        palette = self.get_current_palette()
        self.list.setStyleSheet(f"""
            QListWidget {{
                background: {palette.surface};
                border: 1px solid {palette.border};
                border-radius: 8px;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 7px 8px;
                border-radius: 6px;
                color: {palette.text};
            }}
            QListWidget::item:selected {{
                background: {palette.tile_selected};
                color: {palette.text};
            }}
            QListWidget::item:hover:!selected {{
                background: {palette.surface_hover};
            }}
        """)
        self.status.setStyleSheet(
            f"color: {palette.text_secondary}; font-size: 11px;")

    # -- data ----------------------------------------------------------------

    def refresh(self, keep_selection: bool = False):
        wanted = self._current.id if (keep_selection and self._current) else None
        needle = self.search.text().strip().lower()

        self._loading = True
        self.list.clear()
        for note in self.store.sorted_notes():
            if needle and needle not in note.title.lower() \
                    and needle not in note.body.lower():
                continue
            label = ("📌 " if note.pinned else "") + (note.title or "Untitled")
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, note.id)
            preview = note.preview(64)
            if preview:
                item.setToolTip(preview)
            self.list.addItem(item)
        self._loading = False

        # Re-selecting after a refresh must NOT widen the filter: typing in the
        # filter box refreshes the list, and if the note you were on falls out
        # of the match, clearing the filter to go find it again would undo the
        # keystroke you just typed.
        if wanted and self._select_row(wanted):
            return
        if self.list.count():
            self.list.setCurrentRow(0)
        else:
            self._show_note(None)

    def select_note(self, note_id: str):
        """Jump to a note by id, used when something ELSE opened it (the
        terminal's /note, a link). Unlike the refresh path this one does clear
        an active filter, because the user's intent is to see that note."""
        if self._select_row(note_id):
            self.editor.setFocus()
            return
        if self.search.text():
            self.search.clear()          # refresh() re-lists everything
            if self._select_row(note_id):
                self.editor.setFocus()

    def _select_row(self, note_id: str) -> bool:
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == note_id:
                self.list.setCurrentRow(row)
                return True
        return False

    def create_note(self, title: str = "", body: str = "") -> Note:
        note = Note(title=title or "New note", body=body)
        self.store.add_note(note)
        self.refresh()
        self.select_note(note.id)
        self.title_field.selectAll()
        self.title_field.setFocus()
        self.changed.emit()
        return note

    def _on_selected(self, current, _previous):
        if self._loading:
            return
        self._flush()
        if current is None:
            self._show_note(None)
            return
        note_id = current.data(Qt.ItemDataRole.UserRole)
        self._show_note(self.store.get_note(note_id))

    def _show_note(self, note: Optional[Note]):
        self._loading = True
        self._current = note
        has_note = note is not None
        self.title_field.setEnabled(has_note)
        self.editor.setEnabled(has_note)
        for button in (self.bullet_btn, self.indent_btn, self.outdent_btn,
                       self.pin_btn, self.delete_btn):
            button.setEnabled(has_note)
        if note is None:
            self.title_field.setText("")
            self.editor.setPlainText("")
            self.status.setText("No note selected. Press New to start one.")
        else:
            self.title_field.setText(note.title)
            self.editor.setPlainText(note.body)
            self.pin_btn.setText("Unpin" if note.pinned else "Pin")
            self.status.setText(f"Saved {_friendly_stamp(note.updated_at)}")
        self._loading = False

    def _touch(self, *_args):
        if self._loading or self._current is None:
            return
        self.status.setText("Saving…")
        self._autosave.start()

    def _save_current(self):
        if self._current is None:
            return
        title = self.title_field.text().strip() or "Untitled"
        body = self.editor.toPlainText()
        if title == self._current.title and body == self._current.body:
            self.status.setText(f"Saved {_friendly_stamp(self._current.updated_at)}")
            return
        self._current.title = title
        self._current.body = body
        self.store.update_note(self._current)
        self.status.setText(f"Saved {_friendly_stamp(self._current.updated_at)}")
        # Rewriting the list here would steal focus mid-sentence; just fix the
        # row's label in place.
        item = self.list.currentItem()
        if item is not None:
            item.setText(("📌 " if self._current.pinned else "") + title)
        self.changed.emit()

    def _flush(self):
        """Force a pending autosave out before switching away from a note."""
        if self._autosave.isActive():
            self._autosave.stop()
            self._save_current()

    def _toggle_pin(self):
        if self._current is None:
            return
        self._flush()
        self._current.pinned = not self._current.pinned
        self.store.update_note(self._current)
        self.pin_btn.setText("Unpin" if self._current.pinned else "Pin")
        self.refresh(keep_selection=True)
        self.changed.emit()

    def _delete_current(self):
        if self._current is None:
            return
        answer = QMessageBox.question(
            self, "Delete note",
            f"Delete “{self._current.title}”?\n\nThis can't be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._autosave.stop()
        self.store.delete_note(self._current.id)
        self._current = None
        self.refresh()
        self.changed.emit()

    def hideEvent(self, event):
        """Leaving the tab must not cost an unsaved sentence."""
        self._flush()
        super().hideEvent(event)


def _friendly_stamp(iso: str) -> str:
    """'2026-08-11T15:04:58' -> '3:04 PM'. Today's notes only need the clock;
    older ones get the date too."""
    from datetime import datetime
    try:
        when = datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return iso
    clock = when.strftime("%I:%M %p").lstrip("0")
    if when.date() == datetime.now().date():
        return clock
    return f"{when.strftime('%b %d')} at {clock}"
