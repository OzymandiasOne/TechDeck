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
from pathlib import Path
from typing import Iterable, Optional


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


def _resolve_root(override: str, *parts: str) -> Optional[Path]:
    """Shared override-or-autodiscover logic. A non-empty override always wins
    (returned even if it doesn't exist, so the caller can show a precise
    error). Otherwise auto-discover under the Pilot Program roots."""
    if override and override.strip():
        return Path(override.strip()).expanduser()
    return resolve_under_pilot_program(*parts)


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
    import openpyxl
    order_to_serials: dict[str, set] = {}
    dypn_to_order_serial: dict[str, tuple] = {}

    wb = openpyxl.load_workbook(po_path, data_only=True)
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
