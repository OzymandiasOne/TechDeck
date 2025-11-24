"""
TechDeck Update Checker
Handles automatic update detection and notification.

Checks for updates from GitHub Pages manifest, supports mandatory updates,
and provides version comparison.
"""

import requests
import threading
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from datetime import datetime, timedelta
from packaging import version


class UpdateInfo:
    """Information about an available update."""
    
    def __init__(self, data: Dict[str, Any]):
        # Support both old and new manifest formats
        self.version: str = data.get("latest_version") or data.get("version", "0.0.0")
        self.download_url: str = data.get("download_url", "")
        self.critical: bool = data.get("critical", False)
        self.release_notes: str = data.get("release_notes", "")
        self.min_version: str = data.get("min_supported_version") or data.get("min_version", "0.0.0")
        
        # Legacy support for 'mandatory' field
        if data.get("mandatory", False):
            self.critical = True
    
    def is_newer_than(self, current_version: str) -> bool:
        """Check if this update is newer than current version."""
        try:
            return version.parse(self.version) > version.parse(current_version)
        except Exception:
            return False
    
    def requires_mandatory_update(self, current_version: str) -> bool:
        """
        Check if update is mandatory.
        
        An update is mandatory if:
        - The 'critical' flag is set, OR
        - The current version is below min_supported_version
        """
        try:
            is_critical = self.critical
            is_below_min = version.parse(current_version) < version.parse(self.min_version)
            return is_critical or is_below_min
        except Exception:
            return False


class UpdateChecker:
    """
    Checks for application updates from GitHub Pages.
    
    Usage:
        checker = UpdateChecker(
            current_version="0.7.0",
            update_url="https://ozymandiasone.github.io/TechDeck-updates/manifest.json",
            check_interval_hours=24
        )
        
        checker.set_update_callback(lambda info: print(f"Update available: {info.version}"))
        checker.start()
    """
    
    def __init__(
        self,
        current_version: str,
        update_url: str,
        check_interval_hours: int = 24,
        timeout: int = 10
    ):
        """
        Initialize update checker.
        
        Args:
            current_version: Current app version (e.g., "0.7.0")
            update_url: URL to manifest.json on GitHub Pages
            check_interval_hours: Hours between update checks
            timeout: HTTP request timeout in seconds
        """
        self.current_version = current_version
        self.update_url = update_url
        self.check_interval = check_interval_hours * 3600  # Convert to seconds
        self.timeout = timeout
        
        # Callbacks
        self.update_available_callback: Optional[Callable[[UpdateInfo], None]] = None
        self.mandatory_update_callback: Optional[Callable[[UpdateInfo], None]] = None
        self.error_callback: Optional[Callable[[str], None]] = None
        
        # State
        self.is_running = False
        self.check_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        
        # Last check time
        self.last_check_time: Optional[datetime] = None
        self.latest_update_info: Optional[UpdateInfo] = None
    
    def set_update_callback(self, callback: Callable[[UpdateInfo], None]) -> None:
        """Set callback for when non-mandatory update is available."""
        self.update_available_callback = callback
    
    def set_mandatory_update_callback(self, callback: Callable[[UpdateInfo], None]) -> None:
        """Set callback for when mandatory update is required."""
        self.mandatory_update_callback = callback
    
    def set_error_callback(self, callback: Callable[[str], None]) -> None:
        """Set callback for when update check fails."""
        self.error_callback = callback
    
    def start(self) -> None:
        """Start background update checking."""
        if self.is_running:
            return
        
        self.is_running = True
        self.stop_event.clear()
        
        self.check_thread = threading.Thread(
            target=self._check_loop,
            name="UpdateChecker",
            daemon=True
        )
        self.check_thread.start()
    
    def stop(self) -> None:
        """Stop background update checking."""
        if not self.is_running:
            return
        
        self.is_running = False
        self.stop_event.set()
        
        if self.check_thread:
            self.check_thread.join(timeout=2)
    
    def check_now(self) -> Optional[UpdateInfo]:
        """
        Check for updates immediately (blocking).
        
        Returns:
            UpdateInfo if update available, None otherwise
        """
        try:
            response = requests.get(
                self.update_url,
                timeout=self.timeout,
                headers={'User-Agent': f'TechDeck/{self.current_version}'}
            )
            
            if response.status_code != 200:
                self._handle_error(f"Update check failed: HTTP {response.status_code}")
                return None
            
            data = response.json()
            update_info = UpdateInfo(data)
            
            self.last_check_time = datetime.now()
            self.latest_update_info = update_info
            
            # Check if update is available
            if update_info.is_newer_than(self.current_version):
                # Check if it's mandatory
                if update_info.requires_mandatory_update(self.current_version):
                    self._handle_mandatory_update(update_info)
                else:
                    self._handle_update_available(update_info)
                
                return update_info
            
            return None
            
        except requests.RequestException as e:
            self._handle_error(f"Update check failed: {str(e)}")
            return None
        except Exception as e:
            self._handle_error(f"Update check error: {str(e)}")
            return None
    
    def _check_loop(self) -> None:
        """Background thread that checks for updates periodically."""
        # Check immediately on start
        self.check_now()
        
        while not self.stop_event.is_set():
            # Wait for check interval (with early exit on stop)
            if self.stop_event.wait(timeout=self.check_interval):
                break
            
            # Check for updates
            self.check_now()
    
    def _handle_update_available(self, info: UpdateInfo) -> None:
        """Handle optional update notification."""
        if self.update_available_callback:
            try:
                self.update_available_callback(info)
            except Exception as e:
                print(f"Error in update callback: {e}")
    
    def _handle_mandatory_update(self, info: UpdateInfo) -> None:
        """Handle mandatory update notification."""
        if self.mandatory_update_callback:
            try:
                self.mandatory_update_callback(info)
            except Exception as e:
                print(f"Error in mandatory update callback: {e}")
    
    def _handle_error(self, error_msg: str) -> None:
        """Handle update check error."""
        if self.error_callback:
            try:
                self.error_callback(error_msg)
            except Exception as e:
                print(f"Error in error callback: {e}")
    
    def get_time_since_last_check(self) -> Optional[timedelta]:
        """Get time elapsed since last successful check."""
        if self.last_check_time is None:
            return None
        return datetime.now() - self.last_check_time
    
    def should_check_now(self) -> bool:
        """Check if enough time has passed for another update check."""
        if self.last_check_time is None:
            return True
        
        time_since = self.get_time_since_last_check()
        if time_since is None:
            return True
        
        return time_since.total_seconds() >= self.check_interval
