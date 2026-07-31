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

v1.1.1: the Material Type fill is black (form-data look); only the
batch/nest stamp stays red.

v1.2.0 (C.D. request 2026-07-31, formatting sample supplied as a marked-up
packet):
  - The batch/nest stamp is now TWO LEFT-ALIGNED LINES with colons -
    "BATCH: S036" / "NEST: 503884" - instead of one centered
    "BATCH S036 - NEST 503884" line.
  - New DIFFICULTY label stamped into the Alternate Source Code cell:
    SIMPLE / MEDIUM / DIFFICULT, colour-coded, read from the
    "EB 922 Schedule.xlsx" -> CURRENT PIPELINE sheet, where the rating is
    carried ONLY by the fill colour of column E (there is no text in it).

    The schedule tracks both departments, and column E is greyed out by
    conditional formatting for 922 rows (`=$A1=922`) and for shipped rows
    (`=$F1="SHIPPED"`) - those read as N/A. openpyxl reports the STORED fill
    and cannot see conditional formatting, so both rules are re-checked in
    code before a stored colour is trusted; otherwise a 922 row with a
    left-over yellow fill would be mislabelled MEDIUM when the user sees grey.

    Nothing is stamped for N/A, unrated, or not-found nests. Those are
    collected and reported in ONE popup at the end of the run rather than
    printed on the packet.
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


VERSION = "1.2.0"

# Stamp styling per C.D.'s request (feedback 2026-07-13): red, size 16,
# Century Gothic bold, under the Quality Requirements section. v1.2.0 made it
# two left-aligned lines with colons (sample packet 2026-07-31).
STAMP_FONT_FILE = Path(r"C:\Windows\Fonts\GOTHICB.TTF")  # Century Gothic Bold
STAMP_FONT_NAME = "CentGoBd"
STAMP_COLOR = (1, 0, 0)
STAMP_FONTSIZE = 16
# Material Type fill is black (2026-07-24) so it reads as form data, not a
# stamp; only the batch/nest stamp is red.
MATERIAL_COLOR = (0, 0, 0)
MATERIAL_FONTSIZE = 12
BATCH_NEST_TEXT = "BATCH: {batch}\nNEST: {nest}"

# ── Difficulty rating ───────────────────────────────────────────────────────
# Source: EB 922 Schedule.xlsx -> "CURRENT PIPELINE". Column E ("RATING") holds
# NO text - the rating is the cell's fill colour alone. Legend lives in H2:I5.
DIFFICULTY_SHEET = "CURRENT PIPELINE"
DIFFICULTY_REL = Path("922 QTDR Production Packages") / "2 - Planning" / "EB 922 Schedule.xlsx"
DIFFICULTY_FONTSIZE = 16

# Legend fills, sampled from the live workbook 2026-07-31. Matching is
# nearest-colour within _FILL_TOLERANCE so a hand-recoloured cell that is a
# shade off still resolves instead of silently reading as unrated.
DIFFICULTY_FILLS = {
    (218, 242, 208): "SIMPLE",
    (249, 236, 143): "MEDIUM",
    (250, 148, 155): "DIFFICULT",
    (217, 217, 217): None,        # legend I5 = N/A -> nothing is stamped
    (191, 191, 191): None,        # the "SHIPPED" conditional-format grey
}
_FILL_TOLERANCE = 26

# Print colours. MEDIUM is C.D.'s own amber from the sample packet (#FFBF00) -
# the sheet's pale yellow is unreadable on white, so these are display colours,
# not the spreadsheet fills.
DIFFICULTY_COLORS = {
    "SIMPLE":    (0.00, 0.69, 0.31),   # #00B050
    "MEDIUM":    (1.00, 0.75, 0.00),   # #FFBF00
    "DIFFICULT": (1.00, 0.00, 0.00),   # #FF0000
}

# Column headers on CURRENT PIPELINE, looked up by NAME (Hard Rule 1).
_COL_DEPT, _COL_BATCH_NEST, _COL_RATING, _COL_STATUS = "DEPT.", "BATCH / NEST", "RATING", "STATUS"

_BATCH_RE = re.compile(r"^[A-Z0-9]{2,8}$")
_NEST_TOKEN_RE = re.compile(r"\b(\d{5,6})\b")


def _stamp_font():
    """(fontname, fontfile) — Century Gothic Bold, or Helvetica bold fallback."""
    if STAMP_FONT_FILE.exists():
        return STAMP_FONT_NAME, str(STAMP_FONT_FILE)
    return "hebo", None


# ── Difficulty rating lookup ────────────────────────────────────────────────
def _schedule_path(params) -> Path | None:
    """The EB 922 Schedule workbook. Settings override wins; otherwise it is
    discovered under whichever Pilot Program root this machine has (the base
    name differs per install, so it is never hardcoded)."""
    settings = (params or {}).get("settings") or {}
    override = (settings.get("schedule_path") or "").strip()
    if override:
        p = Path(override)
        return p if p.exists() else None
    for root in sdk.pilot_program_roots():
        p = Path(root) / DIFFICULTY_REL
        if p.exists():
            return p
    return None


# Excel's theme-colour index order. The XML lists dk1/lt1/dk2/lt2 but Excel
# indexes them swapped in pairs, so 0=lt1 and 1=dk1 - getting this backwards
# silently returns white for text colours.
_THEME_INDEX_ORDER = ["lt1", "dk1", "lt2", "dk2",
                      "accent1", "accent2", "accent3", "accent4", "accent5",
                      "accent6", "hlink", "folHlink"]
_CLR_SCHEME_RE = re.compile(r"<a:clrScheme.*?</a:clrScheme>", re.S)
_SLOT_RE = re.compile(
    r"<a:(dk1|lt1|dk2|lt2|accent[1-6]|hlink|folHlink)>(.*?)</a:\1>", re.S)
_SRGB_RE = re.compile(r'(?:srgbClr val|sysClr[^>]*lastClr)="([0-9A-Fa-f]{6})"')


def _theme_rgbs(wb) -> list:
    """The workbook's 12 theme colours as (r,g,b), in Excel index order.

    SIMPLE on the schedule is a THEME fill (theme 9 + tint), not a literal
    RGB like MEDIUM and DIFFICULT — openpyxl exposes no .rgb for those, so
    without this every green row read as unrated (caught 2026-07-31: COM saw
    85 SIMPLE rows, openpyxl saw 0).
    """
    try:
        raw = getattr(wb, "loaded_theme", None)
        if not raw:
            return []
        xml = raw.decode("utf-8", "ignore") if isinstance(raw, bytes) else str(raw)
        block = _CLR_SCHEME_RE.search(xml)
        if not block:
            return []
        found = {}
        for name, body in _SLOT_RE.findall(block.group(0)):
            m = _SRGB_RE.search(body)
            if m:
                found[name] = tuple(int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4))
        return [found.get(n) for n in _THEME_INDEX_ORDER]
    except Exception:
        return []


def _apply_tint(rgb, tint):
    """ECMA-376 tint: scale LUMINANCE in HLS, not the raw channels. The naive
    per-channel approximation lands ~7 off; this lands within 1."""
    if not tint:
        return rgb
    import colorsys
    r, g, b = (c / 255.0 for c in rgb)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l = l * (1 + tint) if tint < 0 else l * (1 - tint) + tint
    r, g, b = colorsys.hls_to_rgb(h, max(0.0, min(1.0, l)), s)
    return tuple(int(round(c * 255)) for c in (r, g, b))


def _fill_rgb(cell, theme_rgbs=()):
    """(r, g, b) of a cell's STORED fill, or None when it has no solid fill.

    Handles BOTH literal rgb fills and theme+tint fills. Indexed-palette
    colours still return None rather than a wrong guess.
    """
    try:
        fill = cell.fill
        if fill is None or fill.patternType != "solid":
            return None
        fg = fill.fgColor
        val = getattr(fg, "rgb", None)
        if isinstance(val, str) and len(val) >= 6:
            h = val[-6:]
            return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        if getattr(fg, "type", None) == "theme":
            idx = getattr(fg, "theme", None)
            if isinstance(idx, int) and 0 <= idx < len(theme_rgbs):
                base = theme_rgbs[idx]
                if base:
                    tint = getattr(fg, "tint", 0.0)
                    return _apply_tint(base, tint if isinstance(tint, float) else 0.0)
        return None
    except Exception:
        return None


def _match_fill(rgb):
    """Nearest legend colour within tolerance -> its label (or None)."""
    if rgb is None:
        return None
    best, best_d = None, None
    for ref, label in DIFFICULTY_FILLS.items():
        d = sum((a - b) ** 2 for a, b in zip(rgb, ref)) ** 0.5
        if best_d is None or d < best_d:
            best, best_d = label, d
    return best if best_d is not None and best_d <= _FILL_TOLERANCE else None


def _lookup_difficulty(diff_map, nest):
    """Rating for a nest id. Tries the id as-is first so alphanumeric nests
    ('S20085') resolve, then falls back to a 5-6 digit token pulled out of a
    longer filename stem."""
    if not diff_map or not nest:
        return None
    key = str(nest).strip().upper()
    if key in diff_map:
        return diff_map[key]
    m = _NEST_TOKEN_RE.search(key)
    return diff_map.get(m.group(1)) if m else None


def _load_difficulty_map(params, log):
    """{nest_number: label} from the schedule. Returns (map, problem_text).

    ``problem_text`` is non-empty when the whole lookup was unavailable (file
    missing, or open in Excel) — the caller degrades to no difficulty stamps
    rather than failing the run.
    """
    path = _schedule_path(params)
    if path is None:
        return {}, ("The EB 922 Schedule workbook could not be found, so no "
                    "difficulty labels were stamped.")
    try:
        wb = sdk.load_workbook_resilient(path, data_only=True)
    except Exception as exc:
        return {}, (f"The difficulty ratings could not be read from "
                    f"{path.name}:\n\n{exc}\n\nNo difficulty labels were stamped.")
    try:
        if DIFFICULTY_SHEET not in wb.sheetnames:
            return {}, (f"{path.name} has no '{DIFFICULTY_SHEET}' sheet, so no "
                        f"difficulty labels were stamped.")
        ws = wb[DIFFICULTY_SHEET]
        # Scan for the header row, never assume row 1 (Hard Rule 2); the SDK
        # returns (row_index, {UPPERCASE HEADER: col}).
        hdr_row, hdr = sdk.find_header_row(ws, [_COL_BATCH_NEST, _COL_RATING])
        if not hdr_row:
            return {}, (f"{path.name} has no row containing both "
                        f"'{_COL_BATCH_NEST}' and '{_COL_RATING}' on the "
                        f"'{DIFFICULTY_SHEET}' sheet, so no difficulty labels "
                        f"were stamped.")
        c_dept = hdr.get(_COL_DEPT)
        c_key = hdr.get(_COL_BATCH_NEST)
        c_rate = hdr.get(_COL_RATING)
        c_stat = hdr.get(_COL_STATUS)
        theme_rgbs = _theme_rgbs(wb)

        out = {}
        for row in range(hdr_row + 1, ws.max_row + 1):
            key = ws.cell(row=row, column=c_key).value
            if not key:
                continue
            # Re-check the sheet's conditional formatting in code: 922 rows and
            # SHIPPED rows are greyed to N/A on screen, but openpyxl still sees
            # whatever colour is STORED underneath (row 2 stores yellow, shows
            # grey). Trusting the stored fill there would invent a rating.
            dept = ws.cell(row=row, column=c_dept).value if c_dept else None
            if str(dept).strip() == "922":
                continue
            status = ws.cell(row=row, column=c_stat).value if c_stat else None
            if str(status or "").strip().upper() == "SHIPPED":
                continue
            label = _match_fill(_fill_rgb(ws.cell(row=row, column=c_rate), theme_rgbs))
            if not label:
                continue
            # "BATCH / NEST" reads "S028 503708" — batch first, nest last. Key
            # off the LAST token, never a digits-only match: nests are not
            # always numeric ("V085 S20085"), and a digits-only regex dropped
            # those rows silently (Hard Rule 3's alphanumeric-nest class).
            # Registering the batch token too would collide, since one batch
            # spans many nests with different ratings.
            tokens = str(key).split()
            if not tokens:
                continue
            out[tokens[-1].strip().upper()] = label
        log(f"  Difficulty ratings loaded for {len(out)} nests from {path.name}")
        return out, ""
    finally:
        try:
            wb.close()
        except Exception:
            pass


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


def _find_header_seq(words, *tokens):
    """bbox spanning a run of consecutive words (e.g. 'Alternate Source Code')."""
    n = len(tokens)
    for i, w in enumerate(words):
        if i + n > len(words):
            break
        if all(words[i + k][4] == tokens[k] for k in range(n)):
            last = words[i + n - 1]
            return (w[0], w[1], last[2], last[3])
    return None


def _stamp_first_page(page, batch, nest, material, log, difficulty=None) -> list:
    """Apply the stamps to the output's first page. Returns warning strings.

    ``difficulty`` is a SIMPLE/MEDIUM/DIFFICULT label or None; None stamps
    nothing (N/A, unrated and unknown nests are reported in one popup by the
    caller instead of being printed on the packet).
    """
    warnings = []
    words = page.get_text("words")
    fontname, fontfile = _stamp_font()

    # --- Batch/nest text box under the Quality Requirements grid ---
    qr = _find_header(words, "Quality", "Requirements")
    if qr:
        text = BATCH_NEST_TEXT.format(batch=batch, nest=nest)
        # Two LEFT-aligned lines from the section's left edge (C.D.'s sample
        # packet: "BATCH: S036" at x~379 / "NEST: 503884" on the line below).
        # The 3-row stamp grid under the header is ~54pt tall; land below it.
        rect = fitz.Rect(qr[0] + 4, qr[3] + 67.5, qr[0] + 4 + 300, qr[3] + 120)
        leftover = page.insert_textbox(
            rect, text, fontsize=STAMP_FONTSIZE, fontname=fontname,
            fontfile=fontfile, color=STAMP_COLOR, align=fitz.TEXT_ALIGN_LEFT)
        if leftover < 0:
            warnings.append(f"batch/nest stamp did not fit ({text!r})")
    else:
        warnings.append("Quality Requirements header not found - batch/nest stamp skipped")

    # --- Difficulty label in the Alternate Source Code cell ---
    if difficulty:
        asc = _find_header_seq(words, "Alternate", "Source", "Code")
        if asc:
            cx = (asc[0] + asc[2]) / 2
            rect = fitz.Rect(cx - 85, asc[3] + 13.5, cx + 85, asc[3] + 46)
            leftover = page.insert_textbox(
                rect, difficulty, fontsize=DIFFICULTY_FONTSIZE, fontname=fontname,
                fontfile=fontfile,
                color=DIFFICULTY_COLORS.get(difficulty, STAMP_COLOR),
                align=fitz.TEXT_ALIGN_CENTER)
            if leftover < 0:
                warnings.append(f"difficulty {difficulty!r} did not fit the "
                                f"Alternate Source Code cell")
        else:
            warnings.append("Alternate Source Code header not found - "
                            "difficulty label skipped")

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
                fontfile=fontfile, color=MATERIAL_COLOR, align=fitz.TEXT_ALIGN_CENTER)
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
                 cancel_event=None, difficulty=None) -> tuple:
    """
    Remove MOVE TICKET pages from pdf_path, stamp the first page, write to
    output_path. Returns (ok, warnings). Originals are never modified.

    ``difficulty`` is the SIMPLE/MEDIUM/DIFFICULT label for this nest, or None
    to stamp no difficulty label at all.
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
        warnings.extend(_stamp_first_page(doc[0], batch, pdf_path.stem, material,
                                          log, difficulty))
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
        # An install/build problem, not something the user can fix -> let it hit
        # the generic error path (try again, then send a debug report).
        raise RuntimeError("PyMuPDF (fitz) is not available; cannot process PDFs.")

    # --- Resolve directory ---
    raw_dir = (settings.get("pdf_directory") or "").strip()

    if raw_dir:
        pdf_dir = Path(raw_dir)
    else:
        raw_dir = prompt("Enter path to PDF directory:")
        pdf_dir = Path(raw_dir.strip())

    if not pdf_dir.exists() or not pdf_dir.is_dir():
        raise sdk.UserFacingError(
            f"That folder doesn't exist: {pdf_dir}",
            "Check the path and pick the correct PDF folder, then run again.")

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

    # --- Difficulty ratings (toggleable; 911 Setup passes the toggle in) ----
    want_difficulty = params.get("stamp_difficulty")
    if want_difficulty is None:
        want_difficulty = settings.get("stamp_difficulty", True)
    diff_map, diff_problem = ({}, "")
    if want_difficulty:
        diff_map, diff_problem = _load_difficulty_map(params, log)
    else:
        log("  Difficulty label turned off for this run.")
    unrated = []

    for i, pdf_path in enumerate(selected_pdfs):
        if cancel_event.is_set():
            log("Cancelled.")
            return

        output_name = f"{pdf_path.stem} Move Ticket Omit.pdf"
        output_path = output_dir / output_name

        log(f"[{i+1}/{total}] {pdf_path.name}")

        difficulty = None
        if want_difficulty and not diff_problem:
            difficulty = _lookup_difficulty(diff_map, pdf_path.stem)
            if difficulty:
                log(f"  Difficulty: {difficulty}")
            else:
                unrated.append(pdf_path.stem)

        try:
            ok, warnings = _process_pdf(pdf_path, output_path, batch, log,
                                        cancel_event, difficulty)
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

    # --- Difficulty disclaimer popup (C.D. 2026-07-31) ---------------------
    # Nothing is printed on the packet for an N/A / unrated / unknown nest, so
    # the omission has to be surfaced somewhere the user cannot scroll past.
    if want_difficulty and (diff_problem or unrated):
        if diff_problem:
            body = diff_problem
        else:
            shown = "\n".join(f"  - {n}" for n in unrated[:25])
            body = (f"{len(unrated)} of {total} packet(s) were stamped WITHOUT a "
                    f"difficulty label because the nest has no rating colour on "
                    f"the EB 922 Schedule (CURRENT PIPELINE, column E), is marked "
                    f"N/A, or is not listed:\n\n{shown}"
                    + ("\n  ..." if len(unrated) > 25 else "")
                    + "\n\nEverything else on those packets stamped normally.")
        sdk.show_warning(params, "Difficulty label - not stamped", body)

    if attention:
        sdk.show_warning(
            params, "Move Ticket Omit - check these",
            "Some stamps need a manual look:\n\n" + "\n".join(attention[:20])
            + ("\n..." if len(attention) > 20 else ""))
