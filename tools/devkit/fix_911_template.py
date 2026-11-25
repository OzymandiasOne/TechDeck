"""Put the Part Description formulas back into a 911 BATCH template - IN PLACE, through Excel.

    python -m tools.devkit.fix_911_template --reference <good workbook>          # dry run
    python -m tools.devkit.fix_911_template --reference <good workbook> --write  # both live templates
    python -m tools.devkit.fix_911_template --reference <good> --target <copy.xlsx> --write

WHAT IT REPAIRS (the INSPECTION SHEET tab, nothing else):
  * D16 / D17 - the two formulas that fill Part Description (material code,
    then its size from SOURCE MATERIAL INFO), and the two one-row merges they
    sit in (D16:G16, D17:G17).
  * N18 / O18 - slot 2's first MIN formula and its "MAX" label. N18 is copied
    from N16 in the SAME file, so it carries whatever tolerance logic the
    template has today rather than an old copy of it.

WHY THIS EXISTS: both SACO templates were re-saved on 2026-10-23 and came back
with D16:G17 as one merged, empty cell and N18/O18 blank. Every inspection sheet
911 Setup built for the next four weeks had no Part Description (F.T.
2026-11-19). The same save also FIXED fifty tolerance formulas ($AY23 -> $AY$23),
so rolling the file back to the previous version would have re-broken those -
this puts back only what went missing. 911 Setup v2.6.0 carries a backup and a
popup for the next time it happens; this is the tool that clears the popup.

`--reference` is any nest workbook built from a healthy template (its hidden
INSPECTION SHEET tab is an untouched copy). It is read for the eight cells'
borders, alignment and font only - never for formulas.

WHY EXCEL (COM) AND NOT OPENPYXL: the tab carries ~350 conditional-format rules
and array formulas, and the file lives in a synced library. Excel saves the
same file in place, so its identity never changes (the lesson of the
2026-09-16 telemetry archive, docs/USAGE_TELEMETRY.md). A verified backup is
taken first, outside the synced tree. Dev-only (tools/devkit never ships).
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import shutil
import sys
from pathlib import Path

from tools.devkit.todo_board.model import excel_com_path

TAB = "INSPECTION SHEET"
D16_FORMULA = '=IF(ISBLANK(BB14),"",VLOOKUP(BB14,NEST!B4:H33,7,FALSE))'
D17_FORMULA = "=IF(ISBLANK(D16),\"\",VLOOKUP(D16,'SOURCE MATERIAL INFO'!A:F,3,FALSE))"
O18_FORMULA = '=IF(ISBLANK(L18),"","MAX")'
TEMPLATE_SUBDIR = Path("03 - Processing Forms & Templates") / "00 - SACO"
TEMPLATE_NAMES = ("911 BATCH _.xlsx", "911 PLATE BATCH _.xlsx")
BACKUP_DIR = Path(r"C:\Dev\_repo_backups\templates")
_XL_PASTE_FORMULAS = -4123
_EDGES = (7, 8, 9, 10)          # xlEdgeLeft, Top, Bottom, Right
_CELLS = [f"{c}{r}" for r in (16, 17) for c in "DEFG"]


def _sha1(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def _backup(path: Path) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H%M")
    dest = BACKUP_DIR / f"{path.stem} {stamp} pre-formula-restore{path.suffix}"
    shutil.copy2(path, dest)
    if _sha1(dest) != _sha1(path):
        raise RuntimeError(f"backup of {path.name} does not match the original")
    return dest


def _plan(ws) -> list:
    """What this tab is missing, as (key, description) pairs."""
    todo = []
    d16 = ws.Range("D16")
    if not d16.HasFormula or not ws.Range("D17").HasFormula:
        shape = "one merged cell" if d16.MergeArea.Rows.Count >= 2 else "two cells"
        todo.append(("desc", f"D16/D17 Part Description formulas ({shape} today)"))
    if not ws.Range("N18").HasFormula:
        todo.append(("n18", "N18 MIN formula (copied from this file's N16)"))
    if not ws.Range("O18").HasFormula:
        todo.append(("o18", 'O18 "MAX" label formula'))
    return todo


def _copy_format(src, dst) -> None:
    for prop in ("HorizontalAlignment", "VerticalAlignment", "WrapText", "NumberFormat"):
        setattr(dst, prop, getattr(src, prop))
    dst.Font.Name, dst.Font.Size, dst.Font.Bold = src.Font.Name, src.Font.Size, src.Font.Bold
    for edge in _EDGES:
        s, d = src.Borders(edge), dst.Borders(edge)
        d.LineStyle = s.LineStyle
        if s.LineStyle != -4142:        # xlLineStyleNone has no weight to copy
            d.Weight = s.Weight


def _repair(ws, ref_ws, todo) -> None:
    keys = {k for k, _ in todo}
    if "desc" in keys:
        ws.Range("D16:G17").UnMerge()
        for addr in _CELLS:
            _copy_format(ref_ws.Range(addr), ws.Range(addr))
        ws.Range("D16:G16").Merge()
        ws.Range("D17:G17").Merge()
        # Formats first: a formula written into a Text-formatted cell is stored
        # as the literal string.
        ws.Range("D16").Formula = D16_FORMULA
        ws.Range("D17").Formula = D17_FORMULA
    if "n18" in keys:
        ws.Range("N16").Copy()
        ws.Range("N18").PasteSpecial(Paste=_XL_PASTE_FORMULAS)
        ws.Application.CutCopyMode = False
    if "o18" in keys:
        ws.Range("O18").Formula = O18_FORMULA


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--reference", required=True,
                    help="a nest workbook built from a healthy template (formats only)")
    ap.add_argument("--target", action="append", default=[],
                    help="a template file to repair (repeatable); default: both live templates")
    ap.add_argument("--write", action="store_true", help="apply (default: dry run)")
    args = ap.parse_args(argv)

    reference = Path(args.reference)
    if not reference.is_file():
        print(f"Reference workbook not found: {reference}")
        return 2
    targets = [Path(t) for t in args.target]
    live = not targets
    if live:
        from techdeck.core import plugin_sdk as sdk
        qtdr = sdk.resolve_911_qtdr_root()
        if not qtdr:
            print("911 QTDR root not found on this machine.")
            return 2
        root = Path(qtdr) / TEMPLATE_SUBDIR
        targets = [root / name for name in TEMPLATE_NAMES]

    import win32com.client as win32
    excel = win32.DispatchEx("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    excel.AskToUpdateLinks = False
    failed = False
    ref_wb = None
    try:
        ref_wb = excel.Workbooks.Open(str(reference), UpdateLinks=0, ReadOnly=True)
        ref_ws = ref_wb.Sheets(TAB)
        if not ref_ws.Range("D16").HasFormula or ref_ws.Range("D16").MergeArea.Rows.Count != 1:
            print(f"Reference {reference.name} is not a healthy template copy "
                  f"(its own D16 has no formula, or is merged over two rows).")
            return 2
        for path in targets:
            print(f"\n{path}")
            if not path.is_file():
                print("  MISSING - skipped")
                failed = True
                continue
            wb = excel.Workbooks.Open(excel_com_path(path), UpdateLinks=0,
                                      ReadOnly=not args.write)
            try:
                ws = wb.Sheets(TAB)
                todo = _plan(ws)
                if not todo:
                    print("  healthy - nothing to restore")
                    continue
                for _, what in todo:
                    print(f"  RESTORE {what}")
                if not args.write:
                    continue
                if wb.ReadOnly:
                    print("  SKIPPED - Excel could only open it read-only "
                          "(someone has it open). Nothing changed.")
                    failed = True
                    continue
                backup = _backup(path)
                print(f"  backup  {backup}")
                _repair(ws, ref_ws, todo)
                left = _plan(ws)
                if left:
                    raise RuntimeError(f"still missing after repair: {left}")
                wb.Save()
                print("  saved")
            finally:
                wb.Close(SaveChanges=False)
    finally:
        if ref_wb is not None:
            ref_wb.Close(SaveChanges=False)
        excel.Quit()
    if not args.write:
        print("\nDRY RUN - nothing changed. Re-run with --write to apply.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
