"""
TechDeck Debug Report
=====================
One-click diagnostic snapshot for troubleshooting colleague machines remotely.
Generated from Settings > Help & Feedback > Generate Debug Report; the user
sends the resulting text file to the maintainer (outside TechDeck).

Every collector answers a question this project has actually had to debug
blind at least once:

  System / versions   - is the running exe the version we think it is?
                        (registry install version vs APP_VERSION vs exe mtime)
  Previous session    - what the LAST process was doing when it ended, and
                        whether it ended on purpose. The section that survives
                        "it locked up so I restarted it" — everything live is
                        gone by then, but hang_watchdog rotated that session's
                        final snapshot to last_session.json before this one
                        started (running plugins, how long each had been
                        silent, open prompt, open modal dialog).
  Hang / crash dumps  - hang.log: faulthandler's output for a hard crash (in a
                        frozen windowed build there is no stderr, so this is
                        the ONLY trace), plus all-thread stack dumps taken by
                        the watchdog when the UI thread stops heartbeating.
  OneDrive discovery  - where did OneDrive put the Pilot Program library on
                        THIS machine, and which resolver candidate hit?
                        (the v0.8.6 "Could not locate"/"Workbook Not Found" class)
  Plugin validation   - does every installed plugin load ON THIS MACHINE?
                        (the v0.8.6 plugin_window missing-hiddenimport class)
  Import probe        - is every critical module present in this frozen bundle?
  Connectivity        - can THIS machine reach a cloud MQTT broker? Seeds the
                        "who's online + nudge" firewall question per-machine,
                        since colleagues can't run a probe script themselves —
                        only the exe. 8883=native MQTT, 8884=WSS fallback.
  Usage telemetry     - the machine's FULL successful-run history (the local
                        usage spool) + webhook delivery state. Doubles as the
                        hand-carried delivery channel for usage data from
                        machines whose webhook sends have never gone through.
  Settings snapshot   - kits, sort modes, per-app directory overrides
  Log tails           - app.log (everything outside plugin runs: startup step
                        timings, updater outcomes, discovery errors, unhandled
                        exception tracebacks) + plugin_runs.log (run history,
                        tick-guard reports) + plugin_detail.log (every line a
                        plugin printed, so a run that reported OK but logged a
                        silent in-run warning is diagnosable — the 911-Setup
                        blank-forecast class)
  Live UI probe       - library/home grid geometry (the stacked-card class)

Rules: read-only, never raises (every section is individually guarded), no
document contents — only paths, names, sizes, and TechDeck's own state.

MAINTENANCE PRACTICE: whenever a colleague's debug report turns out to be
MISSING the data needed to diagnose their issue, improve the debugger (here, and
persist the data if it isn't already on disk) so the NEXT report captures it
automatically — don't just ask them to reproduce. This file should accrete a new
collector every time we have to debug blind.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

REPORT_DIR_NAME = "debug_reports"

# Modules a frozen build must contain for the app + every plugin to work.
# Mirrors the ship-readiness gate's concerns, but probed on the END USER's
# machine inside the running process.
_IMPORT_PROBES = [
    "techdeck.core.plugin_sdk",
    "techdeck.core.plugin_window",
    "PySide6.QtCharts",
    "PySide6.QtMultimedia",
    "openpyxl",
    "pandas",
    "fitz",
    "pypdf",
    "qrcode",
    "PIL.Image",
    "win32com.client",
    "pythoncom",
]

_REDACT_MARKERS = ("api_key", "token", "password", "secret")

# Cloud endpoints the connectivity collector probes. Answers whether a future
# "who's online + nudge" feature could reach a cloud MQTT broker from THIS
# machine's network — validated per-machine because end users can only run the
# packaged exe, not a standalone probe script. A raw TCP+TLS connect is the
# right test: native MQTT (8883) needs direct TCP egress, so a proxy-only
# machine correctly shows BLOCK here and would need the WSS-over-443 path.
#   (label, host, port, note)
_CONNECTIVITY_TARGETS = [
    ("Generic HTTPS 443",      "www.cloudflare.com",      443, "non-GitHub HTTPS egress"),
    ("MQTT/TLS 8883 (HiveMQ)", "broker.hivemq.com",      8883, "native MQTT broker"),
    ("MQTT/TLS 8883 (EMQX)",   "broker.emqx.io",         8883, "native MQTT broker"),
    ("MQTT/WSS 8884 (HiveMQ)", "broker.hivemq.com",      8884, "MQTT-over-WSS fallback"),
    ("GitHub Pages 443",       "ozymandiasone.github.io", 443, "control (updater path)"),
]
_CONNECTIVITY_TIMEOUT = 4.0


def _redact(obj):
    """Recursively blank out values whose key looks like a credential."""
    if isinstance(obj, dict):
        return {
            k: ("<redacted>" if any(m in str(k).lower() for m in _REDACT_MARKERS)
                else _redact(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    return obj


def _local_appdata() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home()))
    return Path.home() / ".local" / "share"


# ---------------------------------------------------------------- collectors

def _collect_system() -> list[str]:
    from techdeck.core.constants import APP_VERSION, APP_NAME
    lines = [
        f"Generated:        {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"App:              {APP_NAME} {APP_VERSION}",
        f"Frozen build:     {bool(getattr(sys, 'frozen', False))}",
        f"Executable:       {sys.executable}",
    ]
    try:
        exe = Path(sys.executable)
        lines.append(f"Exe modified:     {datetime.fromtimestamp(exe.stat().st_mtime):%Y-%m-%d %H:%M:%S}"
                     f"   size: {exe.stat().st_size:,}")
    except OSError:
        pass
    lines += [
        f"Python:           {sys.version.split()[0]}",
        f"OS:               {platform.platform()}",
        f"Computer / user:  {os.environ.get('COMPUTERNAME', '?')} / {os.environ.get('USERNAME', '?')}",
    ]
    # Installed-version registry stamp (catches running-from-dist vs installed
    # mismatches, and updates that never applied).
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Anthony Siebenmorgen\TechDeck") as key:
            for name in ("Version", "InstallPath", "DataPath"):
                try:
                    lines.append(f"Registry {name:<12} {winreg.QueryValueEx(key, name)[0]}")
                except OSError:
                    lines.append(f"Registry {name:<12} <not set>")
    except OSError:
        lines.append("Registry:         TechDeck key not found (never installed?)")
    # Screens — DPI/scale matter for layout bugs.
    try:
        from PySide6.QtGui import QGuiApplication
        for i, s in enumerate(QGuiApplication.screens()):
            g = s.geometry()
            lines.append(f"Screen {i}:         {g.width()}x{g.height()} @ scale "
                         f"{s.devicePixelRatio():.2f}  dpi {s.logicalDotsPerInch():.0f}")
    except Exception:
        lines.append("Screens:          <unavailable>")
    return lines


def _collect_environment() -> list[str]:
    keys = ("LOCALAPPDATA", "USERPROFILE", "OneDrive", "OneDriveCommercial",
            "OneDriveConsumer", "ONEDRIVE")
    seen = set()
    lines = []
    for k in keys:
        kl = k.lower()
        if kl in seen:
            continue
        seen.add(kl)
        lines.append(f"{k:<18} = {os.environ.get(k, '<unset>')}")
    lines.extend(_collect_long_path_support())
    return lines


def _collect_long_path_support() -> list[str]:
    """Whether this machine lifts Windows' 260-char path cap process-wide.

    TechDeck does not rely on it (sdk.long_path prefixes paths itself, which
    works either way), but when a report shows a MAX_PATH failure this line
    says whether the machine had the OS-level escape hatch on - which is the
    difference between "we missed a call site" and "the OS never allowed it".
    """
    if os.name != "nt":
        return []
    try:
        import winreg
        with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\FileSystem") as key:
            value = winreg.QueryValueEx(key, "LongPathsEnabled")[0]
        state = "ON" if value else "OFF (260-char cap enforced)"
    except OSError:
        state = "not set (260-char cap enforced)"
    except Exception as exc:                      # noqa: BLE001 - diagnostics
        state = f"<unreadable: {exc}>"
    return [f"{'LongPathsEnabled':<18} = {state}"]


def _collect_onedrive_discovery() -> list[str]:
    from techdeck.core import plugin_sdk as sdk
    lines = ["Pilot Program root candidates (priority order):"]
    roots = sdk.pilot_program_roots()
    for root in roots:
        mark = "EXISTS " if root.exists() else "missing"
        lines.append(f"  [{mark}] {root}")
    for label, resolver in (("922 root", sdk.resolve_922_root),
                            ("911 root", sdk.resolve_911_qtdr_root),
                            ("Forecast dir", sdk.resolve_forecast_dir)):
        try:
            r = resolver("")
            lines.append(f"{label:<14} -> {r if r else 'NOT FOUND'}")
        except Exception as exc:
            lines.append(f"{label:<14} -> resolver error: {exc}")
    try:
        from techdeck.core.feedback_writer import feedback_file_path
        fb = feedback_file_path()
        if fb is None:
            lines.append("Feedback wb    -> NOT FOUND in any candidate")
        else:
            lines.append(f"Feedback wb    -> {fb}  ({fb.stat().st_size:,} bytes)")
    except Exception as exc:
        lines.append(f"Feedback wb    -> probe error: {exc}")
    # Folder names only — enough to spot a tenant-name variant or shortcut
    # layout we don't yet cover, without touching document contents.
    home = Path.home()
    try:
        names = sorted(p.name for p in home.iterdir() if p.is_dir())[:60]
        lines.append(f"Home dir folders ({home}):")
        lines.extend(f"  {n}" for n in names)
    except OSError as exc:
        lines.append(f"Home dir listing failed: {exc}")
    for od in sorted(home.glob("OneDrive*")):
        if not od.is_dir():
            continue
        try:
            names = sorted(p.name for p in od.iterdir() if p.is_dir())[:40]
            lines.append(f"Folders under {od.name}:")
            lines.extend(f"  {n}" for n in names)
        except OSError as exc:
            lines.append(f"Listing {od.name} failed: {exc}")
    return lines


def _collect_plugins() -> list[str]:
    from techdeck.core.plugin_loader import PluginLoader
    loader = PluginLoader()  # default: %LOCALAPPDATA%\TechDeck\plugins
    plugins = loader.discover_plugins()
    lines = [f"Plugins dir: {loader.get_plugins_dir()}",
             f"Discovered:  {len(plugins)}"]
    on_disk = {d.name for d in loader.get_plugins_dir().iterdir() if d.is_dir()}
    undiscovered = sorted(on_disk - {p.id for p in plugins})
    if undiscovered:
        lines.append(f"On disk but NOT discovered: {', '.join(undiscovered)}")
    for plugin in sorted(plugins, key=lambda p: p.id):
        run_file = plugin.path / "run.py"
        try:
            data = run_file.read_bytes()
            stamp = (f"{len(data):,}b sha1:{hashlib.sha1(data).hexdigest()[:8]} "
                     f"mtime:{datetime.fromtimestamp(run_file.stat().st_mtime):%Y-%m-%d %H:%M}")
        except OSError as exc:
            stamp = f"run.py unreadable: {exc}"
        ok, msg = loader.validate_plugin(plugin.id)
        status = "OK  " if ok else "FAIL"
        lines.append(f"  [{status}] {plugin.id:<24} v{plugin.version:<8} "
                     f"family={plugin.family:<6} gui={plugin.requires_main_thread} {stamp}")
        if not ok:
            lines.append(f"         -> {msg}")
    return lines


def _collect_import_probe() -> list[str]:
    import importlib
    lines = []
    for name in _IMPORT_PROBES:
        try:
            importlib.import_module(name)
            lines.append(f"  [OK  ] {name}")
        except Exception as exc:
            lines.append(f"  [FAIL] {name}: {type(exc).__name__}: {exc}")
    return lines


def _collect_settings() -> list[str]:
    from techdeck.core.settings import SettingsManager
    data = _redact(SettingsManager().data)
    return json.dumps(data, indent=2, default=str).splitlines()


def _collect_usage() -> list[str]:
    """The local usage spool — full contents, deliberately. A user's bug
    report hand-delivers their machine's run history, covering machines
    whose webhook sends never succeed (blocked network, URL not yet baked
    into their build)."""
    from techdeck.core import usage_tracker
    status = usage_tracker.telemetry_status()
    lines = [
        f"Webhook configured: {status.get('webhook_configured')}",
        f"Spool: {status.get('spool_path')}",
        f"Rows: {status.get('rows')}  (sent: {status.get('sent')}, "
        f"pending: {status.get('pending')})",
    ]
    if status.get("error"):
        lines.append(f"Status error: {status['error']}")
    spool = usage_tracker.spool_path()
    if spool.is_file():
        try:
            body = spool.read_text(encoding="utf-8", errors="replace").splitlines()
            cap = 4000
            if len(body) > cap:
                lines.append(f"--- usage_log.csv (last {cap} of {len(body)} lines) ---")
                body = body[-cap:]
            else:
                lines.append(f"--- usage_log.csv (complete, {len(body)} lines) ---")
            lines.extend(body)
        except OSError as exc:
            lines.append(f"usage_log.csv unreadable: {exc}")
    else:
        lines.append("usage_log.csv: <missing — no successful runs recorded yet>")
    return lines


def _collect_logs() -> list[str]:
    log_dir = _local_appdata() / "TechDeck" / "logs"
    lines = [f"Log dir: {log_dir}"]
    if not log_dir.is_dir():
        lines.append("  <missing>")
        return lines
    for f in sorted(log_dir.glob("*")):
        try:
            lines.append(f"  {f.name:<28} {f.stat().st_size:>10,} bytes  "
                         f"{datetime.fromtimestamp(f.stat().st_mtime):%Y-%m-%d %H:%M}")
        except OSError:
            pass
    # app.log: everything outside plugin runs — startup step timings, update
    # check/download outcomes, settings-save deferrals, plugin-discovery
    # errors, and unhandled-exception tracebacks (sys/threading excepthooks).
    app_log = log_dir / "app.log"
    if app_log.is_file():
        try:
            tail = app_log.read_text(encoding="utf-8", errors="replace").splitlines()[-250:]
            lines.append("")
            lines.append(f"--- app.log (last {len(tail)} lines) ---")
            lines.extend(tail)
        except OSError as exc:
            lines.append(f"app.log unreadable: {exc}")
    run_log = log_dir / "plugin_runs.log"
    if run_log.is_file():
        try:
            tail = run_log.read_text(encoding="utf-8", errors="replace").splitlines()[-600:]
            lines.append("")
            lines.append(f"--- plugin_runs.log (last {len(tail)} lines) ---")
            lines.extend(tail)
        except OSError as exc:
            lines.append(f"plugin_runs.log unreadable: {exc}")
    # The detail log carries every line a plugin printed (the full console
    # output), so in-run warnings on a run that still reported OK -- e.g. a
    # silent forecast/lookup miss -- are diagnosable from the report.
    detail_log = log_dir / "plugin_detail.log"
    if detail_log.is_file():
        try:
            # 1500 lines ≈ a few dozen runs — enough history that a colleague's
            # report can be mined for step-level timing, not just the last run.
            tail = detail_log.read_text(encoding="utf-8", errors="replace").splitlines()[-1500:]
            lines.append("")
            lines.append(f"--- plugin_detail.log (last {len(tail)} lines) ---")
            lines.extend(tail)
        except OSError as exc:
            lines.append(f"plugin_detail.log unreadable: {exc}")
    return lines


def should_offer_debug_report(prev_session) -> bool:
    """True when the PREVIOUS session ended dirty — killed, crashed, or
    frozen-then-restarted — so the shell should offer to generate a report
    on this start. The offer is self-limiting: the state file rotates every
    startup, so one dirty exit produces exactly one offer.

    Only an explicit ``clean_exit: false`` counts. A missing file, a
    malformed dict, or an old-format snapshot without the key must never
    nag (and note: a successful auto-update marks its exit clean before
    launching the installer, so updating is not a "crash")."""
    if not isinstance(prev_session, dict):
        return False
    return prev_session.get("clean_exit") is False


def _collect_previous_session() -> list[str]:
    """What the LAST session was doing when it ended — the section that
    survives 'it froze so I restarted it'. clean_exit False means that process
    was killed / crashed / hung rather than closed."""
    from techdeck.core import hang_watchdog
    prev = hang_watchdog.previous_session()
    if prev is None:
        return ["<no previous session snapshot — first run since the watchdog "
                "shipped, or the logs dir was cleared>"]
    clean = prev.get("clean_exit")
    # 'frozen' was stamped into the snapshot when dev runs got their own
    # logs\dev tree; older snapshots don't carry it. A dev-run snapshot can
    # only appear here in a report GENERATED from a dev run - the trees no
    # longer cross - but say so anyway rather than read like a field crash.
    frozen = prev.get("frozen")
    build = ("?" if frozen is None
             else "frozen exe" if frozen else "dev run (python -m techdeck)")
    lines = [
        f"Ended cleanly:    {clean}"
        + ("" if clean else "   <-- killed, crashed, or frozen-then-restarted"),
        f"Build:            {build}",
        f"Session started:  {prev.get('session_started')}",
        f"Last written:     {prev.get('written')}   (pid {prev.get('pid')})",
        f"UI thread stale:  {prev.get('ui_thread_stale_s')}s at that moment",
    ]
    for key in ("page", "kit", "active_plugins", "silent_for_s", "run_elapsed_s",
                "queue", "paused", "is_running", "waiting_for_input",
                "input_prompt", "modal_dialog", "spinner_active"):
        if key in prev:
            lines.append(f"  {key:<18} {prev[key]}")
    return lines


def _collect_hang_log() -> list[str]:
    """Stack dumps: hard crashes (faulthandler) and UI-thread hangs caught in
    the act by the watchdog thread."""
    from techdeck.core import hang_watchdog
    path = hang_watchdog.hang_log_path()
    if not path.is_file():
        return ["<no hang.log — no crash or hang has been captured>"]
    try:
        body = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return [f"hang.log unreadable: {exc}"]
    lines = [f"File: {path}  ({path.stat().st_size:,} bytes)"]
    cap = 500
    if len(body) > cap:
        lines.append(f"--- hang.log (last {cap} of {len(body)} lines) ---")
        body = body[-cap:]
    else:
        lines.append(f"--- hang.log (complete, {len(body)} lines) ---")
    lines.extend(body)
    return lines


def _collect_ui_probe(main_window) -> list[str]:
    if main_window is None:
        return ["<no main window reference - skipped>"]
    lines = []
    home = getattr(main_window, "home_page", None)
    if home is not None:
        cards = getattr(home, "tile_cards", {})
        lines.append(f"Home: {len(cards)} tile(s), kit "
                     f"'{home.settings.get_current_profile_name()}', "
                     f"running={getattr(home, '_is_running', '?')}, "
                     f"paused={getattr(home, '_paused', '?')}")
    lib = getattr(main_window, "library_page", None)
    if lib is not None:
        try:
            container = lib._tile_container
            grid = lib.tile_grid
            widgets = []
            for i in range(grid.count()):
                item = grid.itemAt(i)
                w = item.widget() if item else None
                if w is not None:
                    widgets.append(w)
            positions = {(w.x(), w.y()) for w in widgets}
            lines.append(f"Library: {grid.count()} layout item(s), "
                         f"{len(widgets)} widget(s), "
                         f"{len(positions)} distinct position(s), "
                         f"container {container.width()}x{container.height()}, "
                         f"visible={lib.isVisible()}")
            if widgets and len(positions) <= 2:
                if lib.isVisible():
                    lines.append("  WARNING: cards appear stacked while the page "
                                 "is SHOWING (layout bug)")
                else:
                    lines.append("  note: cards not yet laid out - normal while "
                                 "the Library page hasn't been shown; showEvent "
                                 "lays out on first open")
            lines.append(f"Library sort mode: {lib.settings.get_library_sort_mode()}")
        except Exception as exc:
            lines.append(f"Library probe failed: {exc}")
    executor = getattr(getattr(main_window, "home_page", None), "plugin_executor", None)
    if executor is not None:
        try:
            lines.append(f"Executor: active={executor.get_active_plugins()}")
        except Exception:
            pass
    console = getattr(main_window, "console", None)
    if console is not None:
        lines.append(f"Console: waiting_for_input={getattr(console, 'waiting_for_input', '?')}")

    # Run-spinner state (the "Simmering..." console busy indicator). Only
    # _on_all_plugins_done stops it, so if the timer is still active while no
    # plugin is running and the run isn't paused, the spinner is stranded.
    timer = getattr(main_window, "_plugin_spinner_timer", None)
    if timer is not None:
        try:
            timer_active = timer.isActive()
            phase = getattr(main_window, "_spinner_phase", "?")
            label = getattr(console, "_spinner_label", None) if console is not None else None
            label_visible = label.isVisible() if label is not None else "?"
            label_text = label.text() if label is not None else "?"
            lines.append(f"Run spinner: timer_active={timer_active}, "
                         f"phase={phase}, label_visible={label_visible}")
            lines.append(f"  label_text={label_text!r}")
            active = []
            if executor is not None:
                try:
                    active = executor.get_active_plugins()
                except Exception:
                    active = []
            paused = bool(getattr(home, "_paused", False)) if home is not None else False
            if timer_active and not active and not paused:
                lines.append("  WARNING: run spinner is ACTIVE but no plugin is "
                             "running and the run is not paused - spinner stranded "
                             "(all_plugins_done never reached the shell)")
        except Exception as exc:
            lines.append(f"Run spinner probe failed: {exc}")
    return lines


def _collect_disk() -> list[str]:
    import shutil as _shutil
    lines = []
    for label, p in (("LOCALAPPDATA", _local_appdata()), ("Home", Path.home())):
        try:
            usage = _shutil.disk_usage(p)
            lines.append(f"{label:<14} {p}  free {usage.free / 1e9:.1f} GB of {usage.total / 1e9:.1f} GB")
        except OSError as exc:
            lines.append(f"{label:<14} {p}  <{exc}>")
    # Writability check where TechDeck must write.
    probe_dir = _local_appdata() / "TechDeck"
    try:
        probe = probe_dir / "._write_probe"
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        lines.append(f"Write check:   {probe_dir}  OK")
    except OSError as exc:
        lines.append(f"Write check:   {probe_dir}  FAILED: {exc}")
    return lines


def _probe_endpoint(host: str, port: int, timeout: float) -> tuple:
    """TCP-connect (+ TLS handshake) to one endpoint. Returns
    (ok, latency_ms_or_None, detail). Never raises."""
    import socket as _socket
    import ssl as _ssl
    import time as _time
    start = _time.time()
    try:
        with _socket.create_connection((host, port), timeout=timeout) as sock:
            ms = (_time.time() - start) * 1000.0
            # A firewall doing TLS inspection can accept the TCP connect but
            # break the handshake — so verify TLS too, not just the socket.
            try:
                ctx = _ssl.create_default_context()
                with ctx.wrap_socket(sock, server_hostname=host):
                    return True, ms, "TCP+TLS ok"
            except Exception as exc:  # noqa: BLE001
                return True, ms, f"TCP ok, TLS failed ({type(exc).__name__})"
    except Exception as exc:  # noqa: BLE001
        return False, None, type(exc).__name__


def _collect_connectivity() -> list[str]:
    """Can this machine reach a cloud MQTT broker? Every probe runs in parallel
    so a fully-blocked network costs ~one timeout total, not one per target —
    this collector runs on the UI thread when the user clicks Generate Report."""
    import time
    from concurrent.futures import ThreadPoolExecutor
    targets = _CONNECTIVITY_TARGETS
    started = time.time()
    submitted = []
    with ThreadPoolExecutor(max_workers=len(targets)) as pool:
        for label, host, port, note in targets:
            fut = pool.submit(_probe_endpoint, host, port, _CONNECTIVITY_TIMEOUT)
            submitted.append((label, note, fut))
        results = []
        for label, note, fut in submitted:
            try:
                ok, ms, detail = fut.result(timeout=_CONNECTIVITY_TIMEOUT + 2)
            except Exception as exc:  # noqa: BLE001
                ok, ms, detail = False, None, f"probe error: {type(exc).__name__}"
            results.append((label, note, ok, ms, detail))
    lines = []
    for label, note, ok, ms, detail in results:
        status = "OPEN " if ok else "BLOCK"
        lat = f"{ms:6.0f} ms" if ms is not None else "   -- "
        lines.append(f"  [{status}] {label:<26} {lat}  {detail:<28} ({note})")
    lines.append("")
    lines.append(f"Probed {len(targets)} endpoint(s) in {time.time() - started:.1f}s "
                 f"({_CONNECTIVITY_TIMEOUT:.0f}s timeout each, run in parallel).")
    lines.append("Reading: 8883 OPEN -> native MQTT works (simplest); 8883 BLOCK "
                 "but 443 OPEN -> use MQTT-over-WSS on 443.")
    return lines


# ------------------------------------------------------------------ assembly

def generate_debug_report(main_window=None) -> Path:
    """Collect every section and write the report file.

    Returns the written file's path. Individual collectors may fail (their
    section then contains the traceback) but this function only raises if the
    report cannot be written anywhere at all.
    """
    lines: list[str] = ["TechDeck Debug Report"]

    def section(title: str, fn: Callable[[], list[str]]):
        lines.append("")
        lines.append(f"=== {title} " + "=" * max(3, 64 - len(title)))
        try:
            lines.extend(fn())
        except Exception:
            lines.append("[collector failed]")
            lines.extend("  " + l for l in traceback.format_exc().splitlines())

    section("SYSTEM / VERSIONS", _collect_system)
    # Second, deliberately: after "it froze so I restarted it" this is the only
    # section describing the session that actually broke.
    section("PREVIOUS SESSION (state at exit)", _collect_previous_session)
    section("ENVIRONMENT", _collect_environment)
    section("ONEDRIVE / LIBRARY DISCOVERY", _collect_onedrive_discovery)
    section("PLUGINS (validated on this machine)", _collect_plugins)
    section("IMPORT PROBE (frozen bundle contents)", _collect_import_probe)
    section("NETWORK CONNECTIVITY (cloud broker reachability)", _collect_connectivity)
    section("USAGE TELEMETRY (successful-run history)", _collect_usage)
    section("SETTINGS SNAPSHOT", _collect_settings)
    section("DISK / PERMISSIONS", _collect_disk)
    section("LIVE UI PROBE", lambda: _collect_ui_probe(main_window))
    section("HANG / CRASH STACK DUMPS", _collect_hang_log)
    section("LOGS", _collect_logs)
    lines.append("")
    lines.append("=== END OF REPORT " + "=" * 46)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"TechDeck_DebugReport_{os.environ.get('COMPUTERNAME', 'PC')}_{stamp}.txt"

    # Desktop first (colleagues find it instantly; OneDrive-redirected Desktop
    # is fine - it's their own files), else the app data reports dir.
    candidates = [Path.home() / "Desktop", _local_appdata() / "TechDeck" / REPORT_DIR_NAME]
    last_err: Optional[Exception] = None
    for target_dir in candidates:
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            out = target_dir / name
            out.write_text("\n".join(lines), encoding="utf-8")
            return out
        except OSError as exc:
            last_err = exc
    raise OSError(f"Could not write debug report anywhere: {last_err}")
