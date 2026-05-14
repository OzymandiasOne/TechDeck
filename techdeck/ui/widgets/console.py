"""
TechDeck Console/Chat Widget - ENHANCED with Plugin Input Support
Adds ability for plugins to request user input during execution.

FIXED: Uses BlockingQueuedConnection to properly synchronize worker thread with GUI thread
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, 
    QLineEdit, QPushButton, QLabel
)
from PySide6.QtCore import Signal, Qt, Q_ARG, QMetaObject, Slot
from PySide6.QtGui import QTextCursor, QFont
from datetime import datetime
import threading


class ConsoleWidget(QWidget):
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
        
        # ===== Header =====
        header = QHBoxLayout()
        header.setSpacing(8)
        
        title = QLabel("Console / Chat")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        
        self.line_count_label = QLabel("0 lines")
        self.line_count_label.setStyleSheet("font-size: 11px; color: #888;")
        
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setMaximumWidth(80)
        self.clear_btn.clicked.connect(self.clear)
        
        header.addWidget(title)
        header.addWidget(self.line_count_label)
        header.addStretch()
        header.addWidget(self.clear_btn)
        
        self.header = header
        layout.addLayout(self.header)
        
        # ===== Output Area =====
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.document().setMaximumBlockCount(self.MAX_LINES + 100)
        
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.output.setFont(font)
        
        layout.addWidget(self.output, 1)
        
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
        
        # Initial message
        self.append_system("TechDeck Console ready. Type /help for available commands.")
    
    def add_header_button(self, button: QPushButton):
        """Add a button to the console header."""
        count = self.header.count()
        self.header.insertWidget(count - 1, button)
    
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
        
        Args:
            prompt: The prompt text to display to user
        """
        self.waiting_for_input = True
        self.input_prompt = prompt
        
        # Show the prompt in console
        self.append_system(f"🔹 {prompt}")
        self.append_system("   (Type your response below)")
        
        # Update input field to show we're waiting for response
        self.input_field.setPlaceholderText(f"Your response to: {prompt[:50]}...")
        self.input_field.setStyleSheet("border: 2px solid #F59E0B;")  # Orange border
        self.input_field.setFocus()
        
        self._scroll_to_bottom()
    
    @Slot(str)
    def append_user(self, text: str):
        """Append user message to output."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.output.append(f'<span style="color: #888;">[{timestamp}]</span> '
                          f'<span style="color: #60A5FA; font-weight: bold;">You:</span> '
                          f'{self._escape_html(text)}')
        self._scroll_to_bottom()
        self._update_line_count()

    @Slot(str)
    def append_system(self, text: str):
        """Append system message to output."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.output.append(f'<span style="color: #888;">[{timestamp}]</span> '
                          f'<span style="color: #10B981; font-weight: bold;">System:</span> '
                          f'{self._escape_html(text)}')
        self._scroll_to_bottom()
        self._update_line_count()

    @Slot(str)
    def append_assistant(self, text: str):
        """Append assistant message to output."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.output.append(f'<span style="color: #888;">[{timestamp}]</span> '
                          f'<span style="color: #A78BFA; font-weight: bold;">Assistant:</span> '
                          f'{self._escape_html(text)}')
        self._scroll_to_bottom()
        self._update_line_count()

    @Slot(str)
    def append_error(self, text: str):
        """Append error message to output."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.output.append(f'<span style="color: #888;">[{timestamp}]</span> '
                          f'<span style="color: #EF4444; font-weight: bold;">Error:</span> '
                          f'{self._escape_html(text)}')
        self._scroll_to_bottom()
        self._update_line_count()

    @Slot(str, str)
    def append_plugin_output(self, plugin_name: str, text: str):
        """Append plugin output message."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.output.append(f'<span style="color: #888;">[{timestamp}]</span> '
                          f'<span style="color: #F59E0B; font-weight: bold;">[{plugin_name}]:</span> '
                          f'{self._escape_html(text)}')
        self._scroll_to_bottom()
        self._update_line_count()

    @Slot(str)
    def append_game(self, text: str):
        """Append game/easter-egg output — thread-safe via @Slot."""
        self.output.append(
            f'<span style="color: #C084FC; font-family: Consolas, monospace;">'
            f'{self._escape_html(text)}</span>'
        )
        self._scroll_to_bottom()
        self._update_line_count()

    def safe_game_log(self, text: str):
        """Call append_game from any thread safely."""
        QMetaObject.invokeMethod(
            self,
            "append_game",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, text),
        )
    
    def clear(self):
        """Clear console output."""
        self.output.clear()
        self.append_system("Console cleared.")
    
    def _scroll_to_bottom(self):
        """Scroll output to bottom."""
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output.setTextCursor(cursor)
    
    def _update_line_count(self):
        """Update line count indicator in header."""
        doc = self.output.document()
        line_count = doc.blockCount()
        self.line_count_label.setText(f"{line_count} lines")
        
        if line_count > self.MAX_LINES * 0.9:
            self.line_count_label.setStyleSheet("font-size: 11px; color: #F59E0B; font-weight: bold;")
        elif line_count > self.MAX_LINES * 0.75:
            self.line_count_label.setStyleSheet("font-size: 11px; color: #F59E0B;")
        else:
            self.line_count_label.setStyleSheet("font-size: 11px; color: #888;")
    
    def _escape_html(self, text: str) -> str:
        """Escape HTML characters in text."""
        return (text.replace('&', '&amp;')
                   .replace('<', '&lt;')
                   .replace('>', '&gt;')
                   .replace('"', '&quot;')
                   .replace("'", '&#39;'))
