"""
TechDeck Sidebar Navigation - With Theme-Aware Icon Loading
Loads white icons for dark theme, black icons for light theme.

✅ FIXES APPLIED:
- Theme-aware icon folder selection (dark/ or light/)
- 3x super-sampling for crisp high-DPI rendering
- Antialiasing for smooth edges
- No color manipulation (uses pre-colored SVGs)
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
    
    def __init__(self, icon_path: str, text: str, page_id: str, parent=None):
        super().__init__(parent)
        self.icon_path = icon_path
        self.text = text
        self.page_id = page_id
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
        self._load_icon(icon_path)
        
        # Text label
        self.text_label = QLabel(text)
        self.text_label.setStyleSheet("font-size: 13px; background: transparent; border: none;")
        
        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)
        layout.addStretch()
        
        self.update_style()
    
    def _load_icon(self, icon_path: str):
        """Load icon from SVG with 3x super-sampling for crisp display."""
        if icon_path.endswith('.svg'):
            path = Path(icon_path)
            if path.exists():
                try:
                    # Read SVG content (no color manipulation needed)
                    with open(path, 'r', encoding='utf-8') as f:
                        svg_content = f.read()
                    
                    # Create SVG renderer
                    renderer = QSvgRenderer(QByteArray(svg_content.encode('utf-8')))
                    
                    # ✅ Create pixmap at 3x size for crisp rendering on high-DPI displays
                    pixmap = QPixmap(60, 60)  # 3x the 20x20 display size
                    pixmap.fill(Qt.GlobalColor.transparent)
                    
                    # Enable smooth rendering
                    painter = QPainter(pixmap)
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                    renderer.render(painter)
                    painter.end()
                    
                    # Scale down to display size with smooth transformation
                    pixmap = pixmap.scaled(
                        20, 20,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    
                    self.icon_label.setPixmap(pixmap)
                except Exception as e:
                    print(f"Error loading icon {icon_path}: {e}")
                    # Fallback to bullet
                    self.icon_label.setText("•")
            else:
                # Fallback to text if file doesn't exist
                print(f"Icon file not found: {icon_path}")
                self.icon_label.setText("•")
        else:
            # Use emoji or text
            self.icon_label.setText(icon_path)
    
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
    Collapsible sidebar with theme-aware icon loading.
    
    Loads icons from:
    - assets/icons/dark/ for dark theme (white icons)
    - assets/icons/light/ for light theme (black icons)
    
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
        
        # Apply theme colors to sidebar
        self.setStyleSheet(f"""
            background-color: {theme.surface};
            border-right: 1px solid {theme.background};
        """)
        
        # Store theme for icon folder selection
        self.theme = theme
        self.theme_name = self.settings.get_theme()
        
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
        
        # Get path to icon folder based on theme
        project_root = Path(__file__).parent.parent.parent.parent
        
        # ✅ Select icon folder based on theme
        # Dark/Blue themes use white icons (in "light" folder)
        # Light/Salmon themes use black icons (in "dark" folder)
        if self.theme_name in ["dark", "blue"]:
            icon_folder = "light"  # White icons for dark/blue themes
        else:
            icon_folder = "dark"  # Black icons for light/salmon themes
        
        icons_dir = project_root / "assets" / "icons" / icon_folder
        
        print(f"Loading icons from: {icons_dir}")
        print(f"Icons directory exists: {icons_dir.exists()}")
        if icons_dir.exists():
            print(f"Contents: {list(icons_dir.glob('*.svg'))}")
        
        # Toggle button - collapse icon
        collapse_icon_path = icons_dir / "collapse.svg"
        self.collapse_icon_path = collapse_icon_path
        self.expand_icon_path = icons_dir / "expand.svg"
        
        if collapse_icon_path.exists():
            try:
                # Load collapse SVG
                with open(collapse_icon_path, 'r', encoding='utf-8') as f:
                    svg_content = f.read()
                
                renderer = QSvgRenderer(QByteArray(svg_content.encode('utf-8')))
                
                # ✅ Render at 3x size for crisp display
                pixmap = QPixmap(48, 48)  # 3x the 16x16 display size
                pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pixmap)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                renderer.render(painter)
                painter.end()
                
                # Scale down smoothly
                pixmap = pixmap.scaled(
                    16, 16,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                
                self.toggle_btn = QPushButton()
                self.toggle_btn.setIcon(QIcon(pixmap))
                self.toggle_btn.setIconSize(QSize(16, 16))
            except Exception as e:
                print(f"Error loading collapse icon: {e}")
                self.toggle_btn = QPushButton("◄")
        else:
            # Fallback to unicode
            self.toggle_btn = QPushButton("◄")
        
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
        
        # App name
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
        self.app_name.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        
        header_layout.addWidget(self.toggle_btn)
        header_layout.addWidget(self.app_name)
        header_layout.addStretch()
        
        layout.addWidget(header)
        
        # ===== Navigation Buttons =====
        nav_container = QWidget()
        nav_container.setStyleSheet(f"background-color: {theme.surface};")
        nav_layout = QVBoxLayout(nav_container)
        nav_layout.setContentsMargins(4, 8, 4, 8)
        nav_layout.setSpacing(2)
        
        # Create navigation buttons with theme-appropriate icons
        self.nav_buttons = []
        pages = [
            (str(icons_dir / "home.svg"), "Home", "home"),
            (str(icons_dir / "library.svg"), "Library", "library"),
            (str(icons_dir / "settings.svg"), "Settings", "settings"),
            (str(icons_dir / "account.svg"), "My Account", "account"),
        ]
        
        for icon_path, text, page_id in pages:
            btn = NavButton(icon_path, text, page_id)
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
                    svg_content = f.read()
                
                renderer = QSvgRenderer(QByteArray(svg_content.encode('utf-8')))
                
                # ✅ Render at 3x size for crisp display
                pixmap = QPixmap(48, 48)
                pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pixmap)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                renderer.render(painter)
                painter.end()
                
                # Scale down smoothly
                pixmap = pixmap.scaled(
                    16, 16,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                
                self.toggle_btn.setIcon(QIcon(pixmap))
            except Exception as e:
                print(f"Error loading expand icon: {e}")
                self.toggle_btn.setText("►")
        else:
            self.toggle_btn.setText("►")
        
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
                    svg_content = f.read()
                
                renderer = QSvgRenderer(QByteArray(svg_content.encode('utf-8')))
                
                # ✅ Render at 3x size for crisp display
                pixmap = QPixmap(48, 48)
                pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pixmap)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                renderer.render(painter)
                painter.end()
                
                # Scale down smoothly
                pixmap = pixmap.scaled(
                    16, 16,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                
                self.toggle_btn.setIcon(QIcon(pixmap))
            except Exception as e:
                print(f"Error loading collapse icon: {e}")
                self.toggle_btn.setText("◄")
        else:
            self.toggle_btn.setText("◄")
        
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