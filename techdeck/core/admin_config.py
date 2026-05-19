"""
TechDeck Admin Configuration Manager
Handles role-based access control and company-wide settings.

Admin config is stored in ProgramData (system-wide, requires admin to modify).
User config is stored in LocalAppData (per-user, user-writable).
"""

import json
import os
from pathlib import Path
from typing import Optional, Dict, Any
from enum import Enum


class UserRole(Enum):
    """User access levels."""
    USER = "user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


class AdminConfigManager:
    r"""
    Manages admin configuration for role-based access control.
    
    Admin config location:
    - Windows: C:\ProgramData\TechDeck\admin.config
    - Linux: /etc/TechDeck/admin.config
    - macOS: /Library/Application Support/TechDeck/admin.config
    
    Only admins can modify this file.
    """
        
    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize admin config manager.
        
        Args:
            config_dir: Custom config directory (for testing)
        """
        if config_dir is None:
            if os.name == 'nt':
                # Windows: ProgramData
                base = Path(os.environ.get('PROGRAMDATA', 'C:\\ProgramData'))
            elif os.name == 'posix':
                # Linux/Unix
                base = Path('/etc')
            else:
                # macOS
                base = Path('/Library/Application Support')
            
            config_dir = base / 'TechDeck'
        
        self.config_dir = Path(config_dir)
        self.config_file = self.config_dir / 'admin.config'
        
        # Cache loaded config
        self._config: Optional[Dict[str, Any]] = None
        
        # Try to create directory (may fail if not admin - that's OK)
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError):
            pass
        
        # Load existing config
        self.load()
    
    def load(self) -> Dict[str, Any]:
        """
        Load admin configuration from disk.
        
        Returns:
            Admin config dict (or defaults if file doesn't exist)
        """
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
            except (json.JSONDecodeError, IOError, PermissionError) as e:
                print(f"Warning: Could not load admin config: {e}")
                self._config = self._get_defaults()
        else:
            self._config = self._get_defaults()
        
        return self._config
    
    def save(self) -> bool:
        """
        Save admin configuration to disk.
        
        Returns:
            True if saved successfully, False if permission denied
        """
        if self._config is None:
            return False
        
        try:
            # Ensure directory exists
            self.config_dir.mkdir(parents=True, exist_ok=True)
            
            # Save config
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2)
            
            return True
            
        except (IOError, PermissionError) as e:
            print(f"Error: Could not save admin config (requires admin): {e}")
            return False
    
    def _get_defaults(self) -> Dict[str, Any]:
        """Get default admin configuration."""
        return {
            "version": "1.0.0",
            "user_role": UserRole.USER.value,
            "company_api_key": "",
            "update_url": "",
            "plugin_whitelist": [],  # Empty = all plugins allowed
            "plugin_blacklist": [],  # Explicitly blocked plugins
            "mandatory_plugins": [],  # Plugins that must be installed
            "allow_plugin_install": True,
            "allow_custom_profiles": True,
            "locked": False  # If true, only super_admin can modify
        }
    
    # ========== Role Management ==========
    
    def get_user_role(self) -> UserRole:
        """Get current user's role."""
        role_str = self._config.get("user_role", UserRole.USER.value)
        try:
            return UserRole(role_str)
        except ValueError:
            return UserRole.USER
    
    def set_user_role(self, role: UserRole) -> bool:
        """
        Set user role (requires super_admin if locked).
        
        Args:
            role: New role to set
            
        Returns:
            True if successful, False if permission denied
        """
        if self._config.get("locked", False):
            if self.get_user_role() != UserRole.SUPER_ADMIN:
                return False
        
        self._config["user_role"] = role.value
        return self.save()
    
    def is_admin(self) -> bool:
        """Check if current user is admin or super_admin."""
        role = self.get_user_role()
        return role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]
    
    def is_super_admin(self) -> bool:
        """Check if current user is super_admin."""
        return self.get_user_role() == UserRole.SUPER_ADMIN
    
    # ========== API Key Management ==========
    
    def get_api_key(self) -> str:
        """Get company API key (read-only for users)."""
        return self._config.get("company_api_key", "")
    
    def set_api_key(self, key: str) -> bool:
        """
        Set company API key (requires admin).
        
        Args:
            key: New API key
            
        Returns:
            True if successful, False if permission denied
        """
        if not self.is_admin():
            return False
        
        self._config["company_api_key"] = key
        return self.save()
    
    # ========== Update Management ==========
    
    def get_update_url(self) -> str:
        """Get update server URL."""
        return self._config.get("update_url", "")
    
    def set_update_url(self, url: str) -> bool:
        """
        Set update server URL (requires admin).
        
        Args:
            url: New update URL
            
        Returns:
            True if successful, False if permission denied
        """
        if not self.is_admin():
            return False
        
        self._config["update_url"] = url
        return self.save()
    
    # ========== Plugin Management ==========
    
    def is_plugin_allowed(self, plugin_id: str) -> bool:
        """
        Check if a plugin is allowed to run.
        
        Args:
            plugin_id: Plugin ID to check
            
        Returns:
            True if plugin is allowed
        """
        # Check blacklist first
        blacklist = self._config.get("plugin_blacklist", [])
        if plugin_id in blacklist:
            return False
        
        # Check whitelist (empty = all allowed)
        whitelist = self._config.get("plugin_whitelist", [])
        if not whitelist:
            return True
        
        return plugin_id in whitelist
    
    def get_mandatory_plugins(self) -> list[str]:
        """Get list of plugins that must be installed."""
        return self._config.get("mandatory_plugins", [])
    
    def set_plugin_whitelist(self, plugin_ids: list[str]) -> bool:
        """
        Set plugin whitelist (requires admin).
        Empty list = all plugins allowed.
        
        Args:
            plugin_ids: List of allowed plugin IDs
            
        Returns:
            True if successful, False if permission denied
        """
        if not self.is_admin():
            return False
        
        self._config["plugin_whitelist"] = plugin_ids
        return self.save()
    
    def set_plugin_blacklist(self, plugin_ids: list[str]) -> bool:
        """
        Set plugin blacklist (requires admin).
        
        Args:
            plugin_ids: List of blocked plugin IDs
            
        Returns:
            True if successful, False if permission denied
        """
        if not self.is_admin():
            return False
        
        self._config["plugin_blacklist"] = plugin_ids
        return self.save()
    
    def set_mandatory_plugins(self, plugin_ids: list[str]) -> bool:
        """
        Set mandatory plugins (requires admin).
        
        Args:
            plugin_ids: List of required plugin IDs
            
        Returns:
            True if successful, False if permission denied
        """
        if not self.is_admin():
            return False
        
        self._config["mandatory_plugins"] = plugin_ids
        return self.save()
    
    # ========== Permission Checks ==========
    
    def can_install_plugins(self) -> bool:
        """Check if user can install new plugins."""
        if not self._config.get("allow_plugin_install", True):
            return self.is_admin()
        return True
    
    def can_create_profiles(self) -> bool:
        """Check if user can create custom profiles."""
        if not self._config.get("allow_custom_profiles", True):
            return self.is_admin()
        return True
    
    # ========== Configuration Lock ==========
    
    def is_locked(self) -> bool:
        """Check if configuration is locked (requires super_admin to modify)."""
        return self._config.get("locked", False)
    
    def set_locked(self, locked: bool) -> bool:
        """
        Lock/unlock configuration (requires super_admin).
        
        Args:
            locked: True to lock, False to unlock
            
        Returns:
            True if successful, False if permission denied
        """
        if not self.is_super_admin():
            return False
        
        self._config["locked"] = locked
        return self.save()
    
    # ========== Helper Methods ==========
    
    def exists(self) -> bool:
        """Check if admin config file exists."""
        return self.config_file.exists()
    
    def get_config_path(self) -> Path:
        """Get path to admin config file."""
        return self.config_file
    
    def create_default_config(self) -> bool:
        """
        Create default admin config file (requires admin).
        
        Returns:
            True if created, False if permission denied
        """
        if self.exists():
            return True
        
        self._config = self._get_defaults()
        return self.save()
