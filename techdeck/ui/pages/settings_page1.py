"""
TechDeck Settings Page - Tabbed Interface
Three tabs: General, App Settings (Plugins), Personalization
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QComboBox, QPushButton, QFrame, QScrollArea, 
    QLineEdit, QMessageBox, QSpinBox, QTabWidget
)
from PySide6.QtCore import Signal, Qt

from techdeck.core.settings import SettingsManager
from techdeck.core.plugin_loader import PluginLoader
from techdeck.ui.theme import get_theme_names, get_current_palette
from techdeck.ui.utils import make_tinted_svg_copy
from techdeck.ui.widgets.plugin_settings_widget import PluginSettingsWidget
from pathlib import Path


class SettingsPage(QWidget):
    """
    Settings page with three horizontal tabs:
    1. General - App-wide settings (theme, console, API)
    2. App Settings - Per-plugin configuration
    3. Personalization - User profile and appearance
    
    Signals:
        theme_changed(str): Emitted when theme is changed (requires restart)
    """
    
    theme_changed = Signal(str)
    
    def __init__(self, settings: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.plugin_loader = PluginLoader()
        self.plugin_loader.discover_plugins()
        
        # Track current plugin settings widget
        self.current_plugin_widget = None
        
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Create tab widget
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)  # Cleaner look

        # Apply theme-aware tab styling
        theme = get_current_palette(self.settings.get_theme())
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background-color: {theme.background};
            }}
            QTabBar::tab {{
                background-color: {theme.surface};
                color: {theme.text_secondary};
                padding: 10px 20px;
                border: none;
                border-bottom: 2px solid transparent;
                margin-right: 2px;
            }}
            QTabBar::tab:hover {{
                background-color: {theme.surface_hover};
                color: {theme.text};
            }}
            QTabBar::tab:selected {{
                background-color: {theme.surface};
                color: {theme.text};
                border-bottom: 2px solid {theme.accent};
                font-weight: 600;
            }}
        """)
        
        # Add tabs
        self.tabs.addTab(self._create_general_tab(), "General")
        self.tabs.addTab(self._create_plugin_tab(), "App Settings")
        self.tabs.addTab(self._create_personalization_tab(), "Personalization")
        
        layout.addWidget(self.tabs)
    
    # ========== GENERAL TAB ==========
    
    def _create_general_tab(self) -> QWidget:
        """Create General settings tab."""
        widget = QWidget()
        
        # Create scroll area for content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(24)
        
        # ===== Page Title =====
        title = QLabel("General Settings")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)
        
        # ===== Theme Section =====
        theme_section = self._create_section("Theme")
        
        theme_label = QLabel("Application Theme:")
        theme_label.setStyleSheet("font-weight: 600; margin-top: 8px;")
        
        theme_layout = QHBoxLayout()
        self.theme_combo = QComboBox()
        self.theme_combo.addItems([t.capitalize() for t in get_theme_names()])
        self.theme_combo.setMinimumHeight(34)
        self.theme_combo.setMaximumWidth(200)
        
        theme = get_current_palette(self.settings.get_theme())
        # ✅ Select icon folder based on theme
        theme_name = self.settings.get_theme()
        icon_folder = "light" if theme_name in ["dark", "blue"] else "dark"
        icons_dir = Path(__file__).resolve().parents[3] / "assets" / "icons" / icon_folder
        src_arrow = icons_dir / "chevron-down.svg"
        arrow_path = make_tinted_svg_copy(src_arrow, theme.text)
        
        self.theme_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {theme.surface};
                color: {theme.text};
                border: 1px solid {theme.border};
                border-radius: 8px;
                padding: 6px 10px;
                padding-right: 28px;
            }}
            QComboBox:hover {{
                border-color: {theme.border_strong};
            }}
            QComboBox::drop-down {{
                width: 24px;
                border: none;
                background: transparent;
                subcontrol-origin: padding;
                subcontrol-position: center right;
            }}
            QComboBox::down-arrow {{
                image: url("{arrow_path}");
                width: 12px;
                height: 12px;
                background: transparent;
                border: none;
                margin-right: 6px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {theme.surface};
                color: {theme.text};
                border: 1px solid {theme.border};
                border-radius: 4px;
                selection-background-color: {theme.tile_selected};
                outline: none;
            }}
        """)
        
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        
        theme_layout.addWidget(self.theme_combo)
        theme_layout.addStretch()
        
        theme_section.addWidget(theme_label)
        theme_section.addLayout(theme_layout)
        
        theme_note = QLabel("Note: Changing theme requires restarting TechDeck.")
        theme_note.setStyleSheet("color: #888; font-size: 12px; margin-top: 4px;")
        theme_section.addWidget(theme_note)
        
        layout.addLayout(theme_section)
        
        # ===== Console Settings Section =====
        console_section = self._create_section("Console")
        
        console_height_label = QLabel("Default Console Height (pixels):")
        console_height_label.setStyleSheet("font-weight: 600; margin-top: 8px;")
        
        console_height_layout = QHBoxLayout()
        self.console_height_spin = QSpinBox()
        self.console_height_spin.setMinimum(150)
        self.console_height_spin.setMaximum(600)
        self.console_height_spin.setValue(self.settings.get_console_height())
        self.console_height_spin.setSuffix(" px")
        self.console_height_spin.setMinimumHeight(34)
        self.console_height_spin.setMaximumWidth(150)
        
        console_height_layout.addWidget(self.console_height_spin)
        console_height_layout.addStretch()
        
        console_section.addWidget(console_height_label)
        console_section.addLayout(console_height_layout)
        
        console_note = QLabel("This sets the default height when TechDeck starts.\n"
                              "You can still resize it manually with the splitter.")
        console_note.setStyleSheet("color: #888; font-size: 12px; margin-top: 4px;")
        console_section.addWidget(console_note)
        
        layout.addLayout(console_section)
        
        # ===== API Configuration Section =====
        api_section = self._create_section("API Configuration")
        
        api_label = QLabel("OpenAI API Key:")
        api_label.setStyleSheet("font-weight: 600; margin-top: 8px;")
        
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("sk-...")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setMinimumHeight(34)
        self.api_key_input.setMaximumWidth(400)
        
        api_note = QLabel("Required for ChatGPT integration (coming soon).\n"
                         "Leave blank to use company-provided key.")
        api_note.setStyleSheet("color: #888; font-size: 12px; margin-top: 4px;")
        
        # Show/Hide API key button
        api_btn_layout = QHBoxLayout()
        self.show_api_btn = QPushButton("Show")
        self.show_api_btn.setMaximumWidth(80)
        self.show_api_btn.setMinimumHeight(34)
        self.show_api_btn.clicked.connect(self._toggle_api_visibility)
        
        api_btn_layout.addWidget(self.api_key_input)
        api_btn_layout.addWidget(self.show_api_btn)
        api_btn_layout.addStretch()
        
        api_section.addWidget(api_label)
        api_section.addLayout(api_btn_layout)
        api_section.addWidget(api_note)
        
        layout.addLayout(api_section)
        
        # ===== Save Button =====
        save_layout = QHBoxLayout()
        save_layout.setSpacing(12)
        
        self.save_general_btn = QPushButton("Save Settings")
        self.save_general_btn.setProperty("class", "primary")
        self.save_general_btn.setMinimumWidth(150)
        self.save_general_btn.setMinimumHeight(34)
        self.save_general_btn.clicked.connect(self._save_general_settings)
        
        self.reset_btn = QPushButton("Reset to Defaults")
        self.reset_btn.setMinimumHeight(34)
        self.reset_btn.clicked.connect(self._reset_defaults)
        
        save_layout.addWidget(self.save_general_btn)
        save_layout.addWidget(self.reset_btn)
        save_layout.addStretch()
        
        layout.addLayout(save_layout)
        
        # Add stretch at bottom
        layout.addStretch()
        
        scroll.setWidget(content)
        
        # Main layout for tab
        tab_layout = QVBoxLayout(widget)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)
        
        # Load current settings
        self._load_general_settings()
        
        return widget
    
    # ========== PLUGIN TAB ==========
    
    def _create_plugin_tab(self) -> QWidget:
        """Create App Settings (Plugin) tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(24)
        
        # ===== Page Title =====
        title = QLabel("App Settings")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)
        
        # ===== Plugin Selector =====
        selector_layout = QHBoxLayout()
        selector_label = QLabel("Select App:")
        selector_label.setStyleSheet("font-weight: 600; font-size: 14px;")
        
        self.plugin_combo = QComboBox()
        self.plugin_combo.setMinimumHeight(34)
        self.plugin_combo.setMinimumWidth(300)
        self.plugin_combo.currentTextChanged.connect(self._on_plugin_selected)
        
        theme = get_current_palette(self.settings.get_theme())
        # ✅ Select icon folder based on theme
        theme_name = self.settings.get_theme()
        icon_folder = "light" if theme_name in ["dark", "blue"] else "dark"
        icons_dir = Path(__file__).resolve().parents[3] / "assets" / "icons" / icon_folder
        src_arrow = icons_dir / "chevron-down.svg"
        arrow_path = make_tinted_svg_copy(src_arrow, theme.text)
        
        self.plugin_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {theme.surface};
                color: {theme.text};
                border: 1px solid {theme.border};
                border-radius: 8px;
                padding: 6px 10px;
                padding-right: 28px;
            }}
            QComboBox:hover {{
                border-color: {theme.border_strong};
            }}
            QComboBox::drop-down {{
                width: 24px;
                border: none;
                background: transparent;
                subcontrol-origin: padding;
                subcontrol-position: center right;
            }}
            QComboBox::down-arrow {{
                image: url("{arrow_path}");
                width: 12px;
                height: 12px;
                background: transparent;
                border: none;
                margin-right: 6px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {theme.surface};
                color: {theme.text};
                border: 1px solid {theme.border};
                border-radius: 4px;
                selection-background-color: {theme.tile_selected};
                outline: none;
            }}
        """)
        
        selector_layout.addWidget(selector_label)
        selector_layout.addWidget(self.plugin_combo)
        selector_layout.addStretch()
        
        layout.addLayout(selector_layout)
        
        # ===== Divider =====
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("background: #2A2A2A; max-height: 1px;")
        layout.addWidget(divider)
        
        # ===== Plugin Settings Container (Scrollable) =====
        self.plugin_scroll = QScrollArea()
        self.plugin_scroll.setWidgetResizable(True)
        self.plugin_scroll.setStyleSheet("QScrollArea { border: none; }")
        
        # Create container for plugin settings widget
        self.plugin_container = QWidget()
        self.plugin_layout = QVBoxLayout(self.plugin_container)
        self.plugin_layout.setContentsMargins(0, 10, 0, 10)
        
        # Placeholder message
        self.no_plugin_label = QLabel("Select an app from the dropdown above to view its settings.")
        self.no_plugin_label.setStyleSheet("color: #888; font-size: 14px; padding: 40px;")
        self.no_plugin_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plugin_layout.addWidget(self.no_plugin_label)
        
        self.plugin_scroll.setWidget(self.plugin_container)
        layout.addWidget(self.plugin_scroll, 1)
        
        # ===== Save Button =====
        save_plugin_layout = QHBoxLayout()
        self.save_plugin_btn = QPushButton("Save App Settings")
        self.save_plugin_btn.setProperty("class", "primary")
        self.save_plugin_btn.setMinimumWidth(150)
        self.save_plugin_btn.setMinimumHeight(34)
        self.save_plugin_btn.clicked.connect(self._save_plugin_settings)
        self.save_plugin_btn.setEnabled(False)
        
        save_plugin_layout.addWidget(self.save_plugin_btn)
        save_plugin_layout.addStretch()
        
        layout.addLayout(save_plugin_layout)
        
        # Load plugins into dropdown
        self._load_plugin_list()
        
        return widget
    
    # ========== PERSONALIZATION TAB ==========
    
    def _create_personalization_tab(self) -> QWidget:
        """Create Personalization tab."""
        widget = QWidget()
        
        # Create scroll area for content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(24)
        
        # ===== Page Title =====
        title = QLabel("Personalization")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)
        
        # ===== User Profile Section =====
        profile_section = self._create_section("User Profile")
        
        # Name
        name_label = QLabel("Display Name:")
        name_label.setStyleSheet("font-weight: 600; margin-top: 8px;")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter your name")
        self.name_input.setMinimumHeight(34)
        self.name_input.setMaximumWidth(400)
        
        profile_section.addWidget(name_label)
        profile_section.addWidget(self.name_input)
        
        # Email
        email_label = QLabel("Email:")
        email_label.setStyleSheet("font-weight: 600; margin-top: 16px;")
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("your.email@company.com")
        self.email_input.setMinimumHeight(34)
        self.email_input.setMaximumWidth(400)
        
        profile_section.addWidget(email_label)
        profile_section.addWidget(self.email_input)
        
        # Job Title
        title_label = QLabel("Job Title:")
        title_label.setStyleSheet("font-weight: 600; margin-top: 16px;")
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("e.g., Automation Engineer")
        self.title_input.setMinimumHeight(34)
        self.title_input.setMaximumWidth(400)
        
        profile_section.addWidget(title_label)
        profile_section.addWidget(self.title_input)
        
        layout.addLayout(profile_section)
        
        # ===== Appearance Preferences Section =====
        appearance_section = self._create_section("Appearance Preferences")
        
        appearance_note = QLabel("Additional appearance options coming soon:\n"
                                "• Custom accent colors\n"
                                "• Font size preferences\n"
                                "• Sidebar width\n"
                                "• Tile sizes")
        appearance_note.setStyleSheet("color: #888; font-size: 13px; margin-top: 8px;")
        appearance_section.addWidget(appearance_note)
        
        layout.addLayout(appearance_section)
        
        # ===== Save Button =====
        save_layout = QHBoxLayout()
        self.save_personalization_btn = QPushButton("Save Profile")
        self.save_personalization_btn.setProperty("class", "primary")
        self.save_personalization_btn.setMinimumWidth(150)
        self.save_personalization_btn.setMinimumHeight(34)
        self.save_personalization_btn.clicked.connect(self._save_personalization_settings)
        
        save_layout.addWidget(self.save_personalization_btn)
        save_layout.addStretch()
        
        layout.addLayout(save_layout)
        
        # Add stretch at bottom
        layout.addStretch()
        
        scroll.setWidget(content)
        
        # Main layout for tab
        tab_layout = QVBoxLayout(widget)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)
        
        # Load current settings
        self._load_personalization_settings()
        
        return widget
    
    # ========== HELPER METHODS ==========
    
    def _create_section(self, title: str) -> QVBoxLayout:
        """Create a styled section with title and frame."""
        section = QVBoxLayout()
        section.setSpacing(12)
        
        # Section title
        section_title = QLabel(title)
        section_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        section.addWidget(section_title)
        
        # Divider line
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("background: #2A2A2A; max-height: 1px;")
        section.addWidget(divider)
        
        return section
    
    # ========== GENERAL TAB METHODS ==========
    
    def _load_general_settings(self):
        """Load general settings into UI."""
        # Theme
        current_theme = self.settings.get_theme()
        index = self.theme_combo.findText(current_theme.capitalize())
        if index >= 0:
            self.theme_combo.setCurrentIndex(index)
        
        # Console height
        self.console_height_spin.setValue(self.settings.get_console_height())
        
        # API key
        api_key = self.settings.get_api_key()
        self.api_key_input.setText(api_key)
    
    def _on_theme_changed(self, theme_name: str):
        """Handle theme selection change."""
        pass  # Actual save happens on Save button click
    
    def _toggle_api_visibility(self):
        """Toggle API key visibility."""
        if self.api_key_input.echoMode() == QLineEdit.EchoMode.Password:
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.show_api_btn.setText("Hide")
        else:
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.show_api_btn.setText("Show")
    
    def _save_general_settings(self):
        """Save general settings."""
        # Save theme
        theme_name = self.theme_combo.currentText().lower()
        old_theme = self.settings.get_theme()
        theme_changed = (theme_name != old_theme)
        self.settings.set_theme(theme_name)
        
        # Save console height
        console_height = self.console_height_spin.value()
        self.settings.set_console_height(console_height)
        
        # Save API key
        api_key = self.api_key_input.text().strip()
        self.settings.set_api_key(api_key)
        
        # Show confirmation
        if theme_changed:
            QMessageBox.information(
                self,
                "Settings Saved",
                "Settings saved successfully!\n\n"
                "Please restart TechDeck for the theme change to take effect."
            )
            self.theme_changed.emit(theme_name)
        else:
            QMessageBox.information(
                self,
                "Settings Saved",
                "Settings saved successfully!"
            )
    
    def _reset_defaults(self):
        """Reset all general settings to defaults."""
        reply = QMessageBox.question(
            self,
            "Reset to Defaults",
            "Reset all general settings to default values?\n\n"
            "This will:\n"
            "• Set theme to Dark\n"
            "• Reset console height to 250px\n"
            "• Clear API key\n\n"
            "Your profiles and user data will not be affected.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Reset to defaults
            self.settings.set_theme("dark")
            self.settings.set_console_height(250)
            self.settings.set_api_key("")
            
            # Reload UI
            self._load_general_settings()
            
            QMessageBox.information(
                self,
                "Settings Reset",
                "Settings have been reset to defaults.\n\n"
                "Please restart TechDeck for the theme change to take effect."
            )
    
    # ========== PLUGIN TAB METHODS ==========
    
    def _load_plugin_list(self):
        """Load plugins into dropdown."""
        self.plugin_combo.clear()
        
        # Get all plugins
        plugins = self.plugin_loader.get_all_plugins()
        
        if not plugins:
            self.plugin_combo.addItem("No plugins installed")
            self.plugin_combo.setEnabled(False)
            return
        
        # Add plugin names
        for plugin in sorted(plugins, key=lambda p: p.name):
            self.plugin_combo.addItem(plugin.name, plugin.id)
        
        self.plugin_combo.setEnabled(True)
    
    def _on_plugin_selected(self, plugin_name: str):
        """Handle plugin selection from dropdown."""
        if not plugin_name or plugin_name == "No plugins installed":
            return
        
        # Get plugin ID from combo box data
        plugin_id = self.plugin_combo.currentData()
        if not plugin_id:
            return
        
        # Get plugin object
        plugin = self.plugin_loader.get_plugin(plugin_id)
        if not plugin:
            return
        
        # Load plugin.json to get settings schema
        plugin_json_path = plugin.path / "plugin.json"
        if not plugin_json_path.exists():
            self._show_no_settings("Plugin configuration file not found.")
            return
        
        try:
            import json
            with open(plugin_json_path, 'r', encoding='utf-8') as f:
                plugin_data = json.load(f)
        except Exception as e:
            self._show_no_settings(f"Error reading plugin configuration: {e}")
            return
        
        # Check if plugin has settings schema
        if 'settings' not in plugin_data or not plugin_data['settings'].get('fields'):
            self._show_no_settings("This app has no configurable settings.")
            return
        
        # Get current saved values
        current_values = self.settings.get_plugin_settings(plugin_id)
        
        # Clear old widget
        if self.current_plugin_widget:
            self.plugin_layout.removeWidget(self.current_plugin_widget)
            self.current_plugin_widget.deleteLater()
            self.current_plugin_widget = None
        
        # Hide placeholder
        self.no_plugin_label.hide()
        
        # Create new plugin settings widget
        self.current_plugin_widget = PluginSettingsWidget(
            plugin_id=plugin_id,
            schema=plugin_data['settings'],
            current_values=current_values
        )
        
        self.plugin_layout.addWidget(self.current_plugin_widget)
        self.save_plugin_btn.setEnabled(True)
    
    def _show_no_settings(self, message: str):
        """Show message when plugin has no settings."""
        # Clear old widget
        if self.current_plugin_widget:
            self.plugin_layout.removeWidget(self.current_plugin_widget)
            self.current_plugin_widget.deleteLater()
            self.current_plugin_widget = None
        
        # Show message
        self.no_plugin_label.setText(message)
        self.no_plugin_label.show()
        self.save_plugin_btn.setEnabled(False)
    
    def _save_plugin_settings(self):
        """Save current plugin settings."""
        if not self.current_plugin_widget:
            return
        
        # Get values from widget
        values = self.current_plugin_widget.get_values()
        
        # Validate
        if not self.current_plugin_widget.validate():
            QMessageBox.warning(
                self,
                "Validation Error",
                "Please fix the validation errors before saving."
            )
            return
        
        # Save to settings
        plugin_id = self.current_plugin_widget.plugin_id
        self.settings.set_plugin_settings(plugin_id, values)
        
        QMessageBox.information(
            self,
            "Settings Saved",
            f"Settings for '{self.plugin_combo.currentText()}' have been saved."
        )
    
    # ========== PERSONALIZATION TAB METHODS ==========
    
    def _load_personalization_settings(self):
        """Load personalization settings into UI."""
        user_data = self.settings.get_user_data()
        
        self.name_input.setText(user_data.get('name', ''))
        self.email_input.setText(user_data.get('email', ''))
        self.title_input.setText(user_data.get('title', ''))
    
    def _save_personalization_settings(self):
        """Save personalization settings."""
        name = self.name_input.text().strip()
        email = self.email_input.text().strip()
        title = self.title_input.text().strip()
        
        # Update settings
        self.settings.update_user_data(
            name=name,
            email=email,
            title=title
        )
        
        QMessageBox.information(
            self,
            "Profile Saved",
            "Your profile information has been saved."
        )
    
    # ========== PUBLIC METHODS ==========
    
    def refresh(self):
        """Refresh the settings page data."""
        self._load_general_settings()
        self._load_plugin_list()
        self._load_personalization_settings()