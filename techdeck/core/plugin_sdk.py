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

    Covers the two folder names OneDrive uses ('American Steel & Alum' and
    'OneDrive - American Steel & Alum') plus whatever the ONEDRIVE env var
    points at. Existence is NOT checked here — see resolve_under_pilot_program.
    """
    home = Path.home()
    bases = [
        home / "American Steel & Alum",
        home / "OneDrive - American Steel & Alum",
    ]
    od = os.environ.get("ONEDRIVE") or os.environ.get("OneDrive")
    if od:
        bases.append(Path(od))

    seen: set[str] = set()
    out: list[Path] = []
    for base in bases:
        root = base.joinpath(*_PILOT_REL)
        key = str(root).casefold()
        if key not in seen:
            seen.add(key)
            out.append(root)
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

def request_batch_number(params: dict, prompt: str) -> str:
    """Prompt for a batch number through the TechDeck console, falling back to
    stdin input() when run standalone (no console). Returns the raw string."""
    console = params.get("console")
    if console is not None and hasattr(console, "request_input"):
        return console.request_input(prompt)
    return input(prompt + " ")


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
