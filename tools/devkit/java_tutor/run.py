"""
Java Tutor - a chat window for Java coaching, inside TechDeck.

Left:  past lessons, searchable. Click one to re-read it; Continue to pick it
       back up where it stopped.
Right: the conversation. Answers stream in. Code arrives in a real code block
       with a Copy button.

He writes his Java in Eclipse. This window never touches his files - the
engine strips every write tool (see claude_session.py). It can read them.
"""

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMenu, QPushButton, QSplitter, QTextBrowser,
    QTextEdit, QVBoxLayout, QWidget,
)

try:
    from techdeck.core.plugin_window import PluginWindow
except ModuleNotFoundError:  # standalone / headless testing
    import sys
    # tools/devkit/java_tutor/<file> -> parents[3] is the repo root.
    # (Was parents[2] while this lived in plugins/; the DevKit move made it
    # wrong. tests/tools/test_devkit_java_tutor.py pins the depth.)
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from techdeck.core.plugin_window import PluginWindow

try:
    from techdeck.ui.theme_manager import get_theme_manager
except Exception:  # pragma: no cover - theme is a nicety, never load-critical
    get_theme_manager = None

# The sibling modules live beside this file; load them BY PATH so they resolve
# under every plugin-loader import style (dev repo AND %LOCALAPPDATA%
# installs). Same idiom as 922_batch_repeater/master_parts.py.
import importlib.util as _ilu


def _sibling(module_name: str, filename: str):
    spec = _ilu.spec_from_file_location(
        module_name, Path(__file__).resolve().parent / filename)
    assert spec is not None and spec.loader is not None
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


claude_session = _sibling("techdeck_java_tutor_session", "claude_session.py")
history = _sibling("techdeck_java_tutor_history", "history.py")
render = _sibling("techdeck_java_tutor_render", "render.py")
titles = _sibling("techdeck_java_tutor_titles", "titles.py")

logger = logging.getLogger(__name__)

# Module-level: a window in a local goes straight to the garbage collector.
_window = None

# How often the view repaints while text is streaming. Repainting on every
# delta rebuilds the whole document and stutters; 80ms still reads as live.
_STREAM_REPAINT_MS = 80


def run(params: dict, progress_callback, cancel_event):  # noqa: ARG001 - fixed signature
    """TechDeck entrypoint - opens the tutor window."""
    log = params.get("log", print)
    on_success = params.get("on_success")

    log("Opening Java Tutor...")
    progress_callback(20)

    try:
        exe = claude_session.find_claude()
        log(f"Using Claude Code at: {exe}")
    except claude_session.ClaudeUnavailable as exc:
        raise _user_facing(str(exc))

    global _window
    _window = JavaTutorWindow()
    _window.show()

    progress_callback(100)
    log("Java Tutor is open. Close the window when you're done.")
    if callable(on_success):
        on_success()


def _user_facing(message: str):
    """A UserFacingError if the SDK is around, else a plain Exception."""
    try:
        from techdeck.core import plugin_sdk as sdk
        return sdk.UserFacingError(message, "Install Claude Code, then reopen the tutor.")
    except Exception:
        return RuntimeError(message)


def _palette() -> dict:
    """Colours for the transcript.

    The chat area is a CODE SURFACE, not a themed panel - the same call an IDE
    or a terminal makes. It stays dark whatever the app theme is, because the
    syntax colours in render.py (One Dark: purple keywords, green strings, grey
    comments) are chosen against a dark background and go unreadable on a light
    one. A light theme used to repaint `text` dark and `code_bg` pale, which is
    how "I cannot tell where your text ends and mine begins" happens.

    Everything OUTSIDE the transcript - the window, sidebar, buttons, status bar
    - is still fully themed. Only this one surface opts out.

    The font family is still taken from the theme: some themes pick a monospace
    face deliberately (cyberpunk, matrix) and that is a look, not a bug.
    """
    pal = dict(render.DEFAULTS)
    if get_theme_manager is None:
        return pal
    try:
        p = get_theme_manager().get_current_palette()
    except Exception:
        return pal
    family = getattr(p, "font_family", None)
    if family:
        pal["font_family"] = family
    return pal


class InputBox(QTextEdit):
    """The message box.

    Enter sends; Shift+Enter is a newline. That is the chat convention, and it
    is the right way round here because most messages are one line - but pasted
    code is common too, so the newline has to stay reachable. Ctrl+Enter still
    sends, because it used to be the only way and the muscle memory is real.

    Escape asks the window to cancel the turn in flight and hand the message
    back, so a send can be taken back and edited rather than retyped.
    """

    send_requested = Signal()
    cancel_requested = Signal()

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()

        if key == Qt.Key.Key_Escape:
            self.cancel_requested.emit()
            return

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # Shift+Enter is the ONLY newline path; every other modifier
            # combination sends, so Ctrl+Enter keeps working as before.
            if mods & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
                return
            self.send_requested.emit()
            return

        super().keyPressEvent(event)


class ChatView(QTextBrowser):
    """The transcript. Renders markdown, hands Copy clicks back to the window."""

    copy_requested = Signal(int)

    def __init__(self, pal: dict, parent=None):
        super().__init__(parent)
        self._pal = pal
        self.setOpenExternalLinks(False)
        self.setOpenLinks(False)
        self.anchorClicked.connect(self._on_anchor)
        self.document().setDocumentMargin(14)
        # Follow the ACTIVE THEME's font. Some themes (cyberpunk, matrix) set a
        # monospace family on purpose, and the chat view should not fight that -
        # it is a deliberate look, not a bug. `setFont()` is useless here: the
        # app-level stylesheet's font-family beats it, so the family has to be
        # set in the widget's OWN stylesheet. Code blocks are always monospace
        # regardless, via their inline family in render.py.
        # The background has to be set on the WIDGET, not just in the body HTML:
        # the app-level stylesheet paints QTextBrowser with the theme's panel
        # colour, and that shows through the margin around the document and
        # behind the scrollbar. Without this the transcript is a black page
        # floating on a light surface under any light theme.
        self.setStyleSheet(
            "QTextBrowser { font-family: %s; font-size: 14px; "
            "background-color: %s; color: %s; border: none; }"
            % (pal["font_family"], pal["chat_bg"], pal["text"]))

    def _on_anchor(self, url):
        text = url.toString()
        if text.startswith("copy:"):
            try:
                self.copy_requested.emit(int(text.split(":", 1)[1]))
            except ValueError:
                pass
        else:
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(url)


class JavaTutorWindow(PluginWindow):
    """Sidebar of past lessons + the live conversation."""

    def __init__(self):
        super().__init__("java_tutor", "Java Tutor")
        self.setMinimumSize(1040, 700)
        self.resize(1240, 820)

        self._pal = _palette()
        self._cwd = claude_session.TUTOR_CWD

        # Conversation state. `_messages` is what gets rendered; `_streaming`
        # holds the partial answer while a turn is in flight.
        self._messages: list[tuple[str, str]] = []   # (role, markdown)
        self._streaming = ""
        self._code_blocks: list[str] = []
        self._conversations: list[history.Conversation] = []
        # Lesson names live in a sidecar, never in Claude's transcripts.
        self._titles = titles.TitleStore()
        self._read_only = False      # viewing an old lesson, not in it
        # Set by Esc while a turn is in flight. interrupt() makes the turn
        # END rather than return synchronously, so the undo has to happen
        # in the finish handler; this carries the intent across.
        self._cancelling = False
        self._sent_text = ""       # the message a cancel hands back

        self._session = claude_session.ClaudeSession(self)
        self._session.turn_started.connect(self._on_turn_started)
        self._session.delta.connect(self._on_delta)
        self._session.tool_started.connect(self._on_tool)
        self._session.turn_finished.connect(self._on_turn_finished)
        self._session.turn_failed.connect(self._on_turn_failed)
        self._session.session_ready.connect(self._on_session_ready)
        self._session.rate_limit.connect(self._on_rate_limit)
        self._session.sandbox_warning.connect(self._on_sandbox_warning)
        self._session.session_lost.connect(self._on_session_lost)

        self._repaint_timer = QTimer(self)
        self._repaint_timer.setInterval(_STREAM_REPAINT_MS)
        self._repaint_timer.timeout.connect(self._rerender)

        self._build_ui()
        self._refresh_history()
        self._rerender()

    # -- layout ------------------------------------------------------------

    def _build_ui(self):
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._banner = QLabel()
        self._banner.setWordWrap(True)
        self._banner.setVisible(False)
        self._banner.setStyleSheet(
            "background:#5a1d1d;color:#ffd7d7;padding:8px 12px;font-size:12px;")
        outer.addWidget(self._banner)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self._build_sidebar())
        split.addWidget(self._build_chat())
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([300, 940])
        outer.addWidget(split, 1)

        self._main_layout.addWidget(root)

    def _build_sidebar(self) -> QWidget:
        panel = QWidget()
        col = QVBoxLayout(panel)
        col.setContentsMargins(10, 10, 6, 10)
        col.setSpacing(8)

        new_btn = QPushButton("New lesson")
        new_btn.clicked.connect(self._new_lesson)
        col.addWidget(new_btn)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search past lessons...")
        self._search.setClearButtonEnabled(True)
        # Search re-reads transcripts, so wait for a pause in typing.
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(220)
        self._search_timer.timeout.connect(self._apply_search)
        self._search.textChanged.connect(lambda _: self._search_timer.start())
        col.addWidget(self._search)

        self._list = QListWidget()
        self._list.itemActivated.connect(self._open_conversation)
        self._list.itemClicked.connect(self._open_conversation)
        # Rename: right-click, or F2 on the selected lesson.
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._lesson_menu)
        self._rename_sc = QShortcut(QKeySequence("F2"), self._list)
        self._rename_sc.activated.connect(self._rename_selected)
        col.addWidget(self._list, 1)

        self._list_note = QLabel("")
        self._list_note.setWordWrap(True)
        self._list_note.setStyleSheet(
            f"color:{self._pal['muted']};font-size:11px;")
        col.addWidget(self._list_note)

        return panel

    def _build_chat(self) -> QWidget:
        panel = QWidget()
        col = QVBoxLayout(panel)
        col.setContentsMargins(6, 10, 10, 10)
        col.setSpacing(8)

        self._view = ChatView(self._pal)
        self._view.copy_requested.connect(self._copy_code)
        col.addWidget(self._view, 1)

        # Shown instead of the input box when reading an old lesson.
        self._resume_bar = QFrame()
        rb = QHBoxLayout(self._resume_bar)
        rb.setContentsMargins(0, 0, 0, 0)
        self._resume_label = QLabel("Reading a past lesson.")
        self._resume_label.setStyleSheet(f"color:{self._pal['muted']};")
        rb.addWidget(self._resume_label, 1)
        cont = QPushButton("Continue this lesson")
        cont.clicked.connect(self._continue_conversation)
        rb.addWidget(cont)
        self._resume_bar.setVisible(False)
        col.addWidget(self._resume_bar)

        self._input = InputBox()
        self._input.send_requested.connect(self._send)
        self._input.cancel_requested.connect(self._cancel_send)
        self._input.setPlaceholderText(
            "Ask a question, or paste your code here.   "
            "(Enter sends, Shift+Enter for a new line, Esc takes it back)")
        self._input.setFixedHeight(110)
        self._input.setFont(QFont("Consolas", 10))
        # Same code surface as the transcript above it. A themed (often light)
        # input box sitting under a black transcript reads as a rendering fault,
        # and this is the box you paste Java into.
        self._input.setStyleSheet(
            "QTextEdit { background-color: %s; color: %s; "
            "border: 1px solid %s; border-radius: 3px; padding: 6px; }"
            % (self._pal["chat_bg"], self._pal["text"], self._pal["code_border"]))
        col.addWidget(self._input)

        row = QHBoxLayout()
        self._status = QLabel("Ready.")
        self._status.setStyleSheet(f"color:{self._pal['muted']};font-size:11px;")
        row.addWidget(self._status, 1)

        self._usage = QLabel("")
        self._usage.setStyleSheet(f"color:{self._pal['muted']};font-size:11px;")
        row.addWidget(self._usage)

        self._stop_btn = QPushButton("Stop")
        # Stop KEEPS whatever answer streamed in; Esc throws it away and hands
        # your message back. Two different intentions, so two different controls.
        self._stop_btn.setToolTip(
            "Stop the answer here and keep what has arrived.\n"
            "Press Esc instead to cancel and get your message back.")
        self._stop_btn.clicked.connect(self._session.interrupt)
        self._stop_btn.setVisible(False)
        row.addWidget(self._stop_btn)

        self._send_btn = QPushButton("Send")
        self._send_btn.setDefault(True)
        self._send_btn.clicked.connect(self._send)
        row.addWidget(self._send_btn)
        col.addLayout(row)

        # Enter/Shift+Enter/Esc are handled by InputBox itself (it has to see
        # the key before QTextEdit inserts a newline). Esc is ALSO a window
        # shortcut so it still cancels when focus has left the box - during a
        # turn the box is empty and the user may have clicked elsewhere.
        self._shortcuts = []
        esc = QShortcut(QKeySequence("Escape"), self)
        esc.setContext(Qt.ShortcutContext.WindowShortcut)
        esc.activated.connect(self._cancel_send)
        self._shortcuts.append(esc)      # keep alive

        return panel

    # -- history sidebar ---------------------------------------------------

    def _refresh_history(self):
        self._conversations = history.list_conversations(self._cwd, self._titles.titles)
        self._apply_search()

    def _apply_search(self):
        query = self._search.text()
        shown = history.search(self._conversations, query) if query else self._conversations

        self._list.clear()
        for convo in shown:
            item = QListWidgetItem(f"{convo.title}\n{convo.when}  -  {convo.turns} messages")
            item.setData(Qt.ItemDataRole.UserRole, convo.session_id)
            item.setToolTip(convo.preview)
            self._list.addItem(item)

        if not self._conversations:
            self._list_note.setText(
                "No past lessons yet. Anything you do here from now on is saved "
                "automatically and will show up in this list.")
        elif not shown:
            self._list_note.setText("No lesson matches that search.")
        else:
            self._list_note.setText(f"{len(shown)} of {len(self._conversations)} lessons")

    # -- renaming ----------------------------------------------------------

    def _lesson_menu(self, point):
        """Right-click menu for one lesson in the sidebar."""
        item = self._list.itemAt(point)
        if item is None:
            return
        self._list.setCurrentItem(item)
        session_id = item.data(Qt.ItemDataRole.UserRole)
        convo = self._find_conversation(session_id)

        menu = QMenu(self._list)
        menu.addAction("Rename lesson...", self._rename_selected)
        if convo is not None and convo.custom:
            # Only offered when there IS a chosen name to drop back from.
            menu.addAction("Reset to automatic name",
                           lambda: self._apply_rename(session_id, ""))
        menu.exec(self._list.mapToGlobal(point))

    def _rename_selected(self):
        item = self._list.currentItem()
        if item is None:
            return
        session_id = item.data(Qt.ItemDataRole.UserRole)
        convo = self._find_conversation(session_id)
        if convo is None:
            return
        name, ok = QInputDialog.getText(
            self, "Rename lesson", "Lesson name:", text=convo.title)
        if ok:
            self._apply_rename(session_id, name)

    def _apply_rename(self, session_id: str, name: str):
        """Store the name (empty clears it) and redraw, keeping the selection."""
        self._titles.rename(session_id, name)
        self._refresh_history()
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == session_id:
                self._list.setCurrentItem(item)
                break
        convo = self._find_conversation(session_id)
        if convo is not None:
            self._set_status(f"Renamed to \"{convo.title}\".")

    def _find_conversation(self, session_id: str):
        for convo in self._conversations:
            if convo.session_id == session_id:
                return convo
        return None

    def _open_conversation(self, item: QListWidgetItem):
        if self._session.busy:
            self._set_status("Wait for the current answer to finish first.")
            return
        session_id = item.data(Qt.ItemDataRole.UserRole)
        convo = self._find_conversation(session_id)
        if convo is None:
            return

        self._messages = [(m.role, m.text) for m in history.read_messages(convo.path)]
        self._streaming = ""
        self._read_only = True
        self._pending_session = session_id
        self._resume_label.setText(f"Reading: {convo.title}")
        self._resume_bar.setVisible(True)
        self._input.setVisible(False)
        self._send_btn.setEnabled(False)
        self._set_status(f"Opened lesson from {convo.when}.")
        self._rerender()

    def _continue_conversation(self):
        """Rejoin the lesson being read - the next message lands in it."""
        self._session.adopt_session(self._pending_session)
        self._read_only = False
        self._resume_bar.setVisible(False)
        self._input.setVisible(True)
        self._send_btn.setEnabled(True)
        self._input.setFocus()
        self._set_status("Continuing this lesson. Type below.")

    def _new_lesson(self):
        if self._session.busy:
            self._set_status("Wait for the current answer to finish first.")
            return
        self._session.reset()
        self._messages = []
        self._streaming = ""
        self._read_only = False
        self._resume_bar.setVisible(False)
        self._input.setVisible(True)
        self._send_btn.setEnabled(True)
        self._list.clearSelection()
        self._set_status("New lesson. Type below.")
        self._rerender()
        self._input.setFocus()

    # -- sending -----------------------------------------------------------

    def _send(self):
        if self._session.busy or self._read_only:
            return
        text = self._input.toPlainText().strip()
        if not text:
            return
        self._input.clear()
        self._sent_text = text
        self._messages.append(("user", text))
        self._streaming = ""
        self._rerender()
        try:
            self._session.send(text)
        except claude_session.ClaudeUnavailable as exc:
            self._show_banner(str(exc))
        except RuntimeError as exc:
            self._set_status(str(exc))

    def _cancel_send(self):
        """Esc: take back the message being answered.

        Stops the turn, drops the user bubble from the transcript, and puts the
        text back in the box so it can be edited instead of retyped. Silent when
        nothing is in flight - Esc should not be a way to lose what you typed.
        """
        if not self._session.busy:
            return
        self._cancelling = True
        self._set_status("Cancelling...")
        self._session.interrupt()

    def _undo_send(self):
        """Roll the transcript and the input box back to just before the send."""
        self._cancelling = False
        self._streaming = ""
        if self._messages and self._messages[-1][0] == "user":
            self._messages.pop()
        if self._sent_text:
            self._input.setPlainText(self._sent_text)
            cursor = self._input.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self._input.setTextCursor(cursor)
        self._sent_text = ""
        self._send_btn.setEnabled(not self._read_only)
        self._stop_btn.setVisible(False)
        self._repaint_timer.stop()
        self._set_status("Cancelled - your message is back in the box.")
        self._rerender()
        self._input.setFocus()

    # -- engine signals ----------------------------------------------------

    def _on_turn_started(self):
        self._send_btn.setEnabled(False)
        self._stop_btn.setVisible(True)
        self._set_status("Thinking...")
        self._repaint_timer.start()

    def _on_delta(self, text: str):
        self._streaming += text

    def _on_tool(self, name: str):
        if name in ("Read", "Glob", "Grep"):
            self._set_status(f"Reading your files ({name})...")
        else:
            self._set_status(f"Using {name}...")

    def _on_turn_finished(self, full_text: str):
        self._repaint_timer.stop()
        if self._cancelling:
            # An interrupted turn still arrives here, carrying whatever partial
            # answer streamed in. A cancel wants none of it.
            self._undo_send()
            return
        final = full_text or self._streaming
        self._streaming = ""
        if final.strip():
            self._messages.append(("assistant", final))
        self._send_btn.setEnabled(not self._read_only)
        self._stop_btn.setVisible(False)
        self._set_status("Ready.")
        self._rerender()
        self._refresh_history()
        self._input.setFocus()

    def _on_turn_failed(self, message: str):
        self._repaint_timer.stop()
        if self._cancelling:
            self._undo_send()
            return
        if self._streaming.strip():
            self._messages.append(("assistant", self._streaming))
        self._streaming = ""
        self._messages.append(("error", message))
        self._send_btn.setEnabled(not self._read_only)
        self._stop_btn.setVisible(False)
        self._set_status("Something went wrong.")
        self._rerender()

    def _on_session_lost(self):
        """The lesson we tried to continue is gone; a fresh one took over."""
        self._messages.append(
            ("error", "That lesson's saved history is gone, so this is a fresh "
                      "conversation. Your message was sent - the tutor just "
                      "will not remember what came before it."))
        self._rerender()

    def _on_session_ready(self, session_id: str):
        logger.info("java_tutor: session %s", session_id)
        # A lesson planned in Claude Code left its name in `pending` before this
        # session existed. Now that it has an id, bind the two together.
        claimed = self._titles.claim_pending(session_id)
        if claimed:
            logger.info("java_tutor: lesson named %r from the plan", claimed)
            self._set_status(f"Lesson: {claimed}")
        self._refresh_history()

    def _on_rate_limit(self, info: dict):
        windows = info.get("unifiedWindows") or {}
        five = windows.get("five_hour") or {}
        used = five.get("utilization")
        if used is None:
            return
        pct = int(round(float(used) * 100))
        self._usage.setText(f"5-hour usage: {pct}%")
        if pct >= 90:
            self._show_banner(
                f"You have used {pct}% of your 5-hour Claude usage window. "
                "When it runs out the tutor stops until the window resets.")

    def _on_sandbox_warning(self, tools: list):
        self._show_banner(
            "Blocked " + ", ".join(tools) + " - the tutor is read-only and these "
            "were not on the block list. They are denied from your next message "
            "onward. Nothing was written; only file reading is ever allowed.")

    # -- rendering ---------------------------------------------------------

    def _rerender(self):
        pal = self._pal
        parts = []
        self._code_blocks = []

        if not self._messages and not self._streaming:
            parts.append(
                f'<div style="color:{pal["muted"]};margin-top:24px;">'
                "<b>Java Tutor</b><br><br>"
                "Ask a question, or paste code straight in.<br>"
                "I can open your <code>.java</code> files myself - just say which one.<br><br>"
                "I cannot edit your files. You type the code; that is the point."
                "</div>")

        for role, text in self._messages:
            parts.append(self._bubble(role, text, pal))

        if self._streaming:
            parts.append(self._bubble("assistant", self._streaming, pal, live=True))

        # setHtml() rebuilds the document and resets the scrollbar to 0. While a
        # answer streams this runs every _STREAM_REPAINT_MS, so without saving
        # the position the view yanks you back to the top a dozen times a second
        # for the whole answer - it reads as "scrolling is frozen".
        bar = self._view.verticalScrollBar()
        at_bottom = self._is_at_bottom()
        previous = bar.value()

        self._view.setHtml(
            f'<body style="color:{pal["text"]};background-color:{pal["chat_bg"]};">'
            + "".join(parts) + "</body>")

        if at_bottom:
            self._scroll_to_bottom()
        else:
            # Stay where the reader put themselves. maximum() has usually grown,
            # so the old value still points at roughly the same content.
            bar.setValue(min(previous, bar.maximum()))

    def _bubble(self, role: str, text: str, pal: dict, live: bool = False) -> str:
        """One message. BOTH speakers get a coloured rule and a name.

        The tutor's replies used to be a bare `<div>` with no label at all, so a
        long answer followed by a short question ran together as one wall of
        text. Same table shape for both keeps the left edges aligned; only the
        colour and the name change.
        """
        if role == "error":
            return (f'<table width="100%" cellspacing="0" cellpadding="0" '
                    f'style="margin:10px 0;"><tr><td '
                    f'style="border-left:3px solid #ff8b8b;padding-left:12px;">'
                    f'<div style="color:#ff8b8b;">{text}</div>'
                    f"</td></tr></table>")

        speaker = "You" if role == "user" else "Java Tutor"
        colour = pal["user"] if role == "user" else pal["tutor"]

        body, codes = render.to_html(text, pal)
        self._code_blocks.extend(codes)
        caret = f' <span style="color:{colour};">|</span>' if live else ""

        return (
            f'<table width="100%" cellspacing="0" cellpadding="0" '
            f'style="margin:14px 0;"><tr><td '
            f'style="border-left:3px solid {colour};padding-left:12px;">'
            f'<div style="color:{colour};font-size:11px;font-weight:bold;">'
            f'{speaker}</div>'
            f"{body}{caret}</td></tr></table>")

    def _copy_code(self, index: int):
        if 0 <= index < len(self._code_blocks):
            QApplication.clipboard().setText(self._code_blocks[index])
            self._set_status("Code copied.")

    # -- small helpers -----------------------------------------------------

    def _is_at_bottom(self) -> bool:
        bar = self._view.verticalScrollBar()
        return bar.value() >= bar.maximum() - 40

    def _scroll_to_bottom(self):
        self._view.moveCursor(QTextCursor.MoveOperation.End)
        bar = self._view.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _set_status(self, text: str):
        self._status.setText(text)

    def _show_banner(self, text: str):
        self._banner.setText(text)
        self._banner.setVisible(True)

    def closeEvent(self, event):
        if self._session.busy:
            self._session.interrupt()
        self._repaint_timer.stop()
        super().closeEvent(event)
