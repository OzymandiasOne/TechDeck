"""
911 SSPO Invoicing Prep  (plugin id: 911_sspo_invoicing_prep, family: 911)
==========================================================================
Takes an SSPO pricing sheet — including a full copy of the ENTIRE pricing master —
asks for the close-out date range (two calendar pickers, defaulting to the last
7 days), keeps only the rows whose "Firm VPD" date falls inside it, and splits
those into one workbook per Batch + Nest, named "{BATCH} {NEST} Pricing Back
Up.xlsx", each saved in its own "{BATCH} {NEST} Invoicing Docs" subfolder of a
new folder next to the file the user picks. (v2.2.0: the date range replaces
hand-trimming the master before the run; a source without a Firm VPD column
falls back to every valid row, like before.)

The top level of that output folder also gets two weekly reports, both named for
the range's END date:

  "D911 Workorder Close Outs {m-d-yyyy}.xlsx" — reconstruction of the sheet
  previously ripped by hand from the pricing master: the source's columns from A
  through "Machine", the IN-RANGE rows only, values AND cell styles copied
  verbatim, with every row's Scheduling Group set to "Closed".

  "D911 Workorder Material Status {m-d-yyyy}.xlsx" — the weekly material status
  listing invoicing used to build by hand: a fixed 14-column rip of the source
  (Program..Material Status, looked up by header name), EVERY data row, no date
  or nest filter, plain values with source number formats.

Each output workbook is built ENTIRELY from scratch (no template file) and gets:

  Tab 1 "Pricing Back Up"    - the split rows for that Batch+Nest (value snapshot,
                               number formats preserved) + a SUM total under the
                               "Total price per WO" column.
  Tab 2 "Invoice Supplement" - the ASA invoice sheet (logo from the bundled
                               asa_logo.png, blue header band, accounting formats),
                               one line per work order:
                                 A PO / B PO Line  <- looked up from the Working
                                   Forecast List ('911 Forecast' sheet, falling back
                                   to 'Complete 911 QTDR'), matched on Batch + Nest,
                                   copied verbatim (Line may be text like "SSPO")
                                 C-H               <- Batch, Work Order, DYPN,
                                   Material, DYPN QTY, Nest Pkg Nbr from tab 1
                                 I Price/Ea        <- formula =J{r}/G{r}
                                 J Ext. Price      <- live formula into tab 1's
                                   "Total price per WO" cell
                               plus a Grand Total =SUM over column J.
                                 G2 Invoice #      <- the forecast row's "PS/Inv"
                                   (v2.3.0, invoicing's ask 2026-09-04 / answers
                                   2026-09-16); blank when the forecast has none
                                 G3 Invoice Date   <- the forecast row's "Ship Date"

  "ASA Invoice No. {inv} Supplement.pdf" (v2.3.0) - the Invoice Supplement sheet
  alone, printed to PDF through Excel (COM) into the same Invoicing Docs folder,
  named to sort right after the Mie Trak invoice ("ASA Invoice No. {inv}") in the
  finished-docs folder. A nest with NO PS/Inv on the forecast gets NO PDF and is
  named in the run summary - nothing ships without an invoice number, so a
  missing one means "fill the forecast in and re-run" (or print that one by
  hand). If Excel can't be driven (no pywin32 / Excel), the workbooks are still
  written and the summary says the PDFs were skipped.

The live Working Forecast List is NEVER opened directly: it's copied into the
output folder first, the copy is read, and the copy is deleted once every workbook
has been written (even on error/cancel).

GUI plugin: pops a file picker on the main Qt thread (requires_main_thread), splits,
then opens the results folder. A "back up" = a value snapshot (cached numbers, not live
formulas) with each cell's number format preserved so $ and dates still display right.
"""

import os
import re
import shutil
from copy import copy
from datetime import date, datetime
from pathlib import Path
from typing import NamedTuple, Optional

# --- SDK bootstrap (works under the app and for headless CLI testing) -------------
try:
    from techdeck.core import plugin_sdk as sdk
except ModuleNotFoundError:
    import sys
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from techdeck.core import plugin_sdk as sdk

import openpyxl
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (QDateEdit, QDialog, QDialogButtonBox, QFormLayout,
                               QLabel, QMessageBox, QVBoxLayout)

# Hard Rule 3 nest-number regex: accept legacy numeric IDs (503633, P08229) AND
# alphanumeric IDs that contain a digit (5CDAWK); reject footer/total/junk text.
NEST_RE = sdk.NEST_ID_RE  # single home in the SDK — never re-type the pattern

REQUIRED_HEADERS = ["Batch", "Nest Pkg Nbr"]

PBU_SHEET = "Pricing Back Up"
INV_SHEET = "Invoice Supplement"
TOTAL_HEADER = "TOTAL PRICE PER WO"
LOGO_NAME = "asa_logo.png"

# Workorder Close Outs sheet: the source's columns A..Machine, verbatim, with
# Scheduling Group forced to "Closed" (reconstructs the sheet previously hand-ripped
# from the pricing master).
CLOSEOUT_LAST_HEADER = "MACHINE"
CLOSEOUT_STATUS_HEADER = "SCHEDULING GROUP"
CLOSEOUT_STATUS_VALUE = "Closed"

# The close-out date column: a row is in the run only when its Firm VPD falls in
# the picked date range. A source without the column (a hand-trimmed sheet from
# the pre-2.2.0 flow) skips the filter with a warning.
VPD_HEADER = "FIRM VPD"

# Workorder Material Status listing: the weekly report invoicing used to rip by
# hand — these 14 source columns (by header name), EVERY data row, values only.
# Widths reproduce the hand-made original.
MATSTATUS_TITLE = "D911 Workorder Material Status"
MATSTATUS_COLUMNS = [  # (source header, column width)
    ("Program", 8.6), ("Batch", 11.3), ("Work Order", 11.0), ("DYPN", 21.9),
    ("Material", 15.6), ("DYPN QTY", 9.7), ("Nest Pkg Nbr", 12.3),
    ("SCOPE OF WORK", 27.9), ("SubGroup", 9.7), ("Division", 8.1),
    ("Scheduling Group", 23.4), ("Firm VPD", 10.4), ("Notes", 74.4),
    ("Material Status", 14.4),
]

# Forecast sheets searched for the PO / PO Line, in priority order (active
# forecast first; finished batches roll off to the Complete sheet).
FORECAST_SHEETS = ["911 Forecast", "Complete 911 QTDR"]
DEFAULT_FORECAST_FILENAME = "Working Forecast List.xlsx"
FORECAST_COPY_NAME = "~ Working Forecast List (temp copy).xlsx"

# Forecast columns (by header NAME, Hard Rule 1) copied onto the supplement's
# title block: the packing slip / invoice number invoicing keys in (column BD
# on both sheets as of 2026-09-16) and the nest's ship date (column AT).
INV_HEADER = "PS/INV"
SHIP_DATE_HEADER = "SHIP DATE"
FORECAST_SCAN_COLS = 90        # header scan width: BD is column 56, keep headroom
INV_NUMBER_CELL = "G2"
INV_DATE_CELL = "G3"
SUPPLEMENT_PDF_NAME = "ASA Invoice No. {inv} Supplement.pdf"
_XL_TYPE_PDF = 0


class ForecastRow(NamedTuple):
    """What one Batch+Nest row of the Working Forecast List gives the supplement."""
    po: object = None
    line: object = None
    invoice: str = ""          # PS/Inv, as typed (blank = not invoiced yet)
    ship_date: object = None   # date / datetime / None

# ---- Invoice Supplement look (reproduced from the hand-made ASA sheet) ------------
INV_HEADERS = ["PO ", "PO Line", "Batch", "Workorder", "DYPN",
               "Source Material", "Qty", "Nest ", "Price/Ea", "Ext. Price"]
INV_COL_WIDTHS = {"A": 11.0, "B": 9.71, "C": 13.86, "D": 13.0, "E": 14.43,
                  "F": 13.86, "H": 14.43, "I": 14.29, "J": 11.57}
INV_HEADER_ROW = 7
INV_DATA_START = 8
# px, anchor A1. Was (553, 202) = the logo's natural size, which sprawled over
# the invoice fields (F2/F3) and the header band; resized 2026-07-13 to match
# invoicing's corrected sheet (434x121 = 4133850x1152525 EMU) so it stays
# inside its A1:D5 home.
LOGO_SIZE = (434, 121)
# v2.3.0 (print fix, 2026-09-17): the title block's six rows are pinned to TITLE_ROW_HEIGHT_PT each so
# the logo's bottom edge lands on the top of the blue header band instead of
# over it (121 px vs six default 15-pt rows = 120 px, and Excel rounds on
# top of that — the printed PDF showed the logo box overlapping the band).
# Height = rows 1..6 in px (pt * 96/72) minus a 6 px seam (Excel prints the
# picture ~3% larger than the px asked for, so 2 px still overlapped by ~1 pt;
# measured in the PDF 2026-09-17); width scaled with it so the box keeps its
# shape.
TITLE_ROW_HEIGHT_PT = 15.75
_title_px = int(6 * TITLE_ROW_HEIGHT_PT * 96 / 72)          # 126
LOGO_SEAM_PX = 6
LOGO_PRINT_SIZE = (round(LOGO_SIZE[0] * (_title_px - LOGO_SEAM_PX) / LOGO_SIZE[1]),
                   _title_px - LOGO_SEAM_PX)

ACCT_FMT = '_("$"* #,##0.00_);_("$"* \\(#,##0.00\\);_("$"* "-"??_);_(@_)'
_THIN = Side(style="thin")
_MEDIUM = Side(style="medium")
HDR_FONT = Font(name="Tahoma", size=8, bold=True, color="FFFFFFFF")
HDR_FILL = PatternFill("solid", fgColor="FF273991")
HDR_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
HDR_ALIGN = Alignment(horizontal="center", vertical="center")
LABEL_FONT = Font(name="Tahoma", size=10, bold=True)
DATA_FONT = Font(name="Tahoma", size=10)
DATA_ALIGN = Alignment(horizontal="center", vertical="center")
GT_LABEL_BORDER = Border(left=_THIN, right=_MEDIUM, top=_THIN, bottom=_THIN)
GT_VALUE_BORDER = Border(right=_THIN, top=_THIN, bottom=_THIN)


def _as_str(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _safe_filename(name):
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()


def _pick_sheet(wb, log):
    """Find the sheet + header row that has both Batch and Nest Pkg Nbr (Hard Rules
    1-2: locate by name, scan for the header row; visible sheets only, so a hidden
    staging tab or the old hand-made Material Status tab can't win). Returns
    (ws, header_row, header_map)."""
    for name in sdk.visible_sheetnames(wb):
        ws = wb[name]
        hdr_row, hmap = sdk.find_header_row(ws, REQUIRED_HEADERS, max_scan=12)
        if hdr_row:
            log(f"Using sheet '{ws.title}' (header on row {hdr_row}).")
            return ws, hdr_row, hmap
    raise ValueError(
        "Could not find a sheet with 'Batch' and 'Nest Pkg Nbr' columns.")


def _ask_date_range(parent=None):
    """Modal close-out date-range dialog: two calendar pickers, defaulting to the
    last 7 days (a week back through today — one whole close-out week when run on
    the usual Friday). Returns (start_date, end_date) as datetime.date with
    start <= end, or None on cancel. Main-thread only (this is a GUI plugin)."""
    dlg = QDialog(parent)
    dlg.setWindowTitle("Close-out date range")
    layout = QVBoxLayout(dlg)
    layout.addWidget(QLabel(
        "Rows whose Firm VPD falls in this range are split and closed out.\n"
        "For a single date, set both pickers to the same day."))
    form = QFormLayout()
    today = QDate.currentDate()
    start_edit = QDateEdit(today.addDays(-6))
    end_edit = QDateEdit(today)
    for edit in (start_edit, end_edit):
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("M/d/yyyy")
    form.addRow("From (Firm VPD):", start_edit)
    form.addRow("Through:", end_edit)
    layout.addLayout(form)
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    layout.addWidget(buttons)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None
    start = start_edit.date().toPython()
    end = end_edit.date().toPython()
    if start > end:
        start, end = end, start
    return start, end


# ---------------------------------------------------------------------------------
# PO / PO Line lookup from the Working Forecast List
# ---------------------------------------------------------------------------------
def _copy_forecast(settings, out_dir, log):
    """Copy the Working Forecast List into out_dir so the live file is never read
    directly. Returns the copy's Path, or None (with a logged warning) if the
    forecast can't be located — the split still runs, PO/Line just stay blank."""
    override = str(settings.get("forecast_dir", "") or "").strip()
    fdir = sdk.resolve_forecast_dir(override)
    if fdir is None:
        log("WARNING: could not locate the 'Forecast and Inventory Reports' folder - "
            "PO / PO Line will be left blank. Set it in this app's Settings.")
        return None
    fname = str(settings.get("forecast_filename", "") or "").strip() or DEFAULT_FORECAST_FILENAME
    src = Path(fdir) / fname
    if not sdk.exists(src):
        log(f"WARNING: forecast workbook not found at {src} - "
            "PO / PO Line will be left blank.")
        return None
    dest = out_dir / FORECAST_COPY_NAME
    log(f"Copying {src.name} into the output folder (the live file is never opened)...")
    sdk.copy_resilient(src, dest, log)  # hydrate + locked-open message (Hard Rule 13)
    return dest


def _read_po_map(copy_path, log, cancel_event):
    """{(BATCH, NEST): ForecastRow} from the local forecast copy.

    Reads the '911 Forecast' sheet first, then 'Complete 911 QTDR' (older batches
    roll off to it) — first sheet wins on duplicate keys. PO and Line are copied
    verbatim (Line is sometimes the text 'SSPO', not a number); PS/Inv and Ship
    Date ride along for the supplement's title block (v2.3.0) — either column
    missing on a sheet just leaves those fields blank, with one warning.
    """
    # Resilient even on the local copy: it can be open in Excel, and the
    # resilient loader is a cheap no-op on a healthy local file (Hard Rule 13).
    wb = sdk.load_workbook_resilient(copy_path, log=log, data_only=True,
                                     read_only=True)
    po_map = {}
    try:
        for sheet_name in FORECAST_SHEETS:
            if sheet_name not in wb.sheetnames:
                log(f"WARNING: sheet '{sheet_name}' not found in the forecast.")
                continue
            ws = wb[sheet_name]
            cols = None  # (po, line, batch, nest, inv, ship) 0-based; set at header row
            for i, row in enumerate(ws.iter_rows(max_col=FORECAST_SCAN_COLS)):
                if cancel_event is not None and i % 256 == 0 and cancel_event.is_set():
                    return {}
                vals = [c.value for c in row]
                if cols is None:
                    # Scan for the header row (Hard Rule 2). Batch header varies
                    # ('Batch /DR' vs 'Batch/Order'), so match any BATCH* header.
                    hmap = {str(v).strip().upper(): j
                            for j, v in enumerate(vals) if isinstance(v, str) and v.strip()}
                    batch_col = next((j for h, j in hmap.items()
                                      if h.startswith("BATCH")), None)
                    if "PO" in hmap and "LINE" in hmap and "NEST" in hmap \
                            and batch_col is not None:
                        cols = (hmap["PO"], hmap["LINE"], batch_col, hmap["NEST"],
                                hmap.get(INV_HEADER), hmap.get(SHIP_DATE_HEADER))
                        for label, idx in ((INV_HEADER, cols[4]),
                                           (SHIP_DATE_HEADER, cols[5])):
                            if idx is None:
                                log(f"WARNING: no '{label}' column on '{sheet_name}' "
                                    "- that field stays blank on the supplement.")
                    if i >= 8 and cols is None:
                        log(f"WARNING: no PO/Line/Batch/Nest header row found in "
                            f"'{sheet_name}' (looked in the first 8 rows).")
                        break
                    continue
                i_po, i_line, i_batch, i_nest, i_inv, i_ship = cols

                def at(idx):
                    return vals[idx] if idx is not None and idx < len(vals) else None

                batch = _as_str(at(i_batch)).upper()
                nest = _as_str(at(i_nest)).upper()
                po = at(i_po)
                if not batch or not NEST_RE.match(nest) or po in (None, ""):
                    continue
                po_map.setdefault((batch, nest), ForecastRow(
                    po=po, line=at(i_line), invoice=_as_str(at(i_inv)),
                    ship_date=at(i_ship)))
    finally:
        wb.close()
    log(f"  found PO numbers for {len(po_map)} batch+nest combinations.")
    return po_map


# ---------------------------------------------------------------------------------
# Output workbook (built from scratch: split data on tab 1, invoice supplement on 2)
# ---------------------------------------------------------------------------------
def _build_supplement(wb, hmap, rows, po_info, logo_path):
    """Create the Invoice Supplement sheet from scratch in `wb` (whose first sheet
    is the filled Pricing Back Up tab). `hmap` = {UPPER HEADER: 1-based col} of the
    source slice; `po_info` is (po, line) or None."""
    ws = wb.create_sheet(INV_SHEET)
    for letter, width in INV_COL_WIDTHS.items():
        ws.column_dimensions[letter].width = width
    # Print setup (v2.3.0): the sheet is printed to PDF through Excel, and its
    # ten columns spill onto a second page at default settings. One page wide,
    # landscape, as many pages tall as the rows need.
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True

    # Title block: ASA logo over merged A1:D5, manual-fill invoice fields at F2/F3.
    ws.merge_cells("A1:D5")
    for r in range(1, INV_HEADER_ROW):
        ws.row_dimensions[r].height = TITLE_ROW_HEIGHT_PT
    if sdk.exists(logo_path):
        img = XLImage(str(logo_path))
        img.width, img.height = LOGO_PRINT_SIZE
        ws.add_image(img, "A1")
    ws["F2"] = "Invoice #"
    ws["F2"].font = LABEL_FONT
    ws["F3"] = "Invoice Date:"
    ws["F3"].font = LABEL_FONT
    ws[INV_NUMBER_CELL].font = DATA_FONT
    ws[INV_DATE_CELL].font = DATA_FONT
    ws[INV_DATE_CELL].number_format = "mm-dd-yy"
    # v2.3.0: filled from the forecast row (PS/Inv + Ship Date). Blank stays
    # blank — never a guess — so a hand-filled value is still the fallback.
    if po_info is not None and po_info.invoice:
        ws[INV_NUMBER_CELL] = po_info.invoice
    if po_info is not None and po_info.ship_date not in (None, ""):
        ws[INV_DATE_CELL] = po_info.ship_date

    # Header band.
    for j, title in enumerate(INV_HEADERS, start=1):
        c = ws.cell(row=INV_HEADER_ROW, column=j, value=title)
        c.font = HDR_FONT
        c.fill = HDR_FILL
        c.border = HDR_BORDER
        c.alignment = HDR_ALIGN

    # Data rows. Column C-H sources on tab 1, looked up by header NAME (Hard Rule 1).
    src_cols = [hmap.get(h) for h in
                ("BATCH", "WORK ORDER", "DYPN", "MATERIAL", "DYPN QTY", "NEST PKG NBR")]
    total_col = hmap.get(TOTAL_HEADER)
    total_letter = get_column_letter(total_col) if total_col else None
    po, po_line = (po_info.po, po_info.line) if po_info else (None, None)

    for idx, src_row in enumerate(rows):
        r = INV_DATA_START + idx
        src_r = 2 + idx                       # matching data row on tab 1
        for j in range(1, 11):
            c = ws.cell(row=r, column=j)
            c.font = DATA_FONT
            c.alignment = DATA_ALIGN
        ws.cell(row=r, column=1, value=po)
        ws.cell(row=r, column=2, value=po_line)
        for k, sc in enumerate(src_cols):     # C..H
            if sc:
                ws.cell(row=r, column=3 + k, value=src_row[sc - 1].value)
        pea = ws.cell(row=r, column=9, value=f"=J{r}/G{r}")      # I: Price/Ea
        pea.number_format = ACCT_FMT
        ext = ws.cell(row=r, column=10)                          # J: Ext. Price
        ext.number_format = ACCT_FMT
        if total_letter:
            ext.value = f"='{PBU_SHEET}'!{total_letter}{src_r}"

    # Blank spacer row, then the boxed Grand Total.
    gt_row = INV_DATA_START + len(rows) + 1
    lbl = ws.cell(row=gt_row, column=9, value="Grand Total")
    lbl.font = LABEL_FONT
    lbl.border = GT_LABEL_BORDER
    lbl.alignment = Alignment(horizontal="center", vertical="top")
    val = ws.cell(row=gt_row, column=10,
                  value=f"=SUM(J{INV_DATA_START}:J{gt_row - 1})")
    val.font = Font(bold=True)
    val.border = GT_VALUE_BORDER
    val.number_format = ACCT_FMT


def _copy_cell(src_c, dst_c, value=None):
    """Copy a source cell's value + full style (font/fill/border/alignment/number
    format) onto dst_c; `value` overrides the copied value."""
    dst_c.value = src_c.value if value is None else value
    dst_c.font = copy(src_c.font)
    dst_c.fill = copy(src_c.fill)
    dst_c.border = copy(src_c.border)
    dst_c.alignment = copy(src_c.alignment)
    dst_c.number_format = src_c.number_format


def _write_closeouts(src_ws, hdr_row, hmap, valid_rows, out_dir, report_date, log):
    """Write the 'D911 Workorder Close Outs {m-d-yyyy}.xlsx' workbook at the top of
    out_dir: the source sheet's columns A through "Machine" (values and cell styles
    verbatim, so the hand-ripped original is reproduced exactly) with every row's
    Scheduling Group set to "Closed". Named for `report_date` (the range's end date,
    so a Monday catch-up run still stamps the close-out Friday). Returns the
    filename written."""
    last_col = hmap.get(CLOSEOUT_LAST_HEADER)
    if not last_col:
        last_col = max(hmap.values())
        log(f"  WARNING: no '{CLOSEOUT_LAST_HEADER}' column - the Close Outs sheet "
            "will include every column instead.")
    status_col = hmap.get(CLOSEOUT_STATUS_HEADER)
    if not status_col or status_col > last_col:
        status_col = None
        log(f"  WARNING: no '{CLOSEOUT_STATUS_HEADER}' column - no rows marked "
            f"'{CLOSEOUT_STATUS_VALUE}'.")

    wb = openpyxl.Workbook()
    ws = wb.active                      # stays "Sheet1", like the hand-made original
    for j in range(1, last_col + 1):
        letter = get_column_letter(j)
        dim = src_ws.column_dimensions.get(letter)
        if dim is not None and dim.width:
            ws.column_dimensions[letter].width = dim.width
        _copy_cell(src_ws.cell(row=hdr_row, column=j), ws.cell(row=1, column=j))
    for r_i, src_row in enumerate(valid_rows, start=2):
        for j in range(1, last_col + 1):
            _copy_cell(src_row[j - 1], ws.cell(row=r_i, column=j),
                       value=CLOSEOUT_STATUS_VALUE if j == status_col else None)

    d = report_date
    fname = _safe_filename(
        f"D911 Workorder Close Outs {d.month}-{d.day}-{d.year}.xlsx")
    sdk.save_workbook(wb, out_dir / fname)
    return fname


def _write_material_status(src_ws, hdr_row, hmap, all_rows, out_dir, report_date,
                           log, cancel_event):
    """Write the 'D911 Workorder Material Status {m-d-yyyy}.xlsx' listing at the top
    of out_dir: the MATSTATUS_COLUMNS source columns (by header name), EVERY data
    row — deliberately NOT filtered by the close-out date range or the nest regex,
    because the weekly listing covers the whole master. Values only, source number
    formats kept (so Firm VPD still shows as a date). Returns the filename, or None
    if cancelled."""
    cols = []                                    # (source col or None, header text)
    for name, _ in MATSTATUS_COLUMNS:
        c = hmap.get(name.upper())
        if c is None:
            log(f"  WARNING: no '{name}' column in the source - that Material "
                "Status column will be blank.")
            cols.append((None, name))
        else:
            cols.append((c, src_ws.cell(row=hdr_row, column=c).value))

    wb = openpyxl.Workbook()
    ws = wb.active
    for j, ((_, header), (_, width)) in enumerate(zip(cols, MATSTATUS_COLUMNS),
                                                  start=1):
        ws.cell(row=1, column=j, value=header)
        ws.column_dimensions[get_column_letter(j)].width = width
    error_cells = 0                # '#VALUE!'-style formula errors in the source
    for r_i, src_row in enumerate(all_rows, start=2):
        if cancel_event is not None and r_i % 256 == 0 and cancel_event.is_set():
            return None
        for j, (c, _) in enumerate(cols, start=1):
            if c is None:
                continue
            src_c = src_row[c - 1]
            if isinstance(src_c.value, str) and src_c.value.startswith("#"):
                error_cells += 1
            dst = ws.cell(row=r_i, column=j, value=src_c.value)
            if src_c.number_format and src_c.number_format != "General":
                dst.number_format = src_c.number_format
    if error_cells:
        log(f"  WARNING: {error_cells} cell(s) in the source carry an Excel "
            "formula error (#VALUE! etc.) - they're copied as-is; fix them in "
            "the pricing master.")

    d = report_date
    fname = _safe_filename(
        f"{MATSTATUS_TITLE} {d.month}-{d.day}-{d.year}.xlsx")
    sdk.save_workbook(wb, out_dir / fname)
    return fname


def _supplement_pdf_name(invoice: str) -> str:
    """'ASA Invoice No. {inv} Supplement.pdf' - invoicing's own naming, chosen so
    the supplement sorts right behind the Mie Trak invoice PDF ('ASA Invoice No.
    {inv}') in the finished-docs folder."""
    return _safe_filename(SUPPLEMENT_PDF_NAME.format(inv=str(invoice).strip()))


class _SupplementPdfExporter:
    """Prints the Invoice Supplement sheet of a saved workbook to PDF through
    Excel (COM). ONE hidden Excel instance for the whole run, started on the
    first export and quit on close(); a machine that can't drive Excel (no
    pywin32, no Excel) records `error` once and every export returns False, so
    the workbooks still get written and the summary can say the PDFs were
    skipped. GUI plugin => main thread; CoInitialize is a harmless no-op there."""

    def __init__(self, log):
        self._log = log
        self._excel = None
        self._started = False
        self.error: Optional[str] = None

    def _start(self) -> bool:
        if self._started:
            return self._excel is not None
        self._started = True
        try:
            import pythoncom
            import win32com.client as win32
        except ImportError:
            self.error = "Excel automation (pywin32) is not available"
            self._log(f"  WARNING: {self.error} - no supplement PDFs this run.")
            return False
        try:
            pythoncom.CoInitialize()
            excel = win32.DispatchEx("Excel.Application")
            excel.Visible = False
            excel.DisplayAlerts = False
            self._excel = excel
            return True
        except Exception as exc:
            self.error = f"Excel could not be started ({exc})"
            self._log(f"  WARNING: {self.error} - no supplement PDFs this run.")
            return False

    def export(self, xlsx_path: Path, pdf_path: Path) -> bool:
        if not self._start():
            return False
        wb = None
        try:
            # Plain paths on purpose: Excel COM does not accept the \\?\ prefix.
            wb = self._excel.Workbooks.Open(str(xlsx_path), ReadOnly=True)
            wb.Worksheets(INV_SHEET).ExportAsFixedFormat(_XL_TYPE_PDF, str(pdf_path))
            if not sdk.exists(pdf_path):
                raise RuntimeError("Excel reported success but no PDF appeared")
            return True
        except Exception as exc:
            self._log(f"  WARNING: could not print {xlsx_path.name} to PDF: {exc}")
            return False
        finally:
            if wb is not None:
                try:
                    wb.Close(SaveChanges=False)
                except Exception:
                    pass

    def close(self):
        if self._excel is not None:
            try:
                self._excel.Quit()
            except Exception:
                pass
            self._excel = None


class SplitResult(NamedTuple):
    written: list                     # [(relative path, row_count)]
    missing_po: list                  # display names with no forecast row at all
    closeout_name: Optional[str]
    matstatus_name: Optional[str]
    missing_invoice: list = []        # forecast row found, PS/Inv blank -> no PDF
    pdfs: list = []                   # relative paths of supplement PDFs written
    pdf_error: Optional[str] = None   # Excel unavailable: PDFs skipped wholesale


def _write_output(headers, hmap, rows, po_info, logo_path, out_path, log):
    """Build one output workbook from scratch for a single Batch+Nest group."""
    wb = openpyxl.Workbook()

    # ---- Tab 1: the split pricing rows (value snapshot) -------------------------
    ws1 = wb.active
    ws1.title = PBU_SHEET
    last_col = len(headers)
    for j, h in enumerate(headers, start=1):
        c = ws1.cell(row=1, column=j, value=h)
        c.font = Font(bold=True)
    for r_i, src_row in enumerate(rows, start=2):
        for j, src_c in enumerate(src_row, start=1):
            dst = ws1.cell(row=r_i, column=j, value=src_c.value)
            if src_c.number_format and src_c.number_format != "General":
                dst.number_format = src_c.number_format
    for j in range(1, last_col + 1):
        ws1.column_dimensions[get_column_letter(j)].width = 16

    last_data = 1 + len(rows)
    total_col = hmap.get(TOTAL_HEADER)
    if total_col:
        letter = get_column_letter(total_col)
        tot = ws1.cell(row=last_data + 1, column=total_col,
                       value=f"=SUM({letter}2:{letter}{last_data})")
        tot.number_format = '"$"#,##0.00'
        tot.font = Font(bold=True)
    else:
        log(f"  WARNING: no '{TOTAL_HEADER}' column - skipped the tab-1 total.")

    # ---- Tab 2: Invoice Supplement, built from scratch ---------------------------
    _build_supplement(wb, hmap, rows, po_info, logo_path)
    sdk.save_workbook(wb, out_path)


def split_workbook(src_path, out_dir, settings, log,
                   progress_callback=None, cancel_event=None, date_range=None,
                   pdf_exporter=None):
    """Split src_path into one from-scratch workbook per (Batch, Nest), each in its
    own "{BATCH} {NEST} Invoicing Docs" subfolder, plus the Workorder Close Outs
    and Workorder Material Status workbooks at the top of out_dir.

    `date_range` = (start_date, end_date) inclusive: only rows whose Firm VPD date
    falls inside it are split / closed out, so the user can feed the ENTIRE pricing
    master instead of hand-trimming it first. None (or a source without a Firm VPD
    column) keeps every valid row. The Material Status listing always covers every
    data row regardless of the range.

    Returns a SplitResult: written = [(relative path, row_count)], missing_po =
    display names of groups with no forecast row at all, the two report filenames
    (None if cancelled before they were written), missing_invoice = groups whose
    forecast row has no PS/Inv yet (supplement left blank, no PDF), pdfs = the
    supplement PDFs written, pdf_error = why NO PDFs could be made (Excel
    unavailable), else None.

    `pdf_exporter` is injectable for tests; default drives Excel through COM."""
    src_path = Path(src_path)
    out_dir = Path(out_dir)
    logo_path = Path(__file__).resolve().parent / LOGO_NAME

    sdk.ensure_dir(out_dir)
    forecast_copy = None
    exporter = pdf_exporter if pdf_exporter is not None else _SupplementPdfExporter(log)
    try:
        forecast_copy = _copy_forecast(settings, out_dir, log)
        if progress_callback:
            progress_callback(8)
        po_map = _read_po_map(forecast_copy, log, cancel_event) if forecast_copy else {}
        if cancel_event is not None and cancel_event.is_set():
            log("Cancelled.")
            return SplitResult([], [], None, None)
        if progress_callback:
            progress_callback(12)

        sdk.ensure_local(src_path, log=log)      # hydrate OneDrive placeholders (Rule 13)
        log(f"Opening {src_path.name} ...")
        wb = sdk.load_workbook_resilient(src_path, log=log, data_only=True)
        ws, hdr_row, hmap = _pick_sheet(wb, log)

        last_col = max(hmap.values())             # 1-based last real header column
        headers = [ws.cell(row=hdr_row, column=j).value for j in range(1, last_col + 1)]
        i_batch = hmap["BATCH"]                    # 1-based
        i_nest = hmap["NEST PKG NBR"]

        i_vpd = hmap.get(VPD_HEADER)
        if date_range is not None and not i_vpd:
            log(f"WARNING: no '{VPD_HEADER}' column in the source - the date range "
                "can't be applied, so every valid row is included (the pre-2.2.0 "
                "hand-trimmed flow).")
            date_range = None
        if date_range is not None:
            log(f"Close-out range: {date_range[0]:%m/%d/%Y} through "
                f"{date_range[1]:%m/%d/%Y} (on Firm VPD).")

        # Group IN-RANGE data rows by (batch, nest), preserving first-seen order;
        # keep the flat source-order row list too for the Close Outs sheet, and
        # EVERY data row (range or not) for the Material Status listing.
        groups, order, valid_rows, all_rows = {}, [], [], []
        skipped, out_of_range, vpd_seen = 0, 0, []
        for i, row in enumerate(ws.iter_rows(min_row=hdr_row + 1, max_col=last_col)):
            if cancel_event is not None and i % 256 == 0 and cancel_event.is_set():
                log("Cancelled.")
                return SplitResult([], [], None, None)
            if all(c.value in (None, "") for c in row):
                continue
            all_rows.append(row)
            nest = _as_str(row[i_nest - 1].value)
            batch = _as_str(row[i_batch - 1].value)
            if not NEST_RE.match(nest):
                skipped += 1
                continue
            if date_range is not None:
                v = row[i_vpd - 1].value
                d = v.date() if isinstance(v, datetime) else v if isinstance(v, date) else None
                if d is not None:
                    vpd_seen.append(d)
                if d is None or not (date_range[0] <= d <= date_range[1]):
                    out_of_range += 1
                    continue
            key = (batch, nest)
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(row)
            valid_rows.append(row)

        if not order:
            if date_range is not None and out_of_range:
                span = (f"the dates run {min(vpd_seen):%m/%d/%Y} to "
                        f"{max(vpd_seen):%m/%d/%Y}" if vpd_seen
                        else "no row has a Firm VPD date at all")
                raise sdk.UserFacingError(
                    f"No rows have a Firm VPD between {date_range[0]:%m/%d/%Y} and "
                    f"{date_range[1]:%m/%d/%Y} ({out_of_range} valid rows fall "
                    f"outside it - {span}).",
                    "Run it again and pick the week you are closing out.")
            raise ValueError("No rows with a valid nest number were found.")

        report_date = date_range[1] if date_range is not None else date.today()
        closeout_name = _write_closeouts(ws, hdr_row, hmap, valid_rows, out_dir,
                                         report_date, log)
        in_range = f" in range (of {out_of_range + len(valid_rows)} valid)" \
            if date_range is not None else ""
        log(f"  wrote {closeout_name}  ({len(valid_rows)} rows{in_range}, "
            f"Scheduling Group -> '{CLOSEOUT_STATUS_VALUE}')")

        matstatus_name = _write_material_status(ws, hdr_row, hmap, all_rows,
                                                out_dir, report_date, log,
                                                cancel_event)
        if matstatus_name is None:
            log("Cancelled.")
            return SplitResult([], [], None, None)
        log(f"  wrote {matstatus_name}  (every data row: {len(all_rows)})")

        written, missing_po, missing_invoice, pdfs = [], [], [], []
        for gi, (batch, nest) in enumerate(order):
            if cancel_event is not None and cancel_event.is_set():
                log("Cancelled.")
                break
            rows = groups[(batch, nest)]
            po_info = po_map.get((batch.upper(), nest.upper()))
            if po_info is None:
                missing_po.append(f"{batch} {nest}")
                log(f"  WARNING: {batch} {nest} not found in the forecast - "
                    "PO / PO Line left blank.")
            sub_dir = out_dir / _safe_filename(f"{batch} {nest} Invoicing Docs")
            sdk.ensure_dir(sub_dir)
            fname = _safe_filename(f"{batch} {nest} Pricing Back Up.xlsx")
            _write_output(headers, hmap, rows, po_info, logo_path,
                          sub_dir / fname, log)
            rel = f"{sub_dir.name}\\{fname}"
            written.append((rel, len(rows)))
            log(f"  wrote {rel}  ({len(rows)} row{'s' if len(rows) != 1 else ''})")

            # v2.3.0: the supplement goes to PDF only once the nest has its
            # invoice number - a blank PS/Inv means "not invoiced yet", and a
            # PDF with an empty Invoice # would just get filed by mistake.
            if po_info is not None and po_info.invoice:
                pdf_name = _supplement_pdf_name(po_info.invoice)
                if exporter.export(sub_dir / fname, sub_dir / pdf_name):
                    pdfs.append(f"{sub_dir.name}\\{pdf_name}")
                    log(f"  wrote {sub_dir.name}\\{pdf_name}")
            elif po_info is not None:
                missing_invoice.append(f"{batch} {nest}")
                log(f"  WARNING: {batch} {nest} has no PS/Inv on the forecast "
                    "- Invoice # left blank, no PDF.")
            if progress_callback:
                progress_callback(15 + int(80 * (gi + 1) / len(order)))

        if skipped:
            log(f"Skipped {skipped} row(s) without a valid nest number (footers/blanks).")
        if out_of_range:
            log(f"Left out {out_of_range} valid row(s) whose Firm VPD is outside "
                "the range (they stay in the Material Status listing).")
        return SplitResult(written, missing_po, closeout_name, matstatus_name,
                           missing_invoice, pdfs, exporter.error)
    finally:
        exporter.close()
        # The forecast copy is working scratch only - always remove it, even on
        # error/cancel, so it never lingers next to the real output files.
        if forecast_copy is not None and sdk.exists(forecast_copy):
            try:
                forecast_copy.unlink()
                log("Removed the temporary forecast copy.")
            except OSError as e:
                log(f"WARNING: could not delete the temporary forecast copy "
                    f"({forecast_copy.name}): {e} - delete it by hand.")


# ---------------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------------
def run(params, progress_callback, cancel_event):
    log = params.get("log", print)
    settings = params.get("settings", {}) or {}

    start_dir = str(Path.home() / "Downloads")
    # GUI plugin (main thread), so the console's blocking picker is off-limits:
    # sdk.pick_file_gui gives the same Sentry Drone contract (kill-cam when the
    # drone is owned + enabled for this app, plain dialog otherwise).
    src = sdk.pick_file_gui(
        params, "Choose the pricing workbook to split", start_dir,
        "Excel files (*.xlsx *.xlsm);;All files (*.*)")
    if not src:
        log("No file chosen - nothing to do.")
        return

    src = Path(src)
    date_range = _ask_date_range()
    if date_range is None:
        log("No date range chosen - nothing to do.")
        return
    out_dir = src.parent / f"{src.stem} - Back Ups"
    progress_callback(5)

    try:
        result = split_workbook(src, out_dir, settings, log, progress_callback,
                                cancel_event, date_range)
    except Exception as e:
        log(f"ERROR: {e}")
        QMessageBox.critical(None, "911 SSPO Invoicing Prep",
                             f"Could not split the file:\n\n{e}")
        return

    written, missing_po = result.written, result.missing_po
    closeout_name, matstatus_name = result.closeout_name, result.matstatus_name
    if not written:                                # cancelled
        return

    total = sum(n for _, n in written)
    progress_callback(100)
    log(f"Done. Wrote {len(written)} file(s), {total} data row(s) total, "
        f"{len(result.pdfs)} supplement PDF(s).")
    log(f"Folder: {out_dir}")
    # GUI plugins suppress the shell's auto success chime; fire it ourselves now
    # that the files are actually written (the meaningful moment).
    on_success = params.get("on_success")
    if callable(on_success):
        on_success()
    msg = (f"Done! Wrote {len(written)} back-up file(s) "
           f"({total} rows total), each in its own Invoicing Docs folder, to:"
           f"\n\n{out_dir}")
    if result.pdfs:
        msg += (f"\n\nInvoice Supplement PDFs: {len(result.pdfs)} printed, one per "
                "nest with an invoice number, next to its back-up workbook.")
    if closeout_name:
        msg += f"\n\nWorkorder Close Outs sheet (top level): {closeout_name}"
    if matstatus_name:
        msg += f"\nWorkorder Material Status listing (top level): {matstatus_name}"
    if result.pdf_error:
        msg += (f"\n\nNo supplement PDFs were made: {result.pdf_error}. The "
                "workbooks are all there - print the Invoice Supplement sheets "
                "by hand, or run again on a machine with Excel.")
    if result.missing_invoice:
        msg += ("\n\nNo invoice number (PS/Inv) in the Working Forecast List yet for:"
                "\n  " + "\n  ".join(result.missing_invoice)
                + "\n\nTheir Invoice # was left blank and no PDF was printed. Fill "
                  "PS/Inv in on the forecast and re-run, or print that one by hand.")
    if missing_po:
        msg += ("\n\nNo PO found in the Working Forecast List for:\n  "
                + "\n  ".join(missing_po)
                + "\n\nTheir PO / PO Line columns were left blank - fill them in "
                  "by hand or fix the forecast and re-run.")
    QMessageBox.information(None, "911 SSPO Invoicing Prep", msg)
    try:
        os.startfile(str(out_dir))                 # open the results folder in Explorer
    except Exception:
        pass
