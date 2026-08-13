"""
TechDeck Admin Configuration Manager
Handles role-based access control and company-wide settings.

Admin config is stored in ProgramData (system-wide, requires admin to modify).
User config is stored in LocalAppData (per-user, user-writable).
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


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
                logger.warning("Could not load admin config: %s", e)
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
            logger.error("Could not save admin config (requires admin): %s", e)
            return False
    
    def _get_defaults(self) -> Dict[str, Any]:
        """Get default admin configuration."""
        return {
            "version": "1.0.0",
            "user_role": UserRole.USER.value,
            "locked": False,  # If true, only super_admin can modify
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
    
    # NOTE: The plugin allow/deny-list, mandatory-plugins, company-API-key,
    # configurable-update-URL, and install/profile permission gates were never
    # wired into loading or execution — pure scaffolding — so they were removed.
    # Only role state (below) is live, gating the /admin console command. If a
    # real policy need appears, reintroduce enforcement at the call site, not
    # just the accessor.

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
