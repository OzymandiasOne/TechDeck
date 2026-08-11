"""
TechDeck Settings Manager
Handles loading, saving, and validating application settings.
Manages profiles, user data, app configuration, and plugin settings.
"""

import json
import os
import sys
import threading
import time
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
    "911_repeater": "911_batch_repeater",  # id now matches its folder
    # Chain entries point at the FINAL id: tile/unlock migration is a single
    # dict lookup (no chaining), so an old->intermediate entry would leave a
    # stale tile for one launch.
    "911_linear_inch_calc": "911_sspo_award_review",   # renamed 2026-06-04
    "911_runtime_estimator": "911_sspo_award_review",  # renamed 2026-07-13
    "linear_inch_calculator": "customer_dxf_analysis",  # renamed 2026-06-10 (via customer_dxf_quoting)
    # 2026-07-29: absorbed the (never-released) DXF Offset Tool and renamed
    "customer_dxf_quoting": "customer_dxf_analysis",
    # 2026-07-02 naming convention: id = family-prefixed snake_case of the
    # Library name (911_/922_/qa_/game_; family-less plugins unprefixed).
    "pricing_backup_splitter": "911_sspo_invoicing_prep",      # one-off drop-in copies
    "911_pricing_backup_splitter": "911_sspo_invoicing_prep",  # brief interim id
    "batch_repeater": "922_batch_repeater",
    "922_form_seeker": "922_formingfinder",
    "qa_rework": "qa_gemba_analyzer",
    "steeltube_game": "game_asa_the_video_game",
}

# Plugin IDs that were RETIRED (not renamed). Stripped from profile tiles / plugin
# settings / stats on load so a removed plugin leaves no dead reference behind.
_REMOVED_PLUGIN_IDS = {
    "911_linear_inch_cuttime",  # 2026-07-09: absorbed into 911_runtime_estimator
}


# Process-wide default-location instance + guards. The shell (GUI thread), the
# plugin executor (worker thread), and the SDK (inside a plugin) all construct
# SettingsManager() with no arguments; before this each got its OWN in-memory
# copy of settings.json and wrote the WHOLE document on every change, so a later
# writer silently reverted an earlier one's edits (a run's run_count/total_runs
# bump clobbered by the shell's stale-snapshot ticket write, and vice-versa).
# Sharing one instance means everyone mutates one document. _SETTINGS_LOCK then
# serializes the actual disk write so the two threads can't tear the file.
_default_instance: Optional["SettingsManager"] = None
_default_instance_lock = threading.Lock()
_SETTINGS_LOCK = threading.RLock()


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

    def __new__(cls, settings_dir: Optional[Path] = None):
        # The default-location manager is a process-wide singleton so every
        # caller shares ONE in-memory document (see _default_instance note). An
        # explicit settings_dir (tests, alternate stores) always gets its own
        # independent instance.
        if settings_dir is None:
            global _default_instance
            with _default_instance_lock:
                if _default_instance is None:
                    _default_instance = super().__new__(cls)
                return _default_instance
        return super().__new__(cls)

    def __init__(self, settings_dir: Optional[Path] = None):
        """
        Initialize settings manager.

        Args:
            settings_dir: Optional custom settings directory.
                         Defaults to %LOCALAPPDATA%/TechDeck on Windows.
        """
        # The shared singleton is constructed once but __init__ runs on every
        # SettingsManager() call — guard so we don't reload the document (and
        # blow away in-flight state) on the 2nd..Nth construction.
        with _default_instance_lock:
            if getattr(self, '_initialized', False):
                return

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

            self._initialized = True
    
    def load(self) -> None:
        """Load settings from disk, recovering from the .bak copy when the live
        file is missing or corrupt before falling back to fresh defaults."""
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
                self._validate_and_migrate()
                return
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load settings: {e}")
                # Corrupt live file — try the last-known-good backup before
                # discarding the user's profile/tickets/unlocks.
                if self._load_from_backup():
                    return
                print("Creating new settings file.")
                self._create_default_settings()
        else:
            # Live file absent. On an older build a crash between unlink and
            # rename could leave exactly this state with a good .bak beside it —
            # recover it rather than silently resetting the user to defaults.
            if self._load_from_backup():
                return
            self._create_default_settings()

    def _load_from_backup(self) -> bool:
        """Restore self.data from the .bak copy. Returns True on success. The
        subsequent _validate_and_migrate() re-writes a fresh settings.json, so a
        recovered backup heals the missing/corrupt live file."""
        backup_path = self.settings_file.with_suffix('.bak')
        if not backup_path.exists():
            return False
        try:
            with open(backup_path, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Settings backup also unreadable: {e}")
            return False
        print(f"Recovered settings from backup: {backup_path}")
        self._validate_and_migrate()
        return True
    
    def save(self) -> None:
        """Save current settings to disk atomically.

        Serialized by _SETTINGS_LOCK so the GUI thread and a plugin worker
        thread (which now share ONE document) can't race on the temp file.
        os.replace swaps the target in a SINGLE atomic step on both Windows and
        POSIX, so there is never a window where settings.json is absent — the
        old delete-then-rename could crash into exactly that gap and, since
        load() didn't recover the .bak, silently wipe the user's profile.
        """
        with _SETTINGS_LOCK:
            # Encode first. If another thread mutates the shared document
            # mid-encode we get "dictionary changed size during iteration";
            # retry a few times, then defer this save to the next write rather
            # than raising (the in-memory document is the shared source of
            # truth and isn't lost — and raising here would flip a successful
            # plugin run to ERROR in the executor).
            payload = None
            for _ in range(8):
                try:
                    payload = json.dumps(self.data, indent=2)
                    break
                except RuntimeError:
                    continue
            if payload is None:
                print("Warning: settings save skipped (document busy); "
                      "will persist on the next write")
                return

            try:
                temp_fd, temp_path = tempfile.mkstemp(
                    suffix='.tmp',
                    prefix='settings_',
                    dir=self.settings_dir,
                    text=True
                )
                try:
                    with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                        f.write(payload)
                        f.flush()
                        os.fsync(f.fileno())

                    # Atomic swap, retried for the transient Windows "Access is
                    # denied" that Defender/the search indexer/OneDrive throw when
                    # they briefly hold a handle on the temp or target file.
                    last_err: Optional[BaseException] = None
                    for attempt in range(5):
                        try:
                            os.replace(temp_path, self.settings_file)
                            last_err = None
                            break
                        except PermissionError as e:
                            last_err = e
                            time.sleep(0.1 * (attempt + 1))
                    if last_err is not None:
                        raise last_err

                    # Refresh the backup FROM the good file we just wrote (never
                    # from the pre-existing live file — if that was externally
                    # corrupted, copying it would poison the .bak and defeat
                    # recovery). Best-effort: a miss just leaves the prior .bak.
                    try:
                        shutil.copy2(self.settings_file,
                                     self.settings_file.with_suffix('.bak'))
                    except OSError:
                        pass
                except Exception:
                    # Clean up temp file on error
                    if Path(temp_path).exists():
                        try:
                            Path(temp_path).unlink()
                        except OSError:
                            pass
                    raise
            except (IOError, OSError) as e:
                # Defer rather than raise: a raise here propagates into the
                # plugin executor and flips a SUCCESSFUL run to ERROR. The
                # in-memory document is intact and the next write retries.
                print(f"Warning: settings save deferred ({e}); "
                      "will retry on the next write")
    
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

        # Migrate the renamed "salmon" theme -> "cherry_blossom"
        if self.data.get("settings", {}).get("theme") == "salmon":
            self.data["settings"]["theme"] = "cherry_blossom"

        # Repair total_runs frozen by the pre-singleton settings race
        self._backfill_total_runs()

        self.save()

    def _backfill_total_runs(self) -> None:
        """Repair a total_runs counter frozen by the pre-singleton settings race.

        Before SettingsManager became a shared singleton, the executor's
        worker-thread total_runs bump was silently reverted by the shell's
        stale-snapshot ticket write after every run — so total_runs sat frozen
        while the shell-written family_runs tallies kept climbing (reported as
        the first four achievements never progressing while the family ones
        did). Those family tallies are a trustworthy floor: every tallied run
        was also a total run. Monotonic and idempotent — only ever raises
        total_runs; once repaired, both counters advance together and this is
        a no-op. The tree's planting stamp shifts by the same delta so the
        repair doesn't instantly fast-forward its growth.
        """
        settings = self.data.setdefault("settings", {})
        family_runs = settings.get("family_runs", {})
        if not isinstance(family_runs, dict):
            return
        floor = sum(int(v) for v in family_runs.values())
        current = int(settings.get("total_runs", 0))
        if floor <= current:
            return
        delta = floor - current
        settings["total_runs"] = floor
        if "tree_planted_runs" in settings:
            settings["tree_planted_runs"] = int(settings["tree_planted_runs"]) + delta
    
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
        # Rename dict keys in plugin_settings and plugin_stats; drop retired ones.
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
            for removed_id in _REMOVED_PLUGIN_IDS:
                bucket.pop(removed_id, None)

        # Rewrite tile references in every profile (preserve order, dedupe);
        # a retired plugin is dropped entirely.
        for profile in self.data.get("profiles", {}).values():
            tiles = profile.get("tiles")
            if not isinstance(tiles, list):
                continue
            new_tiles: List[str] = []
            for tile in tiles:
                mapped = _PLUGIN_ID_RENAMES.get(tile, tile)
                if mapped in _REMOVED_PLUGIN_IDS:
                    continue
                if mapped not in new_tiles:
                    new_tiles.append(mapped)
            profile["tiles"] = new_tiles

        # Rewrite Emporium purchases: locked plugins are unlocked by their
        # plugin id, so a rename must carry the purchase over or the user
        # loses a game they paid tickets for (preserve order, dedupe).
        unlocked = self.data.get("settings", {}).get("unlocked_items")
        if isinstance(unlocked, list):
            new_unlocked: List[str] = []
            for item in unlocked:
                mapped = _PLUGIN_ID_RENAMES.get(item, item)
                if mapped not in new_unlocked:
                    new_unlocked.append(mapped)
            self.data["settings"]["unlocked_items"] = new_unlocked

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

    def is_professional(self) -> bool:
        """Professional theme: the light look with the playful features (Ticket
        Counter, My Stuff, My House, games, tickets, fidget) hidden — for client
        presentations."""
        return self.get_theme() == "professional"

    def get_dev_mode_enabled(self) -> bool:
        """Persisted state of the Home dev-mode toggle. Only source builds read
        this (techdeck.ui.dev_mode gates on is_dev_build) — a frozen exe never
        consults it, so a stray true can't surface DevKit in a shipped build."""
        return bool(self.data.get("settings", {}).get("dev_mode", False))

    def set_dev_mode_enabled(self, enabled: bool) -> None:
        if "settings" not in self.data:
            self.data["settings"] = {}
        self.data["settings"]["dev_mode"] = bool(enabled)
        self.save()

    # Library page tile sort. "alphabetical" sorts by plugin display name;
    # "family" groups by 911 -> 922 -> General, alphabetical within each group.
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

    # ---- Feedback "Which Feature?" list state -------------------------------
    # Reconciliation state for the Submit Feedback dropdown (see
    # techdeck.core.feedback_features): the last-seen live plugin roster plus a
    # retired-entry map with per-entry version-update counters. Stored as an
    # opaque blob at the top level of settings.json.

    def get_feedback_feature_state(self) -> Dict[str, Any]:
        state = self.data.get("feedback_features")
        return state if isinstance(state, dict) else {}

    def set_feedback_feature_state(self, state: Dict[str, Any]) -> None:
        self.data["feedback_features"] = dict(state)
        self.save()

    # ---- Remembered master-toggle selections --------------------------------
    # What each plugin's GroupedToggleDialog was last submitted with, keyed by
    # a caller-chosen memory key (normally the plugin id). Lives at the top
    # level of settings.json rather than under plugin_settings, so it can never
    # collide with a plugin's own Settings > Apps fields.
    #
    # Kept here (not in the plugin folder) so it survives an app update: the
    # installer replaces plugins/, but %LOCALAPPDATA%\TechDeck\settings.json is
    # user data and is left alone. Asked for by A.T. 2026-08-07 -- Saco was
    # re-unticking the same two toggles on every single 911 Setup run.

    def get_toggle_memory(self, memory_key: str) -> Dict[str, Any]:
        store = self.data.get("toggle_memory")
        if not isinstance(store, dict):
            return {}
        remembered = store.get(memory_key)
        return remembered if isinstance(remembered, dict) else {}

    def set_toggle_memory(self, memory_key: str, state: Dict[str, Any]) -> None:
        store = self.data.get("toggle_memory")
        if not isinstance(store, dict):
            store = {}
        store[memory_key] = dict(state)
        self.data["toggle_memory"] = store
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
        """Record a successful run: bump run_count, reset consecutive_errors,
        and bump the lifetime total (drives My House tree growth)."""
        if "plugin_stats" not in self.data:
            self.data["plugin_stats"] = {}
        stats = self.data["plugin_stats"].setdefault(plugin_id, {})
        stats["run_count"] = stats.get("run_count", 0) + 1
        stats["consecutive_errors"] = 0
        self.data.setdefault("settings", {})["total_runs"] = self.get_total_runs() + 1
        self.save()

    # ========== My House tree growth ==========
    # The tree grows one stage per TREE_RUNS_PER_STAGE plugin runs since the
    # sapling is planted: sapling (1) -> full grown (5) = 4 steps, ~a month of
    # use at 50 runs/stage. Tunable here.
    TREE_STAGES = 5
    TREE_RUNS_PER_STAGE = 50

    def get_total_runs(self) -> int:
        """Lifetime successful plugin runs."""
        return int(self.data.get("settings", {}).get("total_runs", 0))

    def plant_tree(self) -> None:
        """Stamp the planting moment (run count) so the sapling grows from now."""
        self.data.setdefault("settings", {})["tree_planted_runs"] = self.get_total_runs()
        self.save()

    def get_tree_stage(self) -> int:
        """0 = unplanted (no sapling owned); 1 = sapling ... 5 = full grown."""
        if "deco_sapling" not in self.get_unlocked_items():
            return 0
        planted = int(self.data.get("settings", {}).get("tree_planted_runs", 0))
        grown = max(0, self.get_total_runs() - planted) // self.TREE_RUNS_PER_STAGE
        return min(self.TREE_STAGES, 1 + grown)

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

    # ========== Tickets / Woogy's Emporium ==========

    # Fresh profiles (no "tickets" key yet) start with enough for exactly one
    # toy at Woogy's Emporium (cheapest toy = Beyblade, 60) with a little left
    # over. Existing balances are untouched - the default only applies while
    # the key is absent; the first earn/spend persists a real value.
    STARTING_TICKETS = 75

    def get_tickets(self) -> int:
        """Tickets the user has earned (spent at Woogy's Emporium)."""
        return int(self.data.get("settings", {}).get("tickets", self.STARTING_TICKETS))

    def add_tickets(self, amount: int) -> int:
        """Award tickets; returns the new balance."""
        if "settings" not in self.data:
            self.data["settings"] = {}
        bal = max(0, self.get_tickets() + int(amount))
        self.data["settings"]["tickets"] = bal
        self.save()
        return bal

    def spend_tickets(self, amount: int) -> bool:
        """Deduct tickets if affordable. Returns True on success."""
        amount = int(amount)
        if amount < 0 or self.get_tickets() < amount:
            return False
        self.data.setdefault("settings", {})["tickets"] = self.get_tickets() - amount
        self.save()
        return True

    def get_unlocked_items(self) -> list:
        """IDs of catalog items the user has purchased."""
        return list(self.data.get("settings", {}).get("unlocked_items", []))

    def is_unlocked(self, item_id: str) -> bool:
        return item_id in self.get_unlocked_items()

    def unlock_item(self, item_id: str) -> None:
        items = self.get_unlocked_items()
        if item_id not in items:
            items.append(item_id)
            self.data.setdefault("settings", {})["unlocked_items"] = items
            self.save()

    # ========== Achievements ==========

    def record_family_run(self, family: str) -> None:
        """Tally a successful run by plugin family (drives family achievements)."""
        if not family:
            return
        runs = self.data.setdefault("settings", {}).setdefault("family_runs", {})
        runs[family] = int(runs.get(family, 0)) + 1
        self.save()

    def get_family_runs(self, family: str) -> int:
        """Lifetime successful runs of plugins in the given family."""
        return int(self.data.get("settings", {}).get("family_runs", {}).get(family, 0))

    def record_run_batch(self, count: int) -> None:
        """Remember the largest number of plugins ever launched together in one run."""
        count = int(count)
        if count > self.get_max_run_batch():
            self.data.setdefault("settings", {})["max_run_batch"] = count
            self.save()

    def get_max_run_batch(self) -> int:
        """Most plugins ever queued in a single multi-run."""
        return int(self.data.get("settings", {}).get("max_run_batch", 0))

    def get_claimed_achievements(self) -> list:
        """IDs of achievements whose ticket reward has already been claimed."""
        return list(self.data.get("settings", {}).get("claimed_achievements", []))

    def is_achievement_claimed(self, achievement_id: str) -> bool:
        return achievement_id in self.get_claimed_achievements()

    def claim_achievement(self, achievement_id: str) -> None:
        """Mark an achievement claimed so its reward can't be collected twice."""
        claimed = self.get_claimed_achievements()
        if achievement_id not in claimed:
            claimed.append(achievement_id)
            self.data.setdefault("settings", {})["claimed_achievements"] = claimed
            self.save()

    def reset_store(self) -> None:
        """Wipe all Emporium purchases: clear unlocked items + equipped spinner
        + equipped background (re-locks purchasable plugins, reverts the My House
        wallpaper to default). Tickets are left untouched."""
        s = self.data.setdefault("settings", {})
        s["unlocked_items"] = []
        s["equipped_spinner"] = None
        s["equipped_background"] = None
        s["beyblade_build"] = None      # parts are re-locked; the build with them
        self.save()

    def get_equipped_spinner(self) -> Optional[str]:
        """Item id of the equipped fidget-spinner skin, or None for default."""
        return self.data.get("settings", {}).get("equipped_spinner")

    def set_equipped_spinner(self, item_id: Optional[str]) -> None:
        self.data.setdefault("settings", {})["equipped_spinner"] = item_id
        self.save()

    def get_beyblade_build(self) -> Optional[str]:
        """The last combination the player assembled in the beyblade builder.

        Kept SEPARATE from `equipped_spinner` on purpose: the equipped slot is
        whatever they are spinning right now, and equipping a plain spinner
        would otherwise erase the fact that they ever built anything. This is
        what the "Build Your Own" tile shows, so their build stays on the tile
        regardless of what is currently equipped.
        """
        return self.data.get("settings", {}).get("beyblade_build")

    def set_beyblade_build(self, variant: Optional[str]) -> None:
        self.data.setdefault("settings", {})["beyblade_build"] = variant
        self.save()

    # The My House / Garden background wallpaper. Stored as the sprite FILENAME
    # (matches the catalog item's "sprite"); defaults to the red-check backdrop.
    DEFAULT_BACKGROUND = "sLibraryBG_4.png"

    def get_equipped_background(self) -> str:
        """Filename of the equipped My House background; defaults to sLibraryBG_4."""
        return (self.data.get("settings", {}).get("equipped_background")
                or self.DEFAULT_BACKGROUND)

    def set_equipped_background(self, name: Optional[str]) -> None:
        self.data.setdefault("settings", {})["equipped_background"] = name
        self.save()

    # ========== Shelf (Phase D — single-slot snapshot of a paused/queued run) ==========

    def get_shelf(self) -> Optional[Dict[str, Any]]:
        """Return the current shelf entry, or None if empty.

        Shape:
            {
              "stored_at": ISO8601 UTC timestamp,
              "remaining_tile_ids": [str, ...],
              "shared_state": {"911": {...}, "922": {...}, "General": {...}},
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

    # Ships with the build (assets/roguemode); seeded into the user's library
    # on first run so a fresh install isn't silent.
    DEFAULT_ROGUE_TRACK = "Love On A Real Train - Tangerine Dream.mp3"

    def ensure_roguemode_default_track(self) -> None:
        """One-time seed of the bundled default Rogue Mode track.

        Fresh installs have an empty roguemode library. Copy the bundled
        track into the user's audio dir and register it in the Default
        playlist. Guarded by a seeded flag so a user who deletes the track
        later doesn't get it forced back on every launch.
        """
        rm = self.get_roguemode_settings()
        if rm.get("default_track_seeded"):
            return
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            src_dir = Path(sys._MEIPASS) / "assets" / "roguemode"
        else:
            src_dir = Path(__file__).resolve().parents[2] / "assets" / "roguemode"
        src = src_dir / self.DEFAULT_ROGUE_TRACK
        rm["default_track_seeded"] = True
        if src.is_file():
            try:
                dest = self.get_roguemode_audio_dir() / src.name
                if not dest.exists():
                    shutil.copyfile(src, dest)
                playlist = rm.setdefault("playlists", {}).setdefault("Default", [])
                if dest.name not in playlist:
                    playlist.append(dest.name)
            except Exception:
                pass  # never let seeding break startup; flag stays set
        self.set_roguemode_settings(rm)

    # ========== Helpers ==========

    @staticmethod
    def _utc_iso() -> str:
        """Get current UTC timestamp in ISO 8601 format."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
