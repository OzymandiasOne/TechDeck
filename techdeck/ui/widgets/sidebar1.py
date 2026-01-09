"""
TechDeck Sidebar Navigation - With SVG Icon Support and Theme Integration
Collapsible sidebar with SVG icons, tooltips, proper layout resizing, and dynamic theming.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
)
from PySide6.QtCore import Signal, Qt, QPropertyAnimation, QEasingCurve, QSize, QByteArray
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer
from pathlib import Path


class NavButton(QPushButton):
    """Custom navigation button with icon and text."""
    
    def __init__(self, icon_path: str, text: str, page_id: str, icon_color: str = "#ECECEC", parent=None):
        super().__init__(parent)
        self.icon_path = icon_path
        self.text = text
        self.page_id = page_id
        self.icon_color = icon_color
        self.collapsed = False
        
        self.setCheckable(True)
        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Create layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(12)
        
        # Icon label
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(20, 20)
        self.icon_label.setStyleSheet("background: transparent; border: none;")
        self._load_icon(icon_path, icon_color)
        
        # Text label
        self.text_label = QLabel(text)
        self.text_label.setStyleSheet("font-size: 13px; background: transparent; border: none;")
        
        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)
        layout.addStretch()
        
        self.update_style()
    
    def _load_icon(self, icon_path: str, color: str):
        """Load icon from SVG with custom color or use emoji/text."""
        if icon_path.endswith('.svg'):
            # Load SVG icon with custom color
            path = Path(icon_path)
            if path.exists():
                try:
                    # Read SVG content
                    with open(path, 'r', encoding='utf-8') as f:
                        svg_content = f.read()
                    
                    # Replace 'currentColor' with actual color
                    svg_content = svg_content.replace('currentColor', color)
                    
                    # Create SVG renderer
                    renderer = QSvgRenderer(QByteArray(svg_content.encode('utf-8')))
                    
                    # Create pixmap and render SVG onto it
                    pixmap = QPixmap(20, 20)
                    pixmap.fill(Qt.GlobalColor.transparent)
                    
                    painter = QPainter(pixmap)
                    renderer.render(painter)
                    painter.end()
                    
                    self.icon_label.setPixmap(pixmap)
                except Exception as e:
                    print(f"Error loading icon {icon_path}: {e}")
                    # Fallback to bullet
                    self.icon_label.setText("â€¢")
                    self.icon_label.setStyleSheet(f"font-size: 18px; color: {color};")
            else:
                # Fallback to text if file doesn't exist
                print(f"Icon file not found: {icon_path}")
                self.icon_label.setText("â€¢")
                self.icon_label.setStyleSheet(f"font-size: 18px; color: {color};")
        else:
            # Use emoji or text
            self.icon_label.setText(icon_path)
            self.icon_label.setStyleSheet(f"font-size: 18px; color: {color};")
    
    def set_collapsed(self, collapsed: bool):
        """Toggle between icon-only and full display."""
        self.collapsed = collapsed
        self.text_label.setVisible(not collapsed)
        
        if collapsed:
            self.setToolTip(self.text)
            self.setFixedWidth(50)
        else:
            self.setToolTip("")
            self.setMinimumWidth(200)
            self.setMaximumWidth(200)
    
    def update_style(self):
        """Update button styling."""
        self.setStyleSheet("""
            NavButton {
                background-color: transparent;
                border: none;
                border-radius: 8px;
                text-align: left;
            }
            NavButton:hover {
                background-color: rgba(255, 255, 255, 0.05);
            }
            NavButton:checked {
                background-color: rgba(255, 255, 255, 0.1);
            }
        """)


class Sidebar(QWidget):
    """
    Collapsible sidebar with SVG icon support and theme integration.
    
    Signals:
        page_changed(str): Emitted when page selection changes
    """
    
    page_changed = Signal(str)
    
    def __init__(self, parent=None, settings_manager=None):
        """
        Initialize sidebar.
        
        Args:
            parent: Parent widget (Qt convention - comes first)
            settings_manager: SettingsManager instance for theme access
        """
        super().__init__(parent)
        
        if settings_manager is None:
            raise ValueError("Sidebar requires a SettingsManager instance")
        
        self.settings = settings_manager
        
        # State
        self.collapsed = False
        self.expanded_width = 200
        self.collapsed_width = 50
        
        # Set fixed width
        self.setFixedWidth(self.expanded_width)
        
        # Get theme colors
        from techdeck.ui.theme import get_current_palette
        theme = get_current_palette(self.settings.get_theme())
        
        # Apply theme colors to sidebar - style widget directly for border to show
        self.setStyleSheet(f"""
            background-color: {theme.surface};
            border-right: 1px solid {theme.background};
        """)
        
        # Store theme for icon colors
        self.theme = theme
        
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # ===== Header =====
        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet(f"background-color: {theme.surface};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 0, 8, 0)
        header_layout.setSpacing(8)
        
        # Get path to collapse/expand SVG icons
        project_root = Path(__file__).parent.parent.parent.parent
        
        # Select icon folder based on theme (light icons for dark/blue, dark icons for light)
        theme_name = settings_manager.get_theme()
        icon_folder = "light" if theme_name in ["dark", "blue"] else "dark"
        icons_dir = project_root / "assets" / "icons" / icon_folder
        
        print(f"Looking for icons in: {icons_dir}")
        print(f"Icons directory exists: {icons_dir.exists()}")
        if icons_dir.exists():
            print(f"Contents: {list(icons_dir.glob('*.svg'))}")
        
        # Toggle button - try to use SVG, fallback to unicode
        collapse_icon = icons_dir / "collapse.svg"
        if collapse_icon.exists():
            try:
                # Load collapse SVG
                with open(collapse_icon, 'r', encoding='utf-8') as f:
                    svg_content = f.read().replace('currentColor', theme.text)
                
                renderer = QSvgRenderer(QByteArray(svg_content.encode('utf-8')))
                pixmap = QPixmap(16, 16)
                pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pixmap)
                renderer.render(painter)
                painter.end()
                
                self.toggle_btn = QPushButton()
                self.toggle_btn.setIcon(QIcon(pixmap))
                self.toggle_btn.setIconSize(QSize(16, 16))
            except Exception as e:
                print(f"Error loading collapse icon: {e}")
                self.toggle_btn = QPushButton("â—„")
        else:
            # Fallback to unicode
            self.toggle_btn = QPushButton("â—„")
        
        self.toggle_btn.setFixedSize(34, 34)
        self.toggle_btn.setToolTip("Collapse sidebar")
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.clicked.connect(self.toggle_collapse)
        self.toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                font-size: 14px;
                border-radius: 6px;
                color: {theme.text};
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.05);
            }}
        """)
        
        # Store icon paths for toggle button
        self.collapse_icon_path = collapse_icon
        self.expand_icon_path = icons_dir / "expand.svg"
        
        # App name - FIXED: Added explicit border, padding, and margin properties
        self.app_name = QLabel("TechDeck")
        self.app_name.setStyleSheet(f"""
            font-size: 15px;
            font-weight: 600;
            color: {theme.text};
            background-color: transparent;
            border: none;
            padding: 0px;
            margin: 0px;
        """)
        # Ensure label doesn't accept focus
        self.app_name.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        
        header_layout.addWidget(self.toggle_btn)
        header_layout.addWidget(self.app_name)
        header_layout.addStretch()
        
        layout.addWidget(header)
        
        # Separator line (uses theme color)
        # separator = QWidget()
        # separator.setFixedHeight(1)
        # separator.setStyleSheet(f"background-color: {theme.console_bg};")
        # layout.addWidget(separator)
        
        # ===== Navigation Buttons =====
        nav_container = QWidget()
        nav_container.setStyleSheet(f"background-color: {theme.surface};")
        nav_layout = QVBoxLayout(nav_container)
        nav_layout.setContentsMargins(4, 8, 4, 8)
        nav_layout.setSpacing(2)
        
        # Create navigation buttons with SVG icons
        self.nav_buttons = []
        pages = [
            (str(icons_dir / "home.svg"), "Home", "home"),
            (str(icons_dir / "library.svg"), "Library", "library"),
            (str(icons_dir / "forgeai.svg"), "ForgeAI", "forgeai"),
            (str(icons_dir / "settings.svg"), "Settings", "settings"),
            (str(icons_dir / "account.svg"), "My Account", "account"),
        ]
        
        # Use theme text color for icons
        icon_color = theme.text
        
        for icon_path, text, page_id in pages:
            btn = NavButton(icon_path, text, page_id, icon_color)
            btn.clicked.connect(lambda checked, pid=page_id: self._on_nav_clicked(pid))
            self.nav_buttons.append(btn)
            nav_layout.addWidget(btn)
        
        # Select Home by default
        self.nav_buttons[0].setChecked(True)
        
        nav_layout.addStretch()
        layout.addWidget(nav_container)
        
        # Create animation
        self.animation = QPropertyAnimation(self, b"minimumWidth")
        self.animation.setDuration(200)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        
        self.size_animation = QPropertyAnimation(self, b"maximumWidth")
        self.size_animation.setDuration(200)
        self.size_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
    
    def toggle_collapse(self):
        """Toggle sidebar collapse state."""
        if self.collapsed:
            self.expand()
        else:
            self.collapse()
    
    def collapse(self):
        """Collapse sidebar to icon-only mode."""
        if self.collapsed:
            return
        
        self.collapsed = True
        
        # Update toggle button icon to expand
        if self.expand_icon_path.exists():
            try:
                with open(self.expand_icon_path, 'r', encoding='utf-8') as f:
                    svg_content = f.read().replace('currentColor', self.theme.text)
                
                renderer = QSvgRenderer(QByteArray(svg_content.encode('utf-8')))
                pixmap = QPixmap(16, 16)
                pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pixmap)
                renderer.render(painter)
                painter.end()
                
                self.toggle_btn.setIcon(QIcon(pixmap))
            except Exception as e:
                print(f"Error loading expand icon: {e}")
                self.toggle_btn.setText("â–º")
        else:
            self.toggle_btn.setText("â–º")
        
        self.toggle_btn.setToolTip("Expand sidebar")
        
        # Hide app name
        self.app_name.hide()
        
        # Collapse navigation buttons
        for btn in self.nav_buttons:
            btn.set_collapsed(True)
        
        # Animate width
        self.animation.setStartValue(self.expanded_width)
        self.animation.setEndValue(self.collapsed_width)
        self.size_animation.setStartValue(self.expanded_width)
        self.size_animation.setEndValue(self.collapsed_width)
        
        self.animation.start()
        self.size_animation.start()
    
    def expand(self):
        """Expand sidebar to full mode."""
        if not self.collapsed:
            return
        
        self.collapsed = False
        
        # Update toggle button icon to collapse
        if self.collapse_icon_path.exists():
            try:
                with open(self.collapse_icon_path, 'r', encoding='utf-8') as f:
                    svg_content = f.read().replace('currentColor', self.theme.text)
                
                renderer = QSvgRenderer(QByteArray(svg_content.encode('utf-8')))
                pixmap = QPixmap(16, 16)
                pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pixmap)
                renderer.render(painter)
                painter.end()
                
                self.toggle_btn.setIcon(QIcon(pixmap))
            except Exception as e:
                print(f"Error loading collapse icon: {e}")
                self.toggle_btn.setText("â—„")
        else:
            self.toggle_btn.setText("â—„")
        
        self.toggle_btn.setToolTip("Collapse sidebar")
        
        # Show app name
        self.app_name.show()
        
        # Expand navigation buttons
        for btn in self.nav_buttons:
            btn.set_collapsed(False)
        
        # Animate width
        self.animation.setStartValue(self.collapsed_width)
        self.animation.setEndValue(self.expanded_width)
        self.size_animation.setStartValue(self.collapsed_width)
        self.size_animation.setEndValue(self.expanded_width)
        
        self.animation.start()
        self.size_animation.start()
    
    def _on_nav_clicked(self, page_id: str):
        """Handle navigation button click."""
        # Uncheck all other buttons
        for btn in self.nav_buttons:
            if btn.page_id != page_id:
                btn.setChecked(False)
        
        # Emit signal
        self.page_changed.emit(page_id)
    
    def set_current_page(self, page_id: str):
        """Programmatically set current page."""
        for btn in self.nav_buttons:
            btn.setChecked(btn.page_id == page_id)