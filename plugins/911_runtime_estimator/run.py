"""
911 Runtime Estimator Plugin for TechDeck
=========================================

Given a ROOT directory containing one subfolder per order (e.g. F124, P003,
S029, V092 ...), this plugin:

  1. Walks each order folder, locating the nest work-package PDFs and the
     order's BATCH LIST workbook (folder names are resolved DEFENSIVELY -- the
     PDFs may live in 'NEST PACKAGES' or 'WPDD SKETCHES' under a
     'CUI- TECH DATA READ ME' folder, and layouts vary between orders).
  2. Parses each nest packet PDF (PyMuPDF) for thickness, pieces, material,
     source, stock size, mil spec, and plate weight -- cross-checking fields
     across the page-1 data row, the SUMMARY page, the part sketch, and the
     MOVE TICKET, exactly like the 911 Setup plugin.
  3. Joins batch-list rows to nests by 'Nest Pkg Nbr' and computes a per-row
     cutting-time estimate (thickness band x thickness x pieces, +180 min per
     bevel piece) -- see CALCULATION below.
  4. Writes ONE consolidated workbook with two sheets (Plates / Non-Plates).
     Each is a flat data table that reproduces EVERY batch-list column in its
     native order, then our generated columns. 'Material' on the table is the
     MOVE TICKET designation; the batch list's own 'Material' (an EB stock code)
     is shown as 'Source Material'.
  5. Drops a REAL, refreshable Excel PivotTable below the data on each sheet
     (Nest Pkg Nbr -> Sum of Est Cut Hours, grand total at the bottom) by
     driving Excel via COM (pywin32). If Excel/COM is unavailable or errors, it
     falls back to a static nest->sum summary so a run never hard-crashes.

CALCULATION (per batch-list row; thickness drives the band):
    band(t): t < 0.5 -> 6 ; 0.5 <= t < 1.0 -> 9 ; 1.0 <= t < 2.0 -> 12 ; t >= 2.0 -> 18   (min/pc)
    Factor   = thickness * band(thickness)          # literal multiply
    row base = Factor * (row PPN Quantity)
    bevel    = 180 * (row PPN Quantity)  IF row SCOPE OF WORK contains 'BEVEL', else 0
    row est (min) = row base + bevel
    row est (hr)  = row est (min) / 60

The bevel test is a CONTAINS check (real batch lists use compound scopes like
'CUT/BEVEL'), case-insensitive.

Prompts via console for the ROOT directory only (no pre-configured settings
required). Optional 'output_dir' setting picks where the workbook is saved;
blank saves it inside ROOT.
"""

from __future__ import annotations

import re
import datetime
from pathlib import Path
from typing import Optional

# SDK bootstrap (works in-process and for standalone CLI testing).
try:
    from techdeck.core import plugin_sdk as sdk
except ModuleNotFoundError:
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from techdeck.core import plugin_sdk as sdk

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

import openpyxl
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


VERSION = "1.0.0"

# We reproduce EVERY batch-list column verbatim, in its native order, then
# append our own generated columns after them. The batch list's own 'Material'
# column is an EB stock code; we surface it as 'Source Material' to keep it
# distinct from the part-material designation we pull off the MOVE TICKET pages.
BATCH_HEADER_RENAME = {"Material": "Source Material"}
# 'Order' (which order folder a row came from) leads the table; our other
# generated columns follow the batch-list block (in this order). 'Material' is
# the MOVE TICKET designation (sits right after MIL SPEC on the packet);
# 'Source' is the PDF SRCE/SOURCE field (where the stock came from).
GENERATED_COLS = ["Process", "Thickness (in)", "Stock L", "Stock W",
                  "Mil Spec", "Material", "Source", "Est Cut Hours", "Flags"]
# For each OUTPUT header, the UPPERCASE row key its value is read from. Most map
# to their own upper-cased name; these two are indirections (the display name
# differs from the key the value is stored under).
HEADER_SOURCE_KEY = {
    "Source Material": "MATERIAL",      # batch list 'Material' (EB stock code)
    "Material": "MT MATERIAL",          # MOVE TICKET material designation (new)
}

# The column the pivot sums (our formula-driven estimate, in hours).
EST_COL = "Est Cut Hours"

# Number that triggers the bevel surcharge, per piece.
BEVEL_MINUTES = 180.0


# ──────────────────────────────────────────────────────────────────────────
# Calculation
# ──────────────────────────────────────────────────────────────────────────

def band_minutes(thickness: float) -> int:
    """Minutes-per-piece band for a plate thickness (inches).

    Lower-inclusive / upper-exclusive; the >= band wins on a boundary.
    """
    if thickness < 0.5:
        return 6
    if thickness < 1.0:
        return 9
    if thickness < 2.0:
        return 12
    return 18


def row_estimate_hours(thickness: Optional[float], ppn_qty: float, scope: str):
    """Return (est_hours, factor_min_per_pc, bevel_min) for one batch-list row.

    Returns (None, None, None) when thickness is unknown (can't estimate).
    """
    if thickness is None or thickness <= 0:
        return None, None, None
    qty = ppn_qty if (ppn_qty and ppn_qty > 0) else 0
    factor = thickness * band_minutes(thickness)          # min/pc
    base = factor * qty
    bevel = BEVEL_MINUTES * qty if _is_bevel(scope) else 0.0
    est_min = base + bevel
    return est_min / 60.0, factor, bevel


def _is_bevel(scope) -> bool:
    """True if the scope-of-work text contains 'BEVEL' (case-insensitive).

    Real batch lists use compound scopes like 'CUT/BEVEL', so this is a
    CONTAINS test, not exact-equals.
    """
    return scope is not None and "BEVEL" in str(scope).strip().upper()


def _is_plate_row(row: dict) -> bool:
    """True if a data row is a plate (vs a structural shape/bar/tube). A row is
    a plate when its Description says PLATE, or when an estimate was computed
    (a plate thickness was found). Non-plates — T-SECTION, BAR, TUBE, ANGLE,
    etc. — have no plate thickness and land on the Non-Plates sheet."""
    desc = str(row.get("Description") or "").upper()
    if "PLATE" in desc:
        return True
    return row.get(EST_COL) is not None


# ──────────────────────────────────────────────────────────────────────────
# PDF field parsing (mirrors 911 Setup's labeled-value approach)
# ──────────────────────────────────────────────────────────────────────────

_LABEL_RE = re.compile(r'^[A-Z][A-Z0-9 ./#-]*:')
_NUM_RE = re.compile(r'^-?\d*\.?\d+$')
_CUT_METHOD_RE = re.compile(r'\b(PLASMA|LASER|WATER\s*JET|WATERJET|WJET|TELESIS|OXY\w*)\b',
                            re.IGNORECASE)
# "1.000 THK #109X360"  /  "0.500X90X360"  /  "0.375 THICK"
_SIZE_LW_HASH_RE = re.compile(r'#\s*(\d+(?:\.\d+)?)\s*[xX]\s*(\d+(?:\.\d+)?)')
_SIZE_LW_PLAIN_RE = re.compile(
    r'(\d+(?:\.\d+)?)\s*[xX]\s*(\d+(?:\.\d+)?)\s*[xX]\s*(\d+(?:\.\d+)?)')
_THK_FROM_DESC_RE = re.compile(r'(\d*\.?\d+)\s*TH(?:K|ICK)', re.IGNORECASE)


def _looks_like_label(s: str) -> bool:
    return bool(_LABEL_RE.match(s.strip()))


def _labeled_value(text: str, label: str):
    """Value following 'label:' -- same line or the next line. Returns None
    when blank or when the following token is itself another field label."""
    pat = re.compile(
        re.escape(label) + r'\s*:[ \t]*(?P<same>[^\n]*)(?:\n[ \t]*(?P<next>[^\n]*))?',
        re.IGNORECASE,
    )
    m = pat.search(text)
    if not m:
        return None
    same = (m.group("same") or "").strip()
    if same and not _looks_like_label(same):
        return same
    nxt = (m.group("next") or "").strip()
    if nxt and not _looks_like_label(nxt):
        return nxt
    return None


def _find_nest_pdf(folder: Path, nest_number: str):
    """The PDF in `folder` whose stem contains the nest number, or None."""
    if not folder.exists():
        return None
    nest_upper = nest_number.upper()
    for f in folder.iterdir():
        if (f.is_file() and f.suffix.lower() == ".pdf"
                and nest_upper in f.stem.upper()):
            return f
    return None


def _page1_pieces_thickness(page1_text: str):
    """Pull (pieces, thickness) from the page-1 'Orders Pieces Thickness Length
    Width' data row. Labels appear as a block, then the values as a block, so
    we find the label block and read the value sequence after it.

    Returns (pieces|None, thickness|None).
    """
    lines = [ln.strip() for ln in page1_text.splitlines()]
    labels = ["ORDERS", "PIECES", "THICKNESS", "LENGTH", "WIDTH"]
    start = None
    for i in range(len(lines) - len(labels) + 1):
        if [lines[i + k].upper() for k in range(len(labels))] == labels:
            start = i + len(labels)
            break
    if start is None:
        return None, None
    # Collect the numeric value tokens that follow (skip any trailing label
    # like 'Remnant Used'). Order is Orders, Pieces, Thickness, Length, Width.
    nums = []
    for ln in lines[start:]:
        if _NUM_RE.match(ln):
            nums.append(ln)
        if len(nums) >= 3:
            break
    pieces = _to_float(nums[1]) if len(nums) >= 2 else None
    thickness = _to_float(nums[2]) if len(nums) >= 3 else None
    # Pieces is a count -> int-ish
    if pieces is not None:
        pieces = int(round(pieces))
    return pieces, thickness


def _parse_size(full_text: str):
    """Return (stock_L, stock_W) from a part-sketch 'SIZE:' field, normalized
    L=max, W=min. Thickness-only sizes (e.g. '0.375 THICK') -> (None, None).

    A packet can carry more than one 'SIZE:' field (e.g. the nest sheet's
    usable area '85.06 X 53.74' AND the part-sketch stock size
    '1.000 THK #109X360'). We scan every SIZE value and prefer a stock-format
    match: the '#L X W' hash form first, then the 'thk X L X W' three-number
    form.
    """
    values = []
    for m in re.finditer(r'SIZE\s*:[ \t]*([^\n]*)(?:\n[ \t]*([^\n]*))?', full_text,
                         re.IGNORECASE):
        same = (m.group(1) or "").strip()
        cand = same if (same and not _looks_like_label(same)) else (m.group(2) or "").strip()
        if cand and not _looks_like_label(cand):
            values.append(cand)
    # Prefer the '#L X W' hash form.
    for v in values:
        mm = _SIZE_LW_HASH_RE.search(v)
        if mm:
            a, b = float(mm.group(1)), float(mm.group(2))
            return max(a, b), min(a, b)
    # Then the 'thk X L X W' three-number form (ignore the leading thickness).
    for v in values:
        mm = _SIZE_LW_PLAIN_RE.search(v)
        if mm:
            dims = sorted((float(mm.group(2)), float(mm.group(3))))
            return dims[1], dims[0]
    return None, None


def parse_nest_pdf(pdf_path: Path) -> dict:
    """Parse a nest packet PDF. Returns a dict of extracted fields (any may be
    None). Thickness is the only field the calculation needs."""
    out = {"thickness": None, "pieces": None, "material": None, "source": None,
           "stock_l": None, "stock_w": None, "mil_spec": None,
           "plate_weight": None, "process": None, "mt_material": None}
    doc = fitz.open(str(pdf_path))
    try:
        pages = [p.get_text() for p in doc]
    finally:
        doc.close()
    full = "\n".join(pages)
    page1 = pages[0] if pages else ""

    out["pieces"], out["thickness"] = _page1_pieces_thickness(page1)

    # Cut method / process from page 1 (PLASMA / LASER / ...).
    m = _CUT_METHOD_RE.search(page1)
    if m:
        out["process"] = m.group(1).upper().replace("  ", " ")

    # Material: REMNANT 'TYPE:' OR part-sketch 'MATL:' OR move-ticket 'MATERIAL:'.
    out["material"] = (_labeled_value(full, "TYPE")
                       or _labeled_value(full, "MATL")
                       or _labeled_value(full, "MATERIAL"))
    # Source: REMNANT 'SOURCE:' OR part-sketch 'SRCE:'.
    out["source"] = _labeled_value(full, "SOURCE") or _labeled_value(full, "SRCE")
    # MOVE TICKET material designation (e.g. 'HSS'), distinct from the batch
    # list's stock 'Material' code -- pulled only from MOVE TICKET pages.
    out["mt_material"] = _move_ticket_material(pages)
    # Mil spec.
    out["mil_spec"] = _labeled_value(full, "MIL SPEC")
    if not out["mil_spec"]:
        mm = re.search(r'MIL-S-\S+', full, re.IGNORECASE)
        out["mil_spec"] = mm.group(0) if mm else None
    # Stock L x W from a part sketch.
    out["stock_l"], out["stock_w"] = _parse_size(full)
    # Plate weight: REMNANT 'WEIGHT: n LBS' else page-1 'Plate/Max Part Weight'.
    out["plate_weight"] = _parse_plate_weight(full, page1)

    # Thickness fallback from REMNANT 'THICK:' if page-1 row missed it.
    if out["thickness"] is None:
        tv = _labeled_value(full, "THICK")
        if tv:
            out["thickness"] = _to_float(tv)
    return out


def _move_ticket_material(pages) -> Optional[str]:
    """The 'MATERIAL:' value from a MOVE TICKET page (the part-material
    designation, e.g. 'HSS') -- the value that sits right after 'MIL SPEC:' on
    the move ticket. Returns the first non-empty one found, scanning only pages
    that mention MOVE TICKET so a stray 'MATERIAL' elsewhere can't win."""
    for txt in pages:
        if "MOVE TICKET" in txt.upper():
            val = _labeled_value(txt, "MATERIAL")
            if val:
                return val
    return None


def _parse_plate_weight(full: str, page1: str):
    w = _labeled_value(full, "WEIGHT")
    if w:
        mm = re.search(r'(\d+(?:\.\d+)?)', w)
        if mm:
            return _to_float(mm.group(1))
    # page-1 'Plate/Max Part Weight  1181 / 3' -> first number before slash.
    mm = re.search(r'Plate/Max Part Weight\s*[^0-9]*(\d+(?:\.\d+)?)', page1,
                   re.IGNORECASE)
    if mm:
        return _to_float(mm.group(1))
    return None


def _to_float(v):
    if v is None:
        return None
    try:
        return float(str(v).strip().replace(",", ""))
    except (ValueError, TypeError):
        return None


def thickness_from_description(desc) -> Optional[float]:
    """Fallback thickness parse from a batch-list Description like
    'PLATE ; STL ; 1.125 THK #90 X 360 ; SF'."""
    if not desc:
        return None
    m = _THK_FROM_DESC_RE.search(str(desc))
    return _to_float(m.group(1)) if m else None


# ──────────────────────────────────────────────────────────────────────────
# Folder + batch-list resolution
# ──────────────────────────────────────────────────────────────────────────

def find_cui_folder(order_folder: Path) -> Optional[Path]:
    """Locate the 'CUI- TECH DATA READ ME' folder (name varies in spacing/dash).
    Falls back to any subfolder that itself contains a NEST PACKAGES / WPDD
    SKETCHES folder or a *BATCH*LIST*.xlsx. Returns the order folder itself if
    the packets live directly under it."""
    for sub in order_folder.iterdir():
        if sub.is_dir() and "CUI" in sub.name.upper() and "TECH" in sub.name.upper():
            return sub
    # Fallback: a subfolder holding the packet folders or a batch list.
    for sub in order_folder.iterdir():
        if not sub.is_dir():
            continue
        names = {c.name.upper() for c in sub.iterdir() if c.is_dir()} if sub.exists() else set()
        if "NEST PACKAGES" in names or "WPDD SKETCHES" in names:
            return sub
        if any("BATCH" in f.name.upper() and "LIST" in f.name.upper()
               for f in sub.glob("*.xlsx")):
            return sub
    # Maybe packets are directly under the order folder.
    return order_folder


def find_pdf_folder(cui_folder: Path) -> Optional[Path]:
    """Prefer 'NEST PACKAGES' (nest-named packet PDFs); fall back to
    'WPDD SKETCHES', then the CUI folder itself."""
    for name in ("NEST PACKAGES", "WPDD SKETCHES"):
        cand = cui_folder / name
        if cand.exists() and any(cand.glob("*.pdf")):
            return cand
    # Case-insensitive scan.
    for sub in cui_folder.iterdir():
        if sub.is_dir() and sub.name.upper() in ("NEST PACKAGES", "WPDD SKETCHES"):
            if any(sub.glob("*.pdf")):
                return sub
    if any(cui_folder.glob("*.pdf")):
        return cui_folder
    return None


def find_batch_list(cui_folder: Path) -> Optional[Path]:
    """Glob for the '*BATCH*LIST*.xlsx' workbook, skipping Excel lock files."""
    candidates = [f for f in cui_folder.glob("*.xlsx")
                  if "BATCH" in f.name.upper() and "LIST" in f.name.upper()
                  and not f.name.startswith("~$")]
    if candidates:
        return candidates[0]
    # Search one level down too.
    for f in cui_folder.rglob("*.xlsx"):
        if ("BATCH" in f.name.upper() and "LIST" in f.name.upper()
                and not f.name.startswith("~$")):
            return f
    return None


def load_batch_rows(batch_list_path: Path):
    """Return (headers_in_order, rows) from the batch-list sheet.

    headers_in_order : list[str]  -- the header names in column order
    rows             : list[dict] -- {HEADER_UPPER: value} per data row

    Locates the sheet + header row by scanning for 'Nest Pkg Nbr'/'PPN Quantity'
    so it survives column/row shifts and extra sheets (SCRAP, Sheet3 ...).
    """
    wb = openpyxl.load_workbook(batch_list_path, data_only=True)
    try:
        target_ws = None
        header_row = None
        cols = {}
        for ws in wb.worksheets:
            hr, cmap = sdk.find_header_row(ws, ["Nest Pkg Nbr", "PPN Quantity"])
            if hr is not None:
                target_ws, header_row, cols = ws, hr, cmap
                break
        if target_ws is None:
            return [], []

        # Header names in column order (preserve original casing for output).
        ordered = []
        for c in range(1, target_ws.max_column + 1):
            v = target_ws.cell(header_row, c).value
            if isinstance(v, str) and v.strip():
                ordered.append((c, v.strip()))
        headers_in_order = [name for _, name in ordered]

        rows = []
        nest_col = cols.get("NEST PKG NBR")
        for r in range(header_row + 1, target_ws.max_row + 1):
            # Skip fully blank rows and rows without a nest.
            nest_val = target_ws.cell(r, nest_col).value if nest_col else None
            if nest_val is None or str(nest_val).strip() == "":
                continue
            row = {}
            for c, name in ordered:
                row[name.upper()] = target_ws.cell(r, c).value
            rows.append(row)
        return headers_in_order, rows
    finally:
        wb.close()


# ──────────────────────────────────────────────────────────────────────────
# Workbook output
# ──────────────────────────────────────────────────────────────────────────

_HDR_FILL = PatternFill("solid", fgColor="305496")
_HDR_FONT = Font(bold=True, color="FFFFFF")
_PIVOT_FILL = PatternFill("solid", fgColor="1F4E78")
_TOTAL_FILL = PatternFill("solid", fgColor="FFE699")
_MISSING_FILL = PatternFill("solid", fgColor="FFFF00")
_THIN = Side(style="thin", color="BFBFBF")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def _is_date(v):
    return isinstance(v, (datetime.datetime, datetime.date))


def write_workbook(out_path: Path, data_headers, plate_rows, nonplate_rows, log):
    """Write the workbook with two identically-structured sheets: 'Plates' and
    'Non-Plates'. Each holds ONLY the flat data table (every batch-list column
    plus our generated columns) with the yellow missing-data highlighting; the
    real PivotTables are added afterwards via Excel COM (see add_real_pivots).

    Returns sheets_meta: [(sheet_name, data_row_count), ...] for the pivot pass.
    """
    wb = Workbook()
    ws_plate = wb.active
    ws_plate.title = "Plates"
    write_data_table(ws_plate, data_headers, plate_rows)

    ws_other = wb.create_sheet("Non-Plates")
    write_data_table(ws_other, data_headers, nonplate_rows)

    wb.save(str(out_path))
    return [("Plates", len(plate_rows)), ("Non-Plates", len(nonplate_rows))]


def write_data_table(ws, data_headers, data_rows):
    """Write one sheet's flat data table (header row 1, then data; rows missing
    an estimate flagged yellow). No summary block -- pivots are layered on later
    by add_real_pivots / add_static_pivots."""
    for c, name in enumerate(data_headers, start=1):
        cell = ws.cell(1, c, name)
        cell.font = _HDR_FONT
        cell.fill = _HDR_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center",
                                   wrap_text=True)
        cell.border = _BORDER

    est_idx = data_headers.index(EST_COL) + 1
    for ri, row in enumerate(data_rows, start=2):
        # Rows missing the data needed to compute an estimate are flagged
        # yellow so they're easy to find and fill in by hand.
        missing = row.get(EST_COL) is None
        for c, name in enumerate(data_headers, start=1):
            val = row.get(name)
            cell = ws.cell(ri, c, val)
            cell.border = _BORDER
            if missing:
                cell.fill = _MISSING_FILL
            if _is_date(val):
                cell.number_format = "MM/DD/YYYY"
            if c == est_idx and isinstance(val, (int, float)):
                cell.number_format = "0.000"
    ws.freeze_panes = "A2"
    _autosize(ws, data_headers)


def _nest_sums(data_rows):
    """Aggregate rows to nest -> summed Est Cut Hours. Returns
    (sums: dict[nest -> hours], grand_est, grand_qty)."""
    sums = {}
    grand_est = 0.0
    grand_qty = 0.0
    for row in data_rows:
        est = row.get(EST_COL) or 0.0
        qty = _to_float(row.get("PPN Quantity")) or 0.0
        nest = str(row.get("Nest Pkg Nbr") or "").strip()
        sums[nest] = sums.get(nest, 0.0) + est
        grand_est += est
        grand_qty += qty
    return sums, grand_est, grand_qty


def _nest_qty_groups(data_rows):
    """Group rows by (nest, PPN Quantity) -> summed Est Cut Hours, mirroring the
    real pivot's nest -> PPN row hierarchy. Returns (groups, grand_est) where
    groups maps (nest, ppn) -> est hours."""
    groups = {}
    grand_est = 0.0
    for row in data_rows:
        est = row.get(EST_COL) or 0.0
        nest = str(row.get("Nest Pkg Nbr") or "").strip()
        ppn = _to_float(row.get("PPN Quantity"))
        groups[(nest, ppn)] = groups.get((nest, ppn), 0.0) + est
        grand_est += est
    return groups, grand_est


# Excel COM enum constants we need under late binding (no makepy types).
_XL_DATABASE = 1        # PivotCache SourceType (xlDatabase)
_XL_ROW_FIELD = 1       # PivotField.Orientation (xlRowField)
_XL_SUM = -4157         # xlConsolidationFunction (xlSum)


def add_real_pivots(out_path, data_headers, sheets_meta, log):
    """Open the saved workbook in Excel via COM and drop a REAL PivotTable below
    the data table on each sheet: row field = Nest Pkg Nbr, data field =
    Sum of Est Cut Hours, with the grand-total row turned on. Returns True on
    success. Requires Excel + pywin32; on any failure returns False so the
    caller can fall back to a static summary.

    Runs on the plugin's worker thread, so COM MUST be initialised on this
    thread (CoInitialize) before any Dispatch call.
    """
    try:
        import pythoncom
        import win32com.client as win32
    except ImportError:
        log("  Excel COM (pywin32) unavailable; writing static summary instead.")
        return False

    if EST_COL not in data_headers:
        return False
    nest_header = next((h for h in data_headers if h.upper() == "NEST PKG NBR"),
                       "Nest Pkg Nbr")
    qty_header = next((h for h in data_headers if h.upper() == "PPN QUANTITY"), None)
    last_col = get_column_letter(len(data_headers))

    pythoncom.CoInitialize()
    excel = None
    try:
        excel = win32.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        wb = excel.Workbooks.Open(str(out_path))
        for sheet_name, n_rows in sheets_meta:
            if n_rows < 1:
                continue
            ws = wb.Worksheets(sheet_name)
            last_row = n_rows + 1  # +1 for the header row
            src = ws.Range(f"A1:{last_col}{last_row}")
            dest = ws.Cells(last_row + 3, 1)  # 2 blank rows under the data
            cache = wb.PivotCaches().Create(SourceType=_XL_DATABASE, SourceData=src)
            table_name = sheet_name.replace("-", "") + "Pivot"
            pt = cache.CreatePivotTable(TableDestination=dest, TableName=table_name)
            pt.PivotFields(nest_header).Orientation = _XL_ROW_FIELD
            # PPN Quantity as a SECOND row field (nested under the nest) so each
            # nest's PPN values show per row -- displayed, not summed.
            if qty_header:
                pt.PivotFields(qty_header).Orientation = _XL_ROW_FIELD
            df = pt.AddDataField(pt.PivotFields(EST_COL),
                                 f"Sum of {EST_COL}", _XL_SUM)
            df.NumberFormat = "0.000"
            # In Excel's naming, ColumnGrand = the grand total OF each column,
            # i.e. the total row at the BOTTOM (total of all nests) -- what we
            # want. RowGrand would add a redundant rightmost total column.
            pt.ColumnGrand = True
            pt.RowGrand = False
        wb.Save()
        wb.Close(SaveChanges=True)
        log("  Added real Excel PivotTables (nest / PPN Quantity -> "
            "Sum of Est Cut Hours).")
        return True
    except Exception as e:
        log(f"  Excel pivot creation failed ({e}); writing static summary instead.")
        return False
    finally:
        try:
            if excel is not None:
                excel.Quit()
        except Exception:
            pass
        pythoncom.CoUninitialize()


def add_static_pivots(out_path, plate_rows, nonplate_rows, log):
    """Fallback when Excel COM is unavailable: reopen the workbook with openpyxl
    and append a static nest -> Sum of Est Cut Hours summary (+ grand total) to
    each sheet, mirroring what the real PivotTable would have shown."""
    wb = openpyxl.load_workbook(out_path)
    for sheet_name, rows in (("Plates", plate_rows), ("Non-Plates", nonplate_rows)):
        if sheet_name in wb.sheetnames:
            _write_static_summary(wb[sheet_name], rows)
    wb.save(out_path)
    log("  Wrote static nest summary (Excel PivotTable unavailable).")


def _write_static_summary(ws, data_rows):
    """Append a nest / PPN Quantity -> Sum of Est Cut Hours block (+ Grand Total)
    below the data table, mirroring the real pivot's nest -> PPN row layout."""
    groups, grand_est = _nest_qty_groups(data_rows)
    start = ws.max_row + 3
    for c, label in ((1, "Nest Pkg Nbr"), (2, "PPN Quantity"),
                     (3, f"Sum of {EST_COL}")):
        cell = ws.cell(start, c, label)
        cell.fill = _PIVOT_FILL
        cell.font = Font(bold=True, color="FFFFFF")
        cell.border = _BORDER
    r = start + 1
    for nest, ppn in sorted(groups, key=lambda k: (str(k[0]), k[1] or 0)):
        ws.cell(r, 1, nest)
        if ppn is not None:
            q = ws.cell(r, 2, round(ppn)); q.number_format = "0"
        e = ws.cell(r, 3, round(groups[(nest, ppn)], 3)); e.number_format = "0.000"
        r += 1
    ws.cell(r, 1, "Grand Total").font = Font(bold=True)
    e = ws.cell(r, 3, round(grand_est, 3)); e.number_format = "0.000"
    for c in (1, 2, 3):
        ws.cell(r, c).fill = _TOTAL_FILL
        ws.cell(r, c).font = Font(bold=True)
        ws.cell(r, c).border = _BORDER


def _autosize(ws, data_headers):
    widths = {}
    for c, name in enumerate(data_headers, start=1):
        widths[c] = max(len(str(name)), 10)
    for row in ws.iter_rows(min_row=2, max_row=min(ws.max_row, 400)):
        for cell in row:
            if cell.value is not None and cell.column <= len(data_headers):
                widths[cell.column] = max(widths.get(cell.column, 10),
                                          min(len(str(cell.value)) + 2, 45))
    for c, w in widths.items():
        ws.column_dimensions[get_column_letter(c)].width = w


# ──────────────────────────────────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────────────────────────────────

def run(params: dict, progress_callback, cancel_event):
    log = params.get("log", print)
    settings = params.get("settings", {}) or {}

    if not PYMUPDF_AVAILABLE:
        log("ERROR: PyMuPDF (fitz) is not available; cannot parse PDFs.")
        return

    log("=" * 60)
    log(f"911 Runtime Estimator v{VERSION}")
    log("=" * 60)

    raw = sdk.request_text(params, "Paste the ROOT directory of order folders:")
    if cancel_event.is_set():
        return
    root = Path((raw or "").strip().strip('"'))
    if not root.exists() or not root.is_dir():
        log(f"ERROR: ROOT directory not found: {root}")
        return
    log(f"ROOT: {root}")

    order_folders = sorted([d for d in root.iterdir() if d.is_dir()
                            and not d.name.startswith(".")],
                           key=lambda p: p.name.upper())
    if not order_folders:
        log("ERROR: No order subfolders found under ROOT.")
        return
    log(f"Found {len(order_folders)} order folder(s): "
        f"{', '.join(o.name for o in order_folders)}")
    progress_callback(5)

    # Union of all batch-list headers (in first-seen column order) -> data cols.
    header_order = []           # batch-list headers, ordered
    header_seen = set()
    data_rows = []
    flags_summary = []

    for oi, order_folder in enumerate(order_folders):
        if cancel_event.is_set():
            log("Cancelled.")
            return
        order = order_folder.name
        log(f"\n--- Order {oi + 1}/{len(order_folders)}: {order} ---")

        cui = find_cui_folder(order_folder)
        pdf_folder = find_pdf_folder(cui) if cui else None
        batch_list = find_batch_list(cui) if cui else None

        if batch_list is None:
            log(f"  WARNING: No BATCH LIST workbook found for {order} -- skipping.")
            flags_summary.append(f"{order}: no batch list")
            continue
        log(f"  Batch list: {batch_list.name}")
        if pdf_folder:
            log(f"  PDF folder: {pdf_folder.name}")
        else:
            log(f"  WARNING: No PDF folder with packets found for {order}.")

        headers, rows = load_batch_rows(batch_list)
        if not rows:
            log(f"  WARNING: No data rows in {batch_list.name}.")
            continue
        for h in headers:
            if h.upper() not in header_seen:
                header_seen.add(h.upper())
                header_order.append(h)

        # Parse each unique nest's PDF once.
        nests_in_list = []
        seen_nests = []
        for row in rows:
            n = row.get("NEST PKG NBR")
            if n is not None and str(n).strip():
                ns = str(n).strip()
                if ns not in seen_nests:
                    seen_nests.append(ns)
        nest_pdf_data = {}
        for ns in seen_nests:
            pdf = _find_nest_pdf(pdf_folder, ns) if pdf_folder else None
            if pdf is None:
                nest_pdf_data[ns] = None
                log(f"  FLAG: nest {ns} in batch list has no packet PDF "
                    f"(thickness from Description).")
                flags_summary.append(f"{order}/{ns}: no PDF")
                continue
            try:
                nest_pdf_data[ns] = parse_nest_pdf(pdf)
            except Exception as e:
                nest_pdf_data[ns] = None
                log(f"  WARNING: could not parse {pdf.name}: {e}")

        # Flag PDFs present but not referenced by the batch list.
        if pdf_folder:
            for pdf in pdf_folder.glob("*.pdf"):
                if not any(ns.upper() in pdf.stem.upper() for ns in seen_nests):
                    log(f"  FLAG: packet {pdf.name} not referenced in batch list.")
                    flags_summary.append(f"{order}: orphan PDF {pdf.name}")

        # Build a data row per batch-list row.
        for row in rows:
            nest = str(row.get("NEST PKG NBR") or "").strip()
            pdfd = nest_pdf_data.get(nest)
            ppn = _to_float(row.get("PPN QUANTITY")) or 0.0
            scope = row.get("SCOPE OF WORK") or row.get("SCOPE OF WORK ")
            thickness = (pdfd or {}).get("thickness") if pdfd else None
            thk_src = "PDF"
            if thickness is None:
                thickness = thickness_from_description(row.get("DESCRIPTION"))
                thk_src = "Description" if thickness is not None else "MISSING"

            est_hr, factor, bevel = row_estimate_hours(thickness, ppn, scope)

            out_row = {}
            # Copy every batch-list field by header.
            for h in headers:
                out_row[h] = row.get(h.upper())
            out_row["Order"] = order
            # Location / Process: from batch list if present, else PDF-derived.
            out_row["Location"] = row.get("LOCATION")
            proc = row.get("PROCESS")
            if not proc and pdfd:
                proc = pdfd.get("process")
            out_row["Process"] = proc
            out_row["Thickness (in)"] = thickness
            out_row["Stock L"] = (pdfd or {}).get("stock_l") if pdfd else None
            out_row["Stock W"] = (pdfd or {}).get("stock_w") if pdfd else None
            out_row["Plate Weight"] = (pdfd or {}).get("plate_weight") if pdfd else None
            out_row["Mil Spec"] = (pdfd or {}).get("mil_spec") if pdfd else None
            out_row["MT Material"] = (pdfd or {}).get("mt_material") if pdfd else None
            out_row["Source"] = (pdfd or {}).get("source") if pdfd else None
            out_row["Est Cut Hours"] = round(est_hr, 4) if est_hr is not None else None

            flags = []
            if thk_src == "MISSING":
                flags.append("no thickness")
            elif thk_src == "Description":
                flags.append("thk from desc")
            if _is_bevel(scope):
                flags.append("bevel +180/pc")
            # Cross-check PDF pieces vs PPN quantity (informational).
            out_row["Flags"] = "; ".join(flags)
            # Make uppercase-keyed lookups work for pivot/derived fields.
            out_row["Nest Pkg Nbr"] = nest
            out_row["PPN Quantity"] = row.get("PPN QUANTITY")
            out_row["Description"] = row.get("DESCRIPTION")
            data_rows.append(out_row)

        progress_callback(5 + int(85 * (oi + 1) / len(order_folders)))

    if not data_rows:
        log("\nERROR: No rows produced; nothing to write.")
        return

    # Column order: 'Order' first, then every batch-list column verbatim in
    # native order (with the batch list's 'Material' shown as 'Source
    # Material'), then our generated columns. Nothing from the batch list is
    # dropped.
    batch_headers = [BATCH_HEADER_RENAME.get(h, h) for h in header_order]
    seen = {h.upper() for h in batch_headers} | {"ORDER"}
    data_headers = (["Order"] + batch_headers
                    + [c for c in GENERATED_COLS if c.upper() not in seen])

    # Normalize each row's keys to the exact header strings used in output.
    norm_rows = []
    for row in data_rows:
        nr = {}
        low = {k.upper(): v for k, v in row.items()}
        for h in data_headers:
            nr[h] = low.get(HEADER_SOURCE_KEY.get(h, h.upper()))
        # Preserve the canonical pivot keys.
        nr["Nest Pkg Nbr"] = row.get("Nest Pkg Nbr") or low.get("NEST PKG NBR")
        nr["PPN Quantity"] = row.get("PPN Quantity") if row.get("PPN Quantity") is not None else low.get("PPN QUANTITY")
        nr["Description"] = row.get("Description") if row.get("Description") is not None else low.get("DESCRIPTION")
        nr["Est Cut Hours"] = low.get("EST CUT HOURS")
        norm_rows.append(nr)

    # Split into plate vs non-plate (shapes/bars/tubes) — each gets its own
    # identically-structured sheet. A row is a plate if its Description says
    # PLATE or if we managed to compute an estimate (thickness was found).
    plate_rows = [r for r in norm_rows if _is_plate_row(r)]
    nonplate_rows = [r for r in norm_rows if not _is_plate_row(r)]
    log(f"\nBuilding workbook: {len(plate_rows)} plate rows, "
        f"{len(nonplate_rows)} non-plate rows.")

    # Output path.
    out_dir = settings.get("output_dir", "").strip()
    out_base = Path(out_dir) if out_dir else root
    stamp = datetime.datetime.now().strftime("%Y-%m-%d")
    out_path = out_base / f"911 RUNTIME ESTIMATOR - {root.name} - {stamp}.xlsx"
    try:
        sheets_meta = write_workbook(out_path, data_headers, plate_rows,
                                     nonplate_rows, log)
    except PermissionError:
        log(f"  Output file is open/locked: {out_path.name}. Close it and re-run.")
        return

    # Layer on the real Excel PivotTables; fall back to a static summary if
    # Excel COM isn't available or errors.
    if not add_real_pivots(out_path, data_headers, sheets_meta, log):
        try:
            add_static_pivots(out_path, plate_rows, nonplate_rows, log)
        except PermissionError:
            log(f"  Output file is open/locked: {out_path.name}. Close it and re-run.")
            return

    _, grand_est, grand_qty = _nest_sums(plate_rows)
    progress_callback(100)
    log("\n" + "=" * 60)
    log(f"DONE. Wrote: {out_path}")
    log(f"  Plate rows: {len(plate_rows)}  |  Non-plate rows: {len(nonplate_rows)}")
    log(f"  Grand total estimate: {grand_est:.2f} hr across {int(grand_qty)} pieces")
    if flags_summary:
        log(f"  Flags ({len(flags_summary)}):")
        for f in flags_summary[:25]:
            log(f"    - {f}")
        if len(flags_summary) > 25:
            log(f"    ... and {len(flags_summary) - 25} more")
    log("=" * 60)


if __name__ == "__main__":
    import threading
    run({"log": print}, lambda p: print(f"[{p}%]"), threading.Event())
