"""
TechDeck Plugin Executor
Handles loading, validation, and execution of plugins with progress tracking and cancellation.

PHASE 1 FIX: Added thread safety with RLock for all shared dictionary access
PHASE 2 FIX: Added configurable timeout mechanism to prevent runaway plugins
"""

import os
import threading
import logging
import logging.handlers
import traceback
from pathlib import Path
from PySide6.QtCore import QTimer
import time
from typing import Dict, Any, Callable, Optional
from dataclasses import dataclass
from enum import Enum

from techdeck.core.plugin_loader import PluginLoader, Plugin
from techdeck.ui.widgets.console import InputAborted


# Default plugin IDLE timeout. The watchdog is inactivity-based: a plugin is
# only cancelled after this many seconds with NO log/progress activity (and
# while it is not blocked waiting for user input). This lets legitimately
# long jobs run for hours — common when OneDrive sync stalls file I/O — as
# long as they keep making progress, while still catching a genuinely hung
# plugin. A per-plugin "timeout" in plugin.json overrides this; 0 disables it.
DEFAULT_PLUGIN_TIMEOUT = 1800  # seconds of inactivity

# Auto-pause threshold. If a plugin sits at a console input prompt for this
# many seconds with no user response, the watchdog fires the on_input_idle
# callback (HomePage routes that to pause_run). Lets a distracted user come
# back to a clearly-paused run instead of finding a silently-blocked plugin.
INPUT_IDLE_PAUSE_THRESHOLD = 60


def _run_log_dir() -> Path:
    """Directory for persistent plugin run logs."""
    if os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA', Path.home()))
    else:
        base = Path.home() / '.local' / 'share'
    return base / 'TechDeck' / 'logs'


_run_logger: Optional[logging.Logger] = None


def get_run_logger() -> logging.Logger:
    """Return the shared plugin run-log logger, configuring a rotating file
    handler on first use. Writes to %LOCALAPPDATA%/TechDeck/logs/plugin_runs.log
    so colleague-reported failures can be diagnosed after the fact. Never
    raises — logging must not break plugin execution."""
    global _run_logger
    if _run_logger is not None:
        return _run_logger

    logger = logging.getLogger('techdeck.plugin_runs')
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        try:
            log_dir = _run_log_dir()
            log_dir.mkdir(parents=True, exist_ok=True)
            handler = logging.handlers.RotatingFileHandler(
                log_dir / 'plugin_runs.log',
                maxBytes=1_000_000,
                backupCount=5,
                encoding='utf-8',
            )
            handler.setFormatter(logging.Formatter(
                '%(asctime)s %(levelname)-7s %(message)s'
            ))
            logger.addHandler(handler)
        except Exception:
            # If the file handler can't be created, fall back to a no-op
            # handler so logging calls never raise.
            logger.addHandler(logging.NullHandler())

    _run_logger = logger
    return logger


_detail_logger: Optional[logging.Logger] = None


def get_detail_logger() -> logging.Logger:
    """Return the shared plugin DETAIL logger, configuring a rotating file handler
    on first use. Writes every line a plugin emits (the full console output) to
    %LOCALAPPDATA%/TechDeck/logs/plugin_detail.log, so failures that only surface
    as in-run warnings (e.g. 911 Setup logging 'No forecast rows found for nest X'
    while the run still reports OK) can be diagnosed from a debug report after the
    fact — plugin_runs.log keeps only the START/OK/ERROR summary. Never raises."""
    global _detail_logger
    if _detail_logger is not None:
        return _detail_logger

    logger = logging.getLogger('techdeck.plugin_detail')
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        try:
            log_dir = _run_log_dir()
            log_dir.mkdir(parents=True, exist_ok=True)
            handler = logging.handlers.RotatingFileHandler(
                log_dir / 'plugin_detail.log',
                maxBytes=2_000_000,
                backupCount=3,
                encoding='utf-8',
            )
            handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
            logger.addHandler(handler)
        except Exception:
            logger.addHandler(logging.NullHandler())

    _detail_logger = logger
    return logger


class PluginStatus(Enum):
    """Plugin execution status."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    CANCELLED = "cancelled"
    ERROR = "error"
    TIMEOUT = "timeout"  # PHASE 2: New status
    PAUSED = "paused"    # Phase C: parked by /pause or auto-idle


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
        # Last log/progress activity per plugin — drives the inactivity watchdog
        self.last_activity: Dict[str, float] = {}
        # When the current console input prompt started (per plugin). Set when
        # waiting_for_input flips True, cleared when it flips False. Drives the
        # auto-pause on long input idle (Phase C).
        self._input_wait_started: Dict[str, float] = {}
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
            # Record an ERROR result so callers that read get_result() after a
            # failed start (e.g. the shell's completion handler) see this
            # failure instead of a stale result from a previous run.
            with self._lock:
                self.results[plugin_id] = PluginResult(
                    plugin_id=plugin_id,
                    status=PluginStatus.ERROR,
                    message=f"Validation failed: {error_msg}",
                    error=error_msg,
                )
            get_run_logger().error("RUN REFUSED %s: %s", plugin_id, error_msg)
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
            # Seed activity timestamp for the inactivity watchdog
            self.last_activity[plugin_id] = time.time()

            # Console reference (if any) lets the watchdog tell "blocked waiting
            # for user input" apart from "genuinely hung".
            console = (params or {}).get('console')
            # Thread-safe callback fired by the watchdog when an input prompt
            # has been idle past INPUT_IDLE_PAUSE_THRESHOLD. HomePage wires
            # this to a Signal that routes to pause_run on the GUI thread.
            on_input_idle = (params or {}).get('on_input_idle')

            # Check if plugin requires main thread
            if plugin.requires_main_thread:
                # Execute in main thread using QTimer
                def execute_in_main_thread():
                    self._execute_plugin_directly(
                        plugin, params or {}, log_callback, progress_callback,
                        completion_callback, cancel_event, effective_timeout
                    )

                QTimer.singleShot(0, execute_in_main_thread)
            else:
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

                # Start inactivity watchdog if an idle limit is set
                if effective_timeout > 0:
                    monitor_thread = threading.Thread(
                        target=self._timeout_monitor,
                        args=(plugin_id, effective_timeout, log_callback,
                              console, on_input_idle),
                        name=f"Timeout-{plugin_id}",
                        daemon=True
                    )
                    monitor_thread.start()
            
        return True
    
    def _touch_activity(self, plugin_id: str) -> None:
        """Mark the plugin as active right now, resetting the inactivity
        watchdog. Called on every log line and progress update."""
        with self._lock:
            if plugin_id in self.last_activity:
                self.last_activity[plugin_id] = time.time()

    def _timeout_monitor(
        self,
        plugin_id: str,
        timeout: int,
        log_callback: Optional[Callable[[str], None]],
        console: Any = None,
        on_input_idle: Optional[Callable[[], None]] = None,
    ) -> None:
        """
        Inactivity watchdog. Cancels a plugin only after `timeout` seconds with
        NO log/progress activity. Time spent blocked waiting for user input
        (console.waiting_for_input) does not count as inactivity.

        This replaces the old wall-clock timeout, which wrongly killed long
        but healthy jobs — e.g. the 922 repeater, which can run for hours when
        OneDrive stalls file I/O. As long as a plugin keeps logging or
        reporting progress, it is never cancelled by the watchdog.

        Phase C: also tracks how long the current input prompt has been
        pending. When that crosses INPUT_IDLE_PAUSE_THRESHOLD seconds, fires
        ``on_input_idle`` (once per prompt). HomePage uses that to enter a
        clear paused state instead of leaving the plugin silently blocked.

        Args:
            plugin_id: Plugin ID to monitor
            timeout: Max seconds of inactivity before cancelling
            log_callback: Logging callback
            console: Optional console; if it is waiting for input, the idle
                     timer is held so user think-time never trips the watchdog.
            on_input_idle: Optional thread-safe callback fired once when an
                     input prompt has been pending longer than
                     INPUT_IDLE_PAUSE_THRESHOLD.
        """
        pause_signalled = False
        while True:
            time.sleep(1)  # Check every second

            # Check if plugin is still running
            with self._lock:
                if plugin_id not in self.running_threads:
                    return  # Plugin completed normally

                thread = self.running_threads.get(plugin_id)
                if thread is None or not thread.is_alive():
                    return  # Plugin finished

            is_waiting = console is not None and getattr(console, 'waiting_for_input', False)
            if is_waiting:
                # Track when this prompt started so we know when to auto-pause.
                with self._lock:
                    if plugin_id not in self._input_wait_started:
                        self._input_wait_started[plugin_id] = time.time()
                    wait_start = self._input_wait_started[plugin_id]
                    # Keep the inactivity timer fresh — user think-time isn't "hung".
                    self.last_activity[plugin_id] = time.time()

                # Auto-pause once if we cross the threshold and a callback exists.
                if (on_input_idle is not None
                        and not pause_signalled
                        and (time.time() - wait_start) >= INPUT_IDLE_PAUSE_THRESHOLD):
                    pause_signalled = True
                    try:
                        on_input_idle()
                    except Exception as e:
                        # Never let a misbehaving callback stop the watchdog.
                        if log_callback:
                            log_callback(f"on_input_idle callback error: {e}")
                continue
            else:
                # Prompt was answered (or never started); reset for the NEXT prompt
                # this plugin might raise.
                with self._lock:
                    self._input_wait_started.pop(plugin_id, None)
                pause_signalled = False

            # Cancel only after `timeout` seconds with no activity
            with self._lock:
                last = self.last_activity.get(plugin_id, time.time())
            idle = time.time() - last
            if idle >= timeout:
                if log_callback:
                    log_callback(
                        f"WARNING: no activity for {timeout}s - plugin appears "
                        f"hung, cancelling..."
                    )
                with self._lock:
                    if plugin_id in self.cancel_events:
                        self.cancel_events[plugin_id].set()
                    if plugin_id in self.results:
                        result = self.results[plugin_id]
                        result.status = PluginStatus.TIMEOUT
                        result.message = f"Cancelled after {timeout}s of inactivity"
                        result.error = "Plugin stopped making progress (inactivity timeout)"
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
            self._touch_activity(plugin_id)
            try:
                get_detail_logger().info("%s | %s", plugin_id, message)
            except Exception:
                pass  # detail logging must never break a run
            if log_callback:
                try:
                    log_callback(message)
                except Exception as e:
                    print(f"Error in log callback: {e}")

        def safe_progress(value: int):
            self._touch_activity(plugin_id)
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
            from techdeck.core.settings import SettingsManager
            from techdeck.core.flavor import get_start_message
            settings_manager = SettingsManager()
            start_msg = get_start_message(plugin.name)
            safe_log(start_msg)
            safe_progress(0)
            get_run_logger().info(
                "RUN START %s (v%s) idle_limit=%ss",
                plugin_id, plugin.version, timeout,
            )

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
            # Stash this plugin's own id + family so SDK helpers (e.g.
            # request_batch_number) can resolve their context without the caller
            # threading it through every call.
            plugin_params['plugin_id'] = plugin_id
            plugin_params['plugin_family'] = getattr(plugin, 'family', 'other')

            # Inject plugin settings
            plugin_settings = settings_manager.get_plugin_settings(plugin_id)
            plugin_params['settings'] = plugin_settings

            # Execute plugin
            plugin_result = run_func(plugin_params, safe_progress, cancel_event)

            # PHASE 2: Calculate execution time
            execution_time = time.time() - start_time

            # Check if cancelled or timed out
            if cancel_event.is_set():
                with self._lock:
                    timed_out = result.status == PluginStatus.TIMEOUT
                    if timed_out:
                        safe_log(f"Plugin timed out after {execution_time:.1f}s")
                    else:
                        result.status = PluginStatus.CANCELLED
                        result.message = "Cancelled by user"
                        safe_log("Plugin execution cancelled")
                    result.execution_time = execution_time
                get_run_logger().warning(
                    "RUN %s %s after %.1fs",
                    "TIMEOUT" if timed_out else "CANCELLED", plugin_id, execution_time,
                )
            else:
                with self._lock:
                    result.status = PluginStatus.SUCCESS
                    result.message = "Completed successfully"
                    result.progress = 100
                    result.execution_time = execution_time
                settings_manager.increment_plugin_runs(plugin_id)
                safe_progress(100)
                get_run_logger().info("RUN OK %s in %.1fs", plugin_id, execution_time)
                try:
                    from techdeck.core.usage_tracker import record_run
                    record_run(plugin_id, plugin.name,
                               getattr(plugin, 'family', 'other'), execution_time)
                except Exception:
                    pass  # telemetry must never affect a run

        except InputAborted as exc:
            # Plugin's request_input was aborted. reason="paused" → user (or
            # auto-idle) hit /pause, so park the run; anything else (e.g.
            # "cancelled" from Clear) collapses to the cancelled path.
            execution_time = time.time() - start_time
            with self._lock:
                if exc.reason == "paused":
                    result.status = PluginStatus.PAUSED
                    result.message = "Paused"
                    safe_log("Plugin paused waiting for input.")
                else:
                    result.status = PluginStatus.CANCELLED
                    result.message = f"Cancelled ({exc.reason})"
                    safe_log(f"Plugin input cancelled: {exc.reason}")
                result.execution_time = execution_time
            get_run_logger().info(
                "RUN %s %s after %.1fs (input aborted: %s)",
                "PAUSED" if exc.reason == "paused" else "CANCELLED",
                plugin_id, execution_time, exc.reason,
            )

        except Exception as e:
            # PHASE 2: Calculate execution time even on error
            execution_time = time.time() - start_time

            # Record consecutive errors (kept for future heuristics).
            try:
                from techdeck.core.settings import SettingsManager
                SettingsManager().record_plugin_error(plugin_id)
            except Exception:
                pass

            # Handle errors
            with self._lock:
                result.status = PluginStatus.ERROR
                result.message = f"Error: {str(e)}"
                result.error = str(e)
                result.execution_time = execution_time
            safe_log(f"Plugin error: {str(e)}")
            safe_progress(0)
            get_run_logger().error(
                "RUN ERROR %s after %.1fs\n%s",
                plugin_id, execution_time, traceback.format_exc(),
            )

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
                if plugin_id in self.last_activity:
                    del self.last_activity[plugin_id]
                if plugin_id in self._input_wait_started:
                    del self._input_wait_started[plugin_id]
    
    def _execute_plugin_directly(
        self,
        plugin: Plugin,
        params: Dict[str, Any],
        log_callback: Optional[Callable[[str], None]],
        progress_callback: Optional[Callable[[int], None]],
        completion_callback: Optional[Callable[[PluginResult], None]],
        cancel_event: threading.Event,
        timeout: int
    ) -> None:
        """Execute plugin directly in main thread (for GUI plugins)."""
        plugin_id = plugin.id
        start_time = time.time()
        
        with self._lock:
            result = self.results[plugin_id]
            result.status = PluginStatus.RUNNING
        
        def safe_log(message: str):
            self._touch_activity(plugin_id)
            try:
                get_detail_logger().info("%s | %s", plugin_id, message)
            except Exception:
                pass  # detail logging must never break a run
            if log_callback:
                try:
                    log_callback(message)
                except Exception as e:
                    print(f"Error in log callback: {e}")

        def safe_progress(value: int):
            self._touch_activity(plugin_id)
            if progress_callback:
                try:
                    clamped = max(0, min(100, value))
                    with self._lock:
                        result.progress = clamped
                    progress_callback(clamped)
                except Exception as e:
                    print(f"Error in progress callback: {e}")
        
        try:
            from techdeck.core.settings import SettingsManager
            from techdeck.core.flavor import get_start_message
            settings_manager = SettingsManager()
            safe_log(get_start_message(plugin.name))
            safe_progress(0)
            get_run_logger().info("RUN START %s (v%s) [main thread]", plugin_id, plugin.version)

            module = self.plugin_loader.load_plugin_module(plugin_id)

            if not hasattr(module, 'run'):
                raise RuntimeError("Plugin missing 'run' function")

            run_func = module.run
            if not callable(run_func):
                raise RuntimeError("Plugin 'run' is not callable")

            plugin_params = params.copy()
            plugin_params['log'] = safe_log
            plugin_params['plugin_id'] = plugin_id
            plugin_params['plugin_family'] = getattr(plugin, 'family', 'other')

            plugin_settings = settings_manager.get_plugin_settings(plugin_id)
            plugin_params['settings'] = plugin_settings

            plugin_result = run_func(plugin_params, safe_progress, cancel_event)

            execution_time = time.time() - start_time

            with self._lock:
                result.status = PluginStatus.SUCCESS
                result.message = "Completed successfully"
                result.progress = 100
                result.execution_time = execution_time
            settings_manager.increment_plugin_runs(plugin_id)
            safe_progress(100)
            get_run_logger().info("RUN OK %s in %.1fs", plugin_id, execution_time)
            try:
                from techdeck.core.usage_tracker import record_run
                record_run(plugin_id, plugin.name,
                           getattr(plugin, 'family', 'other'), execution_time)
            except Exception:
                pass  # telemetry must never affect a run

        except InputAborted as exc:
            execution_time = time.time() - start_time
            with self._lock:
                if exc.reason == "paused":
                    result.status = PluginStatus.PAUSED
                    result.message = "Paused"
                    safe_log("Plugin paused waiting for input.")
                else:
                    result.status = PluginStatus.CANCELLED
                    result.message = f"Cancelled ({exc.reason})"
                    safe_log(f"Plugin input cancelled: {exc.reason}")
                result.execution_time = execution_time
            get_run_logger().info(
                "RUN %s %s after %.1fs (input aborted: %s)",
                "PAUSED" if exc.reason == "paused" else "CANCELLED",
                plugin_id, execution_time, exc.reason,
            )

        except Exception as e:
            execution_time = time.time() - start_time

            try:
                from techdeck.core.settings import SettingsManager
                SettingsManager().record_plugin_error(plugin_id)
            except Exception:
                pass

            with self._lock:
                result.status = PluginStatus.ERROR
                result.message = f"Error: {str(e)}"
                result.error = str(e)
                result.execution_time = execution_time
            safe_log(f"Plugin error: {str(e)}")
            safe_progress(0)
            get_run_logger().error(
                "RUN ERROR %s after %.1fs\n%s",
                plugin_id, execution_time, traceback.format_exc(),
            )

        finally:
            if completion_callback:
                try:
                    completion_callback(result)
                except Exception as e:
                    print(f"Error in completion callback: {e}")

            with self._lock:
                if plugin_id in self.cancel_events:
                    del self.cancel_events[plugin_id]
                if plugin_id in self.start_times:
                    del self.start_times[plugin_id]
                if plugin_id in self.last_activity:
                    del self.last_activity[plugin_id]
                if plugin_id in self._input_wait_started:
                    del self._input_wait_started[plugin_id]
    
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
