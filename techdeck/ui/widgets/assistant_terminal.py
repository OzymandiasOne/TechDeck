"""Terminal surface for the Assistant page: the transcript, the word-bubble
chips, and the command line.

The transcript reuses the console's visual language (monospace, role-coloured
prefixes, dark panel) so it reads as the same kind of place as Home's console, but it is a **separate** widget with its own history file, because this one has
to survive across sessions and the plugin console deliberately does not.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QTextEdit, QLineEdit, QPushButton, QFrame,
    QButtonGroup,
)
from PySide6.QtCore import Qt, Signal, QUrl, QEvent
from PySide6.QtGui import (
    QColor, QDesktopServices, QFont, QPainter, QPainterPath, QPixmap,
    QTextCursor, QTextDocument,
)

from techdeck.ui.theme_aware import ThemeAware
from techdeck.ui.widgets.flow_layout import FlowLayout

# Role → colour role. 'accent' and 'text*' resolve against the live palette;
# the two literals are the same ones the plugin console uses for user input and
# errors, so the two terminals stay recognisably related across every theme.
_USER_COLOR = "#60A5FA"
_ERROR_COLOR = "#EF4444"


AVATAR_PX = 36
_WOOGY_NAME = "Woogy"
_WOOGY_DISC = "#4C3B6E"        # the Emporium's purple, so he sits on his own shelf

# Woogy's sprite is a full figure: three eyestalks and a mouth on top, and a
# striped bucket at his feet. A profile picture wants the face, so the bucket
# is cropped away before the circle is applied. Measured off the art,
# not guessed, and it is a FRACTION so re-drawing him at another size still
# lands on the face.
_WOOGY_FACE_FRACTION = 0.90


def woogy_avatar(size: int = AVATAR_PX) -> QPixmap:
    """Woogy's Emporium sprite as a round profile picture.

    The same ``.tdart`` asset the Emporium and the game use, so he is
    recognisably the same character everywhere. He is drawn on a solid disc:
    the sprite has a transparent background, and a floating head with nothing
    behind it reads as a rendering glitch rather than an avatar.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    face = None
    try:
        from techdeck.ui import pixel_art
        if getattr(sys, "frozen", False):
            base = Path(sys._MEIPASS) / "assets" / "sprites"
        else:
            base = Path(__file__).resolve().parents[3] / "assets" / "sprites"
        sprite = pixel_art.render(pixel_art.load(base / "woogy.tdart"), scale=1)
        crop = sprite.copy(0, 0, sprite.width(),
                           max(1, int(sprite.height() * _WOOGY_FACE_FRACTION)))
        # Smooth, not nearest: this is a ~36px downscale of a 71px sprite, and
        # a non-integer nearest-neighbour shrink drops whole rows of his eyes.
        face = crop.scaled(size, size,
                           Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                           Qt.TransformationMode.SmoothTransformation)
    except Exception:
        face = None

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    path = QPainterPath()
    path.addEllipse(0, 0, size, size)
    painter.setClipPath(path)
    painter.fillPath(path, QColor(_WOOGY_DISC))
    if face is not None and not face.isNull():
        painter.drawPixmap((size - face.width()) // 2,
                           (size - face.height()) // 2, face)
    else:
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "W")
    painter.end()
    return pixmap


def initials_avatar(name: str, color: str, size: int = AVATAR_PX) -> QPixmap:
    """A coloured disc with someone's initials, the Teams convention."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    path = QPainterPath()
    path.addEllipse(0, 0, size, size)
    painter.fillPath(path, QColor(color))
    painter.setPen(QColor("#FFFFFF"))
    font = QFont()
    font.setPointSizeF(max(7.0, size * 0.38))
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter,
                     _initials(name))
    painter.end()
    return pixmap


def _initials(name: str) -> str:
    """'Anthony Siebenmorgen' -> 'AS'. 'ASiebenmorgen' -> 'AS'."""
    words = [w for w in re.split(r"[\s._-]+", (name or "").strip()) if w]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    if words:
        single = words[0]
        caps = re.findall(r"[A-Z]", single)
        if len(caps) >= 2:
            return (caps[0] + caps[1]).upper()
        return single[:2].upper()
    return "?"


class TerminalView(QTextEdit, ThemeAware):
    """Read-only scrollback, laid out like a chat rather than a log.

    Each message gets a profile picture and a name, the way Teams does it:
    Woogy's own sprite for his lines, an initials disc for yours. It is more
    vertical space per line than a bare prefix, and that is the point, a
    conversation should not read like console output.

    Consecutive messages from the same speaker are grouped under one avatar,
    so a reply plus its footnote is one block instead of two heads.
    """

    MAX_BLOCKS = 4000

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.document().setMaximumBlockCount(self.MAX_BLOCKS)
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setFrameShape(QFrame.Shape.NoFrame)
        # A read-only QTextEdit renders anchors but never acts on them, same
        # filter trick the plugin console uses.
        self.viewport().installEventFilter(self)
        self.viewport().setMouseTracking(True)
        self._identity = "You"
        self._last_speaker = ""
        self.setup_theme_awareness()

    def set_identity(self, name: str):
        """Whose initials go on the user's avatar."""
        self._identity = (name or "You").strip() or "You"
        self._register_avatars()

    def apply_theme(self):
        palette = self.get_current_palette()
        self.setStyleSheet(
            f"QTextEdit {{ border: none; background: {palette.console_bg};"
            f" color: {palette.console_text}; padding: 6px; }}")
        self._register_avatars()

    def _register_avatars(self):
        """Bake the two profile pictures into the document's resource table so
        the message HTML can reference them by name."""
        palette = self.get_current_palette()
        document = self.document()
        document.addResource(
            QTextDocument.ResourceType.ImageResource,
            QUrl("techdeck://avatar/woogy"), woogy_avatar().toImage())
        document.addResource(
            QTextDocument.ResourceType.ImageResource,
            QUrl("techdeck://avatar/user"),
            initials_avatar(self._identity, palette.accent).toImage())

    # -- appending -----------------------------------------------------------

    def clear(self):
        super().clear()
        self._last_speaker = ""
        # QTextEdit.clear() empties the document's RESOURCE cache along with
        # its text, so every avatar registered by _register_avatars is gone and
        # the next message renders a broken-image icon where the face should
        # be. Put them back. (Same reason apply_theme re-registers.)
        self._register_avatars()

    def append_line(self, role: str, text: str):
        palette = self.get_current_palette()
        body = _escape(text)

        # System notes, errors and structured output belong to whoever spoke
        # last, so they sit in the message column with no head of their own.
        if role in ("system", "error", "result"):
            colour = {"error": _ERROR_COLOR,
                      "system": palette.text_secondary}.get(role, palette.text)
            self._append_row(None, "", colour, body, continued=True)
            return

        if role == "user":
            speaker, avatar, colour = self._identity, "user", _USER_COLOR
        else:
            speaker, avatar, colour = _WOOGY_NAME, "woogy", palette.accent

        continued = self._last_speaker == avatar
        self._append_row(avatar, speaker, colour, body, continued=continued,
                         body_colour=palette.text)
        self._last_speaker = avatar

    def _append_row(self, avatar, speaker: str, name_colour: str, body: str,
                    continued: bool, body_colour: str = ""):
        palette = self.get_current_palette()
        body_colour = body_colour or palette.text

        if continued or avatar is None:
            cell = ""
        else:
            cell = (f'<img src="techdeck://avatar/{avatar}" '
                    f'width="{AVATAR_PX}" height="{AVATAR_PX}">')

        header = ""
        if speaker and not continued:
            header = (f'<span style="color: {name_colour}; font-weight: bold;">'
                      f'{_escape(speaker)}</span><br>')

        # A two-column table gives a real hanging indent, so a wrapped line
        # stays in the message column instead of running under the avatar.
        self.append(
            f'<table border="0" cellspacing="0" cellpadding="4" width="100%">'
            f'<tr>'
            f'<td width="{AVATAR_PX + 10}" valign="top">{cell}</td>'
            f'<td valign="top">{header}'
            f'<span style="color: {body_colour};">{body}</span></td>'
            f'</tr></table>')
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


class TabStrip(QWidget, ThemeAware):
    """The Chrome-style tab row, backed by checkable buttons rather than a
    QTabBar.

    A QTabBar can't lay this out. Personal Notes sits apart on the right,
    which needs two groups, and a QTabBar always keeps exactly one of *its
    own* tabs selected, so two bars would render two selected tabs at once.
    One exclusive button group spanning both sides gives a single selection
    and full control of the row.

    Buttons carry the stack index they drive, so display order and stack order
    are independent: reordering the row never renumbers anything.
    """

    tab_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buttons: dict = {}

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(3)
        self._left = QHBoxLayout()
        self._left.setContentsMargins(0, 0, 0, 0)
        self._left.setSpacing(3)
        self._right = QHBoxLayout()
        self._right.setContentsMargins(0, 0, 0, 0)
        self._right.setSpacing(3)
        row.addLayout(self._left)
        row.addStretch()
        row.addLayout(self._right)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.setup_theme_awareness()

    def add_tab(self, index: int, label: str, right: bool = False):
        button = QPushButton(label)
        button.setCheckable(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setMinimumHeight(32)
        button.clicked.connect(
            lambda _checked=False, i=index: self.set_current(i))
        self._group.addButton(button)
        self._buttons[index] = button
        (self._right if right else self._left).addWidget(
            button, 0, Qt.AlignmentFlag.AlignBottom)
        self.apply_theme()

    def set_current(self, index: int):
        button = self._buttons.get(index)
        if button is None:
            return
        if not button.isChecked():
            button.setChecked(True)
        self.tab_selected.emit(index)

    def current(self) -> int:
        for index, button in self._buttons.items():
            if button.isChecked():
                return index
        return 0

    def apply_theme(self):
        palette = self.get_current_palette()
        # The selected tab fills with the panel colour so it flows into the
        # content below, exactly like the plugin console's tab bar.
        sheet = f"""
            QPushButton {{
                background-color: {palette.surface};
                color: {palette.text_secondary};
                font-weight: bold;
                padding: 7px 16px;
                border: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }}
            QPushButton:hover:!checked {{
                background-color: {palette.surface_hover};
                color: {palette.text};
            }}
            QPushButton:checked {{
                background-color: {palette.console_bg};
                color: {palette.text};
            }}
        """
        for button in self._buttons.values():
            button.setStyleSheet(sheet)


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
        self.field.setPlaceholderText("/help")
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
