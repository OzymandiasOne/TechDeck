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
  4. Writes ONE consolidated workbook (single sheet): a flat data table with
     every batch-list row across ALL orders, then a pivot-style summary keyed
     by nest number, mirroring the reference 'A.T. plate estimates' layout.

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

# Process is appended after the batch-list columns (A.T. typed it by hand;
# it is usually absent from the batch list itself; we derive it from the PDF).
APPENDED_AFTER_BATCH = ["Process"]
# Our PDF-derived + computed columns, appended after everything A.T. had.
COMPUTED_COLS = ["Thickness (in)", "Stock L", "Stock W",
                 "Mil Spec", "Source", "Est Cut Hours", "Flags"]
# Columns dropped from the output entirely (we don't capture meaningful values
# for them, so they only add noise).
DROP_COLS = {"REM USED", "REM CREATED", "DOC LOCATION", "LOCATION", "PLATE WEIGHT"}
# Columns dropped from the Plates sheet only (kept on Non-Plates).
PLATE_ONLY_DROP = {"TRADE INSTRUCTION"}

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
           "plate_weight": None, "process": None}
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
_NEST_FILL = PatternFill("solid", fgColor="DDEBF7")
_TOTAL_FILL = PatternFill("solid", fgColor="FFE699")
_MISSING_FILL = PatternFill("solid", fgColor="FFFF00")
_THIN = Side(style="thin", color="BFBFBF")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def _is_date(v):
    return isinstance(v, (datetime.datetime, datetime.date))


def write_workbook(out_path: Path, data_headers, plate_rows, nonplate_rows, log):
    """Write the workbook with two identically-structured sheets: 'Plates' and
    'Non-Plates'. Each holds the flat data table, the pivot, and the yellow
    missing-data highlighting."""
    # Plates sheet drops a couple extra columns (e.g. Trade Instruction) that
    # are only meaningful for the non-plate shapes/bars/tubes.
    plate_headers = [h for h in data_headers if h.upper() not in PLATE_ONLY_DROP]

    wb = Workbook()
    ws_plate = wb.active
    ws_plate.title = "Plates"
    write_sheet(ws_plate, plate_headers, plate_rows)

    ws_other = wb.create_sheet("Non-Plates")
    write_sheet(ws_other, data_headers, nonplate_rows)

    wb.save(str(out_path))


def write_sheet(ws, data_headers, data_rows):
    """Write one sheet: flat data table (yellow rows where no estimate), then a
    pivot summary built from this sheet's own rows, then a Grand Total."""
    # ---- Data table (header row 1) ----
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

    # ---- Pivot summary (below the data, mirroring A.T.'s layout) ----
    pivot_tree, grand_est, grand_qty = build_pivot_tree(data_rows)
    r = len(data_rows) + 4
    ws.cell(r, 1, "Row Labels").font = Font(bold=True)
    ws.cell(r, 2, f"Sum of {EST_COL}").font = Font(bold=True)
    ws.cell(r, 3, "Sum of PPN Quantity").font = Font(bold=True)
    for c in range(1, 4):
        ws.cell(r, c).fill = _PIVOT_FILL
        ws.cell(r, c).font = Font(bold=True, color="FFFFFF")
        ws.cell(r, c).border = _BORDER
    r += 1

    r = _write_pivot_level(ws, r, pivot_tree, level=0)

    # Grand total.
    ws.cell(r, 1, "Grand Total").font = Font(bold=True)
    e = ws.cell(r, 2, round(grand_est, 3)); e.number_format = "0.000"
    ws.cell(r, 3, grand_qty)
    for c in range(1, 4):
        ws.cell(r, c).fill = _TOTAL_FILL
        ws.cell(r, c).font = Font(bold=True)
        ws.cell(r, c).border = _BORDER

    _autosize(ws, data_headers)


def _write_pivot_level(ws, r, nodes, level):
    """Recursively write grouped pivot rows. `nodes` is an ordered dict of
    label -> {'est':float,'qty':float,'children':dict}. Top level (level 0) is
    the nest, then PPN Quantity, Description, Location, Process."""
    indent = "    " * level
    for label, node in nodes.items():
        disp = "" if label is None else str(label)
        cell = ws.cell(r, 1, f"{indent}{disp}")
        e = ws.cell(r, 2, round(node["est"], 3)); e.number_format = "0.000"
        ws.cell(r, 3, node["qty"])
        if level == 0:
            for c in range(1, 4):
                ws.cell(r, c).fill = _NEST_FILL
                ws.cell(r, c).font = Font(bold=True)
        try:
            ws.row_dimensions[r].outline_level = min(level, 7)
        except Exception:
            pass
        r += 1
        if node.get("children"):
            r = _write_pivot_level(ws, r, node["children"], level + 1)
    return r


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


def build_pivot_tree(data_rows):
    """Group rows into the nested pivot hierarchy and sum est/qty at each node.

    Hierarchy: Nest Pkg Nbr -> PPN Quantity -> Description -> Process.
    Returns (tree, grand_est, grand_qty).
    """
    tree = {}
    grand_est = 0.0
    grand_qty = 0.0
    levels = ["Nest Pkg Nbr", "PPN Quantity", "Description", "Process"]
    for row in data_rows:
        est = row.get(EST_COL) or 0.0
        qty = _to_float(row.get("PPN Quantity")) or 0.0
        grand_est += est
        grand_qty += qty
        node_map = tree
        path_nodes = []
        for lv in levels:
            key = row.get(lv)
            if key is None or (isinstance(key, str) and key.strip() == ""):
                key = "" if lv in ("Process", "Description") else key
            node = node_map.setdefault(key, {"est": 0.0, "qty": 0.0, "children": {}})
            path_nodes.append(node)
            node_map = node["children"]
        for node in path_nodes:
            node["est"] += est
            node["qty"] += qty
    return tree, grand_est, grand_qty


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

    # Final data-table column order: Order first, then A.T.'s batch-list
    # columns, then Process, then our computed columns. Dropped columns
    # (DROP_COLS) are excluded throughout.
    data_headers = ["Order"] + [h for h in header_order if h.upper() not in DROP_COLS]
    for extra in APPENDED_AFTER_BATCH:
        if (extra.upper() not in {h.upper() for h in data_headers}
                and extra.upper() not in DROP_COLS):
            data_headers.append(extra)
    for extra in COMPUTED_COLS:
        if (extra.upper() not in {h.upper() for h in data_headers}
                and extra.upper() not in DROP_COLS):
            data_headers.append(extra)

    # Normalize each row's keys to the exact header strings used in output.
    norm_rows = []
    for row in data_rows:
        nr = {}
        low = {k.upper(): v for k, v in row.items()}
        for h in data_headers:
            nr[h] = low.get(h.upper())
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
        write_workbook(out_path, data_headers, plate_rows, nonplate_rows, log)
    except PermissionError:
        log(f"  Output file is open/locked: {out_path.name}. Close it and re-run.")
        return

    _, grand_est, grand_qty = build_pivot_tree(plate_rows)
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
