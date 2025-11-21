"""
TechDeck Settings Page
Application settings and preferences.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QComboBox, QPushButton, QFrame, QScrollArea, 
    QLineEdit, QMessageBox, QSpinBox
)
from PySide6.QtCore import Signal, Qt

from techdeck.core.settings import SettingsManager
from techdeck.ui.theme import get_theme_names, get_current_palette
from techdeck.ui.utils import make_tinted_svg_copy
from techdeck.core.constants import APP_NAME, APP_VERSION, APP_RELEASE_NAME
from pathlib import Path


class SettingsPage(QWidget):
    """
    Settings page - app configuration and preferences.
    
    Signals:
        theme_changed(str): Emitted when theme is changed (requires restart)
    """
    
    theme_changed = Signal(str)
    
    def __init__(self, settings: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        
        # Create scroll area for content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(24)
        
        # ===== Page Title =====
        title = QLabel("Settings")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)
        
        # ===== Version Info =====
        version_info = QLabel(f"{APP_NAME} v{APP_VERSION} - {APP_RELEASE_NAME}")
        version_info.setStyleSheet("color: #888; font-size: 13px; margin-top: 4px; margin-bottom: 8px;")
        layout.addWidget(version_info)
        
        # ===== Appearance Section =====
        appearance_section = self._create_section("Appearance")
        
        # Theme selector
        theme_label = QLabel("Theme:")
        theme_label.setStyleSheet("font-weight: 600; margin-top: 8px;")
        
        theme_layout = QHBoxLayout()
        self.theme_combo = QComboBox()
        self.theme_combo.addItems([t.capitalize() for t in get_theme_names()])
        self.theme_combo.setMinimumHeight(34)
        self.theme_combo.setMaximumWidth(200)

        theme = get_current_palette(self.settings.get_theme())

        icons_dir   = Path(__file__).resolve().parents[3] / "assets" / "icons"
        src_arrow   = icons_dir / "chevron-down.svg"
        arrow_path  = make_tinted_svg_copy(src_arrow, theme.text)  # writes a small themed svg, returns file path

        self.theme_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {theme.surface};
                color: {theme.text};
                border: 1px solid {theme.border};
                border-radius: 8px;
                padding: 6px 10px;
                padding-right: 28px;  /* room for arrow */
            }}
            QComboBox:hover {{
                border-color: {theme.border_strong};
            }}
            QComboBox::drop-down {{
                width: 24px;
                border: none;
                background: transparent;      /* remove faint white rectangle */
                subcontrol-origin: padding;
                subcontrol-position: center right;
            }}
            QComboBox::down-arrow {{
                image: url("{arrow_path}");    /* file path (reliable on Windows) */
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
        
        appearance_section.addWidget(theme_label)
        appearance_section.addLayout(theme_layout)
        
        theme_note = QLabel("Note: Changing theme requires restarting TechDeck.")
        theme_note.setStyleSheet("color: #888; font-size: 12px; margin-top: 4px;")
        appearance_section.addWidget(theme_note)
        
        layout.addLayout(appearance_section)
        
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
        
        self.save_btn = QPushButton("Save Settings")
        self.save_btn.setProperty("class", "primary")
        self.save_btn.setMinimumWidth(150)
        self.save_btn.setMinimumHeight(34)
        self.save_btn.clicked.connect(self._save_settings)
        
        self.reset_btn = QPushButton("Reset to Defaults")
        self.reset_btn.setMinimumHeight(34)
        self.reset_btn.clicked.connect(self._reset_defaults)
        
        save_layout.addWidget(self.save_btn)
        save_layout.addWidget(self.reset_btn)
        save_layout.addStretch()
        
        layout.addLayout(save_layout)
        
        # Add stretch at bottom
        layout.addStretch()
        
        scroll.setWidget(content)
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)
        
        # Load current settings
        self._load_settings()
    
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
    
    def _load_settings(self):
        """Load current settings into UI."""
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
    
    def _save_settings(self):
        """Save all settings."""
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
        """Reset all settings to defaults."""
        reply = QMessageBox.question(
            self,
            "Reset to Defaults",
            "Reset all settings to default values?\n\n"
            "This will:\n"
            "â€¢ Set theme to Dark\n"
            "â€¢ Reset console height to 250px\n"
            "â€¢ Clear API key\n\n"
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
            self._load_settings()
            
            QMessageBox.information(
                self,
                "Settings Reset",
                "Settings have been reset to defaults.\n\n"
                "Please restart TechDeck for the theme change to take effect."
            )
    
    def refresh(self):
        """Refresh settings from store."""
        self._load_settings()