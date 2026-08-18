r"""Strip batch data out of the 902 templates, leaving the machinery intact.

Removes only what belongs to one batch -- the pasted EB rows, the batch/PO
numbers, the operator's dropdown picks, and the sample entries left on the
inspection pages. Everything that makes the workbook work stays: formulas,
conditional formatting, the ASA OPERATIONS / ALERTS dropdowns, the tolerance
tables, and the MATERIALS / HULL CODES / LISTS reference sheets.

Excel COM rather than openpyxl, same reason as rebuild_902_cover_sheet.py:
the dropdowns are x14-extension validations that an openpyxl round-trip drops.
ClearContents (never Clear) so formatting and validation survive.
"""

from __future__ import annotations

import sys
from pathlib import Path

import win32com.client as win32

ROOT = Path(r"C:\Users\ASiebenmorgen\OneDrive - American Steel & Alum\Desktop\902\Rebuilt Templates")

ORGANIZER = "902 Batch Organizer TEMPLATE.xlsx"
CUT = "QF-QU-09 902 CUT REV C.xlsx"
FORM = "QF-QU-09 902 FORM REV C.xlsx"

# sheet -> ranges to blank. Reference sheets are absent on purpose.
ORGANIZER_CLEAR = {
    "PO Info Drop": [
        "A6:T505",      # the EB paste zone
        "Y6:Z505",      # ASA OPERATIONS / ALERTS picks (validation survives)
        "J1",           # batch #
        "M1", "O1",     # PO # / PO line
    ],
    "LABELS REF": [
        "A2:B501",      # NEST NO / PART ID
        "K2:L501",      # DIAMETERS / LAYERS
    ],
}

# The inspection pages ship with a few sample entries typed into the input
# cells: P.O ITEM in the blue boxes, and two nominal dimensions. FORM is
# already clean; CUT is not. Clearing a range that is already empty is a
# no-op, so both get the same treatment and the script stays idempotent.
INSPECTION_CLEAR = {
    "PG 1": [
        "BB15:BB35",    # P.O ITEM boxes (BB14 is the header, leave it)
        "L16:L35",      # left dimension block: TARGET + Actual
        "S16:S35",      # right dimension block: TARGET + Actual
    ],
    "PG 2": [
        "BB15:BB35",
        "L16:L35",
        "S16:S35",
    ],
    "PO": [
        "A6:T505",      # the EB paste zone
        "C2",           # batch #
    ],
    "BOM": [
        "B2:B501",      # typed P.O ITEM
        "L2:L501",      # CAD CREATED BY
    ],
}

# controls that get reset rather than emptied
RESET = {
    ORGANIZER: [("PART LABELS", "A1", 1)],   # label page picker back to page 1
}


def _clear_range(rng) -> None:
    """Blank a range, tolerating merged cells.

    Excel refuses ClearContents on a range that only partially covers a merge,
    and the inspection pages merge most of their input cells. The fallback
    walks the range and clears each merge as a whole; it is slow, so it only
    runs where the fast path actually fails.
    """
    try:
        rng.ClearContents()
        return
    except Exception:
        pass

    app = rng.Application
    seen = set()
    for cell in rng:
        if not cell.MergeCells:
            cell.ClearContents()
            continue
        area = cell.MergeArea
        key = area.Address
        if key in seen:
            continue
        seen.add(key)
        # A merge can start outside the range we were asked to clear -- the
        # inspection pages merge each "P.O ITEM" header into the row below its
        # label. Clearing such a merge would take the header with it, so only
        # clear merges that sit wholly inside the target range.
        overlap = app.Intersect(area, rng)
        if overlap is not None and overlap.Count == area.Count:
            area.ClearContents()


def _clear(wb, plan: dict[str, list[str]], label: str) -> int:
    cleared = 0
    for sheet, ranges in plan.items():
        try:
            ws = wb.Worksheets(sheet)
        except Exception:
            continue                      # sheet not in this workbook
        for ref in ranges:
            rng = ws.Range(ref)
            # count what was actually holding something, for the report
            try:
                cleared += wb.Application.WorksheetFunction.CountA(rng)
            except Exception:
                pass
            _clear_range(rng)
    print(f"    {label}: {cleared} cell(s) emptied")
    return cleared


def strip(path: Path, excel) -> None:
    plan = ORGANIZER_CLEAR if path.name == ORGANIZER else INSPECTION_CLEAR
    wb = excel.Workbooks.Open(str(path))
    try:
        print(f"  {path.name}")
        _clear(wb, plan, "batch data")
        for sheet, cell, value in RESET.get(path.name, []):
            wb.Worksheets(sheet).Range(cell).Value = value
            print(f"    reset {sheet}!{cell} -> {value}")
        # park every template on the first thing the user does with it
        first = "PO Info Drop" if path.name == ORGANIZER else "PO"
        wb.Worksheets(first).Activate()
        wb.Save()
    finally:
        wb.Close(SaveChanges=False)


def main(names: list[str]) -> None:
    targets = [ROOT / n for n in (names or [ORGANIZER, CUT, FORM])]
    missing = [p for p in targets if not p.exists()]
    if missing:
        raise SystemExit("missing: " + ", ".join(p.name for p in missing))

    excel = win32.DispatchEx("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    try:
        for p in targets:
            strip(p, excel)
    finally:
        excel.Quit()


if __name__ == "__main__":
    main(sys.argv[1:])
