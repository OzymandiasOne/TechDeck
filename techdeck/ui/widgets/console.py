"""
TechDeck Console/Chat Widget - ENHANCED with Plugin Input Support
Adds ability for plugins to request user input during execution.

FIXED: Uses BlockingQueuedConnection to properly synchronize worker thread with GUI thread
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLineEdit, QPushButton, QLabel, QTabBar, QStackedWidget, QFrame, QToolButton
)
from PySide6.QtCore import Signal, Qt, Q_ARG, QMetaObject, Slot, QTimer, QEvent, QUrl
from PySide6.QtGui import QTextCursor, QFont, QDesktopServices
import threading

from techdeck.ui.widgets.dashboard import DashboardView
from techdeck.ui.theme_aware import ThemeAware


class InputAborted(Exception):
    """Raised inside request_input() when a pending console input request is
    cancelled. Worker loops that call request_input should let this propagate
    so they unwind.

    ``reason`` distinguishes the cause so the executor can mark the plugin
    result correctly:
      * ``"cancelled"`` (default) — a slash command interrupted an in-console
        game or the user hit Clear.
      * ``"paused"`` — a /pause or auto-idle pause request. The executor maps
        this to PluginStatus.PAUSED so HomePage knows to park the queue
        rather than treat it as a failure.
    """

    def __init__(self, reason: str = "cancelled"):
        super().__init__(reason)
        self.reason = reason


class ConsoleWidget(QWidget, ThemeAware):
    """
    Console/chat widget with message history, command input, and plugin input support.
    
    NEW FEATURE: Plugins can request input from users during execution!
    
    Signals:
        command_entered(str): Emitted when user enters a command
        message_entered(str): Emitted when user enters natural language
        input_provided(str): Emitted when user provides input for plugin request
    """
    
    command_entered = Signal(str)
    message_entered = Signal(str)
    input_provided = Signal(str)  # NEW: For plugin input requests
    before_input_request = Signal()  # Emitted just before showing a plugin input prompt
    dashboard_shown = Signal()  # Emitted when a dashboard is rendered (shell auto-expands)
    cleared = Signal()  # Emitted after the console is cleared (button or /clear)
    
    MAX_LINES = 1000
    CLEANUP_TO_LINES = 800
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        
        # NEW: Track input request state
        self.waiting_for_input = False
        self.input_prompt = ""
        self.input_response = None
        self.input_event = None
        # Who owns the current input request: 'plugin' (supersedes commands) or
        # 'game' (an in-console easter egg that a slash command may interrupt).
        self._input_owner = 'plugin'
        self._input_aborted = False
        self._input_aborted_reason = "cancelled"
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # ===== Header: tab bar (bottom-aligned so tabs meet the panel) + buttons =====
        # The tabs sit inline with the Run/Clear buttons but bottom-align onto
        # the content panel, and the selected tab merges into the panel's top
        # edge — so the active tab flows into the console like a Chrome tab.
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        self.tab_bar = QTabBar()
        self.tab_bar.setObjectName("consoleTabBar")
        self.tab_bar.setExpanding(False)
        self.tab_bar.setDrawBase(False)
        self.tab_bar.setUsesScrollButtons(False)
        self.tab_bar.currentChanged.connect(self._on_tab_changed)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setMaximumWidth(80)
        self.clear_btn.setMinimumHeight(36)  # match Run so the two line up
        self.clear_btn.clicked.connect(self.clear)

        header.addWidget(self.tab_bar, 0, Qt.AlignmentFlag.AlignBottom)
        header.addStretch()
        header.addWidget(self.clear_btn, 0, Qt.AlignmentFlag.AlignTop)
        self.header = header

        # Fixed-height header: top-aligned buttons sit a few px above the
        # bottom-aligned tabs (which stay pinned to the panel top).
        self._header_widget = QWidget()
        self._header_widget.setLayout(header)
        self._header_widget.setFixedHeight(42)

        # ===== Content pages =====
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.document().setMaximumBlockCount(self.MAX_LINES + 100)
        _font = QFont("Consolas", 10)
        _font.setStyleHint(QFont.StyleHint.Monospace)
        self.output.setFont(_font)
        # Clickable lines (append_link): a read-only QTextEdit renders anchors
        # but doesn't act on them, so watch the viewport for hover (hand
        # cursor) and click (open the target).
        self.output.viewport().installEventFilter(self)
        self.output.viewport().setMouseTracking(True)

        self._console_page = QWidget()
        _cp = QVBoxLayout(self._console_page)
        _cp.setContentsMargins(0, 0, 0, 0)
        _cp.addWidget(self.output)

        self.dashboard = DashboardView()
        self._dash_page = QWidget()
        _dp = QVBoxLayout(self._dash_page)
        _dp.setContentsMargins(0, 0, 0, 0)
        _dp.addWidget(self.dashboard, 1)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._console_page)
        self.stack.addWidget(self._dash_page)
        # A populated (but hidden) Dashboard must not lock the window's
        # minimum width — its charts carry real minimums (pie 380 + side 280).
        from techdeck.ui.utils import limit_min_size_to_current_page
        limit_min_size_to_current_page(self.stack)

        # The panel is the single bordered box the active tab connects to.
        # The text area inside is borderless so only the panel draws the box.
        self.panel = QFrame()
        self.panel.setObjectName("consolePanel")
        _pl = QVBoxLayout(self.panel)
        _pl.setContentsMargins(8, 8, 8, 8)
        _pl.addWidget(self.stack)

        # Header + panel share a zero-gap sub-layout so the tabs touch the panel.
        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._header_widget)
        body.addWidget(self.panel, 1)
        layout.addLayout(body, 1)

        # tabData holds the stack page each tab drives, so indices can shift
        # when the Dashboard tab is closed/reopened. Only the Dashboard tab gets
        # a close affordance — a box-less "x" placed next to its label.
        _ci = self.tab_bar.addTab("Console")
        self.tab_bar.setTabData(_ci, self._console_page)
        _di = self.tab_bar.addTab("Dashboard")
        self.tab_bar.setTabData(_di, self._dash_page)
        self.tab_bar.setTabButton(
            _di, QTabBar.ButtonPosition.RightSide, self._make_close_button()
        )

        self.tab_bar.setCurrentIndex(_ci)
        self.stack.setCurrentWidget(self._console_page)
        self._pending_dashboard = None
        self._pending_links = []   # append_link(at_run_end=True) holds lines here

        # ===== Spinner Label (hidden until an animation is active) =====
        self._spinner_label = QLabel()
        self._spinner_label.setTextFormat(Qt.TextFormat.RichText)
        self._spinner_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._spinner_label.setMinimumHeight(24)
        self._spinner_label.setStyleSheet("QLabel { padding: 1px 4px; background: transparent; }")
        self._spinner_label.hide()
        layout.addWidget(self._spinner_label)

        # ===== Input Area =====
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type a command (/help) or message...")
        self.input_field.returnPressed.connect(self._on_input_submitted)
        
        self.send_btn = QPushButton("Send")
        self.send_btn.setProperty("class", "primary")
        self.send_btn.setMinimumHeight(36)
        self.send_btn.clicked.connect(self._on_input_submitted)
        
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_btn)
        
        layout.addLayout(input_layout)
        
        # Theme the tab bar + readout (and re-theme on live theme switch)
        self.setup_theme_awareness()

        # Initial message
        self.append_system("TechDeck online. Type /help for available commands.")
    
    def show_read_more_hint(self):
        """Float a small "read more" pill at the bottom of the output viewport.

        Used by /help, which anchors the scroll at the START of its block —
        the pill makes it obvious there is more content below the fold. It
        hides as soon as the user scrolls (any further append auto-scrolls,
        which also hides it) or after a few seconds.
        """
        from techdeck.ui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_palette()
        if getattr(self, "_read_more_pill", None) is None:
            self._read_more_pill = QLabel(self.output)
            self._read_more_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._read_more_pill.hide()
            self._read_more_timer = QTimer(self)
            self._read_more_timer.setSingleShot(True)
            self._read_more_timer.timeout.connect(self._read_more_pill.hide)
            self.output.verticalScrollBar().valueChanged.connect(
                self._hide_read_more_hint)
        self._read_more_pill.setText("▼  read more  ▼")
        self._read_more_pill.setStyleSheet(
            f"background-color: {theme.surface}; color: {theme.text}; "
            f"border: 1px solid {theme.border_strong}; border-radius: 10px; "
            f"padding: 3px 12px; font-size: 11px;"
        )
        self._read_more_pill.adjustSize()
        vp = self.output.viewport()
        self._read_more_pill.move(
            (vp.width() - self._read_more_pill.width()) // 2,
            vp.height() - self._read_more_pill.height() - 8,
        )
        self._read_more_pill.show()
        self._read_more_pill.raise_()
        self._read_more_timer.start(8000)

    def _hide_read_more_hint(self, _value=None):
        pill = getattr(self, "_read_more_pill", None)
        if pill is not None and pill.isVisible():
            pill.hide()

    def add_header_button(self, button: QPushButton, far_right: bool = False):
        """Add a button to the console header.

        By default the button is inserted just left of the Clear button.
        Pass far_right=True to append it at the very end of the header.
        """
        align = Qt.AlignmentFlag.AlignTop
        if far_right:
            self.header.addWidget(button, 0, align)
        else:
            count = self.header.count()
            self.header.insertWidget(count - 1, button, 0, align)
    
    def _on_input_submitted(self):
        """Handle user input submission."""
        text = self.input_field.text().strip()
        
        if not text:
            return
        
        # Clear input
        self.input_field.clear()

        # Submitting input brings the Console tab forward so the echoed input
        # and any output are visible. Done before emitting so dashboard-showing
        # commands (e.g. /dash) still end on the Dashboard tab.
        self.tab_bar.setCurrentIndex(self._console_tab_index())

        # Something is waiting on console input. A slash command interrupts an
        # in-console game (owner != 'plugin') so the command can run; a running
        # plugin's input prompt supersedes commands and consumes the text as-is.
        if self.waiting_for_input:
            if text.startswith('/') and self._input_owner != 'plugin':
                self.abort_input()
                # fall through to dispatch the command below
            else:
                self._handle_plugin_input(text)
                return

        # Echo user input
        self.append_user(text)
        
        # Determine if it's a command or message
        if text.startswith('/'):
            self.command_entered.emit(text)
        else:
            self.message_entered.emit(text)
    
    def _handle_plugin_input(self, text: str):
        """Handle input provided for plugin request."""
        # Echo the input
        self.append_user(text)
        
        # Store response
        self.input_response = text
        
        # Reset waiting state
        self.waiting_for_input = False
        self.input_field.setPlaceholderText("Type a command (/help) or message...")
        self.input_field.setStyleSheet("")  # Reset any custom styling
        
        # Signal that input was provided
        self.input_provided.emit(text)
        
        # Wake up the waiting thread if using threading.Event
        if self.input_event:
            self.input_event.set()
    
    def request_input(self, prompt: str, owner: str = 'plugin') -> str:
        """
        NEW: Request input from user - BLOCKS until user provides input.

        This method can be called from plugin threads and will safely
        request input from the main GUI thread.

        FIXED: Uses BlockingQueuedConnection to properly synchronize threads

        Args:
            prompt: The prompt/question to show the user
            owner: 'plugin' (default) means a real plugin owns this prompt and it
                   supersedes commands. 'game' marks an in-console easter egg whose
                   prompt a slash command may interrupt (raises InputAborted here).

        Returns:
            str: The user's input

        Raises:
            InputAborted: if the request is cancelled via abort_input()
        """
        from PySide6.QtCore import QThread, QMetaObject

        # If we're on the main GUI thread, we can't block
        if QThread.currentThread() == self.thread():
            raise RuntimeError("request_input() cannot be called from main GUI thread")

        # We're on a worker thread - safe to block
        self.input_response = None
        self._input_owner = owner
        self._input_aborted = False
        self.input_event = threading.Event()

        # FIXED: Use BlockingQueuedConnection to ensure GUI method completes before continuing
        # This is critical - QueuedConnection would be asynchronous and cause the worker thread
        # to wait forever since the GUI method might not have executed yet
        QMetaObject.invokeMethod(
            self,
            "_request_input_gui",
            Qt.ConnectionType.BlockingQueuedConnection,  # ← FIXED: Changed from QueuedConnection
            Q_ARG(str, prompt)
        )

        # Wait for user to provide input
        self.input_event.wait()

        if self._input_aborted:
            raise InputAborted(self._input_aborted_reason)

        return self.input_response

    def abort_input(self, reason: str = "cancelled"):
        """Cancel a pending request_input so a new command can run in its place.

        Originally used to interrupt an in-console game (e.g. blackjack); now
        also used by the executor watchdog and /pause to park a paused plugin
        cleanly. Runs on the GUI thread and wakes the blocked worker, which
        then raises ``InputAborted(reason)`` out of ``request_input``.

        ``reason``: see InputAborted docstring. Default "cancelled" preserves
        existing call sites (the game-interrupt path).
        """
        if not self.waiting_for_input:
            return
        self.waiting_for_input = False
        self._input_aborted = True
        self._input_aborted_reason = reason
        self.input_prompt = ""
        self.input_field.setPlaceholderText("Type a command (/help) or message...")
        self.input_field.setStyleSheet("")
        if self.input_event is not None:
            self.input_event.set()
    
    @Slot(str)
    def _request_input_gui(self, prompt: str):
        """
        Internal method that runs on GUI thread to set up input request.
        Called via QMetaObject.invokeMethod from request_input().
        An empty prompt string activates input mode silently (no system messages).
        """
        # Flush any buffered plugin log messages so they appear before the prompt
        self.before_input_request.emit()
        self.waiting_for_input = True
        self.input_prompt = prompt

        if prompt:
            self.append_system(f"🔹 {prompt}")
            self.append_system("   (Type your response below)")
            self.input_field.setPlaceholderText(f"Your response to: {prompt[:50]}...")
        else:
            # Silent mode — just show the orange border, no noise
            self.input_field.setPlaceholderText("Type command...")

        self.input_field.setStyleSheet("border: 2px solid #F59E0B;")
        self.input_field.setFocus()
        self._scroll_to_bottom()
    
    def request_nest_selection(self, batch_number: str, all_nests: list,
                               existing_nests=None):
        """Show the nest-selection dialog and BLOCK until the user submits.

        Callable from a plugin worker thread (same contract as request_input):
        the modal dialog is run on the GUI thread via BlockingQueuedConnection,
        so this call returns only once the user has chosen.

        Returns the list of selected nest numbers, or None if the user
        cancelled the dialog.
        """
        from PySide6.QtCore import QThread

        if QThread.currentThread() == self.thread():
            raise RuntimeError(
                "request_nest_selection() cannot be called from main GUI thread"
            )

        self._nest_sel_args = (batch_number, list(all_nests), set(existing_nests or []))
        self._nest_sel_result = None

        # Hold the inactivity watchdog while the dialog is up — user think-time
        # in the dialog must not count as a hung plugin (see plugin_executor).
        self.waiting_for_input = True
        try:
            QMetaObject.invokeMethod(
                self,
                "_nest_selection_gui",
                Qt.ConnectionType.BlockingQueuedConnection,
            )
        finally:
            self.waiting_for_input = False

        return self._nest_sel_result

    @Slot()
    def _nest_selection_gui(self):
        """GUI-thread half of request_nest_selection: run the modal dialog."""
        from techdeck.ui.dialogs.nest_selection_dialog import NestSelectionDialog

        batch_number, all_nests, existing = self._nest_sel_args
        dlg = NestSelectionDialog(batch_number, all_nests, existing, parent=self.window())
        if dlg.exec():
            self._nest_sel_result = dlg.selected_nests()
        else:
            self._nest_sel_result = None

    def request_selection(self, items, done_items=None, **kwargs):
        """Show a generic "pick which items to run" dialog and BLOCK until submit.

        Same worker-thread contract as request_nest_selection (the 911 picker is
        a specialization of this). `items` is the list to display; `done_items`
        are flagged as already done. `kwargs` are passed to SelectionDialog
        (window_title, header, root_label, noun, done_label, subhead_prefix,
        prompt_note, ...). Returns the chosen items, or None if cancelled.
        """
        from PySide6.QtCore import QThread

        if QThread.currentThread() == self.thread():
            raise RuntimeError(
                "request_selection() cannot be called from main GUI thread"
            )

        self._sel_args = (list(items), set(done_items or []), dict(kwargs))
        self._sel_result = None

        # Hold the inactivity watchdog while the dialog is up (see plugin_executor).
        self.waiting_for_input = True
        try:
            QMetaObject.invokeMethod(
                self,
                "_selection_gui",
                Qt.ConnectionType.BlockingQueuedConnection,
            )
        finally:
            self.waiting_for_input = False

        return self._sel_result

    @Slot()
    def _selection_gui(self):
        """GUI-thread half of request_selection: run the modal dialog."""
        from techdeck.ui.dialogs.selection_dialog import SelectionDialog

        items, done_items, kwargs = self._sel_args
        dlg = SelectionDialog(items, done_items, parent=self.window(), **kwargs)
        if dlg.exec():
            self._sel_result = dlg.selected()
        else:
            self._sel_result = None

    def request_grouped_toggles(self, groups, **kwargs):
        """Show the two-level stage/option toggle dialog and BLOCK until submit.

        Same worker-thread contract as request_selection. ``groups`` is the
        plain-data spec GroupedToggleDialog takes (see that module); ``kwargs``
        pass through (window_title, header, subtext, run_button_text).
        Returns {group_key: {"enabled": bool, "options": {child_key: bool}}},
        or None if cancelled. First used by the consolidated 922 Setup.
        """
        from PySide6.QtCore import QThread

        if QThread.currentThread() == self.thread():
            raise RuntimeError(
                "request_grouped_toggles() cannot be called from main GUI thread"
            )

        self._gt_args = ([dict(g) for g in groups], dict(kwargs))
        self._gt_result = None

        # Hold the inactivity watchdog while the dialog is up (see plugin_executor).
        self.waiting_for_input = True
        try:
            QMetaObject.invokeMethod(
                self,
                "_grouped_toggles_gui",
                Qt.ConnectionType.BlockingQueuedConnection,
            )
        finally:
            self.waiting_for_input = False

        return self._gt_result

    @Slot()
    def _grouped_toggles_gui(self):
        """GUI-thread half of request_grouped_toggles: run the modal dialog."""
        from techdeck.ui.dialogs.grouped_toggle_dialog import GroupedToggleDialog

        groups, kwargs = self._gt_args
        dlg = GroupedToggleDialog(groups, parent=self.window(), **kwargs)
        if dlg.exec():
            self._gt_result = dlg.result_map()
        else:
            self._gt_result = None

    def request_directory(self, title: str = "Select Folder", start_dir: str = "",
                          style=None):
        """Show the pick-a-folder dialog and BLOCK until the user chooses.
        Same worker-thread contract as request_selection. Returns the picked
        path string, or None if the user cancelled.

        ``style="chopper_gunner"`` opens the MW2 chopper-gunner picker
        (crosshair cursor + lock-on + railgun kill-cam overlay —
        chopper_picker.py) instead of the native dialog. The professional
        theme, and any failure inside the effect, silently fall back to the
        native dialog — the toy must never block a run.

        Prefer this (via sdk.request_directory) over making users paste a
        folder path into the console.
        """
        from PySide6.QtCore import QThread

        if QThread.currentThread() == self.thread():
            raise RuntimeError(
                "request_directory() cannot be called from main GUI thread"
            )

        self._dir_args = (str(title), str(start_dir or ""), style)
        self._dir_result = None

        # Hold the inactivity watchdog while the dialog is up (see plugin_executor).
        self.waiting_for_input = True
        try:
            QMetaObject.invokeMethod(
                self,
                "_directory_gui",
                Qt.ConnectionType.BlockingQueuedConnection,
            )
        finally:
            self.waiting_for_input = False

        return self._dir_result

    @Slot()
    def _directory_gui(self):
        """GUI-thread half of request_directory: run the folder dialog.
        chopper_gunner style → the kill-cam picker, unless the professional
        theme is active or ANYTHING in it fails (then the native dialog)."""
        from PySide6.QtWidgets import QFileDialog

        title, start_dir, style = self._dir_args
        if style == "chopper_gunner":
            try:
                from techdeck.core.settings import SettingsManager
                if not SettingsManager().is_professional():
                    from techdeck.ui.widgets.chopper_picker import (
                        pick_folder_chopper,
                    )
                    self._dir_result = pick_folder_chopper(
                        self.window(), title, start_dir)
                    return
            except Exception:
                pass  # any failure: fall through to the native dialog
        path = QFileDialog.getExistingDirectory(self.window(), title, start_dir)
        self._dir_result = path or None

    def show_warning(self, title: str, text: str):
        """Show a modal warning popup and BLOCK until the user acknowledges it.
        Same worker-thread contract as request_selection/request_directory —
        use for warnings that must not scroll past unseen (via
        sdk.show_warning, which adds the headless fallback)."""
        from PySide6.QtCore import QThread

        if QThread.currentThread() == self.thread():
            raise RuntimeError(
                "show_warning() cannot be called from main GUI thread"
            )

        self._warn_args = (str(title), str(text))

        # Hold the inactivity watchdog while the dialog is up (see plugin_executor).
        self.waiting_for_input = True
        try:
            QMetaObject.invokeMethod(
                self,
                "_warning_gui",
                Qt.ConnectionType.BlockingQueuedConnection,
            )
        finally:
            self.waiting_for_input = False

    @Slot()
    def _warning_gui(self):
        """GUI-thread half of show_warning: run the modal message box."""
        from PySide6.QtWidgets import QMessageBox

        title, text = self._warn_args
        QMessageBox.warning(self.window(), title, text)

    @Slot(str)
    def append_user(self, text: str):
        """Append user message to output."""
        self.output.append(
            f'<span style="color: #60A5FA; font-weight: bold;">You:</span> '
            f'{self._escape_html(text)}'
        )
        self._scroll_to_bottom()

    @Slot(str)
    def append_system(self, text: str):
        """Append system message to output."""
        self.output.append(
            f'<span style="color: #10B981; font-weight: bold;">System:</span> '
            f'{self._escape_html(text)}'
        )
        self._scroll_to_bottom()

    @Slot(str)
    def append_assistant(self, text: str):
        """Append assistant message to output."""
        self.output.append(
            f'<span style="color: #A78BFA; font-weight: bold;">Assistant:</span> '
            f'{self._escape_html(text)}'
        )
        self._scroll_to_bottom()

    @Slot(str)
    def append_error(self, text: str):
        """Append error message to output."""
        self.output.append(
            f'<span style="color: #EF4444; font-weight: bold;">Error:</span> '
            f'{self._escape_html(text)}'
        )
        self._scroll_to_bottom()

    @Slot(str, str)
    def append_plugin_output(self, plugin_name: str, text: str):
        """Append plugin output message."""
        self.output.append(
            f'<span style="color: #F59E0B; font-weight: bold;">[{plugin_name}]:</span> '
            f'{self._escape_html(text)}'
        )
        self._scroll_to_bottom()

    @Slot(str)
    def append_game(self, text: str):
        """Append game/easter-egg output — thread-safe via @Slot."""
        self.output.append(
            f'<span style="color: #C084FC; font-family: Consolas, monospace;">'
            f'{self._escape_html(text)}</span>'
        )
        self._scroll_to_bottom()

    def safe_game_log(self, text: str):
        """Call append_game from any thread safely."""
        QMetaObject.invokeMethod(
            self,
            "append_game",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, text),
        )

    def append_link(self, text: str, target_path: str, prefix: str = "",
                    at_run_end: bool = False):
        """Append a CLICKABLE line that opens `target_path` with its default
        app (image viewer, Explorer, ...). Thread-safe — callable straight
        from a plugin worker. Styled like a normal output line: the optional
        `prefix` renders as a bold channel tag (easter-egg purple, matching
        append_game and distinct from the plugin-output orange) and `text`
        as body-colored text, underlined to denote it's clickable.
        Click handling lives in eventFilter (a read-only QTextEdit renders
        anchors but doesn't act on them).

        `at_run_end=True` defers the line: it's held until the shell calls
        flush_pending_links() after the plugin's completion + ticket
        messages, so the link can be the run's LAST printed line (a line
        appended from run() otherwise races ahead of those)."""
        slot = "_store_pending_link" if at_run_end else "_append_link_gui"
        QMetaObject.invokeMethod(
            self,
            slot,
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, text),
            Q_ARG(str, target_path),
            Q_ARG(str, prefix),
        )

    @Slot(str, str, str)
    def _store_pending_link(self, text: str, target_path: str, prefix: str):
        self._pending_links.append((text, target_path, prefix))

    def flush_pending_links(self):
        """Print any deferred append_link lines (GUI thread; the shell calls
        this at the end of its plugin-completed handler)."""
        while self._pending_links:
            self._append_link_gui(*self._pending_links.pop(0))

    @Slot(str, str, str)
    def _append_link_gui(self, text: str, target_path: str, prefix: str):
        # Body text color = the active theme's text color, so the message half
        # reads exactly like every other appended message (anchors otherwise
        # render in Qt's default link blue).
        from techdeck.ui.theme_manager import get_theme_manager
        body_color = get_theme_manager().get_current_palette().text
        url = QUrl.fromLocalFile(target_path).toString()
        lead = ""
        if prefix:
            lead = (f'<span style="color: #C084FC; font-weight: bold;">'
                    f'{self._escape_html(prefix)}</span> ')
        self.output.append(
            lead + f'<a href="{url}" style="color: {body_color}; '
            f'text-decoration: underline;">{self._escape_html(text)}</a>'
        )
        self._scroll_to_bottom()

    def eventFilter(self, obj, event):
        """Hover/click handling for append_link anchors in the output view."""
        if obj is self.output.viewport():
            et = event.type()
            if et == QEvent.Type.MouseMove:
                anchor = self.output.anchorAt(event.position().toPoint())
                self.output.viewport().setCursor(
                    Qt.CursorShape.PointingHandCursor if anchor
                    else Qt.CursorShape.IBeamCursor)
            elif (et == QEvent.Type.MouseButtonRelease
                    and event.button() == Qt.MouseButton.LeftButton):
                anchor = self.output.anchorAt(event.position().toPoint())
                if anchor:
                    QDesktopServices.openUrl(QUrl(anchor))
                    return True
        return super().eventFilter(obj, event)

    def show_spinner(self, html: str):
        """Show the spinner label with the given HTML content."""
        self._spinner_label.setText(html)
        self._spinner_label.show()

    def update_spinner(self, html: str):
        """Update the spinner label content in-place (called each animation tick)."""
        self._spinner_label.setText(html)

    def hide_spinner(self):
        """Hide the spinner label."""
        self._spinner_label.hide()
        self._spinner_label.setText("")

    # ===== Dashboard API (thread-safe — callable from plugin worker threads) =====
    def show_dashboard(self, spec: dict):
        """Render a dashboard spec on the Dashboard tab and switch to it.

        Safe to call from a plugin's worker thread: the actual render is
        marshalled onto the GUI thread (same pattern as request_input /
        safe_game_log). See techdeck.ui.widgets.dashboard for the spec format.
        """
        self._pending_dashboard = spec
        QMetaObject.invokeMethod(
            self, "_show_dashboard_gui", Qt.ConnectionType.QueuedConnection
        )

    def clear_dashboard(self):
        """Reset the Dashboard tab to its empty state (thread-safe)."""
        QMetaObject.invokeMethod(
            self, "_clear_dashboard_gui", Qt.ConnectionType.QueuedConnection
        )

    @Slot()
    def _show_dashboard_gui(self):
        self.dashboard.render_spec(self._pending_dashboard)
        self.tab_bar.setCurrentIndex(self._ensure_dashboard_tab())
        self.dashboard_shown.emit()

    @Slot()
    def _clear_dashboard_gui(self):
        self.dashboard.clear_dashboard()

    def reopen_dashboard(self):
        """Re-add (if closed) and switch to the Dashboard tab. Backs the /dash
        command and the auto-open when a plugin renders a dashboard."""
        self.tab_bar.setCurrentIndex(self._ensure_dashboard_tab())
        self.dashboard_shown.emit()

    # ----- tab plumbing -----
    def _on_tab_changed(self, index: int):
        if index < 0:
            return
        page = self.tab_bar.tabData(index)
        if page is not None:
            self.stack.setCurrentWidget(page)
            if page is self._dash_page:
                # Refresh the idle view so usage/bankroll are current.
                self.dashboard.refresh_idle()

    def _close_dashboard_tab(self):
        idx = self._dash_tab_index()
        if idx != -1:
            self.tab_bar.removeTab(idx)
            self.stack.setCurrentWidget(self._console_page)

    def _make_close_button(self) -> QToolButton:
        """A small, box-less 'x' that closes the Dashboard tab, sitting right
        next to the label."""
        btn = QToolButton()
        btn.setObjectName("dashCloseBtn")
        btn.setText("×")  # multiplication sign reads as a clean close 'x'
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setFixedSize(16, 16)
        btn.clicked.connect(self._close_dashboard_tab)
        self._style_close_button(btn)
        return btn

    def _style_close_button(self, btn: QToolButton):
        p = self.get_current_palette()
        btn.setStyleSheet(
            "QToolButton#dashCloseBtn { border: none; background: transparent;"
            f" color: {p.text_secondary}; font-size: 16px; font-weight: bold;"
            " padding: 0; margin: 0 0 3px -7px; }"
            f"QToolButton#dashCloseBtn:hover {{ color: {p.text}; }}"
        )

    def _dash_tab_index(self) -> int:
        for i in range(self.tab_bar.count()):
            if self.tab_bar.tabData(i) is self._dash_page:
                return i
        return -1

    def _console_tab_index(self) -> int:
        for i in range(self.tab_bar.count()):
            if self.tab_bar.tabData(i) is self._console_page:
                return i
        return 0

    def _ensure_dashboard_tab(self) -> int:
        idx = self._dash_tab_index()
        if idx == -1:
            idx = self.tab_bar.addTab("Dashboard")
            self.tab_bar.setTabData(idx, self._dash_page)
            self.tab_bar.setTabButton(
                idx, QTabBar.ButtonPosition.RightSide, self._make_close_button()
            )
        return idx

    def apply_theme(self):
        """ThemeAware hook — restyle the Chrome-style tabs so the active tab
        connects into the content panel, plus the borderless text area + readout."""
        p = self.get_current_palette()

        # Console body and the selected tab share ONE color (console_bg, the
        # darker terminal shade) so the active tab blends into the console with
        # no shade difference. The text area is set explicitly (not transparent)
        # to guarantee it matches the tab exactly.
        body_bg = p.console_bg

        # The console box — no outline. Top-left stays square where the tabs
        # connect; the other three corners are rounded.
        self.panel.setStyleSheet(
            f"QFrame#consolePanel {{ background: {body_bg}; border: none;"
            " border-top-left-radius: 0; border-top-right-radius: 6px;"
            " border-bottom-left-radius: 6px; border-bottom-right-radius: 6px; }"
        )
        # Inner text area: borderless, square on all four corners, same body color.
        self.output.setStyleSheet(
            f"QTextEdit {{ border: none; border-radius: 0; background: {body_bg};"
            f" color: {p.console_text}; }}"
        )
        # Tabs: no outlines either. The selected tab fills with body_bg so it is
        # the same color as the console; inactive tabs use the lighter surface
        # fill so they still read as separate tabs.
        self.tab_bar.setStyleSheet(
            "QTabBar#consoleTabBar { background: transparent; }"
            f"QTabBar#consoleTabBar::tab {{ background: {p.surface}; color: {p.text_secondary};"
            " font-weight: bold; padding: 6px 14px; margin-right: 3px; border: none;"
            " border-top-left-radius: 8px; border-top-right-radius: 8px; }"
            f"QTabBar#consoleTabBar::tab:selected {{ background: {body_bg}; color: {p.text}; }}"
            f"QTabBar#consoleTabBar::tab:hover:!selected {{ background: {p.surface_hover}; }}"
        )
        # Re-tint the Dashboard close button if the tab is present.
        di = self._dash_tab_index()
        if di != -1:
            btn = self.tab_bar.tabButton(di, QTabBar.ButtonPosition.RightSide)
            if btn is not None:
                self._style_close_button(btn)

    def clear(self):
        """Clear console output (Clear button or /clear). Emits `cleared` so the
        command handler can tear down in-console sessions (blackjack, rave, moth)."""
        from techdeck.core.audio_manager import get_audio_manager, SOUND_CLEAR
        self.output.clear()
        self.append_system("Console cleared.")
        get_audio_manager().play(SOUND_CLEAR)
        self.cleared.emit()
    
    def _scroll_to_bottom(self):
        """Scroll output to bottom."""
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output.setTextCursor(cursor)
    
    def _escape_html(self, text: str) -> str:
        """Escape HTML characters in text, preserving newlines.

        QTextEdit.append() renders the payload as HTML, so embedded
        `\\n` characters collapse to spaces unless we convert them to
        `<br>` ourselves. This is what lets /help, /profiles, /tiles,
        and /guides render their multi-line output across lines.
        """
        return (text.replace('&', '&amp;')
                   .replace('<', '&lt;')
                   .replace('>', '&gt;')
                   .replace('"', '&quot;')
                   .replace("'", '&#39;')
                   .replace('\n', '<br>'))
