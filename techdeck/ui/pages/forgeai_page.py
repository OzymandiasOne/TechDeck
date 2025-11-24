"""
ForgeAI Page - AI-Powered Plugin Builder
Placeholder page with "Coming Soon" message
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel
)
from PySide6.QtCore import Qt
from techdeck.core.settings import SettingsManager
from techdeck.ui.theme import get_current_palette


class ForgeAIPage(QWidget):
    """
    ForgeAI page - AI-powered plugin builder (Coming Soon).
    """
    
    def __init__(self, settings: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the ForgeAI page UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Get theme
        theme = get_current_palette(self.settings.get_theme())
        
        # Page background
        self.setStyleSheet(f"background-color: {theme.background};")
        
        # Title
        title = QLabel("ForgeAI")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"""
            font-size: 32px;
            font-weight: bold;
            color: {theme.text};
            margin-bottom: 20px;
        """)
        layout.addWidget(title)
        
        # Subtitle
        subtitle = QLabel("Automate your personal workflow on the fly. Develop your own apps with a click of a button.")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(f"""
            font-size: 18px;
            color: {theme.text_secondary};
            margin-bottom: 10px;
        """)
        layout.addWidget(subtitle)
        
        # Coming Soon message
        coming_soon = QLabel("Coming Soon")
        coming_soon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        coming_soon.setStyleSheet(f"""
            font-size: 24px;
            font-weight: 600;
            color: {theme.accent};
            margin-top: 20px;
        """)
        layout.addWidget(coming_soon)
        
        # Add spacer at bottom
        layout.addStretch()
