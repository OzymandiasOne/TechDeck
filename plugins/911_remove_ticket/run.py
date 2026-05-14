"""
911 Remove Ticket Plugin
========================
Scans a directory for PDF files, lists them numbered for selection, removes
any pages containing "PART SKETCH" text from selected files, and saves the
result as "{stem} Move Ticket Omit.pdf" inside a "Move Ticket Omit" subfolder.
Original PDFs are never modified.
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


def _parse_selection(response: str, total_pdfs: int) -> list | None:
    """
    Parse user selection string. Returns a list of 0-based indices into the
    pdfs list, or None if the input is invalid.

    Accepts:
      - "all" or the all-option number  -> all indices
      - space/comma-separated numbers   -> specific indices
    """
    text = response.strip().lower()
    all_num = str(total_pdfs + 1)

    if text == "all" or text == all_num:
        return list(range(total_pdfs))

    # Parse space/comma-separated numbers
    tokens = text.replace(",", " ").split()
    indices = []
    for token in tokens:
        if not token.isdigit():
            return None
        n = int(token)
        if n < 1 or n > total_pdfs:
            return None
        idx = n - 1
        if idx not in indices:
            indices.append(idx)

    return indices if indices else None


def run(params: dict, progress_callback: callable, cancel_event: threading.Event):
    log = params.get("log", print)
    settings = params.get("settings", {})
    console = params.get("console")

    def prompt(msg):
        if console and hasattr(console, "request_input"):
            return console.request_input(msg)
        return input(msg + " ")

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
        raw_dir = prompt("Enter path to PDF directory:")
        pdf_dir = Path(raw_dir.strip())

    if not pdf_dir.exists() or not pdf_dir.is_dir():
        log(f"ERROR: Directory not found: {pdf_dir}")
        return

    pdfs = sorted(p for p in pdf_dir.glob("*.pdf")
                  if p.parent != pdf_dir / "Move Ticket Omit")

    if not pdfs:
        log("No PDF files found in the specified directory.")
        return

    # --- List PDFs for selection ---
    log(f"\nFound {len(pdfs)} PDF(s) in: {pdf_dir.name}")
    log("-" * 48)
    for i, p in enumerate(pdfs, 1):
        log(f"  {i}. {p.name}")
    all_num = len(pdfs) + 1
    log(f"  {all_num}. Process All PDFs")
    log("-" * 48)

    progress_callback(5)

    # --- Get selection ---
    selection = None
    while selection is None:
        if cancel_event.is_set():
            log("Cancelled.")
            return
        raw = prompt('Enter number(s) to process (e.g. "1 3 5"), or "all":')
        selection = _parse_selection(raw, len(pdfs))
        if selection is None:
            log(f"  Invalid input. Enter numbers 1-{all_num}, a list of numbers, or 'all'.")

    selected_pdfs = [pdfs[i] for i in selection]
    log(f"\nProcessing {len(selected_pdfs)} file(s)...")

    output_dir = pdf_dir / "Move Ticket Omit"
    output_dir.mkdir(exist_ok=True)

    processed = 0
    skipped = 0
    errors = 0
    total = len(selected_pdfs)

    for i, pdf_path in enumerate(selected_pdfs):
        if cancel_event.is_set():
            log("Cancelled.")
            return

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
