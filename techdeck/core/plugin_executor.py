"""
TechDeck Plugin Executor
Handles loading, validation, and execution of plugins with progress tracking and cancellation.
"""

import threading
import time
from typing import Dict, Any, Callable, Optional
from dataclasses import dataclass
from enum import Enum

from techdeck.core.plugin_loader import PluginLoader, Plugin


class PluginStatus(Enum):
    """Plugin execution status."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass
class PluginResult:
    """Result of plugin execution."""
    plugin_id: str
    status: PluginStatus
    message: str
    progress: int = 0
    error: Optional[str] = None


class PluginExecutor:
    """
    Manages plugin execution with progress tracking and cancellation support.
    
    Features:
    - Thread-based execution
    - Progress callbacks
    - Cancellation via threading.Event
    - Error handling and reporting
    - Console output integration
    """
    
    def __init__(self, plugin_loader: PluginLoader):
        """
        Initialize plugin executor.
        
        Args:
            plugin_loader: PluginLoader instance for discovering plugins
        """
        self.plugin_loader = plugin_loader
        self.running_threads: Dict[str, threading.Thread] = {}
        self.cancel_events: Dict[str, threading.Event] = {}
        self.results: Dict[str, PluginResult] = {}
    
    def execute_plugin(
        self,
        plugin_id: str,
        params: Optional[Dict[str, Any]] = None,
        log_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
        completion_callback: Optional[Callable[[PluginResult], None]] = None
    ) -> bool:
        """
        Execute a plugin in a separate thread.
        
        Args:
            plugin_id: ID of plugin to execute
            params: Optional parameters to pass to plugin
            log_callback: Function to call with log messages
            progress_callback: Function to call with progress (0-100)
            completion_callback: Function to call when plugin completes
            
        Returns:
            True if execution started, False if plugin not found or invalid
        """
        # Get plugin metadata
        plugin = self.plugin_loader.get_plugin(plugin_id)
        if not plugin:
            if log_callback:
                log_callback(f"Plugin not found: {plugin_id}")
            return False
        
        # Validate plugin before execution
        is_valid, error_msg = self.plugin_loader.validate_plugin(plugin_id)
        if not is_valid:
            if log_callback:
                log_callback(f"Plugin validation failed: {error_msg}")
            return False
        
        # Check if already running
        if plugin_id in self.running_threads and self.running_threads[plugin_id].is_alive():
            if log_callback:
                log_callback(f"Plugin {plugin_id} is already running")
            return False
        
        # Create cancel event
        cancel_event = threading.Event()
        self.cancel_events[plugin_id] = cancel_event
        
        # Initialize result
        self.results[plugin_id] = PluginResult(
            plugin_id=plugin_id,
            status=PluginStatus.PENDING,
            message="Starting...",
            progress=0
        )
        
        # Create execution thread
        thread = threading.Thread(
            target=self._execute_plugin_thread,
            args=(plugin, params or {}, log_callback, progress_callback, 
                  completion_callback, cancel_event),
            name=f"Plugin-{plugin_id}",
            daemon=True
        )
        
        self.running_threads[plugin_id] = thread
        thread.start()
        
        return True
    
    def _execute_plugin_thread(
        self,
        plugin: Plugin,
        params: Dict[str, Any],
        log_callback: Optional[Callable[[str], None]],
        progress_callback: Optional[Callable[[int], None]],
        completion_callback: Optional[Callable[[PluginResult], None]],
        cancel_event: threading.Event
    ) -> None:
        """
        Internal method that runs in the plugin thread.
        
        Args:
            plugin: Plugin object to execute
            params: Parameters to pass to plugin
            log_callback: Logging callback
            progress_callback: Progress callback
            completion_callback: Completion callback
            cancel_event: Event to check for cancellation
        """
        plugin_id = plugin.id
        result = self.results[plugin_id]
        result.status = PluginStatus.RUNNING
        
        # Create wrapped callbacks that are thread-safe
        def safe_log(message: str):
            if log_callback:
                try:
                    log_callback(message)
                except Exception as e:
                    print(f"Error in log callback: {e}")
        
        def safe_progress(value: int):
            if progress_callback:
                try:
                    # Clamp progress to 0-100
                    clamped = max(0, min(100, value))
                    result.progress = clamped
                    progress_callback(clamped)
                except Exception as e:
                    print(f"Error in progress callback: {e}")
        
        try:
            # Log start
            safe_log(f"Starting plugin: {plugin.name}")
            safe_progress(0)
            
            # Load plugin module
            try:
                module = self.plugin_loader.load_plugin_module(plugin_id)
            except Exception as e:
                raise RuntimeError(f"Failed to load plugin module: {e}")
            
            # Get run function
            if not hasattr(module, 'run'):
                raise RuntimeError("Plugin missing 'run' function")
            
            run_func = module.run
            if not callable(run_func):
                raise RuntimeError("Plugin 'run' is not callable")
            
            # Prepare parameters with log callback
            plugin_params = params.copy()
            plugin_params['log'] = safe_log

            # Inject plugin settings
            from techdeck.core.settings import SettingsManager
            settings_manager = SettingsManager()
            plugin_settings = settings_manager.get_plugin_settings(plugin_id)
            plugin_params['settings'] = plugin_settings
            
            # Execute plugin
            safe_log("Executing plugin...")
            
            # Call plugin with standard interface
            # Expected signature: run(params, progress_callback, cancel_event)
            plugin_result = run_func(plugin_params, safe_progress, cancel_event)
            
            # Check if cancelled
            if cancel_event.is_set():
                result.status = PluginStatus.CANCELLED
                result.message = "Cancelled by user"
                safe_log("Plugin execution cancelled")
            else:
                result.status = PluginStatus.SUCCESS
                result.message = "Completed successfully"
                result.progress = 100
                safe_log(f"Plugin completed: {plugin.name}")
                safe_progress(100)
        
        except Exception as e:
            # Handle errors
            result.status = PluginStatus.ERROR
            result.message = f"Error: {str(e)}"
            result.error = str(e)
            safe_log(f"Plugin error: {str(e)}")
            safe_progress(0)
        
        finally:
            # Call completion callback
            if completion_callback:
                try:
                    completion_callback(result)
                except Exception as e:
                    print(f"Error in completion callback: {e}")
            
            # Cleanup
            if plugin_id in self.running_threads:
                del self.running_threads[plugin_id]
            if plugin_id in self.cancel_events:
                del self.cancel_events[plugin_id]
    
    def cancel_plugin(self, plugin_id: str) -> bool:
        """
        Request cancellation of a running plugin.
        
        Args:
            plugin_id: ID of plugin to cancel
            
        Returns:
            True if cancellation requested, False if plugin not running
        """
        if plugin_id in self.cancel_events:
            self.cancel_events[plugin_id].set()
            return True
        return False
    
    def is_plugin_running(self, plugin_id: str) -> bool:
        """
        Check if a plugin is currently running.
        
        Args:
            plugin_id: Plugin ID to check
            
        Returns:
            True if plugin is running
        """
        return (plugin_id in self.running_threads and 
                self.running_threads[plugin_id].is_alive())
    
    def get_result(self, plugin_id: str) -> Optional[PluginResult]:
        """
        Get the result of a plugin execution.
        
        Args:
            plugin_id: Plugin ID
            
        Returns:
            PluginResult if available, None otherwise
        """
        return self.results.get(plugin_id)
    
    def cancel_all(self) -> None:
        """Cancel all running plugins."""
        for plugin_id in list(self.cancel_events.keys()):
            self.cancel_plugin(plugin_id)
    
    def wait_for_completion(self, plugin_id: str, timeout: Optional[float] = None) -> bool:
        """
        Wait for a plugin to complete.
        
        Args:
            plugin_id: Plugin ID to wait for
            timeout: Maximum time to wait in seconds (None = wait forever)
            
        Returns:
            True if plugin completed, False if timeout
        """
        if plugin_id in self.running_threads:
            thread = self.running_threads[plugin_id]
            thread.join(timeout)
            return not thread.is_alive()
        return True  # Not running = already completed
    
    def get_active_plugins(self) -> list[str]:
        """
        Get list of currently running plugin IDs.
        
        Returns:
            List of plugin IDs that are running
        """
        return [pid for pid, thread in self.running_threads.items() 
                if thread.is_alive()]