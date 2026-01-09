"""
TechDeck Settings Page - Tabbed Interface
Three tabs: General, App Settings (Plugins), Personalization
PHASE 2 FIX: Removed console height setting - users drag console to preferred height
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
        # ÃƒÂ¢Ã…â€œÃ¢â‚¬Â¦ FIXED: Select icon folder based on theme
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
        
        api_button_layout = QHBoxLayout()
        self.show_api_btn = QPushButton("Show")
        self.show_api_btn.setMinimumHeight(34)
        self.show_api_btn.setMaximumWidth(80)
        self.show_api_btn.clicked.connect(self._toggle_api_visibility)
        
        api_button_layout.addWidget(self.api_key_input)
        api_button_layout.addWidget(self.show_api_btn)
        api_button_layout.addStretch()
        
        api_section.addWidget(api_label)
        api_section.addLayout(api_button_layout)
        api_section.addWidget(api_note)
        
        layout.addLayout(api_section)
        
        # ===== About TechDeck Section =====
        from techdeck.core.constants import APP_VERSION, APP_RELEASE_NAME
        
        about_section = self._create_section("About TechDeck")
        
        # Version info
        version_label = QLabel(f"Version {APP_VERSION} - {APP_RELEASE_NAME}")
        version_label.setStyleSheet("font-weight: 600; margin-top: 8px; font-size: 14px;")
        
        # Check for updates button
        check_updates_btn = QPushButton("Check for Updates")
        check_updates_btn.setMinimumHeight(36)
        check_updates_btn.setMaximumWidth(180)
        check_updates_btn.clicked.connect(self._check_for_updates)
        
        about_section.addWidget(version_label)
        about_section.addWidget(check_updates_btn)
        
        layout.addLayout(about_section)
        
        # ===== Action Buttons =====
        layout.addStretch()
        
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)
        
        save_btn = QPushButton("Save Settings")
        save_btn.setMinimumHeight(36)
        save_btn.setMaximumWidth(150)
        save_btn.clicked.connect(self._save_general_settings)
        
        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.setMinimumHeight(36)
        reset_btn.setMaximumWidth(150)
        reset_btn.clicked.connect(self._reset_defaults)
        
        button_layout.addWidget(save_btn)
        button_layout.addWidget(reset_btn)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        # Load current settings
        self._load_general_settings()
        
        scroll.setWidget(content)
        
        # Wrap in container
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(scroll)
        
        return container
    
    # ========== PLUGIN TAB ==========
    
    def _create_plugin_tab(self) -> QWidget:
        """Create App Settings (Plugin Configuration) tab."""
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
        title = QLabel("App Settings")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)
        
        subtitle = QLabel("Configure settings for each installed app")
        subtitle.setStyleSheet("color: #888; font-size: 14px; margin-bottom: 12px;")
        layout.addWidget(subtitle)
        
        # ===== Plugin Selection =====
        selection_section = self._create_section("Select App")
        
        select_label = QLabel("Choose an app to configure:")
        select_label.setStyleSheet("font-weight: 600; margin-top: 8px;")
        
        self.plugin_combo = QComboBox()
        self.plugin_combo.setMinimumHeight(34)
        self.plugin_combo.setMaximumWidth(300)
        self.plugin_combo.currentTextChanged.connect(self._on_plugin_selected)
        
        selection_section.addWidget(select_label)
        selection_section.addWidget(self.plugin_combo)
        layout.addLayout(selection_section)
        
        # ===== Plugin Settings Area =====
        settings_section = self._create_section("Configuration")
        
        # Container for plugin-specific settings widget
        self.plugin_layout = QVBoxLayout()
        self.plugin_layout.setSpacing(12)
        
        # Placeholder when no plugin selected
        self.no_plugin_label = QLabel("Select an app to view its settings.")
        self.no_plugin_label.setStyleSheet("color: #888; font-style: italic; padding: 20px;")
        self.no_plugin_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plugin_layout.addWidget(self.no_plugin_label)
        
        settings_section.addLayout(self.plugin_layout)
        layout.addLayout(settings_section)
        
        # ===== Action Buttons =====
        layout.addStretch()
        
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)
        
        self.save_plugin_btn = QPushButton("Save")
        self.save_plugin_btn.setMinimumHeight(36)
        self.save_plugin_btn.setMaximumWidth(150)
        self.save_plugin_btn.setEnabled(False)
        self.save_plugin_btn.clicked.connect(self._save_plugin_settings)
        
        button_layout.addWidget(self.save_plugin_btn)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        # Load plugins
        self._load_plugin_list()
        
        scroll.setWidget(content)
        
        # Wrap in container
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(scroll)
        
        return container
    
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
        
        subtitle = QLabel("Customize your profile information")
        subtitle.setStyleSheet("color: #888; font-size: 14px; margin-bottom: 12px;")
        layout.addWidget(subtitle)
        
        # ===== Profile Section =====
        profile_section = self._create_section("Profile Information")
        
        # Name
        name_label = QLabel("Full Name:")
        name_label.setStyleSheet("font-weight: 600; margin-top: 8px;")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("John Smith")
        self.name_input.setMinimumHeight(34)
        self.name_input.setMaximumWidth(400)
        
        profile_section.addWidget(name_label)
        profile_section.addWidget(self.name_input)
        
        # Email
        email_label = QLabel("Email:")
        email_label.setStyleSheet("font-weight: 600; margin-top: 12px;")
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("john.smith@company.com")
        self.email_input.setMinimumHeight(34)
        self.email_input.setMaximumWidth(400)
        
        profile_section.addWidget(email_label)
        profile_section.addWidget(self.email_input)
        
        # Title
        title_label = QLabel("Job Title:")
        title_label.setStyleSheet("font-weight: 600; margin-top: 12px;")
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Production Manager")
        self.title_input.setMinimumHeight(34)
        self.title_input.setMaximumWidth(400)
        
        profile_section.addWidget(title_label)
        profile_section.addWidget(self.title_input)
        
        layout.addLayout(profile_section)
        
        # ===== Action Buttons =====
        layout.addStretch()
        
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)
        
        save_btn = QPushButton("Save Profile")
        save_btn.setMinimumHeight(36)
        save_btn.setMaximumWidth(150)
        save_btn.clicked.connect(self._save_personalization_settings)
        
        button_layout.addWidget(save_btn)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        # Load current settings
        self._load_personalization_settings()
        
        scroll.setWidget(content)
        
        # Wrap in container
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(scroll)
        
        return container
    
    # ========== HELPER METHODS ==========
    
    def _create_section(self, title: str) -> QVBoxLayout:
        """Create a settings section with title and divider."""
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
        
        # API key
        api_key = self.settings.get_api_key()
        self.api_key_input.setText(api_key)
    
    def _on_theme_changed(self, theme_name: str):
        """Handle theme selection change."""
        # Just update combo selection, actual save happens on Save button
        pass
    
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
        
        # Save API key
        api_key = self.api_key_input.text().strip()
        self.settings.set_api_key(api_key)
        
        # Show confirmation
        if theme_changed:
            # Theme will be applied immediately by shell's handler
            self.theme_changed.emit(theme_name)
            # Don't show message here - shell will show it after applying
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
            "ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¢ Set theme to Dark\n"
            "ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¢ Reset console height to 250px\n"
            "ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¢ Clear API key\n\n"
            "Your profiles and user data will not be affected.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Reset to defaults
            self.settings.set_theme("dark")
            self.settings.set_api_key("")
            
            # Reload UI
            self._load_general_settings()
            
            # Emit theme change to apply immediately
            self.theme_changed.emit("dark")
    
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
        
        # ÃƒÂ¢Ã…â€œÃ¢â‚¬Â¦ FIXED: Clear old widgets FIRST (before adding new ones)
        if self.current_plugin_widget:
            self.plugin_layout.removeWidget(self.current_plugin_widget)
            self.current_plugin_widget.deleteLater()
            self.current_plugin_widget = None
        
        # Clear old version label if it exists
        old_version_label = self.findChild(QLabel, "plugin_version_label")
        if old_version_label:
            self.plugin_layout.removeWidget(old_version_label)
            old_version_label.deleteLater()
        
        # Hide placeholder
        self.no_plugin_label.hide()
        
        # ÃƒÂ¢Ã…â€œÃ¢â‚¬Â¦ NOW add the new version label
        plugin_version = plugin_data.get('version', '1.0.0')
        version_label = QLabel(f"Version: {plugin_version}")
        version_label.setStyleSheet("font-size: 13px; color: #888; margin-bottom: 16px;")
        version_label.setObjectName("plugin_version_label")
        self.plugin_layout.addWidget(version_label)
        
        # Check if plugin has settings schema
        if 'settings' not in plugin_data or not plugin_data['settings'].get('fields'):
            self._show_no_settings("This app has no configurable settings.")
            return
        
        # Get current saved values
        current_values = self.settings.get_plugin_settings(plugin_id)
        
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
        
        # ÃƒÂ¢Ã…â€œÃ¢â‚¬Â¦ ADDED: Clear version label if it exists
        version_label = self.findChild(QLabel, "plugin_version_label")
        if version_label:
            self.plugin_layout.removeWidget(version_label)
            version_label.deleteLater()
        
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
        
        # Validate using the correct method name
        if not self.current_plugin_widget.validate_all():
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
    
    def _check_for_updates(self):
        """Check for updates manually."""
        # Get reference to main window
        main_window = self.window()
        if hasattr(main_window, 'check_for_updates_manual'):
            main_window.check_for_updates_manual()
    
    def refresh(self):
        """Refresh the settings page data."""
        self._load_general_settings()
        self._load_plugin_list()
        self._load_personalization_settings()
