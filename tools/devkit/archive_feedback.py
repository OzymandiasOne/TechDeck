"""Archive finished Feedback rows of the telemetry workbook - IN PLACE, through Excel.

    python -m tools.devkit.archive_feedback                       # dry run: prints the plan
    python -m tools.devkit.archive_feedback --write               # moves every `Complete` row
    python -m tools.devkit.archive_feedback --write \
        --withdrawn "2026-09-16 13:13:49|C.D."                # + a row archived as Withdrawn

Moves every Feedback row whose Status is `Complete` (plus any named with
--withdrawn, archived as `Withdrawn (resubmitting)`) onto the `Archive` sheet, so
the Dev Board's Done column can be cleared. Rows still open are never touched,
and neither is row 2 - the blank row that carries the `Key` calculated-column
formula the flow matches on.

WHY EXCEL (COM) AND NOT OPENPYXL - this is the rule from docs/USAGE_TELEMETRY.md
turned into a tool, so nobody has to remember it:
  * The workbook is written by a Power Automate flow that addresses it by cloud
    item ID. On 2026-09-16 an archive pass saved a copy and REPLACED the original
    (`copy2` + `os.replace`); OneDrive read the vanished file + identical twin as
    a MOVE, the flow followed the item into `Backups\\`, and the Dev Board read a
    dead copy for five days. Excel saves the same file, so its identity never
    changes, and desktop Excel co-authors with the flow instead of racing it.
  * Deleting a ListRow lets Excel shrink `FeedbackTable` and its Status dropdown
    itself. openpyxl updates neither on `delete_rows`, and every earlier pass
    had to repair both by hand.
Rows are picked by Timestamp + User, never by position. Copies are verified on
the Archive sheet BEFORE anything is deleted. Dev-only (tools/devkit never ships).
"""
from __future__ import annotations

import argparse
import sys
import time

from tools.devkit.todo_board.model import telemetry_workbook_path

WITHDRAWN_STATUS = "Withdrawn (resubmitting)"
_XL_UP = -4162


def _text(v) -> str:
    if v is None:
        return ""
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v).strip()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--write", action="store_true", help="apply the plan (default: dry run)")
    ap.add_argument("--withdrawn", action="append", default=[], metavar="'TIMESTAMP|USER'",
                    help="also archive this still-open row, as Withdrawn (repeatable)")
    args = ap.parse_args(argv)

    live = telemetry_workbook_path()
    if live is None:
        print("Telemetry workbook not found (set TECHDECK_TELEMETRY_XLSX).")
        return 2
    withdrawn = {tuple(w.split("|", 1)) for w in args.withdrawn}
    print(f"Workbook: {live}")

    import win32com.client as win32
    xl = win32.DispatchEx("Excel.Application")   # our own instance, never a window the user has open
    xl.Visible = False
    xl.DisplayAlerts = False
    wb = None
    try:
        wb = xl.Workbooks.Open(str(live), ReadOnly=not args.write, UpdateLinks=0)
        fb, ar = wb.Worksheets("Feedback"), wb.Worksheets("Archive")
        table = fb.ListObjects("FeedbackTable")
        print(f"FeedbackTable: {table.Range.Address} ({table.ListRows.Count} rows)")

        plan = []                                  # (list-row index, status to archive under)
        for i in range(1, table.ListRows.Count + 1):
            cells = table.ListRows(i).Range
            ts, user, status = (_text(cells.Cells(1, c).Value) for c in (1, 2, 7))
            if not ts:
                print(f"  keep  row {i}: blank (carries the Key formula)")
            elif (ts, user) in withdrawn:
                plan.append((i, WITHDRAWN_STATUS))
            elif status == "Complete":
                plan.append((i, "Complete"))
            else:
                print(f"  keep  row {i}: {ts} {user} [{status}] - still open")
        for i, st in plan:
            cells = table.ListRows(i).Range
            print(f"  MOVE  row {i}: {_text(cells.Cells(1, 1).Value)} "
                  f"{_text(cells.Cells(1, 2).Value)} -> Archive as '{st}'")
        missing = withdrawn - {(_text(table.ListRows(i).Range.Cells(1, 1).Value),
                                _text(table.ListRows(i).Range.Cells(1, 2).Value))
                               for i, _st in plan}
        if missing:
            print(f"  NOT FOUND (nothing done for these): {sorted(missing)}")

        if not args.write:
            print("DRY RUN - nothing changed. Re-run with --write to apply.")
            return 0
        if not plan:
            print("Nothing to archive.")
            return 0

        first = ar.Cells(ar.Rows.Count, 1).End(_XL_UP).Row + 1
        for k, (i, st) in enumerate(plan):         # copy first, in order ...
            src = table.ListRows(i).Range
            for c in range(1, 7):
                ar.Cells(first + k, c).Value = src.Cells(1, c).Value
                ar.Cells(first + k, c).NumberFormat = src.Cells(1, c).NumberFormat
            ar.Cells(first + k, 7).Value = st
        for k, (i, _st) in enumerate(plan):        # ... verify the copies landed ...
            src = table.ListRows(i).Range
            for c in (1, 2, 4):
                if _text(ar.Cells(first + k, c).Value) != _text(src.Cells(1, c).Value):
                    raise RuntimeError(f"Archive copy of row {i} did not verify - "
                                       "nothing was deleted, nothing was saved.")
        for i, _st in sorted(plan, reverse=True):  # ... then delete, bottom-up
            table.ListRows(i).Delete()
        wb.Save()
        print(f"Saved. FeedbackTable now {table.Range.Address} "
              f"({table.ListRows.Count} rows); Archive ends at row "
              f"{ar.Cells(ar.Rows.Count, 1).End(_XL_UP).Row}.")
        return 0
    finally:
        if wb is not None:
            wb.Close(SaveChanges=False)
        xl.Quit()
        time.sleep(1)


if __name__ == "__main__":
    sys.exit(main())
