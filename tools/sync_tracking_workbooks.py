"""Bring the three tracking workbooks up to date.

    python tools/sync_tracking_workbooks.py           # report the gap only
    python tools/sync_tracking_workbooks.py --write   # apply it

All live in ..\\Other Documents next to the repo:
    TECH_PROCESS_IMPROVEMENT.xlsm         internal build log (TASK | STATE | DESC)
    TechDeck Version Controller.xlsx      the presented record (6 sheets)
    Automation Projects Gantt Chart.xlsm  the project timeline (edited via
                                          Excel COM -- see sync_gantt)

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

import functools
import re
import shutil
import sys
from copy import copy
from datetime import date
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync_workbook_content as C  # noqa: E402
import sync_workbook_tools as T  # noqa: E402

DOCS = Path(__file__).resolve().parents[2] / "Other Documents"
VC = DOCS / "TechDeck Version Controller.xlsx"
PI = DOCS / "TECH_PROCESS_IMPROVEMENT.xlsm"
GANTT = DOCS / "Automation Projects Gantt Chart.xlsm"
GANTT_SHEET = "Gantt Chart"
TODAY = date.today().strftime("%b %d, %Y").replace(" 0", " ")


def _current_version() -> str:
    """The app's version, read from its one source of truth.

    This used to be a hardcoded literal here, which meant the release
    checklist had a silent step nobody had written down: bump the app, then
    remember to bump a copy in a tools script. On the v0.8.6.13 release it was
    already stale — the workbook's OVERVIEW was stamped with the PREVIOUS
    version on the same run that added the new VERSION HISTORY row, so the
    management-facing sheet contradicted itself. Read it instead.
    """
    src = (Path(__file__).resolve().parents[1]
           / "techdeck" / "core" / "constants.py").read_text(encoding="utf-8")
    m = re.search(r'^APP_VERSION\s*=\s*["\']([^"\']+)["\']', src, re.M)
    if not m:
        raise SystemExit("Could not read APP_VERSION from constants.py")
    return m.group(1)


CURRENT_VERSION = _current_version()


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


def last_data_row(ws):
    """Last row holding an actual value.

    NOT `ws.max_row`, which counts rows that carry only formatting. The process
    log has four such rows past its data, so appending at `max_row + 1` left a
    four-row hole in front of every batch of new entries -- and the hole grew
    by four each run, because the next run measured from the new maximum.
    """
    for r in range(ws.max_row, 0, -1):
        if any(ws.cell(row=r, column=c).value not in (None, "")
               for c in range(1, ws.max_column + 1)):
            return r
    return 0


def close_gaps(ws, first_data_row, log=None):
    """Delete fully-empty rows sitting BETWEEN data rows.

    Repairs the holes the `max_row` bug already punched. Trailing empty rows
    are left alone -- those are the sheet's own formatting, not damage.
    """
    removed = 0
    for r in range(last_data_row(ws), first_data_row - 1, -1):
        if all(ws.cell(row=r, column=c).value in (None, "")
               for c in range(1, ws.max_column + 1)):
            ws.delete_rows(r, 1)
            removed += 1
    if removed and log is not None:
        log.append(f"    - closed {removed} empty row(s) left by an "
                   f"earlier append")
    return removed


def upsert(ws, rows, template_row, ncols, key_col=1, log=None):
    """Update rows whose key exists, append the rest. Returns (updated, added)."""
    updated = added = 0
    for values in rows:
        r = find_row(ws, str(values[key_col - 1]), key_col)
        if r is None:
            r = last_data_row(ws) + 1
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


@functools.lru_cache(maxsize=1)
def test_count():
    """How many tests actually PASS, asked of pytest rather than remembered.

    This runs the suite rather than reading `--collect-only`, for two reasons.
    The per-file collection summary proved easy to under-count -- a partially
    consumed line silently drops a whole file's worth, which is how a run
    reported 396 against a real 415. And "N automated tests, run on every
    change" is a claim about tests that pass; counting collected ones would
    keep the number truthful while the suite was red.

    Returns 0 if the run fails or anything is red, and the claim is left alone
    rather than replaced with a number nobody verified. Cached -- both
    workbooks cite it, and an 18-second suite run should happen once.
    """
    import re
    import subprocess
    try:
        # No -q: pytest.ini already sets `addopts = -q`, and a second one makes
        # it -qq, which suppresses the very summary line this reads. That is
        # why an earlier version silently returned 0 on a fully green suite.
        out = subprocess.run(
            [sys.executable, "-m", "pytest"],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True, text=True, timeout=900)
    except (OSError, subprocess.SubprocessError):
        return 0
    if out.returncode != 0:
        return 0
    m = re.search(r"(\d+) passed", out.stdout.replace("\r", "\n"))
    return int(m.group(1)) if m else 0


def open_workbook(path, **kw):
    """Load, or explain the two ways that fails on a OneDrive-synced file.

    Excel holds a deny-read lock, so even the dry run dies on PermissionError
    with a traceback that says nothing about the actual cause. (Same class as
    Hard Rule 13's locked-file case -- the content is on disk, another process
    simply will not share it.)
    """
    try:
        return openpyxl.load_workbook(path, **kw)
    except PermissionError:
        raise SystemExit(
            f"\n  {path.name} is open in Excel.\n"
            f"  Close it and run this again -- Excel will not share the file,\n"
            f"  so nothing can be read from it or written to it meanwhile.\n")
    except OSError as exc:
        raise SystemExit(
            f"\n  {path.name} could not be read ({exc}).\n"
            f"  If OneDrive shows it as cloud-only, open the folder in\n"
            f"  Explorer to download it, then run this again.\n")


def set_pair(ws, label, value):
    r = find_row(ws, label)
    if r:
        ws.cell(row=r, column=2).value = value
    return bool(r)


# ------------------------------------------------------------------ styling
# One visual vocabulary shared by every sheet. The sheets had drifted into
# looking like five separate documents -- different header colours, some sheets
# banded and some not, columns too narrow to show a wrapped description.
TITLE_FILL = PatternFill("solid", fgColor="FF1F3864")
HEAD_FILL = PatternFill("solid", fgColor="FFBDD7EE")
SECT_FILL = PatternFill("solid", fgColor="FFD9E1F2")
BAND_FILL = PatternFill("solid", fgColor="FFF2F6FB")
EDGE = Side(style="thin", color="FF9DB2CE")
BOX = Border(left=EDGE, right=EDGE, top=EDGE, bottom=EDGE)
WRAP = Alignment(wrap_text=True, vertical="top")
MID = Alignment(wrap_text=True, vertical="center", horizontal="center")


def _set(cell, value):
    """Assign unless this is the tail of a merged range (read-only there)."""
    if type(cell).__name__ != "MergedCell":
        cell.value = value


def _title(ws, row, ncols, text):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        _set(cell, text if c == 1 else None)
        cell.fill = TITLE_FILL
        cell.font = Font(bold=True, size=12, color="FFFFFFFF")
        cell.border = BOX
        cell.alignment = Alignment(vertical="center", indent=1)
    ws.row_dimensions[row].height = 26


def _header(ws, row, values):
    for c, v in enumerate(values, start=1):
        cell = ws.cell(row=row, column=c)
        _set(cell, v)
        cell.fill = HEAD_FILL
        cell.font = Font(bold=True, size=10)
        cell.border = BOX
        cell.alignment = MID
    ws.row_dimensions[row].height = 24


def _section(ws, row, ncols, text):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        _set(cell, text if c == 1 else None)
        cell.fill = SECT_FILL
        cell.font = Font(bold=True, size=10, color="FF1F3864")
        cell.border = BOX
        cell.alignment = Alignment(vertical="center", indent=1)
    ws.row_dimensions[row].height = 20


def _data(ws, row, values, band=False):
    for c, v in enumerate(values, start=1):
        cell = ws.cell(row=row, column=c)
        _set(cell, v)
        cell.font = Font(size=10)
        cell.border = BOX
        cell.alignment = WRAP
        cell.fill = BAND_FILL if band else PatternFill()
    ws.row_dimensions[row].height = None      # let Excel autofit the wrap


def _widths(ws, widths):
    for col, w in widths.items():
        ws.column_dimensions[col].width = w


def _view(ws, freeze=None):
    """Set the freeze and CLEAR the saved scroll position.

    A sheet stores where it was last scrolled to as `topLeftCell` on the view,
    and openpyxl carries that through a rewrite untouched. Combined with a
    frozen pane the two disagree -- the view says 'open at row 17', the pane
    says 'the scrollable region starts at row 3' -- and Excel obeys the view,
    so the sheet opens stranded at the bottom with the rows above it
    unreachable. Three sheets shipped like that.

    Setting it to None means 'no opinion', and Excel opens at the top.
    """
    ws.freeze_panes = freeze
    ws.sheet_view.topLeftCell = None
    # Gridlines off everywhere: every cell now carries its own border, and the
    # sheets disagreed about this before (one had them off, five had them on).
    ws.sheet_view.showGridLines = False
    for sel in ws.sheet_view.selection or []:
        sel.activeCell = sel.sqref = freeze or "A1"


def rebuild_tools(wb, notes):
    """AUTOMATION TOOLS is REBUILT, not upserted.

    The problem here was never missing rows -- it was wrong ones. Five tools sat
    under the wrong workflow heading (both 911 extractors and the QR generator
    filed under 922; the 922 runtime tool filed under 911), which is why the 911
    section read as thinner than the work behind it, and four names were stale
    after renames. An upsert can neither move a row between sections nor rename
    one in place; it just adds a second copy alongside the wrong one.
    """
    ws = wb["AUTOMATION TOOLS"]
    ws.delete_rows(1, ws.max_row + 1)
    _widths(ws, {"A": 26, "B": 52, "C": 68, "D": 10, "E": 11})
    _title(ws, 1, 5, "TECHDECK  --  DEPLOYED AUTOMATION TOOLS")
    r, n = 2, 0
    for section, tools in T.TOOL_SECTIONS:
        _section(ws, r, 5, section)
        r += 1
        _header(ws, r, ["TOOL NAME", "WHAT IT DOES", "KEY AUTOMATION",
                        "STATUS", "SINCE VER."])
        r += 1
        for i, row in enumerate(tools):
            _data(ws, r, list(row), band=(i % 2 == 1))
            r += 1
            n += 1
        r += 1                                  # breathing room between sections
    _view(ws, "A2")
    notes.append(f"  AUTOMATION TOOLS           REBUILT -- {n} tools across "
                 f"{len(T.TOOL_SECTIONS)} workflow sections")
    return n


def rebuild_roadmap(wb, notes):
    """ROADMAP is rebuilt too, so a shipped item cannot sit at Planned forever.

    Delivered items STAY on the sheet rather than being deleted -- the sheet's
    job is to show the roadmap being worked through, and a sheet that only ever
    shows what is outstanding hides all of that.
    """
    ws = wb["ROADMAP"]
    ws.delete_rows(1, ws.max_row + 1)
    _widths(ws, {"A": 11, "B": 34, "C": 78, "D": 12, "E": 12})
    _title(ws, 1, 5, "TECHDECK  --  DEVELOPMENT ROADMAP")
    _header(ws, 2, ["PRIORITY", "ITEM", "DESCRIPTION", "WORKFLOW", "PHASE"])
    phase = {"Delivered": 0, "Planned": 1, "Research": 2, "Backlog": 3}
    flow = {"911": 0, "922": 1, "902": 2, "Quality": 3, "Platform": 4}
    pri = {"High": 0, "Medium": 1, "Low": 2}
    rows = sorted(T.ROADMAP_ROWS,
                  key=lambda x: (phase.get(x[4], 9), flow.get(x[3], 9),
                                 pri.get(x[0], 9), x[1]))
    for i, row in enumerate(rows):
        _data(ws, 3 + i, list(row), band=(i % 2 == 1))
    _view(ws, "A3")
    done = sum(1 for x in rows if x[4] == "Delivered")
    notes.append(f"  ROADMAP                    REBUILT -- {len(rows)} items, "
                 f"{done} Delivered")


def restyle(wb, notes):
    """Give the upserted sheets the same look as the rebuilt ones."""
    specs = {
        "VERSION HISTORY": ({"A": 15, "B": 14, "C": 14, "D": 96, "E": 52}, 5, 2),
        "SYSTEM FEATURES": ({"A": 32, "B": 62, "C": 66, "D": 10}, 4, 2),
        "ENGINEERING & RELIABILITY": ({"A": 12, "B": 30, "C": 15, "D": 70,
                                       "E": 62, "F": 40}, 6, 3),
    }
    for sheet, (widths, ncols, head_row) in specs.items():
        ws = wb[sheet]
        _widths(ws, widths)
        _title(ws, 1, ncols, ws.cell(row=1, column=1).value)
        if head_row == 3:                       # sheet carries a subtitle line
            for c in range(1, ncols + 1):
                cell = ws.cell(row=2, column=c)
                cell.fill = SECT_FILL
                cell.font = Font(size=9, italic=True, color="FF1F3864")
                cell.border = BOX
                cell.alignment = Alignment(vertical="center", indent=1)
        _header(ws, head_row, [ws.cell(row=head_row, column=c).value
                               for c in range(1, ncols + 1)])
        band = False
        for r in range(head_row + 1, ws.max_row + 1):
            if ws.cell(row=r, column=1).value in (None, ""):
                continue
            _data(ws, r, [ws.cell(row=r, column=c).value
                          for c in range(1, ncols + 1)], band=band)
            band = not band
        _view(ws, f"A{head_row + 1}")
        notes.append(f"  {sheet:<26} restyled")

    ov = wb["OVERVIEW"]
    _widths(ov, {"A": 24, "B": 80})
    _view(ov)
    _title(ov, 1, 2, ov.cell(row=1, column=1).value)
    for r in range(2, ov.max_row + 1):
        label = ov.cell(row=r, column=1).value
        if label in (None, ""):
            continue
        # A label with nothing beside it is a section heading, not a field.
        if ov.cell(row=r, column=2).value in (None, "") and r != ov.max_row:
            _section(ov, r, 2, label)
            continue
        ov.cell(row=r, column=1).font = Font(bold=True, size=10)
        ov.cell(row=r, column=2).font = Font(size=10)
        for c in (1, 2):
            ov.cell(row=r, column=c).border = BOX
            ov.cell(row=r, column=c).alignment = WRAP
    notes.append("  OVERVIEW                   restyled")


# ------------------------------------------------------------ the two updates
def sync_version_controller(write):
    wb = open_workbook(VC)
    notes = []

    ov = wb["OVERVIEW"]

    # Re-key before the upsert, same as PI_RENAMES: a row logged while the work
    # was unreleased is keyed "In Development", and cutting the release turns
    # that key into the version number. Renaming first lets the upsert MATCH it
    # and update in place - keyed on the new value it would append a second row
    # and leave the "In Development" one stranded.
    vh = wb["VERSION HISTORY"]
    for old, new in C.VERSION_RENAMES.items():
        r = find_row(vh, old)
        # Skip a rename whose target row already exists: that re-key already
        # happened on a past run, and applying it again re-keys a LATER
        # "In Development" row backwards onto an old version. Five duplicate
        # "Beta 0.8.6.11" rows accumulated exactly this way (found 2026-08-20).
        if r and not find_row(vh, new):
            vh.cell(row=r, column=1).value = new
            notes.append(f"  VERSION HISTORY            ~ {old}  ->  {new}")

    for sheet, rows, ncols in (
            ("VERSION HISTORY", C.VERSION_ROWS, 5),
            ("SYSTEM FEATURES", C.SYSTEM_FEATURES, 4),
            ("ENGINEERING & RELIABILITY", C.ENGINEERING, 6)):
        ws = wb[sheet]
        key = 2 if sheet == "ENGINEERING & RELIABILITY" else 1
        log = []
        close_gaps(ws, 4, log)
        u, a = upsert(ws, rows, last_data_row(ws), ncols, key_col=key, log=log)
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

    # The test-count claim goes stale every time the suite changes, so COUNT
    # rather than hardcode -- the previous literal was already wrong by nine.
    n = test_count()
    r = find_row(wb["ENGINEERING & RELIABILITY"], "Automated Test Suite", 2)
    if r and n:
        wb["ENGINEERING & RELIABILITY"].cell(row=r, column=6).value = \
            f"{n} automated tests, run on every change."
        notes.append(f"  ENGINEERING                test count -> {n}")

    n_tools = rebuild_tools(wb, notes)
    rebuild_roadmap(wb, notes)
    restyle(wb, notes)

    set_pair(ov, "Current Version", CURRENT_VERSION)
    set_pair(ov, "Last Updated", TODAY)
    set_pair(ov, "Automation Tools",
             f"{n_tools} deployed across the 911, 922 and 902 production "
             f"workflows plus shared quality, estimating and shop tools")
    # The summary still claimed two workflows after 902 and quality shipped.
    set_pair(ov, "Supported Workflows",
             "911 QTDR Production Packages  |  922 QTDR Pallet Packages  |  "
             "902 QTDR Production Packages  |  Quality, estimating and shop-"
             "floor tooling")
    notes.append(f"  OVERVIEW                   version -> {CURRENT_VERSION}, "
                 f"tools -> {n_tools}, updated -> {TODAY}")

    if write:
        shutil.copy2(VC, VC.with_suffix(".xlsx.bak"))
        wb.save(VC)
    return notes


def sync_process_improvement(write):
    wb = open_workbook(PI, keep_vba=True)
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

    close_gaps(ws, 2, notes)
    tests = test_count()
    rows = [tuple(v.replace("{tests}", str(tests)) if tests else v for v in row)
            for row in C.PI_NEW]
    log = []
    u, a = upsert(ws, rows, last_data_row(ws), 3, log=log)
    notes.append(f"  Sheet1  {u} updated, {a} added")
    notes += log

    if write:
        shutil.copy2(PI, PI.with_suffix(".xlsm.bak"))
        wb.save(PI)
    return notes


def _gantt_month(spec):
    """'YYYY-MM' -> datetime at the first of that month (chart granularity)."""
    from datetime import datetime
    y, m = spec.split("-")
    return datetime(int(y), int(m), 1)


def _gantt_span(start, end):
    """Duration in whole months, endpoints inclusive (Feb..Feb = 1)."""
    s, e = _gantt_month(start), _gantt_month(end)
    return (e.year - s.year) * 12 + (e.month - s.month) + 1


# The chart's calendar bars are hand-painted cell fills across G:AP (G = Feb
# 2026, one column per month) -- no formula or conditional rule draws them, so
# a row whose status or dates change must have its bar repainted or the table
# half and the picture half of the chart disagree. Colors are the sheet's own
# legend swatches (C97:C102), and the painted grammar, read off the existing
# rows: a finished project is GREEN over its working months with RED on the
# finish month; work in progress is GREEN with YELLOW on the planned finish;
# a planned project is BLUE with YELLOW on the planned finish. AMBER
# (continued support) rows never change status, so the painter never touches
# one. Values are hex RGB as stored in the file.
GANTT_BAR_FIRST_COL, GANTT_BAR_LAST_COL = 7, 42          # G .. AP
GANTT_GREEN, GANTT_BLUE = "00B050", "00B0F0"
GANTT_RED, GANTT_YELLOW, GANTT_WHITE = "FF0000", "FFFF00", "FFFFFF"


def _gantt_col(spec):
    """'YYYY-MM' -> its bar column (G = 2026-02)."""
    d = _gantt_month(spec)
    return GANTT_BAR_FIRST_COL + (d.year - 2026) * 12 + (d.month - 2)


def _gantt_bar(status, start, end):
    """{column: hex fill} for one row's repainted bar."""
    body = {C.GANTT_DONE: GANTT_GREEN, C.GANTT_DEV: GANTT_GREEN,
            C.GANTT_PLAN: GANTT_BLUE}.get(status)
    marker = GANTT_RED if status == C.GANTT_DONE else GANTT_YELLOW
    if body is None:                            # Deferred: no repaint grammar
        return None
    s, e = _gantt_col(start), _gantt_col(end)
    bar = {c: GANTT_WHITE for c in range(GANTT_BAR_FIRST_COL,
                                         GANTT_BAR_LAST_COL + 1)}
    for c in range(s, e):
        bar[c] = body
    bar[e] = marker
    return bar


def sync_gantt(write):
    """The Gantt chart is edited cell by cell THROUGH EXCEL, never openpyxl.

    This workbook cannot take the openpyxl round trip the other two survive:
    it carries VBA plus conditional-formatting extension parts that openpyxl
    warns it will strip on save -- and the calendar bars ARE that formatting.
    So the gap is computed from a read-only load (safe: nothing is saved), and
    --write drives Excel COM with macros disabled, so every part of the file
    not named in the diff is left exactly as Excel wrote it.

    Content contract (C.GANTT_ROWS): names in column A are the match keys;
    status/completion/start/end are enforced from version control; duration
    (column F, a plain number on this sheet, not a formula) is derived from
    the dates. A content row missing from the sheet is inserted directly under
    the previous row of its section. Rows the content does not name -- the
    legend, the critical-requirements block, hidden sheets -- are untouched.
    """
    from datetime import datetime

    notes = []
    wb = open_workbook(GANTT, read_only=True, data_only=True)
    ws = wb[GANTT_SHEET]
    grid = {}                                   # column-A text -> (row, values)
    for row in ws.iter_rows(min_col=1, max_col=6):
        a = row[0].value
        if isinstance(a, str) and a.strip():
            grid[a.strip()] = (row[0].row, [c.value for c in row])
    label_ok = isinstance(ws["H2"].value, str) and \
        ws["H2"].value.strip().rstrip(":").lower() == "last updated"

    # Progress Notes drift: rows appended by hand arrive without the sheet's
    # own look (even rows banded F2F2F2, everything wrapped and top-aligned,
    # dates as 'mmm d, yyyy') -- 12 such rows had accumulated by 2026-09-08.
    # Flag any data row missing it; the writer restyles just those.
    ws_n = wb["Progress Notes"]
    restyle_rows = []
    for row in ws_n.iter_rows(min_row=3, min_col=1, max_col=5):
        r = row[0].row
        if r is None or row[0].value in (None, ""):
            continue
        fill = row[0].fill
        got = fill.start_color.rgb if fill is not None and \
            fill.fill_type == "solid" else None
        fill_ok = got == "FFF2F2F2" if r % 2 == 0 else \
            got in (None, "00000000")
        wrap_ok = all(getattr(c, "alignment", None) is not None
                      and c.alignment.wrap_text for c in row)
        fmt_ok = row[0].number_format == "mmm\\ d\\,\\ yyyy"
        if not (fill_ok and wrap_ok and fmt_ok):
            restyle_rows.append(r)
    if restyle_rows:
        notes.append(f"  GANTT CHART                Progress Notes: "
                     f"{len(restyle_rows)} row(s) to restyle")
    wb.close()

    renames = []                                # (sheet row, new name)
    for old, new in C.GANTT_RENAMES.items():
        # Same guard as VERSION_RENAMES: a rename whose target already exists
        # was applied on a past run; applying it again would clobber a row.
        if old in grid and new not in grid:
            grid[new] = grid.pop(old)
            renames.append((grid[new][0], new))
            notes.append(f"  GANTT CHART                ~ {old}  ->  {new}")

    # Update rows are addressed in the sheet's CURRENT numbering and applied
    # before any insert. Insert rows are addressed in the numbering that holds
    # once every insert ABOVE them has landed (prev_row tracks that), so the
    # writer applies them strictly in order.
    updates = []                                # (sheet row, column, value)
    inserts = []                                # (row to insert AT, A-F, bar)
    paints = []                                 # (sheet row, {column: fill})
    prev_row = None
    for entry in C.GANTT_ROWS:
        if entry[0] == "SECTION":
            if entry[1] in grid:
                prev_row = grid[entry[1]][0] + len(inserts)
            continue
        name, status, pct, start, end = entry
        want = [status, pct, _gantt_month(start), _gantt_month(end),
                _gantt_span(start, end)]
        if name not in grid:
            if prev_row is None:
                raise SystemExit(f"  Cannot place {name!r}: no anchor row -- "
                                 f"has the sheet been restructured?")
            prev_row += 1
            inserts.append((prev_row, [name] + want,
                            _gantt_bar(status, start, end)))
            notes.append(f"  GANTT CHART                + {name}")
            continue
        r, have = grid[name]
        prev_row = r + len(inserts)
        changed = []
        for col, w in enumerate(want, start=2):
            h = have[col - 1]
            if isinstance(w, datetime):
                same = h == w
            elif isinstance(w, (int, float)) and isinstance(h, (int, float)):
                same = abs(float(h) - float(w)) < 1e-9
            else:
                same = isinstance(h, str) and h.strip() == w
            if not same:
                updates.append((r, col, w))
                changed.append("BCDEF"[col - 2])
        if changed:
            notes.append(f"  GANTT CHART                {name}: "
                         f"col {'/'.join(changed)}")
        # A status or date change moves the row's calendar bar too. A
        # duration-only or completion-only fix does not.
        if any(c in changed for c in "BDE"):
            bar = _gantt_bar(status, start, end)
            if bar:
                paints.append((r, bar))
                notes.append(f"  GANTT CHART                {name}: bar "
                             f"repainted {start}..{end}")

    if not (renames or updates or inserts or restyle_rows):
        notes.append("  GANTT CHART                up to date")
        return notes
    if not write:
        return notes

    shutil.copy2(GANTT, GANTT.with_suffix(".xlsm.bak"))
    try:
        import win32com.client as com
    except ImportError:
        raise SystemExit("  pywin32 is required to write the Gantt chart "
                         "(pip install pywin32)")
    app = com.DispatchEx("Excel.Application")
    app.DisplayAlerts = False
    app.EnableEvents = False
    app.AutomationSecurity = 3                  # msoAutomationSecurityForceDisable
    wbx = None
    try:
        wbx = app.Workbooks.Open(str(GANTT))
        if wbx.ReadOnly:
            raise SystemExit(
                f"\n  {GANTT.name} is open in Excel.\n"
                f"  Close it and run this again -- Excel handed the writer a\n"
                f"  read-only copy, so nothing can be saved meanwhile.\n")
        sh = wbx.Worksheets(GANTT_SHEET)

        def com_color(hex_rgb):                 # "00B050" -> BGR long
            r_, g_, b_ = (int(hex_rgb[i:i + 2], 16) for i in (0, 2, 4))
            return r_ + (g_ << 8) + (b_ << 16)

        def com_set(row_, col, v):
            # A datetime handed to COM crosses a timezone conversion and lands
            # hours off midnight (2026-09-01 04:00 on this machine). Write the
            # Excel date serial instead -- exact, and the cell keeps its format.
            if isinstance(v, datetime):
                sh.Cells(row_, col).Value2 = (v - datetime(1899, 12, 30)).days
            else:
                sh.Cells(row_, col).Value = v

        def paint(row, bar):
            for col, hex_rgb in bar.items():
                sh.Cells(row, col).Interior.Color = com_color(hex_rgb)

        for r, new in renames:
            sh.Cells(r, 1).Value = new
        # Updates and their repaints first (their row numbers predate the
        # inserts), then inserts in order -- each one's row already allows for
        # the inserts above it.
        for r, col, v in updates:
            com_set(r, col, v)
        for r, bar in paints:
            paint(r, bar)
        for r, values, bar in inserts:
            sh.Rows(r).Insert(-4121, 0)         # xlShiftDown, format from above
            for col, v in enumerate(values, start=1):
                com_set(r, col, v)
            if bar:                             # else it inherits stale fills
                paint(r, bar)
        if restyle_rows:
            shn = wbx.Worksheets("Progress Notes")
            for r in restyle_rows:
                rng = shn.Range(shn.Cells(r, 1), shn.Cells(r, 5))
                if r % 2 == 0:
                    rng.Interior.Color = com_color("F2F2F2")
                else:
                    rng.Interior.ColorIndex = -4142     # xlNone -- white rows
                rng.WrapText = True
                rng.VerticalAlignment = -4160           # xlVAlignTop
                shn.Cells(r, 1).NumberFormat = "mmm d, yyyy"
                shn.Rows(r).AutoFit()
            notes.append(f"  GANTT CHART                Progress Notes: "
                         f"{len(restyle_rows)} row(s) restyled")
        if label_ok:
            sh.Range("I2").Value = datetime.now()
            notes.append(f"  GANTT CHART                last updated -> {TODAY}")
        else:
            notes.append("  GANTT CHART                ! 'Last Updated' label "
                         "not at H2 -- date left alone")
        wbx.Save()
    finally:
        if wbx is not None:
            wbx.Close(SaveChanges=False)
        app.Quit()
    return notes


def main(write=False):
    print("VERSION CONTROLLER")
    for n in sync_version_controller(write):
        print(n)
    print("\nPROCESS IMPROVEMENT LOG")
    for n in sync_process_improvement(write):
        print(n)
    print("\nGANTT CHART")
    for n in sync_gantt(write):
        print(n)
    print("\n" + ("WRITTEN" if write else "DRY RUN - pass --write to apply"))


if __name__ == "__main__":
    main("--write" in sys.argv)
