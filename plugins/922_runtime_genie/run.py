"""
922 Runtime Genie Plugin
========================
Scans 7000 folders in a 922 batch for CNC machine time data, matches each PDF
against the LST reference file list, sums machine times, and writes a run time
estimate (with 40% buffer) to the batch LST folder.

PDF text extraction uses pypdf (simple text-layer PDFs only).
"""
from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Optional, Set

from pypdf import PdfReader

try:
    from techdeck.core import plugin_sdk as sdk
except ModuleNotFoundError:
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from techdeck.core import plugin_sdk as sdk

# ── Regex patterns ─────────────────────────────────────────────────────────────

# Match "Machine time decimal ... <number> min" with flexible spacing/punctuation
_MACHINE_TIME_RE = re.compile(
    r'machine\s+time\s+decimal[^0-9]*([0-9]+\.?[0-9]*)\s*min',
    re.IGNORECASE,
)

SKIP_FOLDER_NAMES = frozenset({"repeat batches"})

# ── LST reference collection ───────────────────────────────────────────────────

def _collect_lst_stems(lst_dir: Path) -> Set[str]:
    """Return case-folded stems of all .lst files found recursively in lst_dir."""
    stems: Set[str] = set()
    if not lst_dir.exists():
        return stems
    for p in lst_dir.rglob("*.lst"):
        stems.add(p.stem.casefold())
    return stems

# ── PDF extraction ─────────────────────────────────────────────────────────────

def _extract_machine_time(pdf_path: Path) -> tuple[Optional[float], Optional[str]]:
    """Return (value_in_minutes, error_message). Value is None on failure."""
    try:
        sdk.ensure_local(pdf_path)  # OneDrive placeholder -> download first (Hard Rule 13)
        reader = PdfReader(str(pdf_path))
        for page in reader.pages:
            text = page.extract_text() or ""
            m = _MACHINE_TIME_RE.search(text)
            if m:
                return float(m.group(1)), None
        return None, "Machine time decimal line not found in PDF text"
    except Exception as exc:
        return None, str(exc)

# ── 7000 folder discovery ──────────────────────────────────────────────────────

def _find_7000_folders(order_dir: Path) -> list[Path]:
    """Find all 7000 folders that live under a CAD-AND-SHOP-PRINTS subtree."""
    results = []
    for p in order_dir.rglob("7000"):
        if not p.is_dir():
            continue
        parts_lower = [seg.lower() for seg in p.parts]
        if "cad-and-shop-prints" in parts_lower:
            results.append(p)
    return results

# ── Plugin entry point ─────────────────────────────────────────────────────────

def run(params: dict, progress_callback, cancel_event: threading.Event) -> None:
    log = params.get('log', print)
    settings = params.get('settings', {}) or {}

    log("Starting 922 Runtime Genie...")
    progress_callback(0)

    # ── Batch input = pick the 'Batch NNN' folder ─────────────────────────────
    # (Sentry Drone capable, family-cache aware — a queued 922 run prompts at
    # most once.)
    picked = sdk.request_922_batch_folder(params, settings.get('base_path', ''))
    if picked is None or cancel_event.is_set():
        return  # user cancelled — the helper already flagged the run
    batch_no, batch_path = picked
    progress_callback(5)

    # ── LST reference stems ────────────────────────────────────────────────────
    lst_dir = batch_path / f"Batch {batch_no} - Documentation" / "LST"
    log(f"LST reference folder: {lst_dir}")
    lst_stems = _collect_lst_stems(lst_dir)
    log(f"LST reference files: {len(lst_stems)}")
    if not lst_stems:
        log("WARNING: No .lst files found in LST folder - all PDFs will be skipped.")
    progress_callback(10)

    # ── Order folders ──────────────────────────────────────────────────────────
    doc_folder_name = f"Batch {batch_no} - Documentation"
    order_dirs = []
    for child in sorted(d for d in batch_path.iterdir() if d.is_dir()):
        if child.name == doc_folder_name:
            continue
        if child.name.strip().casefold() in SKIP_FOLDER_NAMES:
            continue
        order_dirs.append(child)

    log(f"Order folders to scan: {len(order_dirs)}")
    progress_callback(15)

    if not order_dirs:
        raise RuntimeError(f"No order folders found in {batch_path}")

    # ── Scan each order folder ─────────────────────────────────────────────────
    total_minutes = 0.0
    matched_count = 0
    skipped_no_match = 0
    skipped_no_time = 0

    for i, order_dir in enumerate(order_dirs):
        if cancel_event.is_set():
            log("Cancelled.")
            return

        progress_callback(15 + int(i / len(order_dirs) * 70))

        folders_7000 = _find_7000_folders(order_dir)
        if not folders_7000:
            continue

        for folder_7000 in folders_7000:
            if cancel_event.is_set():
                log("Cancelled.")
                return

            pdfs = list(folder_7000.glob("*.pdf"))
            if not pdfs:
                continue

            if len(pdfs) > 1:
                names = ", ".join(p.name for p in pdfs)
                log(f"  WARNING: {len(pdfs)} PDFs in {folder_7000} - using first alphabetically: {pdfs[0].name} (others: {names})")

            pdf = sorted(pdfs)[0]

            if pdf.stem.casefold() not in lst_stems:
                skipped_no_match += 1
                continue

            minutes, err = _extract_machine_time(pdf)
            if minutes is None:
                skipped_no_time += 1
                log(f"  WARNING: Could not extract machine time from {pdf.name} - {err}")
                continue

            log(f"  {pdf.stem}: {minutes} min")
            total_minutes += minutes
            matched_count += 1

    progress_callback(85)

    if cancel_event.is_set():
        log("Cancelled.")
        return

    # ── Calculations ───────────────────────────────────────────────────────────
    total_seconds = total_minutes * 60.0
    total_hours = total_minutes / 60.0
    final_hours = total_hours * 1.4

    # ── Write output file ──────────────────────────────────────────────────────
    lst_dir.mkdir(parents=True, exist_ok=True)
    out_path = lst_dir / f"Run Time Estimate - Batch {batch_no}.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"Run Time Estimate - Batch {batch_no}\n")
        f.write("=" * 30 + "\n")
        f.write(f"Parts matched : {matched_count}\n")
        f.write(f"Total (seconds): {total_seconds:.1f} seconds\n")
        f.write(f"Total (hours)  : {total_hours:.2f} hours\n")
        f.write(f"Final (hours)  : {final_hours:.2f} hours\n")

    progress_callback(100)

    # ── Console summary ────────────────────────────────────────────────────────
    log("=" * 50)
    log(f"Run Time Estimate - Batch {batch_no}")
    log("=" * 50)
    log(f"Parts matched    : {matched_count}")
    log(f"Total (seconds)  : {total_seconds:.1f}")
    log(f"Total (hours)    : {total_hours:.2f}")
    log(f"Final (hours)    : {final_hours:.2f}  (40% buffer applied)")
    if skipped_no_match:
        log(f"Skipped (no LST match)   : {skipped_no_match}")
    if skipped_no_time:
        log(f"Skipped (no time in PDF) : {skipped_no_time}")
    log(f"\nOutput: {out_path}")
    log("=" * 50)


# ── Standalone test harness ────────────────────────────────────────────────────
if __name__ == "__main__":
    import threading
    cancel = threading.Event()
    run(
        params={'log': print, 'settings': {}, 'console': None},
        progress_callback=lambda p: print(f"[{p}%]"),
        cancel_event=cancel,
    )
