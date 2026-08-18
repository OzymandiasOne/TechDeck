r"""Rebuild the 902 Batch Organizer's Cover Sheet to the print-ready format.

Target layout (from '902 Cover Sheet.pdf'):

    1000147009  Line 57                <- PO # + PO Line, typed on 'PO Info Drop'
    4142  211028343B  902 QTDR ASA     <- Batch # + source material + fixed label

    Hull | Qty | Order | Packed | DYPN | Source Material | Operations | Alerts

Everything except the two PO cells autofills from 'PO Info Drop'.  The sheet carries
a dynamic print area so the user opens the tab, hits print, and gets exactly the
populated rows -- no blank pages, header repeated on every page.

Driven through Excel COM rather than openpyxl on purpose: the organizer's
ASA OPERATIONS / ALERTS dropdowns are x14-extension data validations, and an
openpyxl round-trip silently drops them.
"""

from __future__ import annotations

import sys
from pathlib import Path

import win32com.client as win32

# --- layout ---------------------------------------------------------------
HEADERS = ["Hull", "Qty", "Order", "Packed", "DYPN",
           "Source Material", "Operations", "Alerts"]

# column widths in Excel character units; Hull is sized for the organizer's
# "ADD HULL CODE" miss-flag rather than a 3-digit hull, so the warning is
# readable instead of spilling into Qty
WIDTHS = [13, 6, 12, 9, 16, 18, 17, 17]

FIRST_DATA_ROW = 4          # cover sheet row 4  <->  'PO Info Drop' row 6
LAST_DATA_ROW = 503         # 500 lines, matching the drop's A6:A505
DROP = "'PO Info Drop'"
BALLOT_BOX = chr(0x2610)    # the empty square the floor ticks off

# PO # / PO Line inputs live beside the existing green BATCH # cell (J1)
PO_LABEL_CELL, PO_VALUE_CELL = "L1", "M1"
LINE_LABEL_CELL, LINE_VALUE_CELL = "N1", "O1"

# Every EB offload workbook ends with 1-3 footer rows (a piece count, the
# planner's initials, a date). They carry an Order-column value, so gating on
# column A prints them as bogus line items -- but they never carry a DYPN, and
# a real part line always does. So DYPN is the "is this a real line" test.
LINE_TEST = f'{DROP}!$B6=""'


def _pull(col: str) -> str:
    """Pull one 'PO Info Drop' column, blank-for-blank.

    The inner IF matters: a bare reference to an empty cell renders as 0, and
    Operations / Alerts are empty on most lines.
    """
    return f'=IF({LINE_TEST},"",IF({DROP}!${col}6="","",{DROP}!${col}6))'


# one formula per column; the '6' rows get filled down relatively by Excel
COLUMN_FORMULAS = [
    _pull("W"),                                     # A Hull
    _pull("G"),                                     # B Qty
    _pull("A"),                                     # C Order
    f'=IF({LINE_TEST},"","{BALLOT_BOX}")',          # D Packed
    _pull("B"),                                     # E DYPN
    _pull("F"),                                     # F Source Material
    _pull("Y"),                                     # G Operations
    _pull("Z"),                                     # H Alerts
]

TITLE_PO = (
    f'=IF({DROP}!$M$1="","",{DROP}!$M$1&"  Line "&{DROP}!$O$1)'
)
TITLE_BATCH = (
    f'={DROP}!$J$1&"  "&IFERROR(INDEX({DROP}!$F$6:$F$505,1),"")&"  902 QTDR ASA"'
)

# rows 1..3 are the two titles + the header row; the DYPN count gives the live
# line count (column A would over-count by EB's footer rows -- see LINE_TEST)
PRINT_AREA_FORMULA = (
    f"=OFFSET('Cover Sheet'!$A$1,0,0,3+COUNTA({DROP}!$B$6:$B$505),8)"
)

GREEN = 0xCCFFCC            # BGR - same mint as the existing BATCH # input
XL_LEFT_TO_RIGHT = 1
XL_PORTRAIT = 1
XL_CENTER = -4108
XL_UNDERLINE_SINGLE = 2
XL_EDGE_LEFT, XL_EDGE_TOP, XL_EDGE_BOTTOM, XL_EDGE_RIGHT = 7, 8, 9, 10
XL_CONTINUOUS = 1
XL_THIN = 2


def _add_po_inputs(wb) -> None:
    """Give the user somewhere to type the PO number and line."""
    drop = wb.Worksheets("PO Info Drop")

    drop.Range(PO_LABEL_CELL).Value = "PO #"
    drop.Range(LINE_LABEL_CELL).Value = "LINE"
    for cell in (PO_LABEL_CELL, LINE_LABEL_CELL):
        drop.Range(cell).Font.Bold = True
        drop.Range(cell).HorizontalAlignment = XL_CENTER

    for cell in (PO_VALUE_CELL, LINE_VALUE_CELL):
        rng = drop.Range(cell)
        rng.Interior.Color = GREEN
        rng.HorizontalAlignment = XL_CENTER
        rng.NumberFormat = "@"          # keep leading zeros / long IDs as typed
        for edge in (XL_EDGE_LEFT, XL_EDGE_TOP, XL_EDGE_BOTTOM, XL_EDGE_RIGHT):
            border = rng.Borders(edge)
            border.LineStyle = XL_CONTINUOUS
            border.Weight = XL_THIN


# Rewritten in full (rather than patched) so re-running the script is idempotent.
# Changes vs the original: the sheet's real name is 'PO Info Drop' not
# 'OFFLOAD Drop', step 2 warns to stop at column T, step 3 gains the PO cells,
# and the Cover Sheet gets its own step.
INSTRUCTION_STEPS = [
    ("Open the EB '902 OFFLOAD TO ASA' workbook for the batch.",
     "This is the file EB sends with the batch (BATCH sheet: Order / DYPN / Assembly / ... / GEOMETRY)."),
    ("Copy its BATCH-sheet data rows - row 4 down, columns A to T ONLY - and paste as VALUES into 'PO Info Drop' cell A6.",
     "Keep EB's column order (Order through GEOMETRY). Stop at column T: EB leaves unlabelled scratch data in U and W, and pasting those lands on top of the blue P.O ITEM and HULL formulas. Use Paste Special > Values to keep this workbook's formatting."),
    ("Type the Batch #, PO # and PO Line in the green cells at the top of 'PO Info Drop'.",
     "The Batch # flows to the Cover Sheet title and anywhere else the batch number is shown. PO # and Line print as the Cover Sheet's top line - they aren't in EB's file, so they're the one thing you have to look up."),
    ("Fix anything highlighted yellow.",
     "Yellow = a material not in the MATERIALS sheet or an order prefix not in HULL CODES. Add the row to that reference sheet ONCE and every future batch inherits it."),
    ("Pick ASA OPERATIONS for each line (dropdown).",
     "Lines containing PRESS-BRAKE automatically flag CUT + FORM (orange) so forming inspections are never missed."),
    ("Cover Sheet: nothing to fill in - open the tab and print.",
     "It fills itself from 'PO Info Drop' and carries its own print area, so it prints only the lines this batch actually has - no blank pages - with the titles and column headers repeated on every page. EB's trailing footer rows (piece count / initials / date) are left off automatically: a real line always has a DYPN, those don't."),
    ("Print labels straight from the PART LABELS sheet onto Avery 6460 stock - no Word document needed.",
     "Same mechanism as the 922 Rod Labels sheet, laid out 3 x 10 to match the label sheets: change the big blue page number to move through the batch 30 labels at a time and print each page at 100% scale. The gold numbers show which LABELS REF rows are on each label row (they don't print). Do a plain-paper test print over a label sheet to confirm alignment before running stock through."),
    ("Generate inspection sheets from the matching QF-QU-09 CUT / FORM AUTOFILL templates.",
     "Paste the same OFFLOAD data into their PO sheet - part numbers and descriptions fill in from a dropdown, no typing."),
]
FIRST_STEP_ROW = 5


def _update_instructions(wb) -> None:
    ws = wb.Worksheets("INSTRUCTIONS")
    for i, (description, explanation) in enumerate(INSTRUCTION_STEPS):
        row = FIRST_STEP_ROW + i
        ws.Cells(row, 1).Value = i + 1
        ws.Cells(row, 2).Value = description
        ws.Cells(row, 3).Value = explanation


def _build_cover(wb):
    ws = wb.Worksheets("Cover Sheet")
    ws.Cells.Clear()
    ws.Cells.ClearFormats()

    # --- titles ---
    for row, formula in ((1, TITLE_PO), (2, TITLE_BATCH)):
        band = ws.Range(ws.Cells(row, 1), ws.Cells(row, 8))
        band.Merge()
        cell = ws.Cells(row, 1)
        cell.Formula = formula
        cell.HorizontalAlignment = XL_CENTER
        cell.Font.Bold = True
        cell.Font.Underline = XL_UNDERLINE_SINGLE
        cell.Font.Size = 12

    # --- header row ---
    for i, text in enumerate(HEADERS, start=1):
        cell = ws.Cells(3, i)
        cell.Value = text
        cell.Font.Bold = True
        cell.Font.Underline = XL_UNDERLINE_SINGLE
        cell.HorizontalAlignment = XL_CENTER
        cell.VerticalAlignment = XL_CENTER

    # --- data block: one Range.Formula write per column, Excel fills down ---
    for i, formula in enumerate(COLUMN_FORMULAS, start=1):
        col = ws.Range(ws.Cells(FIRST_DATA_ROW, i), ws.Cells(LAST_DATA_ROW, i))
        col.Formula = formula
        col.HorizontalAlignment = XL_CENTER
        col.VerticalAlignment = XL_CENTER

    body = ws.Range(ws.Cells(FIRST_DATA_ROW, 1), ws.Cells(LAST_DATA_ROW, 8))
    body.Font.Name = "Calibri"
    body.Font.Size = 11

    # Operations is the only column long enough to need two lines
    ws.Range(ws.Cells(FIRST_DATA_ROW, 7), ws.Cells(LAST_DATA_ROW, 7)).WrapText = True
    # the ballot box needs a font that actually has the glyph
    ws.Range(ws.Cells(FIRST_DATA_ROW, 4), ws.Cells(LAST_DATA_ROW, 4)).Font.Name = "Segoe UI Symbol"

    for i, width in enumerate(WIDTHS, start=1):
        ws.Columns(i).ColumnWidth = width

    # Cells.ClearFormats leaves row heights behind, so the old sheet's custom
    # heights would survive as random tall rows. Reset, then let the wrapped
    # Operations cells claim the extra line they need.
    ws.Rows(f"1:{LAST_DATA_ROW}").RowHeight = 14.5
    ws.Rows(f"1:{LAST_DATA_ROW}").AutoFit()

    return ws


def _set_print_setup(wb, ws) -> None:
    ws.PageSetup.Orientation = XL_PORTRAIT
    ws.PageSetup.Order = XL_LEFT_TO_RIGHT
    ws.PageSetup.Zoom = False
    ws.PageSetup.FitToPagesWide = 1
    ws.PageSetup.FitToPagesTall = False     # long batches spill to page 2, 3, ...
    ws.PageSetup.CenterHorizontally = True
    ws.PageSetup.PrintTitleRows = "$1:$3"   # titles + headers repeat on every page
    ws.PageSetup.CenterFooter = "Page &P of &N"
    ws.PageSetup.LeftMargin = wb.Application.InchesToPoints(0.4)
    ws.PageSetup.RightMargin = wb.Application.InchesToPoints(0.4)
    ws.PageSetup.TopMargin = wb.Application.InchesToPoints(0.6)
    ws.PageSetup.BottomMargin = wb.Application.InchesToPoints(0.6)
    ws.PageSetup.PrintGridlines = False

    # dynamic print area: only the rows that actually have a line on them
    wb.Names.Add(Name="'Cover Sheet'!Print_Area", RefersTo=PRINT_AREA_FORMULA)


def rebuild(path: Path, excel) -> None:
    wb = excel.Workbooks.Open(str(path))
    try:
        _add_po_inputs(wb)
        _update_instructions(wb)
        ws = _build_cover(wb)
        _set_print_setup(wb, ws)
        # leave the file parked on the paste target, not wherever it was saved last
        wb.Worksheets("PO Info Drop").Activate()
        wb.Save()
        print(f"  rebuilt: {path.name}")
    finally:
        wb.Close(SaveChanges=False)


def main(paths: list[Path]) -> None:
    excel = win32.DispatchEx("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    try:
        for p in paths:
            rebuild(p, excel)
    finally:
        excel.Quit()


if __name__ == "__main__":
    main([Path(a) for a in sys.argv[1:]])
