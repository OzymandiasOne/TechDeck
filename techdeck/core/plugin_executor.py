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
from techdeck.core.plugin_sdk import PluginCancelled  # cooperative-cancel signal (stdlib-only SDK top)

logger = logging.getLogger(__name__)


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


def _as_user_facing(exc: BaseException):
    """Return a UserFacingError for a known user-caused failure, else None.
    Lazy import keeps the SDK out of the executor's import graph."""
    try:
        from techdeck.core.plugin_sdk import as_user_facing
        return as_user_facing(exc)
    except Exception:
        return None


class PluginStatus(Enum):
    """Plugin execution status."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    WARNING = "warning"  # ran to completion but reported issues (set_run_outcome)
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
    # Known user-caused failure (file open in Excel, cloud file won't download,
    # ...). When True, `message` is the plain-language problem and `user_fix`
    # is how to fix it — the shell renders a clean block instead of a traceback.
    is_user_error: bool = False
    user_fix: Optional[str] = None
    # How many ticket-earning systems this run performed. Normally 1; an
    # orchestrating plugin that ran N sibling stages in one run reports N via
    # sdk.set_ticket_units(params, N) and the shell awards N x TICKETS_PER_RUN.
    ticket_units: int = 1
    # Plain-English summary when the plugin finished with a WARNING outcome
    # (sdk.set_run_outcome) — shown instead of the blank "completed" line.
    outcome_message: str = ""


@dataclass
class RunningPlugin:
    """Bookkeeping for one live run — replaces the five parallel dicts that
    were each keyed by plugin_id (running_threads / cancel_events /
    start_times / last_activity / _input_wait_started) and could drift out
    of step. `thread` is None for main-thread (GUI) runs, which ARE
    registered here: before this, a requires_main_thread plugin was invisible
    to is_plugin_running / get_active_plugins, so the close-without-warning
    guard and the hang watchdog's snapshot missed exactly the plugin class
    most likely to freeze the UI, and a double-click could start it twice."""
    plugin_id: str
    cancel_event: threading.Event
    started_at: float
    last_activity: float
    thread: Optional[threading.Thread] = None
    # When the current console input prompt started (None = not prompting).
    # Drives the auto-pause on long input idle (Phase C).
    input_wait_started: Optional[float] = None


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
        # One record per live run (incl. main-thread runs) — see RunningPlugin.
        self._running: Dict[str, RunningPlugin] = {}
        self.results: Dict[str, PluginResult] = {}
        # PHASE 1 FIX: Thread safety - RLock allows same thread to acquire multiple times
        self._lock = threading.RLock()
        # PHASE 2: Default timeout
        self.default_timeout = default_timeout

    @staticmethod
    def _ticket_units_from(plugin_params: dict) -> int:
        """How many ticket-earning systems the plugin reported for this run
        (sdk.set_ticket_units mutates the params dict). Defaults to 1; junk
        values from a misbehaving plugin can never zero out or inflate a run
        to something absurd, so clamp to [1, 20]."""
        try:
            return max(1, min(20, int(plugin_params.get("ticket_units", 1))))
        except (TypeError, ValueError):
            return 1

    @staticmethod
    def _run_outcome_from(plugin_params: dict):
        """The (status, message) a plugin reported via sdk.set_run_outcome, or
        (None, "") if it reported nothing / junk. Only 'warning'/'partial' are
        honoured — any other value collapses to a clean success."""
        raw = plugin_params.get("run_outcome")
        if not isinstance(raw, dict):
            return None, ""
        status = str(raw.get("status", "")).strip().lower()
        if status not in ("warning", "partial"):
            return None, ""
        return status, str(raw.get("message", "") or "")
    
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
            existing = self._running.get(plugin_id)
            if existing is not None and (existing.thread is None
                                         or existing.thread.is_alive()):
                if log_callback:
                    log_callback(f"Plugin {plugin_id} is already running")
                return False

            # Create cancel event + registry record. Main-thread (GUI) runs
            # register too (thread=None) so is_plugin_running, the close
            # warning, and the hang watchdog's snapshot all see them.
            cancel_event = threading.Event()
            now = time.time()
            record = RunningPlugin(
                plugin_id=plugin_id,
                cancel_event=cancel_event,
                started_at=now,
                last_activity=now,
            )
            self._running[plugin_id] = record

            # Initialize result
            self.results[plugin_id] = PluginResult(
                plugin_id=plugin_id,
                status=PluginStatus.PENDING,
                message="Starting...",
                progress=0
            )

            # Console reference (if any) lets the watchdog tell "blocked waiting
            # for user input" apart from "genuinely hung".
            console = (params or {}).get('console')
            # Thread-safe callback fired by the watchdog when an input prompt
            # has been idle past INPUT_IDLE_PAUSE_THRESHOLD. HomePage wires
            # this to a Signal that routes to pause_run on the GUI thread.
            on_input_idle = (params or {}).get('on_input_idle')

            # Check if plugin requires main thread
            if plugin.requires_main_thread:
                # Execute in main thread using QTimer. No inactivity monitor:
                # its cancel flag couldn't preempt a busy main thread anyway —
                # main-thread hangs are the hang watchdog's job.
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

                record.thread = thread
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
            record = self._running.get(plugin_id)
            if record is not None:
                record.last_activity = time.time()

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
                record = self._running.get(plugin_id)
                if record is None:
                    return  # Plugin completed normally
                if record.thread is not None and not record.thread.is_alive():
                    return  # Plugin finished

            is_waiting = console is not None and getattr(console, 'waiting_for_input', False)
            if is_waiting:
                # Track when this prompt started so we know when to auto-pause.
                with self._lock:
                    if record.input_wait_started is None:
                        record.input_wait_started = time.time()
                    wait_start = record.input_wait_started
                    # Keep the inactivity timer fresh — user think-time isn't "hung".
                    record.last_activity = time.time()

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
                    record.input_wait_started = None
                pause_signalled = False

            # Cancel only after `timeout` seconds with no activity
            with self._lock:
                last = record.last_activity
            idle = time.time() - last
            if idle >= timeout:
                if log_callback:
                    log_callback(
                        f"WARNING: no activity for {timeout}s - plugin appears "
                        f"hung, cancelling..."
                    )
                with self._lock:
                    record.cancel_event.set()
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
        timeout: int
    ) -> None:
        """Worker-thread entry — thin wrapper over the shared run body."""
        self._run_plugin_body(plugin, params, log_callback, progress_callback,
                              completion_callback, cancel_event, timeout,
                              threaded=True)

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
        """Main-thread (GUI plugin) entry — same body, run synchronously on
        the GUI thread via QTimer.singleShot(0, ...) from execute_plugin."""
        self._run_plugin_body(plugin, params, log_callback, progress_callback,
                              completion_callback, cancel_event, timeout,
                              threaded=False)

    def _run_plugin_body(
        self,
        plugin: Plugin,
        params: Dict[str, Any],
        log_callback: Optional[Callable[[str], None]],
        progress_callback: Optional[Callable[[int], None]],
        completion_callback: Optional[Callable[[PluginResult], None]],
        cancel_event: threading.Event,
        timeout: int,
        *,
        threaded: bool,
    ) -> None:
        """The one shared execution body. Was two near-verbatim ~200-line
        copies (thread vs main-thread) that drifted: every fix had to land
        twice, and the main-thread copy skipped the post-run cancel check so
        a cancelled GUI run could still report SUCCESS.

        Args:
            plugin: Plugin object to execute
            params: Parameters to pass to plugin
            log_callback: Logging callback
            progress_callback: Progress callback
            completion_callback: Completion callback
            cancel_event: Event to check for cancellation
            timeout: Idle-timeout in seconds (0 = disabled; logged only —
                the monitor thread enforces it, and only for threaded runs)
            threaded: False for main-thread (GUI plugin) runs
        """
        plugin_id = plugin.id
        start_time = time.time()  # PHASE 2: Track execution time
        # Short per-run token stamped onto every detail-log line and the
        # RUN START/end summary lines, so back-to-back runs of the same plugin
        # can be segmented exactly when mining the logs for timing.
        run_token = f"{int(start_time * 1000) & 0xFFFFFF:06x}"

        # PHASE 1 FIX: Thread-safe access to result
        with self._lock:
            result = self.results[plugin_id]
            result.status = PluginStatus.RUNNING

        # Create wrapped callbacks that are thread-safe
        def safe_log(message: str):
            self._touch_activity(plugin_id)
            try:
                get_detail_logger().info("%s [%s] | %s", plugin_id, run_token, message)
            except Exception as e:
                # Detail logging must never break a run. debug level: this
                # fires per log line, so a broken handler must not flood
                # app.log in turn.
                logger.debug("Detail log write failed: %s", e)
            if log_callback:
                try:
                    log_callback(message)
                except Exception as e:
                    logger.warning("Error in log callback: %s", e)

        # Last progress value persisted to the detail log; list so the nested
        # function can rebind it.
        _last_logged_progress = [-100]

        def safe_progress(value: int):
            self._touch_activity(plugin_id)
            clamped = max(0, min(100, value))  # Clamp progress to 0-100
            # Persist the completion curve (every >=5-point move) so log mining
            # can map elapsed time to progress. Console/UI is unaffected.
            if abs(clamped - _last_logged_progress[0]) >= 5 or clamped in (0, 100):
                if clamped != _last_logged_progress[0]:
                    _last_logged_progress[0] = clamped
                    try:
                        get_detail_logger().info(
                            "%s [%s] | [progress] %d%%", plugin_id, run_token, clamped)
                    except Exception as e:
                        logger.debug("Detail log write failed: %s", e)
            if progress_callback:
                try:
                    with self._lock:
                        result.progress = clamped
                    progress_callback(clamped)
                except Exception as e:
                    logger.warning("Error in progress callback: %s", e)
        
        try:
            from techdeck.core.settings import SettingsManager
            from techdeck.core.flavor import get_start_message
            settings_manager = SettingsManager()
            start_msg = get_start_message(plugin.name)
            safe_log(start_msg)
            safe_progress(0)
            if threaded:
                get_run_logger().info(
                    "RUN START %s (v%s) idle_limit=%ss run=%s",
                    plugin_id, plugin.version, timeout, run_token,
                )
            else:
                get_run_logger().info(
                    "RUN START %s (v%s) [main thread] run=%s",
                    plugin_id, plugin.version, run_token,
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
            plugin_params['plugin_family'] = getattr(plugin, 'family', 'General')
            # Stash the cancel flag so deeply-nested helper code can poll it via
            # sdk.raise_if_cancelled(params.get('cancel_event')) without threading
            # the event through every call.
            plugin_params['cancel_event'] = cancel_event

            # Inject plugin settings
            plugin_settings = settings_manager.get_plugin_settings(plugin_id)
            plugin_params['settings'] = plugin_settings

            # Execute plugin. The return value is ignored by design — status
            # is reported through mutations of plugin_params (set_run_outcome,
            # set_ticket_units) and the exceptions above.
            run_func(plugin_params, safe_progress, cancel_event)

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
                    "RUN %s %s after %.1fs run=%s",
                    "TIMEOUT" if timed_out else "CANCELLED", plugin_id,
                    execution_time, run_token,
                )
            else:
                outcome_status, outcome_msg = self._run_outcome_from(plugin_params)
                with self._lock:
                    if outcome_status is not None:
                        result.status = PluginStatus.WARNING
                        result.message = outcome_msg or "Completed with warnings"
                        result.outcome_message = outcome_msg
                    else:
                        result.status = PluginStatus.SUCCESS
                        result.message = "Completed successfully"
                    result.progress = 100
                    result.execution_time = execution_time
                    result.ticket_units = self._ticket_units_from(plugin_params)
                settings_manager.increment_plugin_runs(plugin_id)
                safe_progress(100)
                get_run_logger().info(
                    "RUN %s %s in %.1fs run=%s",
                    "WARNING" if outcome_status is not None else "OK",
                    plugin_id, execution_time, run_token,
                )
                try:
                    from techdeck.core.usage_tracker import record_run
                    record_run(plugin_id, plugin.name,
                               getattr(plugin, 'family', 'General'), execution_time)
                except Exception as telemetry_exc:
                    # Telemetry must never affect a run — but leave a trace.
                    logger.warning("Usage telemetry record failed: %s",
                                   telemetry_exc)

        except PluginCancelled:
            # Cooperative cancel: a plugin called sdk.raise_if_cancelled() after
            # the user hit Cancel. A clean stop, not an error.
            execution_time = time.time() - start_time
            with self._lock:
                result.status = PluginStatus.CANCELLED
                result.message = "Cancelled by user"
                result.execution_time = execution_time
            safe_log("Plugin execution cancelled")
            get_run_logger().info(
                "RUN CANCELLED %s after %.1fs (cooperative) run=%s",
                plugin_id, execution_time, run_token,
            )

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
                "RUN %s %s after %.1fs (input aborted: %s) run=%s",
                "PAUSED" if exc.reason == "paused" else "CANCELLED",
                plugin_id, execution_time, exc.reason, run_token,
            )

        except Exception as e:
            # PHASE 2: Calculate execution time even on error
            execution_time = time.time() - start_time

            # Record consecutive errors (kept for future heuristics).
            try:
                from techdeck.core.settings import SettingsManager
                SettingsManager().record_plugin_error(plugin_id)
            except Exception as stats_exc:
                logger.warning("Could not record error stat for %s: %s",
                               plugin_id, stats_exc)

            # Handle errors — a KNOWN user-caused failure (file open in Excel,
            # cloud file won't download) gets a clean plain-English message; the
            # shell renders problem + fix. Unknown errors keep the raw text (and
            # always the full traceback in the file log for debugging).
            user_err = _as_user_facing(e)
            with self._lock:
                result.status = PluginStatus.ERROR
                if user_err is not None:
                    result.is_user_error = True
                    result.message = user_err.problem
                    result.user_fix = user_err.fix
                    result.error = str(user_err)
                else:
                    result.message = f"Error: {str(e)}"
                    result.error = str(e)
                result.execution_time = execution_time
            if user_err is None:
                safe_log(f"Plugin error: {str(e)}")
            safe_progress(0)
            get_run_logger().error(
                "RUN ERROR %s after %.1fs run=%s\n%s",
                plugin_id, execution_time, run_token, traceback.format_exc(),
            )

        finally:
            # Call completion callback
            if completion_callback:
                try:
                    completion_callback(result)
                except Exception as e:
                    logger.warning("Error in completion callback: %s", e)

            # Thread-safe cleanup: one registry record to drop.
            with self._lock:
                self._running.pop(plugin_id, None)
    
    def cancel_plugin(self, plugin_id: str) -> bool:
        """
        Request cancellation of a running plugin.
        
        Args:
            plugin_id: ID of plugin to cancel
            
        Returns:
            True if cancellation requested, False if plugin not running
        """
        with self._lock:
            record = self._running.get(plugin_id)
            if record is not None:
                record.cancel_event.set()
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
        # Main-thread (GUI) runs have no thread object; while their registry
        # record exists, they are running.
        with self._lock:
            record = self._running.get(plugin_id)
            return (record is not None
                    and (record.thread is None or record.thread.is_alive()))
    
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
            record = self._running.get(plugin_id)
            if record is not None:
                return time.time() - record.started_at
            # If not currently running, check if we have a result with execution_time
            result = self.results.get(plugin_id)
            if result and result.execution_time > 0:
                return result.execution_time
        return None

    def get_last_activity(self, plugin_id: str) -> Optional[float]:
        """Timestamp of the running plugin's last log/progress activity, or
        None if it isn't running. The hang watchdog uses this for its
        'silent for N seconds' snapshot line."""
        with self._lock:
            record = self._running.get(plugin_id)
            return record.last_activity if record is not None else None
    
    def cancel_all(self) -> None:
        """Cancel all running plugins."""
        # Thread-safe iteration over a copy of the keys
        with self._lock:
            plugin_ids = list(self._running.keys())

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
        with self._lock:
            record = self._running.get(plugin_id)
            thread = record.thread if record is not None else None

        if record is not None and thread is None:
            # A main-thread (GUI) run occupies the GUI thread itself — there
            # is nothing to join and blocking here could deadlock. Report
            # "not completed"; in practice this cannot be reached from the
            # GUI thread while such a run is executing.
            return False
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
        # Includes main-thread (GUI) runs (record.thread is None).
        with self._lock:
            return [pid for pid, record in self._running.items()
                    if record.thread is None or record.thread.is_alive()]
