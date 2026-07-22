"""
TechDeck Library Page — browse the full plugin roster and build kits (profiles).

Holds only the LibraryPage view. Its pieces live in sibling modules:
FlowLayout in ui/widgets/flow_layout.py, the tile widgets + info popup in
ui/widgets/library_card.py, and ProfileDialog in ui/dialogs/profile_dialog.py
— all re-exported here for back-compat.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QScrollArea, QMessageBox, QDialog,
    QSizePolicy
)
from PySide6.QtCore import Signal

from pathlib import Path

from techdeck.core.settings import SettingsManager
from techdeck.core.constants import DEFAULT_PROFILE_NAME
from techdeck.ui.utils import make_tinted_svg_copy
from techdeck.ui.theme_aware import ThemeAware
# Re-exported for back-compat with any `from ...library_page import X` caller.
from techdeck.ui.widgets.flow_layout import FlowLayout                   # noqa: F401
from techdeck.ui.widgets.library_card import (                           # noqa: F401
    LibraryPluginCard, PluginInfoDialog, _MissingLibraryTile,
)
from techdeck.ui.dialogs.profile_dialog import ProfileDialog             # noqa: F401


class LibraryPage(QWidget, ThemeAware):
    """
    Library page for browsing and selecting tiles.
    NOW: Shows missing plugins as selected with (Missing) label, allows deselecting them!
    UPDATED: Save button in header bar for better UX, with Open Plugin Folder button in footer.

    Signals:
        saved(): Emitted when user saves tile selection
        return_home(): Emitted when user wants to go back to home
    """

    saved = Signal()
    return_home = Signal()

    def __init__(self, settings: SettingsManager, parent=None, plugin_loader=None):
        super().__init__(parent)
        self.settings = settings
        self.selected_tile_ids = set()
        self._missing_tile_widgets: list = []  # _MissingLibraryTile instances for theme re-stamping

        # Use the shared loader if MainWindow gave us one; otherwise scan now.
        from techdeck.core.plugin_loader import PluginLoader
        if plugin_loader is None:
            plugin_loader = PluginLoader()
            plugin_loader.discover_plugins()
        self.plugin_loader = plugin_loader

        self.available_plugins = list(plugin_loader.plugins.values())
        self.available_tiles = [p.id for p in self.available_plugins]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # ===== Header with Profile Controls =====
        self._header_container = QWidget()
        self._header_container.setFixedHeight(50)
        # Ignored width: the toolbar's fixed-width controls must not floor the
        # page (and with it the window) at ~840px — the tile grid reflows to
        # any width. Squeezed below its natural width, the bar clips on the
        # right instead.
        self._header_container.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        header_layout = QHBoxLayout(self._header_container)
        header_layout.setContentsMargins(20, 8, 20, 8)
        header_layout.setSpacing(12)

        self._profile_label = QLabel("My Kits")

        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(200)
        self.profile_combo.setMinimumHeight(36)
        self.profile_combo.currentTextChanged.connect(self._on_profile_changed)

        self.btn_create = QPushButton("Create")
        self.btn_create.setMinimumHeight(36)
        self.btn_create.setMinimumWidth(90)
        self.btn_create.clicked.connect(self._on_create_profile)

        self.btn_edit = QPushButton("Edit")
        self.btn_edit.setMinimumHeight(36)
        self.btn_edit.setMinimumWidth(90)
        self.btn_edit.clicked.connect(self._on_edit_profile)

        self.btn_save = QPushButton("Save")
        self.btn_save.setMinimumHeight(36)
        self.btn_save.setMinimumWidth(110)
        self.btn_save.clicked.connect(self._on_save)

        # Sort control: alphabetical vs. by family. Persists in settings so the
        # user's choice survives restarts.
        self._sort_label = QLabel("Sort:")
        self.sort_combo = QComboBox()
        self.sort_combo.addItem("Alphabetical", "alphabetical")
        self.sort_combo.addItem("By Family", "family")
        self.sort_combo.setMinimumHeight(36)
        self.sort_combo.setMinimumWidth(140)
        _initial_sort = self.settings.get_library_sort_mode()
        _idx = self.sort_combo.findData(_initial_sort)
        if _idx >= 0:
            self.sort_combo.setCurrentIndex(_idx)
        self.sort_combo.currentIndexChanged.connect(self._on_sort_mode_changed)

        header_layout.addWidget(self._profile_label)
        header_layout.addWidget(self.profile_combo)
        header_layout.addWidget(self.btn_create)
        header_layout.addWidget(self.btn_edit)
        header_layout.addStretch()
        header_layout.addWidget(self._sort_label)
        header_layout.addWidget(self.sort_combo)
        header_layout.addWidget(self.btn_save)

        layout.addWidget(self._header_container)

        # ===== Tile Grid (scrollable) =====
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)

        self._tile_container = QWidget()
        self.tile_grid = FlowLayout(self._tile_container,
                                    margin=24, hspacing=20, vspacing=20)

        self._scroll.setWidget(self._tile_container)
        layout.addWidget(self._scroll, 1)

        # ===== Footer with Open Plugin Folder button =====
        self._footer_container = QWidget()
        self._footer_container.setFixedHeight(60)
        # Same as the header: never floor the page's width.
        self._footer_container.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        footer_layout = QHBoxLayout(self._footer_container)
        footer_layout.setContentsMargins(20, 10, 20, 10)
        footer_layout.setSpacing(12)

        # Bottom-left: re-scan the plugins folder so apps added/removed on disk
        # (and their icons) show up without restarting TechDeck.
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setMinimumHeight(36)
        self.btn_refresh.setMinimumWidth(110)
        self.btn_refresh.setToolTip(
            "Re-scan the plugins folder to pick up apps you added or removed")
        self.btn_refresh.clicked.connect(self._on_refresh)
        footer_layout.addWidget(self.btn_refresh)

        footer_layout.addStretch()

        self.btn_open_plugins = QPushButton("Open Plugin Folder")
        self.btn_open_plugins.setMinimumHeight(36)
        self.btn_open_plugins.setMinimumWidth(170)
        self.btn_open_plugins.clicked.connect(self._open_plugin_folder)

        footer_layout.addWidget(self.btn_open_plugins)
        layout.addWidget(self._footer_container)

        # Subscribes to theme_changed and applies immediately.
        self.setup_theme_awareness()

        # Load initial data
        self.refresh()

    # ========== Theme handling =====================================

    def apply_theme(self):
        """Re-style every theme-sensitive surface owned by LibraryPage."""
        # Games appear/disappear with the Professional theme; the per-tile filter
        # only runs at build time, so rebuild the grid when professional toggles
        # (guarded so the initial theme-apply doesn't pre-empt the first build).
        prof = self.settings.is_professional()
        if getattr(self, "_was_professional", None) != prof:
            self._was_professional = prof
            if getattr(self, "_grid_built", False):
                self._build_tile_grid()
        from techdeck.ui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_palette()
        theme_name = get_theme_manager().get_current_theme()

        self.setStyleSheet(f"""
            LibraryPage {{ background-color: {theme.background}; }}
            LibraryPage QLabel {{ background-color: transparent; }}
        """)

        self._header_container.setStyleSheet(f"""
            QWidget {{
                background-color: {theme.background};
                border-radius: 0px;
            }}
            QWidget QLabel {{
                background-color: transparent;
            }}
        """)
        self._profile_label.setStyleSheet(
            f"font-size: 14px; color: {theme.text}; background: transparent;"
        )

        icon_folder = "light" if theme_name in ["dark", "blue", "cyberpunk", "matrix"] else "dark"
        icons_dir = Path(__file__).resolve().parents[3] / "assets" / "icons" / icon_folder
        arrow_path = make_tinted_svg_copy(icons_dir / "chevron-down.svg", theme.text)

        combo_style = f"""
            QComboBox {{
                background-color: {theme.surface};
                color: {theme.text};
                border: 1px solid {theme.border};
                border-radius: 8px;
                padding: 6px 10px;
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
        """
        self.profile_combo.setStyleSheet(combo_style)
        self.sort_combo.setStyleSheet(combo_style)
        self._sort_label.setStyleSheet(
            f"font-size: 14px; color: {theme.text}; background: transparent;"
        )

        surface_btn_style = f"""
            QPushButton {{
                background-color: {theme.surface};
                color: {theme.text};
                border: 1px solid {theme.border};
                border-radius: 8px;
                font-weight: 500;
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                background-color: {theme.surface_hover};
                border-color: {theme.border_strong};
            }}
            QPushButton:pressed {{
                background-color: {theme.border_strong};
            }}
        """
        self.btn_create.setStyleSheet(surface_btn_style)
        self.btn_edit.setStyleSheet(surface_btn_style)
        self.btn_open_plugins.setStyleSheet(surface_btn_style)
        self.btn_refresh.setStyleSheet(surface_btn_style)

        self.btn_save.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.accent_two};
                color: {theme.accent_two_text};
                border: none;
                border-radius: 8px;
                font-weight: 600;
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                background-color: {theme.accent_two_hover};
            }}
            QPushButton:pressed {{
                background-color: {theme.accent_two_pressed};
            }}
        """)

        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: {theme.background};
            }}
            QScrollArea > QWidget {{
                background-color: {theme.background};
            }}
        """)
        self._tile_container.setStyleSheet(
            f"QWidget {{ background-color: {theme.background}; }}"
        )

        self._footer_container.setStyleSheet(f"""
            QWidget {{
                background-color: {theme.background};
                border-radius: 0px;
            }}
        """)

        # Missing-tile placeholders bake their colors in, so re-stamp them here
        # (LibraryPluginCards re-theme themselves via ThemeAware).
        for tile in self._missing_tile_widgets:
            tile.restyle(theme)

    def refresh(self):
        """Reload profiles and current selection."""
        # Update profile dropdown
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        
        profiles = self.settings.get_profile_names()
        self.profile_combo.addItems(profiles)
        
        current = self.settings.get_current_profile_name()
        index = self.profile_combo.findText(current)
        if index >= 0:
            self.profile_combo.setCurrentIndex(index)
        
        self.profile_combo.blockSignals(False)
        
        # Rebuild tile grid
        self._build_tile_grid()
        
        # Update Edit button state (disable for Default)
        self.btn_edit.setEnabled(current != DEFAULT_PROFILE_NAME)
    
    def _build_tile_grid(self):
        """Build the grid of available tiles + missing tiles from current profile."""
        self._grid_built = True
        # Clear existing tiles
        self._missing_tile_widgets = []
        while self.tile_grid.count():
            item = self.tile_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Get currently selected profile's tiles and sync selected_tile_ids to match
        current_profile_tiles = set(self.settings.get_profile_tiles())
        self.selected_tile_ids = current_profile_tiles.copy()

        from techdeck.ui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_palette()

        # Re-read the live plugin list on every build — never trust the
        # __init__-time capture. If the loader's contents change after this
        # page is constructed, a stale snapshot silently shrinks the library
        # to just the current kit's tiles.
        # Hide purchasable ("locked") plugins until they're unlocked at Woogy's
        # Emporium. This is the source-agnostic gate: any plugin (bundled now, or
        # downloaded later) with locked=true stays hidden until is_unlocked(id).
        # Professional theme also hides games (the playful "Games" family).
        prof = self.settings.is_professional()
        self.available_plugins = [
            p for p in self.plugin_loader.plugins.values()
            if not (getattr(p, "locked", False)
                    and not self.settings.is_unlocked(p.id))
            and not (prof and getattr(p, "family", "") == "Games")
        ]
        self.available_tiles = [p.id for p in self.available_plugins]

        # Combine available tiles + missing tiles from profile
        all_tile_ids = list(set(self.available_tiles) | current_profile_tiles)

        # Sort according to user-selected mode. "alphabetical" by display name,
        # "family" groups 902 -> 911 -> 922 -> QA -> Games -> General (alpha within each).
        sort_mode = self.settings.get_library_sort_mode()
        _family_rank = {"902": 0, "911": 1, "922": 2, "QA": 3, "Games": 4, "General": 5}

        def _name_no_family(name: str) -> str:
            # Drop a leading family prefix ("911 ", "922 ", "qa ") so Alphabetical
            # sorts by the descriptive part of the name. Without this it just mirrors
            # the By-Family grouping (names are family-prefixed), so the two modes
            # would look identical. (Names arrive lowercased from _sort_key.)
            head, _, rest = name.partition(" ")
            return rest if rest and (head.isdigit() or head == "qa") else name

        def _sort_key(tid: str):
            p = self.plugin_loader.get_plugin(tid)
            name = (p.name if p else tid).lower()
            if sort_mode == "family":
                # Group by family rank; alphabetical within each group.
                family = (p.family if p else "General")
                return (_family_rank.get(family, 5), name)
            # Flat A-Z by the descriptive name (family number ignored).
            return (_name_no_family(name),)

        for tile_id in sorted(all_tile_ids, key=_sort_key):
            plugin = self.plugin_loader.get_plugin(tile_id)

            # Professional mode hides games even if one is saved in the profile
            # (the available_plugins filter above only covers the unselected pool).
            if prof and plugin and getattr(plugin, "family", "") == "Games":
                continue

            # Check if this tile is selected in current profile
            is_selected = tile_id in current_profile_tiles

            if plugin:
                # PHASE 3: Use LibraryPluginCard instead of QPushButton
                desc = plugin.description[:60] + "..." if len(plugin.description) > 60 else plugin.description
                
                card = LibraryPluginCard(
                    plugin=plugin,
                    plugin_desc=desc,
                    tile_id=tile_id,
                    theme=theme,
                    is_selected=is_selected,
                    parent=self
                )
                card.toggled.connect(lambda checked, tid=tile_id: self._on_tile_toggled_card(tid, checked))

                self.tile_grid.addWidget(card)
            else:
                # Missing plugin — toggleable placeholder so the user can
                # deselect it and Save to drop the dead id from the kit.
                card = _MissingLibraryTile(tile_id, theme, parent=self)
                card.toggled.connect(lambda checked, tid=tile_id: self._on_tile_toggled_card(tid, checked))
                self._missing_tile_widgets.append(card)
                self.tile_grid.addWidget(card)

        # Schedule a fresh geometry pass — the grid is rebuilt while this page
        # is hidden (init + startup warmup), and the first show must not reuse
        # stale card geometry.
        self.tile_grid.invalidate()
        self._tile_container.updateGeometry()

    def showEvent(self, event):
        """Force the flow layout to run with real geometry on every show.

        The grid is (re)built while the page is hidden, and on some machines
        the first show never triggered a layout pass — every card kept its
        default position, painting stacked with only the last-added card
        visible ("library shows one app until you cycle kits", seen on
        colleague machines in v0.8.6). A kit cycle fixed it only because it
        rebuilt the grid while the page was visible; do the layout pass
        deterministically here instead."""
        super().showEvent(event)
        self.tile_grid.invalidate()
        self.tile_grid.activate()

    def _on_tile_toggled_card(self, tile_id: str, checked: bool):
        """Handle card selection toggle."""
        if checked:
            self.selected_tile_ids.add(tile_id)
        else:
            self.selected_tile_ids.discard(tile_id)
        from techdeck.core.audio_manager import get_audio_manager, SOUND_CLICK
        get_audio_manager().play(SOUND_CLICK)

    def _on_profile_changed(self, profile_name: str):
        """Handle profile selection change."""
        if profile_name:
            self.settings.set_current_profile(profile_name)
            self._build_tile_grid()
            self.btn_edit.setEnabled(profile_name != DEFAULT_PROFILE_NAME)

    def _on_sort_mode_changed(self, _index: int):
        """Persist the new sort mode and rebuild the grid."""
        mode = self.sort_combo.currentData() or "alphabetical"
        self.settings.set_library_sort_mode(mode)
        self._build_tile_grid()
    
    def _on_create_profile(self):
        """Show dialog to create new profile."""
        dialog = ProfileDialog("create", parent=self)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = dialog.get_name()
            
            # Check if name already exists
            if name in self.settings.get_profile_names():
                QMessageBox.warning(
                    self,
                    "Duplicate Name",
                    f"A profile named '{name}' already exists."
                )
                return
            
            # Create profile
            if self.settings.create_profile(name):
                self.settings.set_current_profile(name)
                self.refresh()
                QMessageBox.information(
                    self,
                    "Profile Created",
                    f"Profile '{name}' created successfully!"
                )
    
    def _on_edit_profile(self):
        """Show dialog to edit current profile."""
        current = self.profile_combo.currentText()
        
        if not current:
            return
        
        if current == DEFAULT_PROFILE_NAME:
            QMessageBox.information(
                self,
                "Cannot Edit Default",
                "The Default profile cannot be renamed or deleted."
            )
            return
        
        dialog = ProfileDialog("edit", current_name=current, parent=self)
        result = dialog.exec()
        
        # Check if delete was requested
        if dialog.delete_requested:
            if self.settings.delete_profile(current):
                self.refresh()
                QMessageBox.information(
                    self,
                    "Profile Deleted",
                    f"Profile '{current}' has been deleted."
                )
            return
        
        # Handle rename
        if result == QDialog.DialogCode.Accepted:
            new_name = dialog.get_name()
            
            if new_name != current:
                # Check if new name already exists
                if new_name in self.settings.get_profile_names():
                    QMessageBox.warning(
                        self,
                        "Duplicate Name",
                        f"A profile named '{new_name}' already exists."
                    )
                    return
                
                # Rename profile
                if self.settings.rename_profile(current, new_name):
                    self.refresh()
                    QMessageBox.information(
                        self,
                        "Profile Renamed",
                        f"Profile renamed to '{new_name}'."
                    )
    
    def _on_refresh(self):
        """Re-scan the plugins folder and rebuild the grid so apps added or
        removed on disk (and their icons) appear without restarting TechDeck.

        The loader is shared with the rest of the app, so re-discovering here
        also refreshes the pool the Home page reads next time it rebuilds."""
        try:
            self.plugin_loader.discover_plugins()
        except Exception as e:
            QMessageBox.warning(
                self, "Refresh Failed",
                f"Could not re-scan the plugins folder:\n\n{e}")
            return

        self._build_tile_grid()
        # The page is visible, so run the flow layout now — otherwise newly
        # added cards keep default geometry until the next show (see showEvent).
        self.tile_grid.invalidate()
        self.tile_grid.activate()

        from techdeck.core.audio_manager import get_audio_manager, SOUND_CLICK
        get_audio_manager().play(SOUND_CLICK)

    def _open_plugin_folder(self):
        """Open the plugins directory in the system file explorer."""
        import subprocess
        import os
        import platform
        
        plugins_dir = self.plugin_loader.get_plugins_dir()
        
        # Ensure directory exists
        plugins_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Open file explorer based on OS
            if platform.system() == 'Windows':
                os.startfile(plugins_dir)
            elif platform.system() == 'Darwin':  # macOS
                subprocess.run(['open', str(plugins_dir)])
            else:  # Linux
                subprocess.run(['xdg-open', str(plugins_dir)])
        except Exception as e:
            QMessageBox.warning(
                self,
                "Error Opening Folder",
                f"Could not open plugin folder:\n{plugins_dir}\n\nError: {str(e)}"
            )
    
    def _on_save(self):
        """Save tile selection to current profile and return to home."""
        current_profile = self.profile_combo.currentText()
        
        if not current_profile:
            return
        
        # Save tiles to profile (only selected ones, missing tiles can be removed!)
        self.settings.set_profile_tiles(list(self.selected_tile_ids), current_profile)
        
        # Emit signals
        self.saved.emit()
        self.return_home.emit()