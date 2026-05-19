"""
TechDeck Plugin Window
Base window class for plugins with built-in theming and lifecycle management
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Qt


class PluginWindow(QWidget):
    """
    Base window class for plugins with built-in theming and lifecycle management.
    
    Features:
    - Automatic theme application
    - Consistent window styling
    - Proper cleanup on close
    - Window state management
    """
    
    def __init__(self, plugin_id: str, title: str, parent=None):
        """
        Initialize plugin window.
        
        Args:
            plugin_id: Unique plugin identifier
            title: Window title
            parent: Optional parent widget (typically None for top-level window)
        """
        super().__init__(parent)
        self.plugin_id = plugin_id
        self.setWindowTitle(title)
        
        # Set window flags for standalone window
        self.setWindowFlags(Qt.Window)
        
        # Keep window alive (prevent garbage collection)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        
        # Set default size
        self.setMinimumSize(800, 600)
        
        # Create main layout
        self._main_layout = QVBoxLayout()
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)
        self.setLayout(self._main_layout)
        
        # Apply TechDeck theme
        self._apply_theme()
        
    def _apply_theme(self):
        """Apply TechDeck's current theme to the window"""
        try:
            from techdeck.ui.theme_manager import ThemeManager
            theme_manager = ThemeManager()
            current_theme = theme_manager.get_current_theme()
            
            if current_theme:
                # get_current_theme() returns the theme name as a string
                # Get the actual stylesheet from the theme manager
                from techdeck.ui.theme import generate_stylesheet
                stylesheet = generate_stylesheet(current_theme)
                self.setStyleSheet(stylesheet)
        except Exception as e:
            # If theme manager not available, use basic styling
            print(f"Could not apply theme: {e}")
        
    def set_content(self, widget: QWidget):
        """
        Set the main content widget.
        
        Args:
            widget: The content widget to display in the window
        """
        # Clear existing content
        while self._main_layout.count():
            item = self._main_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Add new content
        self._main_layout.addWidget(widget)
    
    def closeEvent(self, event):
        """Handle window close event with cleanup"""
        # Allow subclasses to add cleanup logic
        super().closeEvent(event)
