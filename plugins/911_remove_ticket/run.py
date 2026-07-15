"""
911 Remove Ticket Plugin
========================
Scans a directory for PDF files, lists them numbered for selection, removes
pages containing "MOVE TICKET" text from selected files, and saves the result
as "{stem} Move Ticket Omit.pdf" inside a "Move Ticket Omit" subfolder.

Pages containing "MIL-SPEC" or "HULL" are always kept, even if they also
contain "MOVE TICKET". Original PDFs are never modified.

v1.1.0 (QA-requested): the output's first page is stamped with
"BATCH {batch} - NEST {nest}" (red, 16pt, Century Gothic bold, centered)
under the Quality Requirements grid, and the Material Type cell — blank on
every packet cover — is filled with the MATERIAL value read off the move
ticket pages before they are removed.
"""

import re
import threading
from pathlib import Path

try:
    import fitz
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from techdeck.core import plugin_sdk as sdk
except ModuleNotFoundError:
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from techdeck.core import plugin_sdk as sdk


VERSION = "1.1.0"

# Stamp styling per C.D.'s request (feedback 2026-07-13): red, size 16,
# centered, Century Gothic bold, under the Quality Requirements section.
STAMP_FONT_FILE = Path(r"C:\Windows\Fonts\GOTHICB.TTF")  # Century Gothic Bold
STAMP_FONT_NAME = "CentGoBd"
STAMP_COLOR = (1, 0, 0)
STAMP_FONTSIZE = 16
MATERIAL_FONTSIZE = 12
BATCH_NEST_TEXT = "BATCH {batch} - NEST {nest}"

_BATCH_RE = re.compile(r"^[A-Z0-9]{2,8}$")


def _stamp_font():
    """(fontname, fontfile) — Century Gothic Bold, or Helvetica bold fallback."""
    if STAMP_FONT_FILE.exists():
        return STAMP_FONT_NAME, str(STAMP_FONT_FILE)
    return "hebo", None


def _same_line_value(words, label_idx):
    """Words to the right of words[label_idx] on the same visual line, joined.

    Stops at a gap > 40pt or at the next 'LABEL:' token, so the neighbouring
    form field's text is never swallowed.
    """
    lx1 = words[label_idx][2]
    ly0, ly1 = words[label_idx][1], words[label_idx][3]
    cy = (ly0 + ly1) / 2
    right = sorted((w for w in words if w[0] > lx1 - 1 and w[1] < cy < w[3]),
                   key=lambda w: w[0])
    out = []
    prev_x1 = lx1
    for w in right:
        if w[0] - prev_x1 > 40 or ":" in w[4]:
            break
        out.append(w[4])
        prev_x1 = w[2]
    return " ".join(out)


def _extract_material(page) -> str:
    """MATERIAL value from a move ticket page, '' if absent."""
    words = page.get_text("words")
    for i, w in enumerate(words):
        if w[4].upper() == "MATERIAL:":
            value = _same_line_value(words, i)
            if value:
                return value
    return ""


def _scan_document(doc, cancel_event=None):
    """(pages to remove, distinct MATERIAL values found on them).

    A page is removed if it contains 'MOVE TICKET' text AND does NOT contain
    'MIL-SPEC' or 'HULL'. Pages with MIL-SPEC or HULL are always kept.
    """
    indices = set()
    materials = set()
    for i, page in enumerate(doc):
        if cancel_event is not None and i % 16 == 0 and cancel_event.is_set():
            break
        text = (page.get_text("text") or "").upper()
        if "MOVE TICKET" in text and "MIL-SPEC" not in text and "HULL" not in text:
            indices.add(i)
            material = _extract_material(page)
            if material:
                materials.add(material)
    return indices, materials


def _find_header(words, first, second):
    """Bounding box of the two-word header 'first second', or None."""
    for i, w in enumerate(words):
        if w[4] == first and i + 1 < len(words) and words[i + 1][4] == second:
            return (w[0], w[1], words[i + 1][2], words[i + 1][3])
    return None


def _stamp_first_page(page, batch, nest, material, log) -> list:
    """Apply both stamps to the output's first page. Returns warning strings."""
    warnings = []
    words = page.get_text("words")
    fontname, fontfile = _stamp_font()

    # --- Batch/nest text box under the Quality Requirements grid ---
    qr = _find_header(words, "Quality", "Requirements")
    if qr:
        cx = (qr[0] + qr[2]) / 2
        text = BATCH_NEST_TEXT.format(batch=batch, nest=nest)
        # The 3-row stamp grid under the header is ~54pt tall; land below it,
        # centered on the section, in the big empty box.
        rect = fitz.Rect(cx - 165, qr[3] + 68, cx + 165, qr[3] + 100)
        leftover = page.insert_textbox(
            rect, text, fontsize=STAMP_FONTSIZE, fontname=fontname,
            fontfile=fontfile, color=STAMP_COLOR, align=fitz.TEXT_ALIGN_CENTER)
        if leftover < 0:
            warnings.append(f"batch/nest stamp did not fit ({text!r})")
    else:
        warnings.append("Quality Requirements header not found - batch/nest stamp skipped")

    # --- Material Type cell fill ---
    hdr = _find_header(words, "Material", "Type")
    if hdr:
        cx = (hdr[0] + hdr[2]) / 2
        # Value row sits just below the header row; anchor on its siblings
        # (e.g. the Material Size value) so the baseline matches the form.
        row = [w for w in words if hdr[3] + 2 <= w[1] <= hdr[3] + 32]
        occupied = [w for w in row if hdr[0] - 25 <= w[0] and w[2] <= hdr[2] + 45]
        if material and not occupied:
            row_top = min((w[1] for w in row), default=hdr[3] + 5)
            rect = fitz.Rect(cx - 70, row_top - 2, cx + 70, row_top + 22)
            leftover = page.insert_textbox(
                rect, material, fontsize=MATERIAL_FONTSIZE, fontname=fontname,
                fontfile=fontfile, color=STAMP_COLOR, align=fitz.TEXT_ALIGN_CENTER)
            if leftover < 0:
                warnings.append(f"material {material!r} did not fit the Material Type cell")
        elif occupied:
            log("  Material Type cell already filled - left as-is")
        elif not material:
            warnings.append("no MATERIAL value found on the move ticket pages - Material Type left blank")
    else:
        warnings.append("Material Type header not found - material fill skipped")

    return warnings


def _process_pdf(pdf_path: Path, output_path: Path, batch: str, log,
                 cancel_event=None) -> tuple:
    """
    Remove MOVE TICKET pages from pdf_path, stamp the first page, write to
    output_path. Returns (ok, warnings). Originals are never modified.
    """
    warnings = []
    try:
        sdk.ensure_local(pdf_path)  # OneDrive placeholder -> download first (Hard Rule 13)
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        log(f"  ERROR opening {pdf_path.name}: {e}")
        return False, warnings

    try:
        remove_pages, materials = _scan_document(doc, cancel_event)

        if not remove_pages:
            log(f"  Skipped (no MOVE TICKET pages found): {pdf_path.name}")
            return False, warnings

        total = len(doc)
        if len(remove_pages) >= total:
            log(f"  WARNING: All {total} pages would be removed - nothing to write for {pdf_path.name}")
            return False, warnings

        material = " / ".join(sorted(materials))
        if len(materials) > 1:
            warnings.append(f"multiple MATERIAL values on the move tickets: {material}")

        doc.delete_pages(sorted(remove_pages))
        warnings.extend(_stamp_first_page(doc[0], batch, pdf_path.stem, material, log))
        doc.save(str(output_path), garbage=3, deflate=True)

        removed = len(remove_pages)
        kept = total - removed
        suffix = f", material '{material}'" if material else ""
        log(f"  {pdf_path.name}: removed {removed} MOVE TICKET page(s), kept {kept}{suffix} -> {output_path.name}")
        return True, warnings
    except Exception as e:
        log(f"  ERROR processing {pdf_path.name}: {e}")
        return False, warnings
    finally:
        doc.close()


def _detect_batch(pdf_dir: Path) -> str:
    """Batch from the standard layout ...\\{batch}\\NEST PACKAGES, '' if unsure."""
    name = pdf_dir.name.strip().upper()
    candidate = ""
    if name == "NEST PACKAGES":
        candidate = pdf_dir.parent.name.strip().upper()
    elif _BATCH_RE.match(name):
        candidate = name
    if candidate and _BATCH_RE.match(candidate):
        return candidate
    return ""


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
        log("ERROR: PyMuPDF (fitz) is not available. Cannot process PDFs.")
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

    # --- Batch for the first-page stamp ---
    batch = _detect_batch(pdf_dir)
    if batch:
        log(f"Batch for the first-page stamp: {batch} (from folder name)")
    else:
        batch = sdk.normalize_911_batch(
            sdk.request_batch_number(params, "Enter the 911 batch number (for the first-page stamp):"))

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
    attention = []
    total = len(selected_pdfs)

    for i, pdf_path in enumerate(selected_pdfs):
        if cancel_event.is_set():
            log("Cancelled.")
            return

        output_name = f"{pdf_path.stem} Move Ticket Omit.pdf"
        output_path = output_dir / output_name

        log(f"[{i+1}/{total}] {pdf_path.name}")

        try:
            ok, warnings = _process_pdf(pdf_path, output_path, batch, log, cancel_event)
            if ok:
                processed += 1
            else:
                skipped += 1
            for w in warnings:
                log(f"  WARNING: {w}")
                attention.append(f"{pdf_path.name}: {w}")
        except Exception as e:
            log(f"  UNEXPECTED ERROR: {e}")
            errors += 1

        pct = 5 + int(90 * (i + 1) / total)
        progress_callback(pct)

    progress_callback(100)
    log(f"\nDone. Processed: {processed}  Skipped (no sketches): {skipped}  Errors: {errors}")

    if attention:
        sdk.show_warning(
            params, "Move Ticket Omit - check these",
            "Some stamps need a manual look:\n\n" + "\n".join(attention[:20])
            + ("\n..." if len(attention) > 20 else ""))
