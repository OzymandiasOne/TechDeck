"""
922 Pallet Stamper Plugin for TechDeck
Stamps work-packet PDFs with PO batch number and pallet assignments.

Integrates with TechDeck's console output and settings system.
"""

import os
import re
import sys
from pathlib import Path
from typing import Dict, Any, Optional
import pandas as pd
import fitz  # PyMuPDF
import warnings

# Suppress openpyxl warnings
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

# Matches any individual span that is part of an old- or new-format stamp.
# Old format produced two separate spans: "PO 401" and "PALLET 2"
# New format produces one span:           "Batch 401 Pallet 2"
_STAMP_SPAN_RE = re.compile(
    r'^(PO\s+\d+|PALLET\s+\d+|Batch\s+\d+\s+Pallet\s+\d+)$',
    re.IGNORECASE
)

# Red color as packed int (fitz encodes RGB 1,0,0 → 0xFF0000 → 16711680)
_RED_COLOR_INT = 0xFF0000


def get_console_input(params: Dict[str, Any], prompt: str) -> str:
    """Get input from user via TechDeck console, falling back to stdin."""
    console = params.get('console')
    if console and hasattr(console, 'request_input'):
        return console.request_input(prompt)
    return input(f"{prompt}: ")


def parse_batch_number(raw: str) -> Optional[str]:
    """
    Extract a numeric batch number from user input.

    Accepts any of:
        "401", "Batch 401", "batch 401", "PO 401", "po 401", "PO#401", etc.

    Returns the digit string (e.g. "401"), or None if no digits found.
    """
    match = re.search(r'\d+', raw)
    return match.group(0) if match else None


def anchor_xy(page, h_offset_in: float, v_offset_in: float):
    """
    Calculate anchor coordinates for stamp based on page rotation.

    Args:
        page: PyMuPDF page object
        h_offset_in: Horizontal offset in inches from right edge
        v_offset_in: Vertical offset in inches from bottom edge

    Returns:
        Tuple of (x, y) coordinates
    """
    ppi = 72.0  # points per inch
    off_x = h_offset_in * ppi
    off_y = v_offset_in * ppi
    w, h = page.rect.width, page.rect.height
    rot = page.rotation % 360

    if rot == 0:
        x, y = w - off_x, h - off_y
    elif rot == 90:
        x, y = off_y, h - off_x
    elif rot == 180:
        x, y = off_x, off_y
    elif rot == 270:
        x, y = w - off_y, off_x
    else:
        x, y = w - off_x, h - off_y

    return x, y


def _find_all_stamp_rects(page) -> list:
    """
    Scan page for any red spans that are part of an old- or new-format stamp.

    Old format (original plugin) produced two separate spans on two lines:
        "PO 401"   and   "PALLET 2"
    New format produces a single span:
        "Batch 401 Pallet 2"

    Returns a list of fitz.Rect (one per matching span, with 2pt padding),
    or an empty list if no stamp is found.
    """
    rects = []
    blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if span.get("color", 0) != _RED_COLOR_INT:
                    continue
                if _STAMP_SPAN_RE.match(span["text"].strip()):
                    b = span["bbox"]
                    rects.append(fitz.Rect(b[0] - 2, b[1] - 2, b[2] + 2, b[3] + 2))

    return rects


def stamp_single(pdf_path: str, batch_no: str, pallet_no: str, font_size: int,
                 h_offset_in: float, v_offset_in: float, log) -> bool:
    """
    Stamp first page of PDF with "Batch <batch_no> Pallet <pallet_no>".

    If a previous stamp matching that pattern is found on the page it is
    removed (via redaction) before the new stamp is inserted.  Both
    operations happen in a single open/save cycle.

    Args:
        pdf_path: Path to PDF file
        batch_no: Batch number
        pallet_no: Pallet number
        font_size: Font size in points
        h_offset_in: Horizontal offset in inches
        v_offset_in: Vertical offset in inches
        log: Logging callback

    Returns:
        True if successful, False otherwise
    """
    try:
        tmp = pdf_path + ".tmp"

        doc = fitz.open(pdf_path)
        try:
            page = doc[0]

            # --- Remove any previously inserted stamp ---
            stamp_rects = _find_all_stamp_rects(page)
            if stamp_rects:
                for r in stamp_rects:
                    page.add_redact_annot(r, fill=(1, 1, 1))
                page.apply_redactions()

            # --- Insert new stamp ---
            x, y = anchor_xy(page, h_offset_in, v_offset_in)
            text_rotate = (-page.rotation) % 180

            page.insert_text(
                fitz.Point(x, y),
                f"Batch {batch_no} Pallet {pallet_no}",
                fontsize=font_size,
                fontname="helv",
                fill=(1, 0, 0),
                rotate=text_rotate
            )

            doc.save(tmp, incremental=False, encryption=fitz.PDF_ENCRYPT_NONE)
        finally:
            doc.close()

        os.replace(tmp, pdf_path)
        return True

    except Exception as e:
        log(f"❌ PDF error for {pdf_path}: {e}")
        return False


def run(params: Dict[str, Any], progress_callback, cancel_event) -> None:
    """
    Main plugin execution function.

    Args:
        params: Dictionary containing 'settings', 'console', 'log'
        progress_callback: Function to call with progress (0-100)
        cancel_event: threading.Event to check for cancellation
    """
    settings = params.get('settings', {})
    log = params.get('log', print)

    log("📦 Starting 922 Pallet Stamper...")
    progress_callback(0)

    # Get settings
    base_path = settings.get('base_path', '')
    font_size = settings.get('font_size', 18)
    h_offset = float(settings.get('h_offset_inches', 4.0))
    v_offset = float(settings.get('v_offset_inches', 7.0))

    # Validate base path
    if not base_path:
        log("❌ Base directory not configured!")
        log("Go to: Settings > Plugin Settings > 922 Pallet Stamper")
        raise ValueError("Base directory not configured")

    # Prompt for batch number via console
    raw_input = get_console_input(
        params,
        'Enter batch number (e.g. "401", "Batch 401", "PO 401"):'
    )
    batch_no = parse_batch_number(raw_input.strip())

    if not batch_no:
        log("❌ No valid batch number entered.")
        raise ValueError("No valid batch number entered")

    log(f"🔢 Batch number: {batch_no}")

    # Construct paths
    batch_path = Path(base_path) / f"Batch {batch_no}"
    doc_folder = batch_path / f"Batch {batch_no} - Documentation"
    xl_path = doc_folder / f"PO H{batch_no} Pallet & Rod Organizer.xlsx"

    # Validate paths
    if not batch_path.is_dir():
        log(f"❌ Batch folder not found: {batch_path}")
        raise ValueError(f"Batch folder not found: {batch_path}")

    if not xl_path.is_file():
        log(f"❌ Organizer Excel file not found: {xl_path}")
        raise ValueError(f"Organizer Excel file not found: {xl_path}")

    log(f"📁 Batch folder: {batch_path.name}")
    log(f"📊 Reading pallet assignments from Excel...")
    progress_callback(10)

    # Read Excel pallet organizer
    try:
        df = pd.read_excel(
            xl_path,
            sheet_name="Pallet Organizer",
            usecols="B,E,H",
            header=3,
            nrows=19
        )
    except Exception as e:
        log(f"❌ Excel read error: {e}")
        raise RuntimeError(f"Excel read error: {e}")

    # Build order-to-pallet mapping
    order_to_pallet = {}
    for col_idx, col in enumerate(df.columns):
        pallet = str(col_idx + 1)
        for order in df[col].dropna():
            order_to_pallet[str(order).strip().upper()] = pallet

    log(f"✅ Found {len(order_to_pallet)} order-to-pallet mappings")
    progress_callback(20)

    if cancel_event.is_set():
        log("Operation cancelled")
        return

    # Collect all order subfolders to process
    subfolders = [
        sub for sub in batch_path.iterdir()
        if sub.is_dir() and not sub.name.endswith("- Documentation")
    ]

    total = len(subfolders)
    stamped_count = 0
    skipped_count = 0
    error_count = 0

    log(f"🔍 Processing {total} order folders...")
    log("")

    for idx, sub in enumerate(subfolders):
        if cancel_event.is_set():
            log("")
            log("⚠️ Cancelled by user")
            log(f"Stamped {stamped_count} of {idx}")
            return

        progress = 20 + int((idx / max(total, 1)) * 75)
        progress_callback(progress)

        # Extract order number (everything before first hyphen)
        parts = sub.name.split('-', 1)
        order_no = parts[0].strip().upper()
        pallet_no = order_to_pallet.get(order_no)

        if pallet_no is None:
            log(f"⚠️ No pallet assignment for order {order_no}")
            skipped_count += 1
            continue

        # Find first PDF in order folder
        pdfs = [f for f in sub.iterdir() if f.suffix.lower() == '.pdf']

        if not pdfs:
            log(f"⚠️ No PDF found in {sub.name}")
            skipped_count += 1
            continue

        pdf_path = str(pdfs[0])
        if stamp_single(pdf_path, batch_no, pallet_no, font_size, h_offset, v_offset, log):
            log(f"✔ Stamped {order_no} → Pallet {pallet_no}")
            stamped_count += 1
        else:
            error_count += 1

    progress_callback(95)

    log("")
    log("=" * 50)
    log("📊 STAMP SUMMARY")
    log("=" * 50)
    log(f"✅ Successfully stamped: {stamped_count}")

    if skipped_count > 0:
        log(f"⚠️ Skipped: {skipped_count}")

    if error_count > 0:
        log(f"❌ Errors: {error_count}")

    log("=" * 50)

    progress_callback(100)

    if error_count > 0:
        log("⚠️ Completed with errors")
    else:
        log("🎉 All done successfully!")


if __name__ == "__main__":
    import threading

    test_settings = {
        'base_path': os.path.join(
            os.path.expanduser("~"),
            "American Steel & Alum",
            "Communication site - Electric Boat ASA Docs",
            "Pilot Program",
            "922 QTDR Production Packages"
        ),
        'font_size': 18,
        'h_offset_inches': 4.0,
        'v_offset_inches': 7.0
    }

    cancel_event = threading.Event()

    def progress(p):
        print(f"Progress: {p}%")

    try:
        run(
            params={'settings': test_settings, 'log': print},
            progress_callback=progress,
            cancel_event=cancel_event
        )
        print("\n✅ Done!")
    except Exception as e:
        print(f"\n❌ Failed: {e}")
