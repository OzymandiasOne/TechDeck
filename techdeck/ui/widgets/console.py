"""
TechDeck Console/Chat Widget
Hybrid terminal and chat interface with command handling.
NOW: Uses theme colors instead of hardcoded colors!
FIXED: Added add_header_button method for shell.py
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, 
    QLineEdit, QPushButton, QLabel
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QTextCursor, QFont
from datetime import datetime


class ConsoleWidget(QWidget):
    """
    Console/chat widget with message history and command input.
    
    Supports both:
    - Commands (starting with /)
    - Natural language (for ChatGPT later)
    
    Signals:
        command_entered(str): Emitted when user enters a command
        message_entered(str): Emitted when user enters natural language
    """
    
    command_entered = Signal(str)
    message_entered = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Enable styled background so theme CSS applies
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # ===== Header =====
        header = QHBoxLayout()
        header.setSpacing(8)
        
        title = QLabel("Console / Chat")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setMaximumWidth(80)
        self.clear_btn.clicked.connect(self.clear)
        
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.clear_btn)
        
        self.header = header  # Store reference for add_header_button method
        layout.addLayout(self.header)
        
        # ===== Output Area =====
        # Remove inline styles - let theme handle it!
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        
        # Set font explicitly for better monospace rendering
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.output.setFont(font)
        
        layout.addWidget(self.output, 1)
        
        # ===== Input Area =====
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)
        
        # Remove inline styles - let theme handle it!
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
        """
        Add a button to the console header (before the Clear button).
        
        Args:
            button: QPushButton to add to header
        """
        # Insert before the Clear button (which is the last widget)
        # Header layout structure: [title, stretch, *new buttons*, clear_btn]
        count = self.header.count()
        # Insert before the last item (Clear button)
        self.header.insertWidget(count - 1, button)
    
    def _on_input_submitted(self):
        """Handle user input submission."""
        text = self.input_field.text().strip()
        
        if not text:
            return
        
        # Clear input
        self.input_field.clear()
        
        # Echo user input
        self.append_user(text)
        
        # Determine if it's a command or message
        if text.startswith('/'):
            # Command
            self.command_entered.emit(text)
        else:
            # Natural language message (for ChatGPT later)
            self.message_entered.emit(text)
    
    def append_user(self, text: str):
        """Append user message to output."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.output.append(f'<span style="color: #888;">[{timestamp}]</span> '
                          f'<span style="color: #60A5FA; font-weight: bold;">You:</span> '
                          f'{self._escape_html(text)}')
        self._scroll_to_bottom()
    
    def append_system(self, text: str):
        """Append system message to output."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.output.append(f'<span style="color: #888;">[{timestamp}]</span> '
                          f'<span style="color: #10B981; font-weight: bold;">System:</span> '
                          f'{self._escape_html(text)}')
        self._scroll_to_bottom()
    
    def append_assistant(self, text: str):
        """Append assistant (ChatGPT) message to output."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.output.append(f'<span style="color: #888;">[{timestamp}]</span> '
                          f'<span style="color: #A78BFA; font-weight: bold;">Assistant:</span> '
                          f'{self._escape_html(text)}')
        self._scroll_to_bottom()
    
    def append_error(self, text: str):
        """Append error message to output."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.output.append(f'<span style="color: #888;">[{timestamp}]</span> '
                          f'<span style="color: #EF4444; font-weight: bold;">Error:</span> '
                          f'{self._escape_html(text)}')
        self._scroll_to_bottom()
    
    def append_plugin_output(self, plugin_name: str, text: str):
        """Append plugin output message."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.output.append(f'<span style="color: #888;">[{timestamp}]</span> '
                          f'<span style="color: #F59E0B; font-weight: bold;">[{plugin_name}]:</span> '
                          f'{self._escape_html(text)}')
        self._scroll_to_bottom()
    
    def clear(self):
        """Clear console output."""
        self.output.clear()
        self.append_system("Console cleared.")
    
    def _scroll_to_bottom(self):
        """Scroll output to bottom."""
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output.setTextCursor(cursor)
    
    def _escape_html(self, text: str) -> str:
        """Escape HTML characters in text."""
        return (text.replace('&', '&amp;')
                   .replace('<', '&lt;')
                   .replace('>', '&gt;')
                   .replace('"', '&quot;')
                   .replace("'", '&#39;'))