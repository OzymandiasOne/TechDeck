"""
TechDeck Plugin SDK
===================
Shared helpers for plugins. Plugins run inside the TechDeck process (or the
frozen exe, which bundles the techdeck package), so they can import this
module directly:

    from techdeck.core import plugin_sdk as sdk

For standalone CLI testing (`python plugins/foo/run.py`), the repo root may
not be on sys.path. Use this bootstrap at the top of a plugin so both modes
work:

    try:
        from techdeck.core import plugin_sdk as sdk
    except ModuleNotFoundError:
        import sys, pathlib
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
        from techdeck.core import plugin_sdk as sdk

This module is the single source of truth for things every plugin used to
reimplement: locating the OneDrive "Pilot Program" roots, parsing a batch
number, finding a batch folder, Excel header lookups, and PDF merge/save.
Fix a bug here once instead of in eight copies.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Iterable, Optional


# ─────────────────────────────────────────────────────────────────────────────
# User-facing errors
#
# A failure the USER can fix (a file left open in Excel, a cloud file that
# won't download, an empty/wrong folder) — NOT a code bug. Raising this instead
# of a bare Exception lets the console print a clean "here's the problem, here's
# the fix" in plain English across every plugin, instead of a raw traceback or a
# cryptic errno. Raise via a factory (locked_file_error, ...) or directly:
#
#     raise UserFacingError("The folder has no DXF files in it.",
#                           "Pick the folder that holds the part files.")
# ─────────────────────────────────────────────────────────────────────────────

class UserFacingError(RuntimeError):
    """An error with a plain-language `problem` + `fix` for the user."""

    def __init__(self, problem: str, fix: str = "", *, detail: str = ""):
        self.problem = " ".join(str(problem).split())
        self.fix = " ".join(str(fix).split())
        self.detail = str(detail).strip()  # e.g. the full file path (for logs)
        msg = self.problem + (f"  Fix: {self.fix}" if self.fix else "")
        super().__init__(msg)


def as_user_facing(exc: BaseException) -> "UserFacingError | None":
    """Map an exception to a UserFacingError when it's a KNOWN user-caused
    failure, else None. This is the executor's safety net so every app shows a
    clean message, not a traceback.

    Walks the exception chain (`__cause__`/`__context__`): a plugin that catches
    a UserFacingError and re-raises `RuntimeError(f"...: {e}")` still surfaces
    cleanly, and a raw share-lock (Errno 13) from an un-converted read site is
    recognized too (open()/copy set exc.filename)."""
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, UserFacingError):
            return cur
        if _is_share_lock(cur):
            fn = getattr(cur, "filename", None)
            if fn:
                return locked_file_error(fn, cur)
            return UserFacingError(
                "A file TechDeck needs is open in another program (usually Excel).",
                "Close any open batch or pricing files, then run again.",
            )
        cur = cur.__cause__ or cur.__context__
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Cooperative cancellation
#
# The executor sets a threading.Event (run()'s 3rd arg) when the user hits
# Cancel; it CANNOT interrupt a running plugin, so plugins must poll it. Call
# raise_if_cancelled(cancel_event) inside any loop that can run for a while
# (over files, PDFs, DXFs, rows, nests, ...) and Cancel responds promptly
# instead of waiting for the whole batch to finish. The executor maps
# PluginCancelled to a clean CANCELLED status (not an error).
# ─────────────────────────────────────────────────────────────────────────────

class PluginCancelled(BaseException):
    """Raised by raise_if_cancelled() when the user cancels a run. Caught by the
    executor and reported as CANCELLED, never ERROR.

    Subclasses BaseException (like KeyboardInterrupt), NOT Exception, so a
    plugin's own `try/except Exception` around per-file work (used to skip a bad
    file and continue) can never accidentally swallow a cancel."""


def cancelled(cancel_event) -> bool:
    """True if the run has been cancelled. Tolerates cancel_event=None (a plugin
    run standalone / in tests), returning False."""
    return bool(cancel_event is not None and cancel_event.is_set())


def raise_if_cancelled(cancel_event) -> None:
    """Bail out of a long operation the instant the user cancels. Call once per
    iteration of any loop that can run a while (over files/PDFs/DXFs/rows/nests).
    Cheap — a plain flag read — so per-item calls are fine. Raises
    PluginCancelled, which the executor turns into a clean CANCELLED."""
    if cancelled(cancel_event):
        raise PluginCancelled()


# ─────────────────────────────────────────────────────────────────────────────
# OneDrive / Pilot Program root resolution
#
# Every machine syncs the same SharePoint library, but the local cache path
# differs by how OneDrive named the folder. We check every known base so a
# plugin never has to make the user type a directory.
# ─────────────────────────────────────────────────────────────────────────────

_PILOT_REL = (
    "Communication site - Electric Boat ASA Docs",
    "Pilot Program",
)


def pilot_program_roots() -> list[Path]:
    """Candidate 'Pilot Program' directories, in priority order, de-duplicated.

    The fixed, known layouts come first and are NOT existence-checked (callers
    like 911 Setup use [0] as the default for error messages). After those,
    DISCOVERED layouts are appended — globbed from disk, so they exist — to
    cover machines where OneDrive named things differently. Colleagues' fresh
    installs hit exactly this (v0.8.6.1): their sync base wasn't one of the
    two hardcoded names, so every batch app failed to locate the root until
    the directory was set manually per app. Discovery covers:

    * any tenant display-name variant: ``~\\<Tenant>\\<site>\\Pilot Program``
    * a personal-OneDrive folder with any tenant suffix: ``~\\OneDrive - *``
    * "Add shortcut to My files" layouts, where the site folder — or the
      'Pilot Program' folder itself — sits inside the personal OneDrive
    * a OneDrive relocated off the user profile (siblings of ``%OneDrive%``)
    * the parent of any manually-set per-app directory override saved in
      Settings > Apps (a user-confirmed location outranks globbed guesses)
    """
    home = Path.home()
    site, pilot = _PILOT_REL
    od = os.environ.get("ONEDRIVE") or os.environ.get("OneDrive")

    out: list[Path] = []
    seen: set[str] = set()

    def add(root: Path) -> None:
        key = str(root).casefold()
        if key not in seen:
            seen.add(key)
            out.append(root)

    # Known fixed layouts — keep these first so machines that work today keep
    # resolving to the exact same path.
    add(home / "American Steel & Alum" / site / pilot)
    add(home / "OneDrive - American Steel & Alum" / site / pilot)
    if od:
        add(Path(od) / site / pilot)

    # Roots derived from saved per-app directory overrides. On a machine
    # where auto-detect failed, the user manually set some app's 922/911
    # folder in Settings > Apps — that override is ground truth for where the
    # library lives, so every other consumer (all batch apps, the feedback
    # writer) should benefit from it too. Those overrides point at a package
    # root directly under Pilot Program, so the override's PARENT is the
    # Pilot Program root. Keys with other semantics (pdf_directory,
    # output_dir, ...) are deliberately not consulted.
    try:
        from techdeck.core.settings import SettingsManager
        _ROOT_OVERRIDE_KEYS = ("base_path", "base_directory", "qtdr_922_root",
                               "qtdr_911_root", "qtdr_base_path", "forecast_dir")
        per_plugin_settings = SettingsManager().data.get("plugin_settings", {})
        for plugin_conf in per_plugin_settings.values():
            if not isinstance(plugin_conf, dict):
                continue
            for key in _ROOT_OVERRIDE_KEYS:
                raw = str(plugin_conf.get(key) or "").strip()
                if not raw:
                    continue
                parent = Path(raw).expanduser().parent
                if parent.is_dir():
                    add(parent)
    except Exception:
        # Settings must never break root resolution (e.g. plugin_sdk used
        # standalone in CLI testing outside the app).
        pass

    # Discovered layouts. Globs are shallow with fixed tails (no ** walks —
    # cheap even on OneDrive). Discovery must never break resolution, so any
    # filesystem oddity just skips it.
    try:
        containers = [home]
        if od:
            od_parent = Path(od).parent
            if str(od_parent).casefold() != str(home).casefold():
                containers.append(od_parent)
        for container in containers:
            # Any tenant-named sync root (also catches the site folder synced
            # inside a personal 'OneDrive - <tenant>' folder).
            for hit in container.glob(f"*/{site}/{pilot}"):
                if hit.is_dir():
                    add(hit)
        # 'Pilot Program' shortcut sitting directly inside a personal OneDrive
        # ("Add shortcut to My files" on the Pilot Program folder itself).
        personals = list(home.glob("OneDrive - *"))
        if od:
            personals.append(Path(od))
        for base in personals:
            for hit in base.glob(pilot):
                if hit.is_dir():
                    add(hit)
    except OSError:
        pass

    return out


def resolve_under_pilot_program(*parts: str) -> Optional[Path]:
    """Return the first existing '<pilot program root>/<parts...>' across all
    candidate roots, or None if none exist."""
    for root in pilot_program_roots():
        candidate = root.joinpath(*parts)
        if candidate.exists():
            return candidate
    return None


def library_roots(library_tail: str) -> list[Path]:
    """All EXISTING on-disk roots of a SharePoint QTDR library, regardless of how
    OneDrive synced it, de-duplicated. ``library_tail`` is the canonical library
    folder name, e.g. ``"922 QTDR Production Packages"``.

    pilot_program_roots() only covers the WHOLE-SITE sync layout
    (``<site>/Pilot Program/<library>``). But a colleague can instead sync a
    single document library directly, which OneDrive names ``<site> - <library>``
    (e.g. ``Communication site - 922 QTDR Production Packages``) with NO
    'Pilot Program' parent — so the canonical-name lookup misses it, and any
    consumer without a manual override (notably the feedback writer) can't find
    files in it. This covers both layouts plus saved per-app overrides."""
    out: list[Path] = []
    seen: set[str] = set()
    tail_cf = library_tail.casefold()

    def add(p: Path) -> None:
        try:
            if not p.is_dir():
                return
        except OSError:
            return
        key = str(p).casefold()
        if key not in seen:
            seen.add(key)
            out.append(p)

    # 1) Saved per-app base_path overrides whose folder IS this library (the
    #    override value itself is the library root — covers the 'Communication
    #    site - <library>' direct-sync naming a user pointed an app at).
    try:
        from techdeck.core.settings import SettingsManager
        per_plugin = SettingsManager().data.get("plugin_settings", {})
        for conf in per_plugin.values():
            if not isinstance(conf, dict):
                continue
            for key in ("base_path", "base_directory"):
                raw = str(conf.get(key) or "").strip()
                if raw and Path(raw).name.casefold().endswith(tail_cf):
                    add(Path(raw).expanduser())
    except Exception:
        pass

    # 2) Whole-site sync: <pilot program root>/<library>.
    for root in pilot_program_roots():
        add(root / library_tail)

    # 3) Direct single-library sync: '<site> - <library>' under the home dir, a
    #    tenant sync folder, or a personal 'OneDrive - <tenant>'. Shallow globs
    #    with a fixed tail (no ** walks), so cheap even on OneDrive.
    home = Path.home()
    od = os.environ.get("ONEDRIVE") or os.environ.get("OneDrive")
    containers = [home, *home.glob("OneDrive - *")]
    if od:
        containers += [Path(od), Path(od).parent]
    try:
        for container in containers:
            for hit in container.glob(f"*{library_tail}"):      # <container>/<site> - <library>
                add(hit)
            for hit in container.glob(f"*/*{library_tail}"):    # <container>/<tenant>/<site> - <library>
                add(hit)
    except OSError:
        pass

    return out


def _resolve_root(override: str, *parts: str) -> Optional[Path]:
    """Shared override-or-autodiscover logic. A non-empty override always wins
    (returned even if it doesn't exist, so the caller can show a precise
    error). Otherwise auto-discover under the Pilot Program roots, and — for a
    single-segment library — fall back to library_roots() so a directly-synced
    'Communication site - <library>' is found even without a manual override."""
    if override and override.strip():
        return Path(override.strip()).expanduser()
    hit = resolve_under_pilot_program(*parts)
    if hit is not None:
        return hit
    if len(parts) == 1:                       # single library folder
        roots = library_roots(parts[0])
        if roots:
            return roots[0]
    return None


def resolve_922_root(override: str = "") -> Optional[Path]:
    """'922 QTDR Production Packages' root."""
    return _resolve_root(override, "922 QTDR Production Packages")


def resolve_911_qtdr_root(override: str = "") -> Optional[Path]:
    """'911 QTDR' root."""
    return _resolve_root(override, "911 QTDR")


def resolve_forecast_dir(override: str = "") -> Optional[Path]:
    """'Forecast and Inventory Reports' root."""
    return _resolve_root(override, "Forecast and Inventory Reports")


# ─────────────────────────────────────────────────────────────────────────────
# Batch number parsing / batch folder location
# ─────────────────────────────────────────────────────────────────────────────

# Accepts "473", "Batch 473", "PO 473", "PO #473", "#473" (case-insensitive).
_BATCH_INPUT_RE = re.compile(
    r'^(?:(?:batch|po)\s+#?\s*|#\s*)([0-9]+)$', re.IGNORECASE
)


def parse_922_batch(raw: str) -> Optional[str]:
    """Parse a 922 batch number (digits) from free-form input.

    Returns the digit string, or None if nothing usable was entered.
    """
    if raw is None:
        return None
    raw = raw.strip()
    m = _BATCH_INPUT_RE.match(raw)
    if m:
        return m.group(1)
    if re.match(r'^[0-9]+$', raw):
        return raw
    return None


def normalize_911_batch(raw: str) -> str:
    """911 batches are alphanumeric (e.g. 'V060', 'S045'). Just trim + upcase."""
    return (raw or "").strip().upper()


def find_922_batch_path(root: Path, batch: str) -> Optional[Path]:
    """Locate 'Batch {n}' under the 922 root, checking the live root first and
    then the '1 - Completed' archive. Returns None if not found."""
    live = root / f"Batch {batch}"
    if live.exists():
        return live
    archived = root / "1 - Completed" / f"Batch {batch}"
    if archived.exists():
        return archived
    return None


def find_911_batch_folder(qtdr_root: Path, batch: str) -> Optional[Path]:
    """Locate a 911 batch folder (named exactly like the batch, e.g. 'V060')
    directly under the given root. Case-insensitive. Returns None if absent."""
    exact = qtdr_root / batch
    if exact.exists():
        return exact
    batch_upper = batch.upper()
    if qtdr_root.exists():
        for entry in qtdr_root.iterdir():
            if entry.is_dir() and entry.name.upper() == batch_upper:
                return entry
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Console input
# ─────────────────────────────────────────────────────────────────────────────

def request_text(params: dict, prompt: str) -> str:
    """Prompt the user for a free-form text answer through the TechDeck
    console, falling back to stdin input() when run standalone. Returns the
    raw string.

    Unlike :func:`request_batch_number` this never reads or writes the
    family-shared cache — every call prompts fresh. Use it for prompts whose
    answers should NOT be reused across same-family plugins (e.g. asking the
    user to pick a line, a mode, a filename).
    """
    console = params.get("console")
    if console is not None and hasattr(console, "request_input"):
        return console.request_input(prompt)
    return input(prompt + " ")


def request_directory(params: dict, title: str = "Select Folder",
                      start_dir: str = "") -> Optional[str]:
    """Ask the user to pick a folder via the native directory dialog (opened
    on the GUI thread by the console), falling back to a pasted-path stdin
    prompt when run standalone. Returns the chosen path string, or None if
    the user cancelled / entered nothing.

    Prefer this over making users paste folder paths through request_text —
    per-run folders (a batch folder, a ROOT of orders) should be clicked,
    not typed.
    """
    console = params.get("console")
    if console is not None and hasattr(console, "request_directory"):
        return console.request_directory(title, start_dir)
    raw = input(f"{title} (paste path): ").strip().strip('"')
    return raw or None


def show_warning(params: dict, title: str, text: str) -> None:
    """Show a modal warning popup (console GUI thread) and block until the
    user acknowledges it. Use for problems the user must see before moving
    on — a console log line scrolls past unnoticed. Headless (or on an older
    TechDeck without console.show_warning) it just logs the text."""
    console = params.get("console")
    if console is not None and hasattr(console, "show_warning"):
        try:
            console.show_warning(title, text)
            return
        except Exception:
            pass
    log = params.get("log", print)
    log(f"WARNING [{title}]: {text}")


def request_grouped_toggles(params: dict, groups: list, **kwargs) -> Optional[dict]:
    """Show the two-level master toggle dialog (stages as checkable parents,
    per-stage option toggles as children — GroupedToggleDialog) and block
    until submit. ``groups`` spec and the returned
    ``{group_key: {"enabled": bool, "options": {child_key: bool}}}`` shape are
    documented in techdeck/ui/dialogs/grouped_toggle_dialog.py; ``kwargs``
    pass through (window_title, header, subtext, run_button_text). Returns
    None if the user cancelled.

    Headless — or on an older TechDeck whose console lacks the method — it
    returns every group/child at its declared default (an all-defaults
    submit), so scripted runs never hang on a dialog.
    """
    console = params.get("console")
    if console is not None and hasattr(console, "request_grouped_toggles"):
        try:
            return console.request_grouped_toggles(groups, **kwargs)
        except TypeError:
            # Older console signature without these kwargs (version tolerance).
            return console.request_grouped_toggles(groups)
    return {g["key"]: {"enabled": bool(g.get("checked", True)),
                       "options": {c["key"]: bool(c.get("checked", True))
                                   for c in g.get("children", [])}}
            for g in groups}


def plugin_settings(plugin_id: str) -> dict:
    """The saved Settings > Apps values for ANY plugin id (empty dict when
    none are stored or the store is unreadable). Lets an orchestrating plugin
    run a sibling stage with the sibling's own configuration — the same values
    the executor would inject if that plugin ran standalone."""
    try:
        from techdeck.core.settings import SettingsManager
        return dict(SettingsManager().get_plugin_settings(plugin_id) or {})
    except Exception:
        return {}


def set_ticket_units(params: dict, units: int) -> None:
    """Report how many ticket-earning systems this run performed (default 1).

    An orchestrating plugin that runs N sibling stages inside ONE plugin run
    (e.g. 922 Setup running Teams Cards + Batch Repeater + Pallet Stamper)
    calls this with N so the shell awards N x TICKETS_PER_RUN on success
    instead of a single run's worth. Values below 1 clamp to 1; on an older
    TechDeck (executor unaware of the key) the extra units are simply ignored
    and the run pays the normal single-run tickets."""
    try:
        params["ticket_units"] = max(1, int(units))
    except (TypeError, ValueError):
        pass


# Run outcomes a plugin may report via set_run_outcome. Absence of a report
# (the default) is treated as a clean success — so existing plugins that simply
# return are unaffected.
RUN_OUTCOME_WARNING = "warning"   # ran to completion, but with issues to surface
RUN_OUTCOME_PARTIAL = "partial"   # some requested work was skipped or failed


def set_run_outcome(params: dict, status: str, message: str = "") -> None:
    """Report that this run finished WITHOUT raising but not cleanly, so
    TechDeck stops claiming a blank 'completed successfully'.

    Use for the middle ground the old all-or-nothing SUCCESS hid: a Teams
    webhook POST returned non-2xx, a nest had no forecast rows, one of several
    stages was skipped. Pass status = RUN_OUTCOME_WARNING or RUN_OUTCOME_PARTIAL
    and a short plain-English `message`; TechDeck shows it (⚠) instead of the ✅
    line, but the run still counts and still earns tickets — the work happened.

    A hard failure should still RAISE (that path stays ERROR). On an older
    TechDeck unaware of the key the run simply reports the normal success."""
    try:
        params["run_outcome"] = {
            "status": str(status),
            "message": str(message or ""),
        }
    except (TypeError, ValueError):
        pass


def request_batch_number(params: dict, prompt: str) -> str:
    """Prompt for a batch number through the TechDeck console, falling back to
    stdin input() when run standalone (no console). Returns the raw string.

    Family-shared caching: when this plugin runs as part of a same-family
    multi-plugin batch (Home page "Run Selected" with several 911s or several
    922s), the first plugin's answer is cached in
    ``params['shared_state'][family]['batch_number']`` and reused silently by
    subsequent same-family plugins in the same run. Cross-family runs and
    single-plugin runs prompt as before.
    """
    shared_state = params.get("shared_state")
    family = params.get("plugin_family")
    log = params.get("log") if callable(params.get("log")) else None

    if shared_state is not None and family:
        cached = shared_state.get(family, {}).get("batch_number")
        if cached:
            if log:
                log(f"[shared] Using batch number {cached} from prior {family} "
                    f"plugin in this run.")
            return cached

    console = params.get("console")
    if console is not None and hasattr(console, "request_input"):
        answer = console.request_input(prompt)
    else:
        answer = input(prompt + " ")

    if shared_state is not None and family and answer:
        shared_state.setdefault(family, {})["batch_number"] = answer
    return answer


# ─────────────────────────────────────────────────────────────────────────────
# Excel header helpers (openpyxl worksheets)
#
# Columns shift between batches/files, so always look up by header NAME. These
# replace the per-plugin header scanners.
# ─────────────────────────────────────────────────────────────────────────────

def find_header_col(ws, header_name: str, header_row: int) -> Optional[int]:
    """1-based column index in `header_row` whose value matches header_name
    (case-insensitive, stripped), or None."""
    target = header_name.strip().upper()
    for col in range(1, ws.max_column + 1):
        val = ws.cell(header_row, col).value
        if val is not None and str(val).strip().upper() == target:
            return col
    return None


def header_map(ws, header_row: int) -> dict[str, int]:
    """{UPPERCASE HEADER: 1-based col} for every string cell in `header_row`."""
    out: dict[str, int] = {}
    for col in range(1, ws.max_column + 1):
        val = ws.cell(header_row, col).value
        if isinstance(val, str) and val.strip():
            out[val.strip().upper()] = col
    return out


def find_header_row(ws, required: Iterable[str], max_scan: int = 30):
    """Scan the first `max_scan` rows for the row containing all `required`
    header names. Returns (row_index, header_map) or (None, {})."""
    required_upper = [r.strip().upper() for r in required]
    limit = min(ws.max_row, max_scan)
    for r in range(1, limit + 1):
        row_map = {}
        for c in range(1, ws.max_column + 1):
            v = ws.cell(row=r, column=c).value
            if isinstance(v, str) and v.strip():
                row_map[v.strip().upper()] = c
        if all(name in row_map for name in required_upper):
            return r, row_map
    return None, {}


# ─────────────────────────────────────────────────────────────────────────────
# 922 tube materials + PO (QF-QU-09) reading
#
# Source-material serials classify a part's stock. STANDARD tubes are
# laser-cuttable (we expect 7000 shop-print folders for orders that contain
# them). OVERSIZED tubes are too thick for the laser (>0.375" NOM) and are cut
# elsewhere, so they do NOT imply a 7000 folder. These sets are the single
# source of truth, shared by 922_lst_organizer and batch_auditor.
# ─────────────────────────────────────────────────────────────────────────────

STANDARD_TUBE_MATERIALS = {
    '218002867', '218003095', '218004492', '218012302', '218019939',
    '218019941', '218021954', '218026206', '218026875', '218026962',
    '218033112', '218136140', '40-00-2020', '40-07-1003',
}

OVERSIZED_TUBE_MATERIALS = {
    '181361440', '218000414', '218001209', '218001975', '218002101',
    '218002191', '218002642', '218002778', '218004273', '218012555',
    '218017859', '218018574', '218019943', '218020020', '218020119',
    '218026338', '218026500', '218032982',
}

ALL_TUBE_MATERIALS = STANDARD_TUBE_MATERIALS | OVERSIZED_TUBE_MATERIALS


def tube_class(serial) -> Optional[str]:
    """Classify a source-material serial: 'standard' (laser tube), 'oversized'
    (too thick for the laser), or None (not a tracked tube material)."""
    if serial is None:
        return None
    s = str(serial).strip()
    if s in STANDARD_TUBE_MATERIALS:
        return "standard"
    if s in OVERSIZED_TUBE_MATERIALS:
        return "oversized"
    return None


def read_qf_qu_09(po_path: Path):
    """Read a 922 'PO H{n} QF-QU-09 REV C' workbook's PO sheet.

    Returns (order_to_serials, dypn_to_order_serial):
      order_to_serials       -> {order: set(source_material_serial, ...)}
      dypn_to_order_serial   -> {dypn: (order, serial)}

    Serials are stripped strings, ready to pass to tube_class(). Header row is
    located by name (ORDER / DYPN / SOURCE MATERIAL), never by position.
    """
    order_to_serials: dict[str, set] = {}
    dypn_to_order_serial: dict[str, tuple] = {}

    wb = load_workbook_resilient(po_path, data_only=True)
    try:
        ws = wb['PO'] if 'PO' in wb.sheetnames else wb.active
        header_row, cols = find_header_row(ws, ['ORDER', 'DYPN', 'SOURCE MATERIAL'])
        if header_row is None:
            return order_to_serials, dypn_to_order_serial

        c_order, c_dypn, c_src = cols['ORDER'], cols['DYPN'], cols['SOURCE MATERIAL']
        for r in range(header_row + 1, ws.max_row + 1):
            def _v(c):
                v = ws.cell(r, c).value
                return str(v).strip() if v not in (None, '') else None
            order, dypn, serial = _v(c_order), _v(c_dypn), _v(c_src)
            if order:
                bucket = order_to_serials.setdefault(order, set())
                if serial:
                    bucket.add(serial)
            if order and dypn:
                dypn_to_order_serial[dypn] = (order, serial)
        return order_to_serials, dypn_to_order_serial
    finally:
        wb.close()


# ─────────────────────────────────────────────────────────────────────────────
# PDF helpers (PyMuPDF / fitz)
# ─────────────────────────────────────────────────────────────────────────────

def merge_pdfs(pdfs: list[Path], out_path: Path) -> None:
    """Merge `pdfs` (in order) into a single PDF at out_path."""
    import fitz
    out = fitz.open()
    try:
        for p in pdfs:
            ensure_local(p)
            src = fitz.open(str(p))
            try:
                out.insert_pdf(src)
            finally:
                src.close()
        out.save(str(out_path))
    finally:
        out.close()


def save_pdf_atomic(doc, dest_path: Path) -> None:
    """Save an open fitz document and atomically replace dest_path.

    fitz cannot save in place (especially after redactions), so write to a
    temp file on the same volume and os.replace it over the target. The caller
    still owns `doc` and should close it afterwards.
    """
    import fitz
    dest_path = Path(dest_path)
    with tempfile.NamedTemporaryFile(
        suffix=".pdf", delete=False, dir=str(dest_path.parent)
    ) as tmp:
        tmp_path = Path(tmp.name)
    doc.save(str(tmp_path), incremental=False, encryption=fitz.PDF_ENCRYPT_NONE)
    os.replace(str(tmp_path), str(dest_path))


# ─────────────────────────────────────────────────────────────────────────────
# OneDrive cloud-placeholder resilience
#
# On a Files-On-Demand tree, a file can EXIST (metadata is local — .exists(),
# globs, and size checks all pass) while its CONTENT is cloud-only. If the
# OneDrive client can't download it on demand, reads fail — openpyxl/zipfile
# raise OSError [Errno 22] "Invalid argument" on a workbook that is plainly
# sitting right there. Bit FormingFinder on a freshly-synced machine (the
# Batch 481 PO workbook, v0.8.6.1 debug report NRAPINI-LT).
# ─────────────────────────────────────────────────────────────────────────────

_CLOUD_ATTRS = (
    0x00001000  # FILE_ATTRIBUTE_OFFLINE
    | 0x00040000  # FILE_ATTRIBUTE_RECALL_ON_OPEN
    | 0x00400000  # FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS
)


def is_cloud_placeholder(path) -> bool:
    """True if `path` is a OneDrive cloud-only / recall-on-access placeholder."""
    try:
        attrs = os.stat(path).st_file_attributes
    except (OSError, AttributeError):
        return False
    return bool(attrs & _CLOUD_ATTRS)


def hydrate_cloud_file(path, log=None, attempts: int = 3, delay: float = 1.5) -> None:
    """Force OneDrive to download a cloud-only file by reading it end to end.

    Raises RuntimeError with user-actionable instructions if the content
    still can't be pulled (OneDrive client stopped, signed out, or offline).
    """
    path = Path(path)
    last_err = None
    for attempt in range(1, attempts + 1):
        try:
            with open(path, "rb") as fh:
                while fh.read(1024 * 1024):
                    pass
            return
        except OSError as exc:
            last_err = exc
            if log:
                log(f"OneDrive download attempt {attempt}/{attempts} failed: {exc}")
            time.sleep(delay)
    raise UserFacingError(
        problem=f"'{path.name}' is stored only in the cloud and Windows "
                f"couldn't download it.",
        fix="Make sure OneDrive is running and signed in, then try again. To "
            "avoid this, right-click the folder in File Explorer and choose "
            "'Always keep on this device'.",
        detail=str(path),
    ) from last_err


def ensure_local(path, log=None) -> None:
    """Make sure `path`'s CONTENT is on disk before a library reads it.

    No-op for normal files; for a OneDrive cloud-only placeholder it forces
    the download (with retries) or raises a user-actionable RuntimeError.
    Call immediately before fitz.open / PdfReader / pd.read_excel / text
    reads of anything under the OneDrive tree (Hard Rule 13)."""
    if is_cloud_placeholder(path):
        if log:
            log(f"'{Path(path).name}' is cloud-only - asking OneDrive to download it...")
        hydrate_cloud_file(path, log=log)


def locked_file_error(path, cause: Exception | None = None) -> "UserFacingError":
    """A UserFacingError for a file Windows won't let us read because another
    program holds it open — PermissionError / [Errno 13].

    This is a DIFFERENT failure from the cloud-only placeholder (Errno 22 /
    BadZipFile, handled by ensure_local): here the file's content is on disk,
    but Excel/Acrobat has it open, or a OneDrive co-author locked it. No
    amount of retrying or copy-to-temp helps — the first opener chose the
    share mode — so the only fix is for the user to close the file. Bit
    902 DXF Prep when the pricing .xlsm was open in Excel (Errno 13,
    CPENG_TOWERPC, v0.8.6.8)."""
    path = Path(path)
    return UserFacingError(
        problem=f"'{path.name}' is open in another program (usually Excel), so "
                f"TechDeck can't read it.",
        fix=f"Close the file everywhere it's open, then run again. If it stays "
            f"stuck, delete the '~${path.stem}' file in that folder.",
        detail=str(path),
    )


def _is_share_lock(exc: Exception) -> bool:
    """True for a Windows sharing-violation / permission-denied read
    (PermissionError, or any OSError with errno 13). NOT a cloud placeholder
    (that's errno 22)."""
    return isinstance(exc, PermissionError) or getattr(exc, "errno", None) == 13


def load_workbook_resilient(path, log=None, **kwargs):
    """openpyxl.load_workbook that survives OneDrive cloud-only placeholders
    AND turns a locked-open workbook into a clear instruction (not a crash).

    A dehydrated workbook fails inside zipfile with OSError [Errno 22] even
    though the path exists — and zipfile's end-of-central-directory reader
    CATCHES that OSError itself and re-raises it as BadZipFile ("File is not
    a zip file"), so the placeholder failure wears two disguises. Hydrate
    placeholders up front (sequential read — the recall path OneDrive
    actually honors; zipfile's backwards seek can stall the recall for 60s+
    and then fail), and treat both exception types as the placeholder
    signature on the retry. Bit 911 Setup as "File is not a zip file"
    (v0.8.6.5, LAPTOP-1AMLBK7B).

    A workbook the user still has open in Excel fails with PermissionError
    [Errno 13] instead — surface `locked_file_error` so they know to close
    it (bit 902 DXF Prep, v0.8.6.8). Use this for ANY workbook under the
    OneDrive tree (Hard Rule 13)."""
    import openpyxl
    import zipfile
    ensure_local(path, log=log)
    try:
        return openpyxl.load_workbook(path, **kwargs)
    except Exception as exc:
        if _is_share_lock(exc):
            raise locked_file_error(path, exc) from exc
        if not isinstance(exc, (OSError, zipfile.BadZipFile)):
            raise
        if not is_cloud_placeholder(path):
            raise
        if log:
            log(f"'{Path(path).name}' is cloud-only - asking OneDrive to download it...")
        hydrate_cloud_file(path, log=log)
        return openpyxl.load_workbook(path, **kwargs)


def read_excel_resilient(path, log=None, **kwargs):
    """pandas.read_excel that survives OneDrive placeholders and reports a
    locked-open workbook clearly — the pandas sibling of
    `load_workbook_resilient`. Pass the same args you'd give pd.read_excel
    (sheet_name, header, usecols, ...). Use for ANY user-editable workbook
    read via pandas (Hard Rule 13)."""
    import pandas as pd
    import zipfile
    ensure_local(path, log=log)
    try:
        return pd.read_excel(path, **kwargs)
    except Exception as exc:
        if _is_share_lock(exc):
            raise locked_file_error(path, exc) from exc
        if not isinstance(exc, (OSError, zipfile.BadZipFile)) or not is_cloud_placeholder(path):
            raise
        if log:
            log(f"'{Path(path).name}' is cloud-only - asking OneDrive to download it...")
        hydrate_cloud_file(path, log=log)
        return pd.read_excel(path, **kwargs)


def open_excel_resilient(path, log=None):
    """pandas.ExcelFile opened resiliently (placeholder hydrate + locked-open
    message). Returns a pd.ExcelFile whose sheets you then read with
    pd.read_excel(xls, sheet_name=...) — the file lock bites at open time, so
    the returned handle reads sheets without re-touching the lock."""
    import pandas as pd
    import zipfile
    ensure_local(path, log=log)
    try:
        return pd.ExcelFile(path)
    except Exception as exc:
        if _is_share_lock(exc):
            raise locked_file_error(path, exc) from exc
        if not isinstance(exc, (OSError, zipfile.BadZipFile)) or not is_cloud_placeholder(path):
            raise
        if log:
            log(f"'{Path(path).name}' is cloud-only - asking OneDrive to download it...")
        hydrate_cloud_file(path, log=log)
        return pd.ExcelFile(path)


def copy_resilient(src, dest, log=None):
    """shutil.copy2 that hydrates a cloud-only source first and reports a
    locked-open file clearly instead of crashing with a raw Errno 13.

    The copy-to-temp pattern (stage a live workbook, then read/edit the copy so
    Excel never sees the synced path) still fails at the COPY if the user has
    the source open in Excel — same PermissionError class as a direct read.
    On a lock we name the actual culprit: usually the source, but on a
    write-back it's the destination. Returns the destination Path."""
    src, dest = Path(src), Path(dest)
    ensure_local(src, log=log)
    try:
        shutil.copy2(src, dest)
        return dest
    except Exception as exc:
        if not _is_share_lock(exc):
            raise
        # Which side is locked? If we can't even read the source, it's the
        # source; otherwise the open handle is on the destination.
        culprit = dest
        try:
            with open(src, "rb") as fh:
                fh.read(1)
        except OSError:
            culprit = src
        raise locked_file_error(culprit, exc) from exc


# ─────────────────────────────────────────────────────────────────────────────
# Power Automate webhook helpers
#
# One JSON POST + one preview-file writer, shared by every plugin that talks
# to a Power Automate flow (922 Setup card creation, 922 Batch Repeater
# REPEAT tagging). Centralized per the Fix Protocol so logging, timeouts and
# error wording stay identical across callers.
# ─────────────────────────────────────────────────────────────────────────────

def post_webhook(url: str, payload: dict, log) -> bool:
    """POST `payload` as JSON to a Power Automate webhook. Returns True on a
    2xx response; logs the failure (and the flow's response body, truncated)
    otherwise. `requests` is bundled (the updater uses it) and respects
    corporate proxies."""
    import requests

    try:
        resp = requests.post(url, json=payload, timeout=60)
    except requests.exceptions.RequestException as exc:
        log(f"ERROR: could not reach the webhook: {exc}")
        log("Check the URL in Settings, your network/VPN, and that the flow is on.")
        return False

    if 200 <= resp.status_code < 300:
        log(f"Webhook accepted the request (HTTP {resp.status_code}).")
        body = (resp.text or "").strip()
        if body:
            log(f"Response: {body[:500]}")
        return True

    log(f"ERROR: webhook returned HTTP {resp.status_code}.")
    log(f"Response: {(resp.text or '')[:500]}")
    return False


def write_payload_preview(payload: dict, filename: str, log) -> None:
    """Save a webhook payload to %LOCALAPPDATA%/TechDeck/<filename> so a dry
    run leaves something inspectable (and replayable into the flow's test
    pane). Failures only log — a preview must never kill the run."""
    import json as _json
    import os
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    out = Path(base) / "TechDeck" / filename
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            _json.dump(payload, fh, indent=2)
        log(f"Preview written to: {out}")
    except OSError as exc:
        log(f"(Could not write preview file: {exc})")
