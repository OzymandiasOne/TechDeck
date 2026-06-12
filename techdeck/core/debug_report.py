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
  OneDrive discovery  - where did OneDrive put the Pilot Program library on
                        THIS machine, and which resolver candidate hit?
                        (the v0.8.6 "Could not locate"/"Workbook Not Found" class)
  Plugin validation   - does every installed plugin load ON THIS MACHINE?
                        (the v0.8.6 plugin_window missing-hiddenimport class)
  Import probe        - is every critical module present in this frozen bundle?
  Settings snapshot   - kits, sort modes, per-app directory overrides
  Log tails           - plugin_runs.log (run history, tick-guard reports)
  Live UI probe       - library/home grid geometry (the stacked-card class)

Rules: read-only, never raises (every section is individually guarded), no
document contents — only paths, names, sizes, and TechDeck's own state.
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
    return lines


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
    run_log = log_dir / "plugin_runs.log"
    if run_log.is_file():
        try:
            tail = run_log.read_text(encoding="utf-8", errors="replace").splitlines()[-250:]
            lines.append("")
            lines.append(f"--- plugin_runs.log (last {len(tail)} lines) ---")
            lines.extend(tail)
        except OSError as exc:
            lines.append(f"plugin_runs.log unreadable: {exc}")
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
    section("ENVIRONMENT", _collect_environment)
    section("ONEDRIVE / LIBRARY DISCOVERY", _collect_onedrive_discovery)
    section("PLUGINS (validated on this machine)", _collect_plugins)
    section("IMPORT PROBE (frozen bundle contents)", _collect_import_probe)
    section("SETTINGS SNAPSHOT", _collect_settings)
    section("DISK / PERMISSIONS", _collect_disk)
    section("LIVE UI PROBE", lambda: _collect_ui_probe(main_window))
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
