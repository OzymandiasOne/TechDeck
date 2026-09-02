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
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QSplitter, QTextBrowser, QTextEdit,
    QVBoxLayout, QWidget,
)

try:
    from techdeck.core.plugin_window import PluginWindow
except ModuleNotFoundError:  # standalone / headless testing
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
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
    """Render colours, pulled from the active TechDeck theme where possible."""
    pal = dict(render.DEFAULTS)
    if get_theme_manager is None:
        return pal
    try:
        p = get_theme_manager().get_current_palette()
    except Exception:
        return pal
    for key, attr in (("text", "text"), ("muted", "text_secondary"),
                      ("code_bg", "console_bg"), ("code_border", "border"),
                      ("accent", "accent"), ("font_family", "font_family")):
        value = getattr(p, attr, None)
        if value:
            pal[key] = value
    return pal


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
        self.setStyleSheet(
            "QTextBrowser { font-family: %s; font-size: 14px; }" % pal["font_family"])

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
        self._read_only = False      # viewing an old lesson, not in it

        self._session = claude_session.ClaudeSession(self)
        self._session.turn_started.connect(self._on_turn_started)
        self._session.delta.connect(self._on_delta)
        self._session.tool_started.connect(self._on_tool)
        self._session.turn_finished.connect(self._on_turn_finished)
        self._session.turn_failed.connect(self._on_turn_failed)
        self._session.session_ready.connect(self._on_session_ready)
        self._session.rate_limit.connect(self._on_rate_limit)
        self._session.sandbox_warning.connect(self._on_sandbox_warning)

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

        self._input = QTextEdit()
        self._input.setPlaceholderText(
            "Ask a question, or paste your code here.   (Ctrl+Enter to send)")
        self._input.setFixedHeight(110)
        self._input.setFont(QFont("Consolas", 10))
        col.addWidget(self._input)

        row = QHBoxLayout()
        self._status = QLabel("Ready.")
        self._status.setStyleSheet(f"color:{self._pal['muted']};font-size:11px;")
        row.addWidget(self._status, 1)

        self._usage = QLabel("")
        self._usage.setStyleSheet(f"color:{self._pal['muted']};font-size:11px;")
        row.addWidget(self._usage)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.clicked.connect(self._session.interrupt)
        self._stop_btn.setVisible(False)
        row.addWidget(self._stop_btn)

        self._send_btn = QPushButton("Send")
        self._send_btn.setDefault(True)
        self._send_btn.clicked.connect(self._send)
        row.addWidget(self._send_btn)
        col.addLayout(row)

        # Ctrl+Enter sends; plain Enter stays a newline so pasted code and
        # multi-line questions work normally.
        self._shortcuts = []
        for seq in ("Ctrl+Return", "Ctrl+Enter"):
            sc = QShortcut(QKeySequence(seq), self._input)
            sc.activated.connect(self._send)
            self._shortcuts.append(sc)   # keep alive

        return panel

    # -- history sidebar ---------------------------------------------------

    def _refresh_history(self):
        self._conversations = history.list_conversations(self._cwd)
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
        self._messages.append(("user", text))
        self._streaming = ""
        self._rerender()
        try:
            self._session.send(text)
        except claude_session.ClaudeUnavailable as exc:
            self._show_banner(str(exc))
        except RuntimeError as exc:
            self._set_status(str(exc))

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
        if self._streaming.strip():
            self._messages.append(("assistant", self._streaming))
        self._streaming = ""
        self._messages.append(("error", message))
        self._send_btn.setEnabled(not self._read_only)
        self._stop_btn.setVisible(False)
        self._set_status("Something went wrong.")
        self._rerender()

    def _on_session_ready(self, session_id: str):
        logger.info("java_tutor: session %s", session_id)

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

        at_bottom = self._is_at_bottom()
        self._view.setHtml(
            f'<body style="color:{pal["text"]};">' + "".join(parts) + "</body>")
        if at_bottom:
            self._scroll_to_bottom()

    def _bubble(self, role: str, text: str, pal: dict, live: bool = False) -> str:
        if role == "user":
            body, codes = render.to_html(text, pal)
            self._code_blocks.extend(codes)
            return (
                f'<table width="100%" cellspacing="0" cellpadding="0" '
                f'style="margin:10px 0;"><tr><td '
                f'style="border-left:3px solid {pal["accent"]};padding-left:12px;">'
                f'<div style="color:{pal["muted"]};font-size:11px;">You</div>'
                f"{body}</td></tr></table>")

        if role == "error":
            return (f'<div style="color:#ff8b8b;margin:10px 0;">{text}</div>')

        body, codes = render.to_html(text, pal)
        self._code_blocks.extend(codes)
        caret = ' <span style="color:%s;">|</span>' % pal["accent"] if live else ""
        return (f'<div style="margin:10px 0 16px 0;">{body}{caret}</div>')

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
