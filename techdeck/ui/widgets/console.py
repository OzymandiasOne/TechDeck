"""
TechDeck Console/Chat Widget - ENHANCED with Plugin Input Support
Adds ability for plugins to request user input during execution.

FIXED: Uses BlockingQueuedConnection to properly synchronize worker thread with GUI thread
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLineEdit, QPushButton, QLabel, QTabBar, QStackedWidget, QFrame, QToolButton
)
from PySide6.QtCore import Signal, Qt, Q_ARG, QMetaObject, Slot
from PySide6.QtGui import QTextCursor, QFont
import threading

from techdeck.ui.widgets.dashboard import DashboardView
from techdeck.ui.theme_aware import ThemeAware


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
        
        # NEW: Check if we're waiting for plugin input
        if self.waiting_for_input:
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
    
    def request_input(self, prompt: str) -> str:
        """
        NEW: Request input from user - BLOCKS until user provides input.
        
        This method can be called from plugin threads and will safely
        request input from the main GUI thread.
        
        FIXED: Uses BlockingQueuedConnection to properly synchronize threads
        
        Args:
            prompt: The prompt/question to show the user
            
        Returns:
            str: The user's input
        """
        from PySide6.QtCore import QThread, QMetaObject
        
        # If we're on the main GUI thread, we can't block
        if QThread.currentThread() == self.thread():
            raise RuntimeError("request_input() cannot be called from main GUI thread")
        
        # We're on a worker thread - safe to block
        self.input_response = None
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
        
        return self.input_response
    
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
        """Clear console output."""
        from techdeck.core.audio_manager import get_audio_manager, SOUND_CLEAR
        self.output.clear()
        self.append_system("Console cleared.")
        get_audio_manager().play(SOUND_CLEAR)
    
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
