"""
911 Remove Ticket Plugin
========================
Scans a directory for PDF files, removes any pages containing "PART SKETCH"
text, and saves the result as "{stem} Move Ticket Omit.pdf" inside a
"Move Ticket Omit" subfolder. Original PDFs are never modified.
"""

import tempfile
import shutil
import threading
from pathlib import Path

try:
    import fitz
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from pypdf import PdfReader, PdfWriter
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False


def _find_part_sketch_pages(pdf_path: Path) -> set:
    """Return a set of 0-based page indices that contain 'PART SKETCH' text."""
    indices = set()
    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        return indices

    for i, page in enumerate(doc):
        text = page.get_text("text") or ""
        if "PART SKETCH" in text:
            indices.add(i)

    doc.close()
    return indices


def _process_pdf(pdf_path: Path, output_path: Path, log) -> bool:
    """
    Remove PART SKETCH pages from pdf_path and write to output_path.
    Returns True on success, False if skipped or failed.
    """
    sketch_pages = _find_part_sketch_pages(pdf_path)

    if not sketch_pages:
        log(f"  Skipped (no PART SKETCH pages): {pdf_path.name}")
        return False

    try:
        reader = PdfReader(str(pdf_path))
        total = len(reader.pages)
        keep = [i for i in range(total) if i not in sketch_pages]

        if not keep:
            log(f"  WARNING: All {total} pages are PART SKETCH — nothing to write for {pdf_path.name}")
            return False

        writer = PdfWriter()
        for idx in keep:
            writer.add_page(reader.pages[idx])

        # Write to temp file first, then move (fitz rule applies to pypdf too)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name

        with open(tmp_path, "wb") as f:
            writer.write(f)

        shutil.move(tmp_path, str(output_path))

        removed = len(sketch_pages)
        kept = len(keep)
        log(f"  {pdf_path.name}: removed {removed} page(s), kept {kept} -> {output_path.name}")
        return True

    except Exception as e:
        log(f"  ERROR processing {pdf_path.name}: {e}")
        return False


def run(params: dict, progress_callback: callable, cancel_event: threading.Event):
    log = params.get("log", print)
    settings = params.get("settings", {})
    console = params.get("console")

    if not PYMUPDF_AVAILABLE:
        log("ERROR: PyMuPDF (fitz) is not available. Cannot detect PART SKETCH pages.")
        return

    if not PYPDF_AVAILABLE:
        log("ERROR: pypdf is not available. Cannot write output PDFs.")
        return

    # --- Resolve directory ---
    raw_dir = (settings.get("pdf_directory") or "").strip()

    if raw_dir:
        pdf_dir = Path(raw_dir)
    else:
        if console and hasattr(console, "request_input"):
            raw_dir = console.request_input("Enter path to PDF directory:")
        else:
            raw_dir = input("Enter path to PDF directory: ")
        pdf_dir = Path(raw_dir.strip())

    if not pdf_dir.exists() or not pdf_dir.is_dir():
        log(f"ERROR: Directory not found: {pdf_dir}")
        return

    log(f"Scanning: {pdf_dir}")

    pdfs = sorted(pdf_dir.glob("*.pdf"))
    if not pdfs:
        log("No PDF files found in the specified directory.")
        return

    output_dir = pdf_dir / "Move Ticket Omit"
    output_dir.mkdir(exist_ok=True)
    log(f"Output folder: {output_dir.name}")

    progress_callback(5)

    processed = 0
    skipped = 0
    errors = 0
    total = len(pdfs)

    for i, pdf_path in enumerate(pdfs):
        if cancel_event.is_set():
            log("Cancelled.")
            return

        # Skip files already in the output folder (shouldn't normally be there, but guard anyway)
        if pdf_path.parent == output_dir:
            continue

        output_name = f"{pdf_path.stem} Move Ticket Omit.pdf"
        output_path = output_dir / output_name

        log(f"[{i+1}/{total}] {pdf_path.name}")

        try:
            ok = _process_pdf(pdf_path, output_path, log)
            if ok:
                processed += 1
            else:
                skipped += 1
        except Exception as e:
            log(f"  UNEXPECTED ERROR: {e}")
            errors += 1

        pct = 5 + int(90 * (i + 1) / total)
        progress_callback(pct)

    progress_callback(100)
    log(f"\nDone. Processed: {processed}  Skipped (no sketches): {skipped}  Errors: {errors}")
