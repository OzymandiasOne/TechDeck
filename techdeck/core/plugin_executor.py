"""
TechDeck Plugin Executor
Handles loading, validation, and execution of plugins with progress tracking and cancellation.

PHASE 1 FIX: Added thread safety with RLock for all shared dictionary access
PHASE 2 FIX: Added configurable timeout mechanism to prevent runaway plugins
"""

import threading
import time
from typing import Dict, Any, Callable, Optional
from dataclasses import dataclass
from enum import Enum

from techdeck.core.plugin_loader import PluginLoader, Plugin


# PHASE 2: Default plugin timeout (5 minutes)
DEFAULT_PLUGIN_TIMEOUT = 300  # seconds


class PluginStatus(Enum):
    """Plugin execution status."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    CANCELLED = "cancelled"
    ERROR = "error"
    TIMEOUT = "timeout"  # PHASE 2: New status


@dataclass
class PluginResult:
    """Result of plugin execution."""
    plugin_id: str
    status: PluginStatus
    message: str
    progress: int = 0
    error: Optional[str] = None
    execution_time: float = 0.0  # PHASE 2: Track execution time


class PluginExecutor:
    """
    Manages plugin execution with progress tracking and cancellation support.
    
    Features:
    - Thread-based execution
    - Progress callbacks
    - Cancellation via threading.Event
    - Error handling and reporting
    - Console output integration
    - Thread-safe dictionary access (PHASE 1 FIX)
    - Configurable timeout mechanism (PHASE 2 FIX)
    """
    
    def __init__(self, plugin_loader: PluginLoader, default_timeout: int = DEFAULT_PLUGIN_TIMEOUT):
        """
        Initialize plugin executor.
        
        Args:
            plugin_loader: PluginLoader instance for discovering plugins
            default_timeout: Default timeout in seconds for plugin execution (0 = no timeout)
        """
        self.plugin_loader = plugin_loader
        self.running_threads: Dict[str, threading.Thread] = {}
        self.cancel_events: Dict[str, threading.Event] = {}
        self.results: Dict[str, PluginResult] = {}
        self.start_times: Dict[str, float] = {}  # PHASE 2: Track start times
        # PHASE 1 FIX: Thread safety - RLock allows same thread to acquire multiple times
        self._lock = threading.RLock()
        # PHASE 2: Default timeout
        self.default_timeout = default_timeout
    
    def execute_plugin(
        self,
        plugin_id: str,
        params: Optional[Dict[str, Any]] = None,
        log_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
        completion_callback: Optional[Callable[[PluginResult], None]] = None,
        timeout: Optional[int] = None  # PHASE 2: Per-plugin timeout override
    ) -> bool:
        """
        Execute a plugin in a separate thread.
        
        Args:
            plugin_id: ID of plugin to execute
            params: Optional parameters to pass to plugin
            log_callback: Function to call with log messages
            progress_callback: Function to call with progress (0-100)
            completion_callback: Function to call when plugin completes
            timeout: Timeout in seconds (None = use default, 0 = no timeout)
            
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
        
        # PHASE 2: Determine effective timeout
        effective_timeout = timeout if timeout is not None else self.default_timeout
        
        # PHASE 1 FIX: Thread-safe check if already running
        with self._lock:
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
            
            # PHASE 2: Record start time
            self.start_times[plugin_id] = time.time()
            
            # Create execution thread
            thread = threading.Thread(
                target=self._execute_plugin_thread,
                args=(plugin, params or {}, log_callback, progress_callback, 
                      completion_callback, cancel_event, effective_timeout),
                name=f"Plugin-{plugin_id}",
                daemon=True
            )
            
            self.running_threads[plugin_id] = thread
            thread.start()
            
            # PHASE 2: Start timeout monitor if timeout is set
            if effective_timeout > 0:
                monitor_thread = threading.Thread(
                    target=self._timeout_monitor,
                    args=(plugin_id, effective_timeout, log_callback),
                    name=f"Timeout-{plugin_id}",
                    daemon=True
                )
                monitor_thread.start()
        
        return True
    
    def _timeout_monitor(
        self,
        plugin_id: str,
        timeout: int,
        log_callback: Optional[Callable[[str], None]]
    ) -> None:
        """
        PHASE 2: Monitor plugin execution and cancel if timeout exceeded.
        
        Args:
            plugin_id: Plugin ID to monitor
            timeout: Timeout in seconds
            log_callback: Logging callback
        """
        start_time = time.time()
        
        while True:
            time.sleep(1)  # Check every second
            
            # Check if plugin is still running
            with self._lock:
                if plugin_id not in self.running_threads:
                    return  # Plugin completed normally
                
                thread = self.running_threads.get(plugin_id)
                if thread is None or not thread.is_alive():
                    return  # Plugin finished
            
            # Check if timeout exceeded
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                # Timeout exceeded - cancel the plugin
                if log_callback:
                    log_callback(f"⚠️ Plugin execution timeout ({timeout}s) - cancelling...")
                
                # Set cancel event
                with self._lock:
                    if plugin_id in self.cancel_events:
                        self.cancel_events[plugin_id].set()
                    
                    # Update result status
                    if plugin_id in self.results:
                        result = self.results[plugin_id]
                        result.status = PluginStatus.TIMEOUT
                        result.message = f"Execution timeout after {timeout} seconds"
                        result.error = "Plugin exceeded maximum execution time"
                
                return
    
    def _execute_plugin_thread(
        self,
        plugin: Plugin,
        params: Dict[str, Any],
        log_callback: Optional[Callable[[str], None]],
        progress_callback: Optional[Callable[[int], None]],
        completion_callback: Optional[Callable[[PluginResult], None]],
        cancel_event: threading.Event,
        timeout: int  # PHASE 2: Timeout parameter
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
            timeout: Execution timeout in seconds
        """
        plugin_id = plugin.id
        start_time = time.time()  # PHASE 2: Track execution time
        
        # PHASE 1 FIX: Thread-safe access to result
        with self._lock:
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
                    with self._lock:
                        result.progress = clamped
                    progress_callback(clamped)
                except Exception as e:
                    print(f"Error in progress callback: {e}")
        
        try:
            # Log start with timeout info
            if timeout > 0:
                safe_log(f"Starting plugin: {plugin.name} (timeout: {timeout}s)")
            else:
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
            
            # PHASE 2: Calculate execution time
            execution_time = time.time() - start_time
            
            # Check if cancelled or timed out
            if cancel_event.is_set():
                with self._lock:
                    # Check if it was a timeout (status already set by monitor)
                    if result.status == PluginStatus.TIMEOUT:
                        safe_log(f"Plugin timed out after {execution_time:.1f}s")
                    else:
                        result.status = PluginStatus.CANCELLED
                        result.message = "Cancelled by user"
                        safe_log("Plugin execution cancelled")
                    result.execution_time = execution_time
            else:
                with self._lock:
                    result.status = PluginStatus.SUCCESS
                    result.message = "Completed successfully"
                    result.progress = 100
                    result.execution_time = execution_time
                safe_log(f"Plugin completed: {plugin.name} ({execution_time:.1f}s)")
                safe_progress(100)
        
        except Exception as e:
            # PHASE 2: Calculate execution time even on error
            execution_time = time.time() - start_time
            
            # Handle errors
            with self._lock:
                result.status = PluginStatus.ERROR
                result.message = f"Error: {str(e)}"
                result.error = str(e)
                result.execution_time = execution_time
            safe_log(f"Plugin error: {str(e)}")
            safe_progress(0)
        
        finally:
            # Call completion callback
            if completion_callback:
                try:
                    completion_callback(result)
                except Exception as e:
                    print(f"Error in completion callback: {e}")
            
            # PHASE 1 FIX: Thread-safe cleanup
            # PHASE 2: Also clean up start_times
            with self._lock:
                if plugin_id in self.running_threads:
                    del self.running_threads[plugin_id]
                if plugin_id in self.cancel_events:
                    del self.cancel_events[plugin_id]
                if plugin_id in self.start_times:
                    del self.start_times[plugin_id]
    
    def cancel_plugin(self, plugin_id: str) -> bool:
        """
        Request cancellation of a running plugin.
        
        Args:
            plugin_id: ID of plugin to cancel
            
        Returns:
            True if cancellation requested, False if plugin not running
        """
        # PHASE 1 FIX: Thread-safe access to cancel_events
        with self._lock:
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
        # PHASE 1 FIX: Thread-safe check
        with self._lock:
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
        # PHASE 1 FIX: Thread-safe access
        with self._lock:
            return self.results.get(plugin_id)
    
    def get_execution_time(self, plugin_id: str) -> Optional[float]:
        """
        PHASE 2: Get the current execution time of a running plugin.
        
        Args:
            plugin_id: Plugin ID
            
        Returns:
            Execution time in seconds, or None if not running
        """
        with self._lock:
            if plugin_id in self.start_times:
                return time.time() - self.start_times[plugin_id]
            # If not currently running, check if we have a result with execution_time
            result = self.results.get(plugin_id)
            if result and result.execution_time > 0:
                return result.execution_time
        return None
    
    def cancel_all(self) -> None:
        """Cancel all running plugins."""
        # PHASE 1 FIX: Thread-safe iteration over copy of keys
        with self._lock:
            plugin_ids = list(self.cancel_events.keys())
        
        for plugin_id in plugin_ids:
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
        # PHASE 1 FIX: Thread-safe access to get thread
        with self._lock:
            thread = self.running_threads.get(plugin_id)
        
        if thread:
            thread.join(timeout)
            return not thread.is_alive()
        return True  # Not running = already completed
    
    def get_active_plugins(self) -> list[str]:
        """
        Get list of currently running plugin IDs.
        
        Returns:
            List of plugin IDs that are running
        """
        # PHASE 1 FIX: Thread-safe iteration
        with self._lock:
            return [pid for pid, thread in self.running_threads.items() 
                    if thread.is_alive()]
