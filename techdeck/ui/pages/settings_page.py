"""
TechDeck Settings Page - Tabbed Interface
Three tabs: General, App Settings (Plugins), Personalization
Personalization tab hosts theme selection, theme builder, and Rogue Mode management.
"""

import json
import shutil
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QFrame, QScrollArea,
    QLineEdit, QMessageBox, QTabWidget,
    QCheckBox, QSlider, QListWidget, QListWidgetItem,
    QFileDialog, QInputDialog, QSizePolicy,
)
from PySide6.QtCore import Signal, Qt

from techdeck.core.settings import SettingsManager
from techdeck.core.plugin_loader import PluginLoader
from techdeck.ui.theme import get_theme_names, get_current_palette, THEMES, is_builtin_theme, delete_custom_theme
from techdeck.ui.utils import make_tinted_svg_copy
from techdeck.ui.widgets.plugin_settings_widget import PluginSettingsWidget


class SettingsPage(QWidget):
    """
    Settings page with three horizontal tabs:
    1. General     – Sound effects + About
    2. App Settings – Per-plugin configuration
    3. Personalization – Profile, Theme (+ builder), Rogue Mode
    """

    theme_changed = Signal(str)

    def __init__(self, settings: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.plugin_loader = PluginLoader()
        self.plugin_loader.discover_plugins()
        self.current_plugin_widget = None
        self._rogue_player = None  # keep alive

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

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

        self.tabs.addTab(self._create_general_tab(),         "General")
        self.tabs.addTab(self._create_plugin_tab(),          "App Settings")
        self.tabs.addTab(self._create_personalization_tab(), "Personalization")

        layout.addWidget(self.tabs)

    # ──────────────────────────────────────────────────────────────────────
    # GENERAL TAB
    # ──────────────────────────────────────────────────────────────────────

    def _create_general_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(24)

        title = QLabel("General Settings")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)

        # ── Sound Effects ──
        audio_section = self._create_section("Sound Effects")

        self.audio_enabled_check = QCheckBox("Enable sound effects")
        self.audio_enabled_check.setStyleSheet("font-weight: 600; margin-top: 8px;")
        self.audio_enabled_check.toggled.connect(self._on_audio_enabled_toggled)

        volume_row = QHBoxLayout()
        volume_row.setSpacing(12)
        volume_label = QLabel("Volume:")
        volume_label.setStyleSheet("font-weight: 600;")
        volume_label.setFixedWidth(60)
        self.audio_volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.audio_volume_slider.setRange(0, 100)
        self.audio_volume_slider.setMaximumWidth(200)
        self.audio_volume_slider.setMinimumHeight(24)
        self.audio_volume_pct = QLabel("80%")
        self.audio_volume_pct.setFixedWidth(36)
        self.audio_volume_slider.valueChanged.connect(
            lambda v: self.audio_volume_pct.setText(f"{v}%")
        )
        volume_row.addWidget(volume_label)
        volume_row.addWidget(self.audio_volume_slider)
        volume_row.addWidget(self.audio_volume_pct)
        volume_row.addStretch()

        audio_section.addWidget(self.audio_enabled_check)
        audio_section.addLayout(volume_row)
        layout.addLayout(audio_section)

        # ── About ──
        from techdeck.core.constants import APP_VERSION, APP_RELEASE_NAME
        about_section = self._create_section("About TechDeck")
        version_label = QLabel(f"Version {APP_VERSION} — {APP_RELEASE_NAME}")
        version_label.setStyleSheet("font-weight: 600; margin-top: 8px; font-size: 14px;")
        check_updates_btn = QPushButton("Check for Updates")
        check_updates_btn.setMinimumHeight(36)
        check_updates_btn.setMaximumWidth(180)
        check_updates_btn.clicked.connect(self._check_for_updates)
        about_section.addWidget(version_label)
        about_section.addWidget(check_updates_btn)
        layout.addLayout(about_section)

        layout.addStretch()

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save Settings")
        save_btn.setMinimumHeight(36)
        save_btn.setMaximumWidth(150)
        save_btn.clicked.connect(self._save_general_settings)
        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.setMinimumHeight(36)
        reset_btn.setMaximumWidth(150)
        reset_btn.clicked.connect(self._reset_defaults)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._load_general_settings()

        scroll.setWidget(content)
        container = QWidget()
        QVBoxLayout(container).addWidget(scroll)
        container.layout().setContentsMargins(0, 0, 0, 0)
        return container

    # ──────────────────────────────────────────────────────────────────────
    # PLUGIN TAB (unchanged logic, just reformatted)
    # ──────────────────────────────────────────────────────────────────────

    def _create_plugin_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(24)

        title = QLabel("App Settings")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)
        sub = QLabel("Configure settings for each installed app")
        sub.setStyleSheet("color: #888; font-size: 14px; margin-bottom: 12px;")
        layout.addWidget(sub)

        selection_section = self._create_section("Select App")
        select_label = QLabel("Choose an app to configure:")
        select_label.setStyleSheet("font-weight: 600; margin-top: 8px;")

        theme = get_current_palette(self.settings.get_theme())
        theme_name = self.settings.get_theme()
        icon_folder = "light" if theme_name in ["dark", "blue", "cyberpunk", "matrix"] else "dark"
        icons_dir = Path(__file__).resolve().parents[3] / "assets" / "icons" / icon_folder
        src_arrow = icons_dir / "chevron-down.svg"
        arrow_path = make_tinted_svg_copy(src_arrow, theme.text)

        self.plugin_combo = QComboBox()
        self.plugin_combo.setMinimumHeight(34)
        self.plugin_combo.setMaximumWidth(300)
        self.plugin_combo.setStyleSheet(self._combo_style(theme, arrow_path))
        self.plugin_combo.currentTextChanged.connect(self._on_plugin_selected)

        selection_section.addWidget(select_label)
        selection_section.addWidget(self.plugin_combo)
        layout.addLayout(selection_section)

        settings_section = self._create_section("Configuration")
        self.plugin_layout = QVBoxLayout()
        self.plugin_layout.setSpacing(12)
        self.no_plugin_label = QLabel("Select an app to view its settings.")
        self.no_plugin_label.setStyleSheet("color: #888; font-style: italic; padding: 20px;")
        self.no_plugin_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plugin_layout.addWidget(self.no_plugin_label)
        settings_section.addLayout(self.plugin_layout)
        layout.addLayout(settings_section)

        layout.addStretch()

        btn_row = QHBoxLayout()
        self.save_plugin_btn = QPushButton("Save App Settings")
        self.save_plugin_btn.setMinimumHeight(36)
        self.save_plugin_btn.setMaximumWidth(150)
        self.save_plugin_btn.setEnabled(False)
        self.save_plugin_btn.clicked.connect(self._save_plugin_settings)
        btn_row.addWidget(self.save_plugin_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._load_plugin_list()

        scroll.setWidget(content)
        container = QWidget()
        QVBoxLayout(container).addWidget(scroll)
        container.layout().setContentsMargins(0, 0, 0, 0)
        return container

    # ──────────────────────────────────────────────────────────────────────
    # PERSONALIZATION TAB
    # ──────────────────────────────────────────────────────────────────────

    def _create_personalization_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(28)

        title = QLabel("Personalization")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)

        # Compute combo arrow style once; reused for theme_combo and rm_combo
        _p_theme = get_current_palette(self.settings.get_theme())
        _p_theme_name = self.settings.get_theme()
        _p_icon_folder = "light" if _p_theme_name in ["dark", "blue", "cyberpunk", "matrix"] else "dark"
        _p_icons_dir = Path(__file__).resolve().parents[3] / "assets" / "icons" / _p_icon_folder
        _p_arrow_path = make_tinted_svg_copy(_p_icons_dir / "chevron-down.svg", _p_theme.text)

        # ── Theme ──
        theme_section = self._create_section("Theme")

        theme_lbl = QLabel("Application Theme:")
        theme_lbl.setStyleSheet("font-weight: 600; margin-top: 8px;")
        theme_section.addWidget(theme_lbl)

        theme_row = QHBoxLayout()
        self.theme_combo = QComboBox()
        self.theme_combo.setMinimumHeight(34)
        self.theme_combo.setMinimumWidth(200)
        self.theme_combo.setStyleSheet(self._combo_style(_p_theme, _p_arrow_path))
        self._refresh_theme_combo()

        apply_theme_btn = QPushButton("Apply Theme")
        apply_theme_btn.setMinimumHeight(34)
        apply_theme_btn.setMaximumWidth(120)
        apply_theme_btn.setProperty("class", "primary")
        apply_theme_btn.clicked.connect(self._apply_theme)

        theme_row.addWidget(self.theme_combo)
        theme_row.addWidget(apply_theme_btn)
        theme_row.addStretch()
        theme_section.addLayout(theme_row)

        theme_note = QLabel("Changing theme requires restarting TechDeck.")
        theme_note.setStyleSheet("color: #888; font-size: 12px; margin-top: 4px;")
        theme_section.addWidget(theme_note)

        # Custom theme management
        builder_row = QHBoxLayout()
        build_btn = QPushButton("+ Build Custom Theme")
        build_btn.setMinimumHeight(34)
        build_btn.clicked.connect(self._open_theme_builder)
        builder_row.addWidget(build_btn)
        builder_row.addStretch()
        theme_section.addLayout(builder_row)

        # Custom themes list
        custom_lbl = QLabel("Custom Themes:")
        custom_lbl.setStyleSheet("font-weight: 600; margin-top: 12px;")
        theme_section.addWidget(custom_lbl)

        self._custom_theme_list = QListWidget()
        self._custom_theme_list.setMaximumHeight(110)
        self._custom_theme_list.setMaximumWidth(400)
        theme_section.addWidget(self._custom_theme_list)

        custom_btn_row = QHBoxLayout()
        edit_theme_btn = QPushButton("Edit Selected")
        edit_theme_btn.setMinimumHeight(30)
        edit_theme_btn.clicked.connect(self._edit_custom_theme)
        del_theme_btn = QPushButton("Delete Selected")
        del_theme_btn.setMinimumHeight(30)
        del_theme_btn.clicked.connect(self._delete_custom_theme)
        custom_btn_row.addWidget(edit_theme_btn)
        custom_btn_row.addWidget(del_theme_btn)
        custom_btn_row.addStretch()
        theme_section.addLayout(custom_btn_row)

        layout.addLayout(theme_section)
        self._refresh_custom_theme_list()

        # ── Rogue Mode ──
        rogue_section = self._create_section("Rogue Mode")

        rogue_desc = QLabel(
            "Upload audio files and build focus playlists. "
            "Launch the player with /roguemode in the console."
        )
        rogue_desc.setStyleSheet("color: #888; font-size: 12px;")
        rogue_desc.setWordWrap(True)
        rogue_section.addWidget(rogue_desc)

        # Launch player button
        launch_row = QHBoxLayout()
        launch_btn = QPushButton("Launch Player")
        launch_btn.setMinimumHeight(34)
        launch_btn.setMaximumWidth(140)
        launch_btn.setProperty("class", "primary")
        launch_btn.clicked.connect(self._launch_rogue_player)
        launch_row.addWidget(launch_btn)
        launch_row.addStretch()
        rogue_section.addLayout(launch_row)

        autoplay_row = QHBoxLayout()
        self._rm_autoplay_check = QCheckBox("Autoplay on open")
        autoplay_row.addWidget(self._rm_autoplay_check)
        autoplay_row.addStretch()
        rogue_section.addLayout(autoplay_row)

        # Playlist management
        pl_lbl = QLabel("Playlists:")
        pl_lbl.setStyleSheet("font-weight: 600; margin-top: 12px;")
        rogue_section.addWidget(pl_lbl)

        pl_row = QHBoxLayout()
        self._rm_pl_combo = QComboBox()
        self._rm_pl_combo.setMinimumHeight(30)
        self._rm_pl_combo.setMinimumWidth(200)
        self._rm_pl_combo.setStyleSheet(self._combo_style(_p_theme, _p_arrow_path))
        self._rm_pl_combo.currentIndexChanged.connect(self._on_rm_playlist_selected)

        new_pl_btn = QPushButton("+ New")
        new_pl_btn.setMinimumHeight(30)
        new_pl_btn.setMinimumWidth(72)
        new_pl_btn.clicked.connect(self._rm_new_playlist)

        del_pl_btn = QPushButton("Delete")
        del_pl_btn.setMinimumHeight(30)
        del_pl_btn.clicked.connect(self._rm_delete_playlist)

        pl_row.addWidget(self._rm_pl_combo)
        pl_row.addWidget(new_pl_btn)
        pl_row.addWidget(del_pl_btn)
        pl_row.addStretch()
        rogue_section.addLayout(pl_row)

        # Song list
        songs_lbl = QLabel("Songs in playlist:")
        songs_lbl.setStyleSheet("font-weight: 600; margin-top: 10px;")
        rogue_section.addWidget(songs_lbl)

        self._rm_song_list = QListWidget()
        self._rm_song_list.setMaximumHeight(140)
        self._rm_song_list.setMaximumWidth(500)
        rogue_section.addWidget(self._rm_song_list)

        song_btn_row = QHBoxLayout()
        upload_btn = QPushButton("+ Upload Audio")
        upload_btn.setMinimumHeight(30)
        upload_btn.clicked.connect(self._rm_upload_audio)
        remove_btn = QPushButton("Remove Selected")
        remove_btn.setMinimumHeight(30)
        remove_btn.clicked.connect(self._rm_remove_song)
        song_btn_row.addWidget(upload_btn)
        song_btn_row.addWidget(remove_btn)
        song_btn_row.addStretch()
        rogue_section.addLayout(song_btn_row)

        save_rm_row = QHBoxLayout()
        save_rm_btn = QPushButton("Save Playlist")
        save_rm_btn.setMinimumHeight(34)
        save_rm_btn.setMaximumWidth(160)
        save_rm_btn.clicked.connect(self._save_roguemode_settings)
        save_rm_row.addWidget(save_rm_btn)
        save_rm_row.addStretch()
        rogue_section.addLayout(save_rm_row)

        layout.addLayout(rogue_section)

        layout.addStretch()

        self._load_personalization_settings()
        self._refresh_rm_playlists()

        scroll.setWidget(content)
        container = QWidget()
        QVBoxLayout(container).addWidget(scroll)
        container.layout().setContentsMargins(0, 0, 0, 0)
        return container

    # ──────────────────────────────────────────────────────────────────────
    # GENERAL TAB METHODS
    # ──────────────────────────────────────────────────────────────────────

    def _load_general_settings(self):
        audio = self.settings.get_audio_settings()
        self.audio_enabled_check.setChecked(audio.get("enabled", True))
        self.audio_volume_slider.setValue(audio.get("volume", 80))
        self._on_audio_enabled_toggled(audio.get("enabled", True))

    def _on_audio_enabled_toggled(self, enabled: bool):
        self.audio_volume_slider.setEnabled(enabled)
        self.audio_volume_pct.setEnabled(enabled)

    def _save_general_settings(self):
        audio_enabled = self.audio_enabled_check.isChecked()
        audio_volume = self.audio_volume_slider.value()
        self.settings.set_audio_settings(audio_enabled, audio_volume)
        from techdeck.core.audio_manager import get_audio_manager
        get_audio_manager().configure(enabled=audio_enabled, volume=audio_volume)
        QMessageBox.information(self, "Settings Saved", "Settings saved successfully!")

    def _reset_defaults(self):
        reply = QMessageBox.question(
            self, "Reset to Defaults",
            "Reset sound settings to defaults?\n\nYour profiles and theme will not be affected.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.settings.set_audio_settings(True, 80)
            from techdeck.core.audio_manager import get_audio_manager
            get_audio_manager().configure(enabled=True, volume=80)
            self._load_general_settings()

    # ──────────────────────────────────────────────────────────────────────
    # PLUGIN TAB METHODS
    # ──────────────────────────────────────────────────────────────────────

    def _load_plugin_list(self):
        self.plugin_combo.clear()
        plugins = self.plugin_loader.get_all_plugins()
        if not plugins:
            self.plugin_combo.addItem("No plugins installed")
            self.plugin_combo.setEnabled(False)
            return
        for plugin in sorted(plugins, key=lambda p: p.name):
            self.plugin_combo.addItem(plugin.name, plugin.id)
        self.plugin_combo.setEnabled(True)

    def _on_plugin_selected(self, plugin_name: str):
        if not plugin_name or plugin_name == "No plugins installed":
            return
        plugin_id = self.plugin_combo.currentData()
        if not plugin_id:
            return
        plugin = self.plugin_loader.get_plugin(plugin_id)
        if not plugin:
            return
        plugin_json_path = plugin.path / "plugin.json"
        if not plugin_json_path.exists():
            self._show_no_settings("Plugin configuration file not found.")
            return
        try:
            with open(plugin_json_path, "r", encoding="utf-8") as f:
                plugin_data = json.load(f)
        except Exception as e:
            self._show_no_settings(f"Error reading plugin configuration: {e}")
            return

        if self.current_plugin_widget:
            self.plugin_layout.removeWidget(self.current_plugin_widget)
            self.current_plugin_widget.deleteLater()
            self.current_plugin_widget = None
        old_version_label = self.findChild(QLabel, "plugin_version_label")
        if old_version_label:
            self.plugin_layout.removeWidget(old_version_label)
            old_version_label.deleteLater()

        self.no_plugin_label.hide()
        version_label = QLabel(f"Version: {plugin_data.get('version', '1.0.0')}")
        version_label.setStyleSheet("font-size: 13px; color: #888; margin-bottom: 16px;")
        version_label.setObjectName("plugin_version_label")
        self.plugin_layout.addWidget(version_label)

        if "settings" not in plugin_data or not plugin_data["settings"].get("fields"):
            self._show_no_settings("This app has no configurable settings.")
            return

        current_values = self.settings.get_plugin_settings(plugin_id)
        self.current_plugin_widget = PluginSettingsWidget(
            plugin_id=plugin_id,
            schema=plugin_data["settings"],
            current_values=current_values,
        )
        self.plugin_layout.addWidget(self.current_plugin_widget)
        self.save_plugin_btn.setEnabled(True)

    def _show_no_settings(self, message: str):
        if self.current_plugin_widget:
            self.plugin_layout.removeWidget(self.current_plugin_widget)
            self.current_plugin_widget.deleteLater()
            self.current_plugin_widget = None
        version_label = self.findChild(QLabel, "plugin_version_label")
        if version_label:
            self.plugin_layout.removeWidget(version_label)
            version_label.deleteLater()
        self.no_plugin_label.setText(message)
        self.no_plugin_label.show()
        self.save_plugin_btn.setEnabled(False)

    def _save_plugin_settings(self):
        if not self.current_plugin_widget:
            return
        values = self.current_plugin_widget.get_values()
        if not self.current_plugin_widget.validate_all():
            QMessageBox.warning(self, "Validation Error", "Please fix the validation errors before saving.")
            return
        plugin_id = self.current_plugin_widget.plugin_id
        self.settings.set_plugin_settings(plugin_id, values)
        QMessageBox.information(
            self, "Settings Saved",
            f"Settings for '{self.plugin_combo.currentText()}' have been saved."
        )

    # ──────────────────────────────────────────────────────────────────────
    # PERSONALIZATION TAB METHODS — PROFILE
    # ──────────────────────────────────────────────────────────────────────

    def _load_personalization_settings(self):
        current_theme = self.settings.get_theme()
        idx = self.theme_combo.findData(current_theme)
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)

    # ──────────────────────────────────────────────────────────────────────
    # PERSONALIZATION TAB METHODS — THEME
    # ──────────────────────────────────────────────────────────────────────

    def _refresh_theme_combo(self):
        current = self.settings.get_theme()
        self.theme_combo.clear()
        for name in get_theme_names():
            self.theme_combo.addItem(name.replace("_", " ").title(), name)
        idx = self.theme_combo.findData(current)
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)

    def _apply_theme(self):
        theme_name = self.theme_combo.currentData()
        if not theme_name:
            return
        self.settings.set_theme(theme_name)
        self.theme_changed.emit(theme_name)

    def _open_theme_builder(self, edit_name: str = ""):
        from techdeck.ui.dialogs.theme_builder_dialog import ThemeBuilderDialog
        dlg = ThemeBuilderDialog(self.settings, parent=self, edit_name=edit_name)
        dlg.theme_saved.connect(self._on_custom_theme_saved)
        dlg.exec()

    def _on_custom_theme_saved(self, name: str):
        self._refresh_theme_combo()
        self._refresh_custom_theme_list()
        # Select the newly saved theme in the combo
        idx = self.theme_combo.findData(name)
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)

    def _refresh_custom_theme_list(self):
        self._custom_theme_list.clear()
        for name in get_theme_names():
            if not is_builtin_theme(name):
                item = QListWidgetItem(name.replace("_", " ").title())
                item.setData(Qt.ItemDataRole.UserRole, name)
                self._custom_theme_list.addItem(item)

    def _edit_custom_theme(self):
        item = self._custom_theme_list.currentItem()
        if not item:
            QMessageBox.information(self, "Edit Theme", "Select a custom theme to edit.")
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        self._open_theme_builder(edit_name=name)

    def _delete_custom_theme(self):
        item = self._custom_theme_list.currentItem()
        if not item:
            QMessageBox.information(self, "Delete Theme", "Select a custom theme to delete.")
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self, "Delete Theme",
            f"Delete custom theme '{name}'? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            delete_custom_theme(name, self.settings.get_custom_themes_dir())
            self._refresh_theme_combo()
            self._refresh_custom_theme_list()
            if self.settings.get_theme() == name:
                self.settings.set_theme("dark")

    # ──────────────────────────────────────────────────────────────────────
    # PERSONALIZATION TAB METHODS — ROGUE MODE
    # ──────────────────────────────────────────────────────────────────────

    def _launch_rogue_player(self):
        from techdeck.ui.widgets.rogue_mode_player import RogueModePlayer
        self._rogue_player = RogueModePlayer.get_or_create(self.settings, parent=self)

    def _refresh_rm_playlists(self):
        rm = self.settings.get_roguemode_settings()
        playlists = rm.get("playlists", {})
        current_pl = rm.get("current_playlist", "")
        self._rm_pl_combo.blockSignals(True)
        self._rm_pl_combo.clear()
        for name in playlists:
            self._rm_pl_combo.addItem(name, name)
        self._rm_pl_combo.blockSignals(False)
        idx = self._rm_pl_combo.findData(current_pl)
        self._rm_pl_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._rm_autoplay_check.setChecked(rm.get("autoplay", True))
        self._refresh_rm_songs()

    def _refresh_rm_songs(self):
        self._rm_song_list.clear()
        if self._rm_pl_combo.count() == 0:
            return
        pl_name = self._rm_pl_combo.currentData()
        if not pl_name:
            return
        rm = self.settings.get_roguemode_settings()
        files = rm.get("playlists", {}).get(pl_name, [])
        for fn in files:
            item = QListWidgetItem(Path(fn).stem)
            item.setData(Qt.ItemDataRole.UserRole, fn)
            self._rm_song_list.addItem(item)

    def _on_rm_playlist_selected(self, idx: int):
        if idx < 0:
            return
        name = self._rm_pl_combo.currentData()
        self.settings.update_roguemode_setting("current_playlist", name)
        self._refresh_rm_songs()

    def _rm_new_playlist(self):
        name, ok = QInputDialog.getText(self, "New Playlist", "Playlist name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        rm = self.settings.get_roguemode_settings()
        if name in rm.get("playlists", {}):
            QMessageBox.warning(self, "Rogue Mode", f"Playlist '{name}' already exists.")
            return
        rm.setdefault("playlists", {})[name] = []
        rm["current_playlist"] = name
        self.settings.set_roguemode_settings(rm)
        self._refresh_rm_playlists()
        idx = self._rm_pl_combo.findData(name)
        if idx >= 0:
            self._rm_pl_combo.setCurrentIndex(idx)

    def _rm_delete_playlist(self):
        if self._rm_pl_combo.count() == 0:
            return
        pl_name = self._rm_pl_combo.currentData()
        if not pl_name:
            return
        reply = QMessageBox.question(
            self, "Delete Playlist",
            f"Delete playlist '{pl_name}'? (Audio files will not be deleted.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            rm = self.settings.get_roguemode_settings()
            rm.get("playlists", {}).pop(pl_name, None)
            if rm.get("current_playlist") == pl_name:
                remaining = list(rm.get("playlists", {}).keys())
                rm["current_playlist"] = remaining[0] if remaining else ""
            self.settings.set_roguemode_settings(rm)
            self._refresh_rm_playlists()

    def _rm_upload_audio(self):
        if self._rm_pl_combo.count() == 0:
            QMessageBox.information(
                self, "Upload Audio", "Create a playlist first, then upload audio."
            )
            return
        pl_name = self._rm_pl_combo.currentData()
        if not pl_name:
            return
        audio_dir = self.settings.get_roguemode_audio_dir()
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Audio Files", str(audio_dir),
            "Audio Files (*.mp3 *.wav *.ogg *.flac *.m4a *.aac);;All Files (*.*)"
        )
        if not paths:
            return
        rm = self.settings.get_roguemode_settings()
        playlist = rm.setdefault("playlists", {}).setdefault(pl_name, [])
        added = 0
        for src in paths:
            src_path = Path(src)
            dest = audio_dir / src_path.name
            if dest.name in playlist:
                continue  # already in playlist
            try:
                if not dest.exists():
                    shutil.copy2(str(src_path), str(dest))
                playlist.append(dest.name)
                added += 1
            except Exception as e:
                QMessageBox.warning(self, "Upload Error", f"Could not copy {src_path.name}:\n{e}")
        if added:
            self.settings.set_roguemode_settings(rm)
            self._refresh_rm_songs()
            from techdeck.ui.widgets.rogue_mode_player import RogueModePlayer
            player = RogueModePlayer._instance
            if player is not None:
                try:
                    player.refresh_playlists()
                except RuntimeError:
                    pass

    def _rm_remove_song(self):
        item = self._rm_song_list.currentItem()
        if not item:
            return
        pl_name = self._rm_pl_combo.currentData()
        fn = item.data(Qt.ItemDataRole.UserRole)
        rm = self.settings.get_roguemode_settings()
        playlist = rm.get("playlists", {}).get(pl_name, [])
        if fn in playlist:
            playlist.remove(fn)
            self.settings.set_roguemode_settings(rm)
            self._refresh_rm_songs()
            from techdeck.ui.widgets.rogue_mode_player import RogueModePlayer
            player = RogueModePlayer._instance
            if player is not None:
                try:
                    player.refresh_playlists()
                except RuntimeError:
                    pass

    def _save_roguemode_settings(self):
        rm = self.settings.get_roguemode_settings()
        rm["autoplay"] = self._rm_autoplay_check.isChecked()
        self.settings.set_roguemode_settings(rm)
        from techdeck.ui.widgets.rogue_mode_player import RogueModePlayer
        player = RogueModePlayer._instance
        if player is not None:
            try:
                player.refresh_playlists()
            except RuntimeError:
                pass
        QMessageBox.information(self, "Rogue Mode", "Playlist saved.")

    # ──────────────────────────────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────────────────────────────

    def _create_section(self, title: str) -> QVBoxLayout:
        section = QVBoxLayout()
        section.setSpacing(10)
        section_title = QLabel(title)
        section_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        section.addWidget(section_title)
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("background: #2A2A2A; max-height: 1px;")
        section.addWidget(divider)
        return section

    def _combo_style(self, theme, arrow_path: str) -> str:
        return f"""
            QComboBox {{
                background-color: {theme.surface};
                color: {theme.text};
                border: 1px solid {theme.border};
                border-radius: 8px;
                padding: 6px 10px;
                padding-right: 28px;
            }}
            QComboBox:hover {{ border-color: {theme.border_strong}; }}
            QComboBox::drop-down {{
                width: 24px; border: none; background: transparent;
                subcontrol-origin: padding; subcontrol-position: center right;
            }}
            QComboBox::down-arrow {{
                image: url("{arrow_path}"); width: 12px; height: 12px;
                background: transparent; border: none; margin-right: 6px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {theme.surface}; color: {theme.text};
                border: 1px solid {theme.border}; border-radius: 4px;
                selection-background-color: {theme.tile_selected}; outline: none;
            }}
        """

    def _check_for_updates(self):
        main_window = self.window()
        if hasattr(main_window, "check_for_updates_manual"):
            main_window.check_for_updates_manual()

    def refresh(self):
        self._load_general_settings()
        self._load_plugin_list()
        self._load_personalization_settings()
        self._refresh_custom_theme_list()
        self._refresh_rm_playlists()
