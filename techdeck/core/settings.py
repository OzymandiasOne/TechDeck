"""
TechDeck Settings Manager
Handles loading, saving, and validating application settings.
Manages profiles, user data, app configuration, and plugin settings.

PHASE 2 FIX: Added atomic writes (temp file + rename) to prevent corruption on crashes
PHASE 2 FIX: Added basic API key encryption for secure storage at rest
"""

import json
import os
import base64
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


class SettingsManager:
    """
    Manages application settings and profiles.
    
    Responsibilities:
    - Load/save settings.json with atomic writes (PHASE 2)
    - Profile CRUD operations
    - Plugin settings management
    - API key encryption/decryption (PHASE 2)
    - Data validation and migrations
    - Ensure Default profile always exists
    """
    
    # PHASE 2: Simple XOR encryption key (obfuscation, not cryptographic security)
    # For true security, use Windows DPAPI or keyring library
    _ENCRYPTION_KEY = b"TechDeck_v1_Local_Storage_Key_2024"
    
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
        """
        PHASE 2 FIX: Save current settings to disk using atomic write.
        
        Uses temporary file + rename pattern to ensure settings are never
        left in a corrupted state if the process crashes during write.
        """
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
                # PHASE 2: Removed console_height - users drag to preferred height
                "api_key": "",
                "api_usage": {
                    "tokens_used": 0,
                    "last_reset": now
                }
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
            now = self._utc_iso()
            self.data["settings"] = {
                "theme": "dark",
                "api_key": "",
                "api_usage": {
                    "tokens_used": 0,
                    "last_reset": now
                }
            }
        
        # PHASE 2: Remove console_height if it exists (migration)
        if "console_height" in self.data.get("settings", {}):
            del self.data["settings"]["console_height"]
        
        # Ensure plugin_settings exists
        if "plugin_settings" not in self.data:
            self.data["plugin_settings"] = {}
        
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
    
    # ========== PHASE 2: API Key Encryption/Decryption ==========
    
    @classmethod
    def _encrypt_api_key(cls, api_key: str) -> str:
        """
        PHASE 2: Encrypt API key using simple XOR cipher with base64 encoding.
        
        Note: This is obfuscation, not cryptographic security. For production,
        consider using Windows DPAPI (via pywin32) or the keyring library.
        
        Args:
            api_key: Plain text API key
            
        Returns:
            Base64-encoded encrypted string
        """
        if not api_key:
            return ""
        
        # XOR encryption
        key_bytes = cls._ENCRYPTION_KEY
        encrypted = bytearray()
        
        for i, char in enumerate(api_key.encode('utf-8')):
            encrypted.append(char ^ key_bytes[i % len(key_bytes)])
        
        # Base64 encode for storage
        return base64.b64encode(bytes(encrypted)).decode('utf-8')
    
    @classmethod
    def _decrypt_api_key(cls, encrypted_key: str) -> str:
        """
        PHASE 2: Decrypt API key.
        
        Args:
            encrypted_key: Base64-encoded encrypted string
            
        Returns:
            Plain text API key
        """
        if not encrypted_key:
            return ""
        
        try:
            # Base64 decode
            encrypted_bytes = base64.b64decode(encrypted_key.encode('utf-8'))
            
            # XOR decryption (same as encryption)
            key_bytes = cls._ENCRYPTION_KEY
            decrypted = bytearray()
            
            for i, byte in enumerate(encrypted_bytes):
                decrypted.append(byte ^ key_bytes[i % len(key_bytes)])
            
            return decrypted.decode('utf-8')
        except Exception as e:
            print(f"Warning: Could not decrypt API key: {e}")
            return ""
    
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
    
    def get_api_key(self) -> str:
        """
        PHASE 2: Get OpenAI API key (decrypted).
        
        Returns:
            Plain text API key
        """
        encrypted = self.data.get("settings", {}).get("api_key", "")
        
        # Check if it looks like an encrypted key (base64)
        if encrypted and not encrypted.startswith("sk-"):
            # Decrypt it
            return self._decrypt_api_key(encrypted)
        
        # If it starts with "sk-", it's already plain text (legacy)
        # Return as-is and re-save encrypted on next set
        return encrypted
    
    def set_api_key(self, key: str) -> None:
        """
        PHASE 2: Set OpenAI API key (encrypted before storage).
        
        Args:
            key: Plain text API key
        """
        if "settings" not in self.data:
            self.data["settings"] = {}
        
        # Encrypt the key before storing
        encrypted = self._encrypt_api_key(key)
        self.data["settings"]["api_key"] = encrypted
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
    
    # ========== Helpers ==========
    
    @staticmethod
    def _utc_iso() -> str:
        """Get current UTC timestamp in ISO 8601 format."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
