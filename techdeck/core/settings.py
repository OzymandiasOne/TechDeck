"""
TechDeck Settings Manager
Handles loading, saving, and validating application settings.
Manages profiles, user data, app configuration, and plugin settings.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import tempfile
import shutil

from techdeck.core.constants import (
    DEFAULT_PROFILE_NAME,
    SETTINGS_DIR_NAME,
    SETTINGS_FILE_NAME,
    CONFIG_VERSION,
)


# Plugin folder/IDs renamed in the line-prefix rename. Maps old ID -> new ID.
# Applied once at load so existing installs keep their profile tiles, plugin
# settings, and run stats after the rename.
_PLUGIN_ID_RENAMES = {
    "lst_organizer": "922_lst_organizer",
    "part_sketch_extractor": "911_sketch_extractor",
    "po_packet_extractor": "911_po_pdf_extractor",
    "run_time_estimator": "922_runtime_genie",
}


class SettingsManager:
    """
    Manages application settings and profiles.

    Responsibilities:
    - Load/save settings.json with atomic writes
    - Profile CRUD operations
    - Plugin settings management
    - Data validation and migrations
    - Ensure Default profile always exists
    """

    def __init__(self, settings_dir: Optional[Path] = None):
        """
        Initialize settings manager.
        
        Args:
            settings_dir: Optional custom settings directory.
                         Defaults to %LOCALAPPDATA%/TechDeck on Windows.
        """
        if settings_dir is None:
            # Default: %LOCALAPPDATA%/TechDeck on Windows
            if os.name == 'nt':
                base = Path(os.environ.get('LOCALAPPDATA', Path.home()))
            else:
                base = Path.home() / '.local' / 'share'
            settings_dir = base / SETTINGS_DIR_NAME
        
        self.settings_dir = Path(settings_dir)
        self.settings_file = self.settings_dir / SETTINGS_FILE_NAME
        self.data: Dict[str, Any] = {}
        
        # Ensure directory exists
        self.settings_dir.mkdir(parents=True, exist_ok=True)
        
        # Load or create settings
        self.load()
    
    def load(self) -> None:
        """Load settings from disk. Creates default if doesn't exist."""
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
                self._validate_and_migrate()
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load settings: {e}")
                print("Creating new settings file.")
                self._create_default_settings()
        else:
            self._create_default_settings()
    
    def save(self) -> None:
        """Save current settings to disk using atomic write (temp file + rename)."""
        try:
            # Create a temporary file in the same directory
            temp_fd, temp_path = tempfile.mkstemp(
                suffix='.tmp',
                prefix='settings_',
                dir=self.settings_dir,
                text=True
            )
            
            try:
                # Write to temp file
                with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                    json.dump(self.data, f, indent=2)
                
                # Atomic rename (on Windows, need to handle existing file)
                temp_path_obj = Path(temp_path)
                
                if os.name == 'nt':
                    # Windows: remove target first if it exists
                    if self.settings_file.exists():
                        # Create backup before replacing
                        backup_path = self.settings_file.with_suffix('.bak')
                        if backup_path.exists():
                            backup_path.unlink()
                        shutil.copy2(self.settings_file, backup_path)
                        self.settings_file.unlink()
                    
                    # Now rename temp to target
                    temp_path_obj.rename(self.settings_file)
                else:
                    # Unix: atomic rename (overwrites target)
                    temp_path_obj.rename(self.settings_file)
                
            except Exception as e:
                # Clean up temp file on error
                if Path(temp_path).exists():
                    Path(temp_path).unlink()
                raise
                
        except IOError as e:
            print(f"Error saving settings: {e}")
            raise
    
    def _create_default_settings(self) -> None:
        """Create default settings structure."""
        now = self._utc_iso()
        
        self.data = {
            "version": CONFIG_VERSION,
            "user": {
                "username": os.environ.get('USERNAME', 'user'),
                "name": "",
                "email": "",
                "title": "",
                "avatar": None
            },
            "current_profile": DEFAULT_PROFILE_NAME,
            "profiles": {
                DEFAULT_PROFILE_NAME: {
                    "created_at": now,
                    "modified_at": now,
                    "tiles": []
                }
            },
            "settings": {
                "theme": "dark",
            },
            "plugin_settings": {}
        }
        self.save()
    
    def _validate_and_migrate(self) -> None:
        """Validate settings structure and run migrations if needed."""
        # Ensure top-level keys exist
        if "version" not in self.data:
            self.data["version"] = CONFIG_VERSION
        
        if "user" not in self.data:
            self.data["user"] = {
                "username": os.environ.get('USERNAME', 'user'),
                "name": "",
                "email": "",
                "title": "",
                "avatar": None
            }
        
        if "current_profile" not in self.data:
            self.data["current_profile"] = DEFAULT_PROFILE_NAME
        
        if "profiles" not in self.data:
            self.data["profiles"] = {}
        
        if "settings" not in self.data:
            self.data["settings"] = {
                "theme": "dark",
            }
        
        # PHASE 2: Remove console_height if it exists (migration)
        if "console_height" in self.data.get("settings", {}):
            del self.data["settings"]["console_height"]

        # Ensure audio settings exist with defaults
        if "audio" not in self.data.get("settings", {}):
            self.data["settings"]["audio"] = {"enabled": True, "volume": 80}
        
        # Ensure plugin_settings exists
        if "plugin_settings" not in self.data:
            self.data["plugin_settings"] = {}

        # Ensure plugin_stats exists (run counts + consecutive error tracking)
        if "plugin_stats" not in self.data:
            self.data["plugin_stats"] = {}
        
        # Ensure Default profile exists
        if DEFAULT_PROFILE_NAME not in self.data["profiles"]:
            now = self._utc_iso()
            self.data["profiles"][DEFAULT_PROFILE_NAME] = {
                "created_at": now,
                "modified_at": now,
                "tiles": []
            }
        
        # Ensure current_profile points to a valid profile
        if self.data["current_profile"] not in self.data["profiles"]:
            self.data["current_profile"] = DEFAULT_PROFILE_NAME
        
        # Migrate legacy blank profile ("") to Default
        self._migrate_blank_profile()

        # Migrate renamed plugin IDs (folder rename) across tiles/settings/stats
        self._migrate_plugin_ids()

        self.save()
    
    def _migrate_blank_profile(self) -> None:
        """Migrate legacy blank profile key to Default profile."""
        if "" in self.data["profiles"]:
            blank_profile = self.data["profiles"][""]
            default_profile = self.data["profiles"][DEFAULT_PROFILE_NAME]
            
            # Merge tiles (default profile tiles take precedence)
            merged_tiles = list(set(blank_profile.get("tiles", []) + default_profile.get("tiles", [])))
            default_profile["tiles"] = merged_tiles
            
            # Update timestamps if blank was newer
            if blank_profile.get("modified_at", "") > default_profile.get("modified_at", ""):
                default_profile["modified_at"] = blank_profile["modified_at"]
            
            # Delete blank profile
            del self.data["profiles"][""]
            
            # If current_profile was "", update to Default
            if self.data.get("current_profile") == "":
                self.data["current_profile"] = DEFAULT_PROFILE_NAME

    def _migrate_plugin_ids(self) -> None:
        """Rewrite plugin IDs that changed in the folder rename.

        Updates the keys under plugin_settings/plugin_stats and the tile
        references in every profile. Idempotent: only acts when an old ID is
        present, and never overwrites an entry already stored under the new ID.
        """
        # Rename dict keys in plugin_settings and plugin_stats
        for section in ("plugin_settings", "plugin_stats"):
            bucket = self.data.get(section)
            if not isinstance(bucket, dict):
                continue
            for old_id, new_id in _PLUGIN_ID_RENAMES.items():
                if old_id not in bucket:
                    continue
                if new_id not in bucket:
                    bucket[new_id] = bucket[old_id]
                del bucket[old_id]

        # Rewrite tile references in every profile (preserve order, dedupe)
        for profile in self.data.get("profiles", {}).values():
            tiles = profile.get("tiles")
            if not isinstance(tiles, list):
                continue
            new_tiles: List[str] = []
            for tile in tiles:
                mapped = _PLUGIN_ID_RENAMES.get(tile, tile)
                if mapped not in new_tiles:
                    new_tiles.append(mapped)
            profile["tiles"] = new_tiles

    # ========== Profile Management ==========
    
    def get_profile_names(self) -> List[str]:
        """Get list of all profile names, sorted alphabetically."""
        return sorted(self.data["profiles"].keys())
    
    def get_current_profile_name(self) -> str:
        """Get name of currently selected profile."""
        return self.data["current_profile"]
    
    def set_current_profile(self, profile_name: str) -> bool:
        """
        Set the current profile.
        
        Args:
            profile_name: Name of profile to activate
            
        Returns:
            True if successful, False if profile doesn't exist
        """
        if profile_name in self.data["profiles"]:
            self.data["current_profile"] = profile_name
            self.save()
            return True
        return False
    
    def get_profile_tiles(self, profile_name: Optional[str] = None) -> List[str]:
        """
        Get tile IDs for a profile.
        
        Args:
            profile_name: Profile to get tiles from. If None, uses current profile.
            
        Returns:
            List of tile IDs
        """
        if profile_name is None:
            profile_name = self.data["current_profile"]
        
        if profile_name in self.data["profiles"]:
            return self.data["profiles"][profile_name].get("tiles", [])
        return []
    
    def set_profile_tiles(self, tiles: List[str], profile_name: Optional[str] = None) -> None:
        """
        Set tile IDs for a profile.
        
        Args:
            tiles: List of tile IDs
            profile_name: Profile to modify. If None, uses current profile.
        """
        if profile_name is None:
            profile_name = self.data["current_profile"]
        
        if profile_name in self.data["profiles"]:
            self.data["profiles"][profile_name]["tiles"] = tiles
            self.data["profiles"][profile_name]["modified_at"] = self._utc_iso()
            self.save()
    
    def create_profile(self, profile_name: str) -> bool:
        """
        Create a new profile.
        
        Args:
            profile_name: Name for the new profile
            
        Returns:
            True if created, False if name already exists
        """
        if profile_name in self.data["profiles"]:
            return False
        
        now = self._utc_iso()
        self.data["profiles"][profile_name] = {
            "created_at": now,
            "modified_at": now,
            "tiles": []
        }
        self.save()
        return True
    
    def rename_profile(self, old_name: str, new_name: str) -> bool:
        """
        Rename a profile.
        
        Args:
            old_name: Current profile name
            new_name: New profile name
            
        Returns:
            True if renamed, False if old doesn't exist or new already exists
        """
        # Can't rename Default profile
        if old_name == DEFAULT_PROFILE_NAME:
            return False
        
        if old_name not in self.data["profiles"]:
            return False
        
        if new_name in self.data["profiles"]:
            return False
        
        # Move profile data to new key
        self.data["profiles"][new_name] = self.data["profiles"][old_name]
        self.data["profiles"][new_name]["modified_at"] = self._utc_iso()
        del self.data["profiles"][old_name]
        
        # Update current_profile if it was the renamed one
        if self.data["current_profile"] == old_name:
            self.data["current_profile"] = new_name
        
        self.save()
        return True
    
    def delete_profile(self, profile_name: str) -> bool:
        """
        Delete a profile.
        
        Args:
            profile_name: Name of profile to delete
            
        Returns:
            True if deleted, False if doesn't exist or is Default
        """
        # Can't delete Default profile
        if profile_name == DEFAULT_PROFILE_NAME:
            return False
        
        if profile_name not in self.data["profiles"]:
            return False
        
        del self.data["profiles"][profile_name]
        
        # If deleting current profile, switch to Default
        if self.data["current_profile"] == profile_name:
            self.data["current_profile"] = DEFAULT_PROFILE_NAME
        
        self.save()
        return True
    
    # ========== User Data ==========
    
    def get_user_data(self) -> Dict[str, Any]:
        """Get user profile data."""
        return self.data.get("user", {})
    
    def update_user_data(self, **kwargs) -> None:
        """
        Update user profile data.
        
        Args:
            **kwargs: Fields to update (name, email, title, avatar, etc.)
        """
        if "user" not in self.data:
            self.data["user"] = {}
        
        self.data["user"].update(kwargs)
        self.save()
    
    # ========== App Settings ==========
    
    def get_theme(self) -> str:
        """Get current theme name."""
        return self.data.get("settings", {}).get("theme", "dark")

    def set_theme(self, theme_name: str) -> None:
        """Set current theme."""
        if "settings" not in self.data:
            self.data["settings"] = {}
        self.data["settings"]["theme"] = theme_name
        self.save()

    # Library page tile sort. "alphabetical" sorts by plugin display name;
    # "family" groups by 911 -> 922 -> other, alphabetical within each group.
    _LIBRARY_SORT_MODES = ("alphabetical", "family")

    def get_library_sort_mode(self) -> str:
        return self.data.get("settings", {}).get("library_sort_mode", "alphabetical")

    def set_library_sort_mode(self, mode: str) -> None:
        if mode not in self._LIBRARY_SORT_MODES:
            mode = "alphabetical"
        if "settings" not in self.data:
            self.data["settings"] = {}
        self.data["settings"]["library_sort_mode"] = mode
        self.save()
    
    # ========== Plugin Settings ==========
    
    def get_plugin_settings(self, plugin_id: str) -> Dict[str, Any]:
        """
        Get all settings for a plugin.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            Dictionary of plugin settings (empty if not configured)
        """
        if "plugin_settings" not in self.data:
            self.data["plugin_settings"] = {}
        
        return self.data["plugin_settings"].get(plugin_id, {})
    
    def set_plugin_settings(self, plugin_id: str, settings: Dict[str, Any]) -> None:
        """
        Set all settings for a plugin.
        
        Args:
            plugin_id: Plugin identifier
            settings: Dictionary of settings to save
        """
        if "plugin_settings" not in self.data:
            self.data["plugin_settings"] = {}
        
        self.data["plugin_settings"][plugin_id] = settings
        self.save()
    
    def get_plugin_setting(self, plugin_id: str, key: str, default: Any = None) -> Any:
        """
        Get a specific setting for a plugin.
        
        Args:
            plugin_id: Plugin identifier
            key: Setting key
            default: Default value if setting not found
            
        Returns:
            Setting value or default
        """
        plugin_settings = self.get_plugin_settings(plugin_id)
        return plugin_settings.get(key, default)
    
    def set_plugin_setting(self, plugin_id: str, key: str, value: Any) -> None:
        """
        Set a specific setting for a plugin.
        
        Args:
            plugin_id: Plugin identifier
            key: Setting key
            value: Setting value
        """
        if "plugin_settings" not in self.data:
            self.data["plugin_settings"] = {}
        
        if plugin_id not in self.data["plugin_settings"]:
            self.data["plugin_settings"][plugin_id] = {}
        
        self.data["plugin_settings"][plugin_id][key] = value
        self.save()
    
    def reset_plugin_settings(self, plugin_id: str, defaults: Dict[str, Any]) -> None:
        """
        Reset plugin settings to defaults.
        
        Args:
            plugin_id: Plugin identifier
            defaults: Default settings dictionary
        """
        if "plugin_settings" not in self.data:
            self.data["plugin_settings"] = {}
        
        self.data["plugin_settings"][plugin_id] = defaults.copy()
        self.save()
    
    def delete_plugin_settings(self, plugin_id: str) -> None:
        """
        Delete all settings for a plugin.
        
        Args:
            plugin_id: Plugin identifier
        """
        if "plugin_settings" in self.data and plugin_id in self.data["plugin_settings"]:
            del self.data["plugin_settings"][plugin_id]
            self.save()
    
    # ========== Plugin Stats ==========

    def get_plugin_stats(self, plugin_id: str) -> Dict[str, Any]:
        """Get run stats for a plugin (run_count, consecutive_errors)."""
        return self.data.get("plugin_stats", {}).get(plugin_id, {})

    def increment_plugin_runs(self, plugin_id: str) -> None:
        """Record a successful run: bump run_count, reset consecutive_errors."""
        if "plugin_stats" not in self.data:
            self.data["plugin_stats"] = {}
        stats = self.data["plugin_stats"].setdefault(plugin_id, {})
        stats["run_count"] = stats.get("run_count", 0) + 1
        stats["consecutive_errors"] = 0
        self.save()

    def record_plugin_error(self, plugin_id: str) -> None:
        """Record a failed run: bump consecutive_errors."""
        if "plugin_stats" not in self.data:
            self.data["plugin_stats"] = {}
        stats = self.data["plugin_stats"].setdefault(plugin_id, {})
        stats["consecutive_errors"] = stats.get("consecutive_errors", 0) + 1
        self.save()

    # ========== Audio Settings ==========

    def get_audio_settings(self) -> dict:
        """Get audio settings dict with keys 'enabled' (bool) and 'volume' (int 0-100)."""
        defaults = {"enabled": True, "volume": 80}
        return self.data.get("settings", {}).get("audio", defaults)

    def set_audio_settings(self, enabled: bool, volume: int) -> None:
        """Persist audio settings."""
        if "settings" not in self.data:
            self.data["settings"] = {}
        self.data["settings"]["audio"] = {"enabled": enabled, "volume": max(0, min(100, volume))}
        self.save()

    # ========== Blackjack Bankroll ==========

    def get_blackjack_bankroll(self) -> int:
        """Get persisted blackjack bankroll (default $500)."""
        return self.data.get("settings", {}).get("blackjack_bankroll", 500)

    def set_blackjack_bankroll(self, amount: int) -> None:
        """Persist blackjack bankroll."""
        if "settings" not in self.data:
            self.data["settings"] = {}
        self.data["settings"]["blackjack_bankroll"] = max(0, amount)
        self.save()

    # ========== Shelf (Phase D — single-slot snapshot of a paused/queued run) ==========

    def get_shelf(self) -> Optional[Dict[str, Any]]:
        """Return the current shelf entry, or None if empty.

        Shape:
            {
              "stored_at": ISO8601 UTC timestamp,
              "remaining_tile_ids": [str, ...],
              "shared_state": {"911": {...}, "922": {...}, "other": {...}},
              "originating_profile": str
            }
        """
        shelf = self.data.get("shelf")
        if isinstance(shelf, dict) and shelf.get("remaining_tile_ids"):
            return shelf
        return None

    def set_shelf(self, entry: Dict[str, Any]) -> None:
        """Persist a single shelf entry. Overwrites any prior shelf without prompt."""
        self.data["shelf"] = entry
        self.save()

    def clear_shelf(self) -> None:
        """Remove any persisted shelf entry."""
        if "shelf" in self.data:
            del self.data["shelf"]
            self.save()

    # ========== Custom Themes ==========

    def get_custom_themes_dir(self) -> Path:
        """Directory where user-created theme JSON files are stored."""
        d = self.settings_dir / "themes"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ========== Rogue Mode ==========

    def get_roguemode_audio_dir(self) -> Path:
        """Directory where Rogue Mode audio files are stored."""
        d = self.settings_dir / "roguemode"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def get_roguemode_settings(self) -> dict:
        """Return Rogue Mode settings dict (playlists, current_playlist, volume, loop_mode)."""
        defaults = {
            "playlists": {"Default": []},
            "current_playlist": "Default",
            "volume": 75,
            "loop_mode": "loop_all",
            "autoplay": True,
        }
        stored = self.data.get("settings", {}).get("roguemode", {})
        merged = {**defaults, **stored}
        # Ensure Default playlist always exists when playlists is empty
        if not merged.get("playlists"):
            merged["playlists"] = {"Default": []}
            merged["current_playlist"] = "Default"
        return merged

    def set_roguemode_settings(self, data: dict) -> None:
        """Persist Rogue Mode settings dict."""
        if "settings" not in self.data:
            self.data["settings"] = {}
        self.data["settings"]["roguemode"] = data
        self.save()

    def update_roguemode_setting(self, key: str, value) -> None:
        """Update a single key in Rogue Mode settings."""
        rm = self.get_roguemode_settings()
        rm[key] = value
        self.set_roguemode_settings(rm)

    # ========== Helpers ==========

    @staticmethod
    def _utc_iso() -> str:
        """Get current UTC timestamp in ISO 8601 format."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
