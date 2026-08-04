"""Bring the two tracking workbooks up to date.

    python tools/sync_tracking_workbooks.py           # report the gap only
    python tools/sync_tracking_workbooks.py --write   # apply it

Both live in ..\\Other Documents next to the repo:
    TECH_PROCESS_IMPROVEMENT.xlsm     internal build log (TASK | STATE | DESC)
    TechDeck Version Controller.xlsx  the presented record (6 sheets)

Why this is a script and not a hand edit: the workbooks kept drifting because
updating them was a manual step at the end of a long session, and manual steps
at the end of long sessions get skipped. The content lives in
`sync_workbook_content.py`, so keeping the record current is an edit to one
list, and running this is idempotent -- rows are matched on their key column,
so existing entries are updated in place and only new ones are appended.

Read the TONE RULE at the top of the content module before adding anything:
engagement features ARE logged, but the Version Controller is read outside the
team and never uses in-house names.
"""
from __future__ import annotations

import shutil
import sys
from copy import copy
from datetime import date
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync_workbook_content as C  # noqa: E402

DOCS = Path(__file__).resolve().parents[2] / "Other Documents"
VC = DOCS / "TechDeck Version Controller.xlsx"
PI = DOCS / "TECH_PROCESS_IMPROVEMENT.xlsm"
TODAY = date.today().strftime("%b %d, %Y").replace(" 0", " ")
CURRENT_VERSION = "0.8.6.10"


# --------------------------------------------------------------------- helpers
def style_from(ws, src_row, dst_row, ncols):
    """Copy a template row's formatting to a new row so appends match."""
    for c in range(1, ncols + 1):
        s, d = ws.cell(row=src_row, column=c), ws.cell(row=dst_row, column=c)
        d.font, d.fill = copy(s.font), copy(s.fill)
        d.border, d.alignment = copy(s.border), copy(s.alignment)
        d.number_format = s.number_format
    if ws.row_dimensions[src_row].height:
        ws.row_dimensions[dst_row].height = ws.row_dimensions[src_row].height


def find_row(ws, key, col=1):
    for r in range(1, ws.max_row + 1):
        v = ws.cell(row=r, column=col).value
        if isinstance(v, str) and v.strip().lower() == key.strip().lower():
            return r
    return None


def upsert(ws, rows, template_row, ncols, key_col=1, log=None):
    """Update rows whose key exists, append the rest. Returns (updated, added)."""
    updated = added = 0
    for values in rows:
        r = find_row(ws, str(values[key_col - 1]), key_col)
        if r is None:
            r = ws.max_row + 1
            style_from(ws, template_row, r, ncols)
            added += 1
            if log is not None:
                log.append(f"    + {values[key_col - 1]}")
        else:
            updated += 1
        for i, v in enumerate(values, start=1):
            if v is not None:
                ws.cell(row=r, column=i).value = v
    return updated, added


def set_pair(ws, label, value):
    r = find_row(ws, label)
    if r:
        ws.cell(row=r, column=2).value = value
    return bool(r)


# ------------------------------------------------------------ the two updates
def sync_version_controller(write):
    wb = openpyxl.load_workbook(VC)
    notes = []

    ov = wb["OVERVIEW"]
    tools = wb["AUTOMATION TOOLS"]
    # Renames first, or the new name is appended as a DUPLICATE of a row that
    # already exists under the old one.
    for old, new in C.TOOL_RENAMES.items():
        r = find_row(tools, old)
        if r:
            tools.cell(row=r, column=1).value = new
            notes.append(f"  AUTOMATION TOOLS           renamed {old} -> {new}")
    n_tools = sum(1 for r in range(1, tools.max_row + 1)
                  if str(tools.cell(row=r, column=4).value).strip() == "Active")
    n_tools += sum(1 for t in C.AUTOMATION_TOOLS
                   if find_row(tools, t[0]) is None)
    set_pair(ov, "Current Version", CURRENT_VERSION)
    set_pair(ov, "Last Updated", TODAY)
    set_pair(ov, "Automation Tools",
             f"{n_tools} deployed  (9 x 922  |  6 x 911  |  1 x 902  |  "
             f"{n_tools - 16} x cross-workflow)")
    notes.append(f"  OVERVIEW    version -> {CURRENT_VERSION}, tools -> "
                 f"{n_tools}, updated -> {TODAY}")

    for sheet, rows, ncols in (
            ("VERSION HISTORY", C.VERSION_ROWS, 5),
            ("AUTOMATION TOOLS", C.AUTOMATION_TOOLS, 5),
            ("SYSTEM FEATURES", C.SYSTEM_FEATURES, 4),
            ("ENGINEERING & RELIABILITY", C.ENGINEERING, 6),
            ("ROADMAP", C.ROADMAP, 5)):
        ws = wb[sheet]
        key = 2 if sheet in ("ENGINEERING & RELIABILITY", "ROADMAP") else 1
        log = []
        u, a = upsert(ws, rows, ws.max_row, ncols, key_col=key, log=log)
        notes.append(f"  {sheet:<26} {u} updated, {a} added")
        notes += log

    # Prose written before the tone rule.
    for sheet, old, new in C.PROSE_FIXES:
        ws = wb[sheet]
        for r in range(1, ws.max_row + 1):
            for c in range(1, ws.max_column + 1):
                cell = ws.cell(row=r, column=c)
                if isinstance(cell.value, str) and old in cell.value:
                    cell.value = cell.value.replace(old, new)
                    notes.append(f"  {sheet:<26} reworded: {old[:40]}...")

    # The test-count claim goes stale every time the suite grows.
    r = find_row(wb["ENGINEERING & RELIABILITY"], "Automated Test Suite", 2)
    if r:
        wb["ENGINEERING & RELIABILITY"].cell(row=r, column=6).value = \
            "405 automated tests, run on every change."
        notes.append("  ENGINEERING                test count -> 405")

    if write:
        shutil.copy2(VC, VC.with_suffix(".xlsx.bak"))
        wb.save(VC)
    return notes


def sync_process_improvement(write):
    wb = openpyxl.load_workbook(PI, keep_vba=True)
    ws = wb["Sheet1"]
    notes, renamed = [], 0

    for old, (new, desc) in C.PI_RENAMES.items():
        r = find_row(ws, old)
        if r:
            ws.cell(row=r, column=1).value = new
            ws.cell(row=r, column=3).value = desc
            renamed += 1
            notes.append(f"    ~ {old}  ->  {new}")
    notes.insert(0, f"  Sheet1  {renamed} entries reframed")

    log = []
    u, a = upsert(ws, C.PI_NEW, ws.max_row, 3, log=log)
    notes.append(f"  Sheet1  {u} updated, {a} added")
    notes += log

    if write:
        shutil.copy2(PI, PI.with_suffix(".xlsm.bak"))
        wb.save(PI)
    return notes


def main(write=False):
    print("VERSION CONTROLLER")
    for n in sync_version_controller(write):
        print(n)
    print("\nPROCESS IMPROVEMENT LOG")
    for n in sync_process_improvement(write):
        print(n)
    print("\n" + ("WRITTEN" if write else "DRY RUN - pass --write to apply"))


if __name__ == "__main__":
    main("--write" in sys.argv)
