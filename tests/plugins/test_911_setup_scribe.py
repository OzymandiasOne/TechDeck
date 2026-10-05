"""911 Setup v2.3.0 - the SCRIBE VERIFICATION sheet (floor feedback 2026-09-18).

Two tickets, four changes, each measured on real batches before it was built:

1. The sheet is an Excel table fixed at `A1:?25` in BOTH SACO templates, so a
   nest's 25th part onward never appeared (7 of 98 recent nests have more than
   24 parts, up to 37). The table now fits the part count, both ways.
2. Parts are listed in the nest packet's SUMMARY OF NEST order, which is how QA
   walks them at final inspection (the BATCH LIST order differed on 52 of 98).
3. When the packet's quantity disagrees with the BATCH LIST, the PACKET's goes
   on the sheet (still highlighted) - QA checks the sheet against the package.
4. The reason "QA has noticed some QTYs are wrong" could not be reproduced on
   shape batches: on PLATE nests the check had never run. Plate work orders
   look like '3X24-814' and the summary parser only knew 'XX700969', so those
   rows were silently unverifiable (L022 5CDBBM: 4 of 34 rows read).
"""

import importlib.util
from pathlib import Path

import openpyxl
import pytest
from openpyxl.worksheet.table import Table

PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "911_setup" / "run.py"


@pytest.fixture(scope="module")
def su():
    spec = importlib.util.spec_from_file_location("su_911_setup_scribe", PLUGIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── the work-order pattern ──────────────────────────────────────────────────
# The three shapes that exist: measured over 755 summary rows in 128 packets.
@pytest.mark.parametrize("wo,ok", [
    ("XX700969", True), ("X4604973", True), ("BJ700123", True),
    ("3X24-814", True), ("3x24-459", True),                 # PLATE (was rejected)
    # a window that slipped two lines offers a PART NUMBER as the work order -
    # REF is '00' on every shape row, so this pattern is the only guard
    ("H4130401-24M", False), ("H4524570-63", False), ("EB218001123CP12", False),
    ("00", False), ("-", False), ("WORK ORDER", False),
])
def test_summary_work_order_pattern(su, wo, ok):
    assert bool(su._SUMMARY_WO_RE.match(wo)) is ok


def test_summary_parser_reads_shape_and_plate_rows_in_packet_order(su, tmp_path):
    fitz = pytest.importorskip("fitz")
    # the real flat line sequence: shape rows carry REF '00' and an SK '-',
    # plate rows count 1, 2, 3 and have no SK
    lines = ["SUMMARY OF NEST N5CDBBMS", "REF", "PART NUMBER", "QTY", "WORK ORDER", "SK",
             "1", "H4130401-24M", "1", "XX700969",
             "2", "EB218001123CP12", "5", "3X24-814",
             "3", "EB218001123CP12", "5", "3X24-813",
             "00", "H4524570-63", "2", "X4604973", "-",
             "00", "H4524570-62", "1", "X4604974", "-"]
    pdf = tmp_path / "5CDBBM.pdf"
    doc = fitz.open()
    page = doc.new_page()
    for k, ln in enumerate(lines):
        page.insert_text((72, 60 + 14 * k), ln, fontsize=9)
    doc.save(pdf)
    doc.close()

    got = su._parse_packet_summary_qtys(pdf)
    assert list(got.items()) == [
        (("H4130401-24M", "XX700969"), 1),
        (("EB218001123CP12", "3X24-814"), 5),
        (("EB218001123CP12", "3X24-813"), 5),
        (("H4524570-63", "X4604973"), 2),
        (("H4524570-62", "X4604974"), 1),
    ]


# ── packet order ────────────────────────────────────────────────────────────

def _row(wo, dypn, qty=1):
    return (wo, dypn, "STL", qty, "503854", "CUT")


def test_rows_follow_the_packet_and_unlisted_rows_are_kept_last(su):
    rows = [_row("X1", "H1-33"), _row("X9", "H9-99"), _row("X2", "H1-25"),
            _row("X8", "H8-88"), _row("X3", "H1-17")]
    pmap = {("H1-17", "X3"): 1, ("H1-25", "X2"): 1, ("H1-33", "X1"): 1}
    ordered, moved = su._order_rows_like_packet(rows, pmap)
    assert moved
    assert [r[1] for r in ordered] == ["H1-17", "H1-25", "H1-33", "H9-99", "H8-88"]
    assert sorted(ordered) == sorted(rows)                      # nothing dropped


def test_same_part_on_two_work_orders_is_placed_by_work_order(su):
    # real: H4143521-25 sits on two work orders in one nest
    rows = [_row("X7449604", "H4143521-25"), _row("X8411422", "H4143521-25")]
    pmap = {("H4143521-25", "X8411422"): 1, ("H4143521-25", "X7449604"): 1}
    ordered, moved = su._order_rows_like_packet(rows, pmap)
    assert moved and [r[0] for r in ordered] == ["X8411422", "X7449604"]


def test_no_packet_summary_leaves_the_batch_list_order_alone(su):
    rows = [_row("X1", "H1-33"), _row("X2", "H1-25")]
    assert su._order_rows_like_packet(rows, {}) == (rows, False)
    same = {("H1-33", "X1"): 1, ("H1-25", "X2"): 1}
    assert su._order_rows_like_packet(rows, same) == (rows, False)


# ── the packet's quantity wins ──────────────────────────────────────────────

def test_mismatch_writes_the_packets_qty_and_highlights_it(su):
    wb = openpyxl.Workbook()
    ws = wb.active
    rows = [_row("X1", "H1-33", 2), _row("X2", "H1-25", 4), _row("X9", "H9-99", 7)]
    su._paste_batch_rows_into_nest(ws, rows)
    logged, mism, unv = [], [], []
    su._flag_qty_mismatches(ws, rows, {("H1-33", "X1"): 2, ("H1-25", "X2"): 3},
                            "503854", "911 BATCH V093 503854.xlsx",
                            logged.append, mism, unv)
    assert ws.cell(4, 9).value == 2 and ws.cell(4, 9).fill.fgColor.rgb in ("00000000", None)
    assert ws.cell(5, 9).value == 3                              # the PACKET's 3, not 4
    assert ws.cell(5, 9).fill.fgColor.rgb.endswith("FFFF00")
    assert ws.cell(6, 9).value == 7                              # unverified keeps its qty
    assert mism == [("503854", "H1-25", "X2", 4, 3)]
    assert unv == [("503854", "H9-99", "X9", 7)]
    assert any("BATCH LIST says 4" in ln and "packet's 3 was written" in ln for ln in logged)


# ── the table fits the part count ───────────────────────────────────────────

def _template(plate: bool):
    """The SCRIBE sheet exactly as both SACO templates ship it: a table over
    rows 1-25 of formulas mirroring NEST rows 4-27."""
    wb = openpyxl.Workbook()
    wb.active.title = "NEST"
    ws = wb.create_sheet("SCRIBE VERIFICATION")
    heads = (["PART ID"] if plate else []) + ["QTY", "DYPN", "HULL CODE", "MILL - SPEC",
                                              "MAT TYPE", "UNIQUE - TRACE"]
    for c, h in enumerate(heads, 1):
        ws.cell(1, c).value = h
    first = 2 if plate else 1
    for r in range(2, 26):
        n = r + 2
        ws.cell(r, first).value = f'=IF(ISBLANK(NEST!I{n}), "", NEST!I{n})'
        ws.cell(r, first + 1).value = f'=IF(ISBLANK(NEST!G{n}), "", NEST!G{n})'
        ws.cell(r, first + 2).value = f'=IF(ISBLANK(NEST!F{n}), "", LEFT(NEST!F{n}, 2))'
        if not plate:
            ws.cell(r, 6).value = f'=IF(ISBLANK(NEST!G{n}), "", "N/A")'
    last_col = "G" if plate else "F"
    table = Table(displayName="Table1", ref=f"A1:{last_col}25")
    from openpyxl.worksheet.filters import AutoFilter
    table.autoFilter = AutoFilter(ref=f"A1:{last_col}25")
    ws.add_table(table)
    return wb


@pytest.mark.parametrize("plate", [False, True])
def test_table_grows_past_24_parts(su, plate):
    wb = _template(plate)
    assert su._fit_scribe_table(wb, 37, lambda *_: None) == 37
    ws = wb["SCRIBE VERIFICATION"]
    t = ws.tables["Table1"]
    last_col = "G" if plate else "F"
    assert t.ref == f"A1:{last_col}38" and t.autoFilter.ref == t.ref   # the two refs move together
    dypn = 3 if plate else 2
    assert ws.cell(25, dypn).value == '=IF(ISBLANK(NEST!G27), "", NEST!G27)'     # untouched
    assert ws.cell(26, dypn).value == '=IF(ISBLANK(NEST!G28), "", NEST!G28)'     # the 25th part
    assert ws.cell(38, dypn).value == '=IF(ISBLANK(NEST!G40), "", NEST!G40)'     # the 37th
    assert ws.cell(38, dypn + 1).value == '=IF(ISBLANK(NEST!F40), "", LEFT(NEST!F40, 2))'
    assert ws.cell(39, dypn).value is None


def test_table_shrinks_so_a_short_nest_prints_short(su):
    wb = _template(plate=True)
    ws = wb["SCRIBE VERIFICATION"]
    ws.cell(20, 7).value = "old trace"                           # a literal below the new end
    assert su._fit_scribe_table(wb, 6, lambda *_: None) == 6
    assert ws.tables["Table1"].ref == "A1:G7"
    assert ws.cell(7, 3).value == '=IF(ISBLANK(NEST!G9), "", NEST!G9)'
    assert all(ws.cell(r, c).value is None for r in range(8, 26) for c in range(1, 8))


def test_table_fit_is_idempotent_and_never_raises(su):
    wb = _template(plate=False)
    su._fit_scribe_table(wb, 30, lambda *_: None)
    before = [[c.value for c in row] for row in wb["SCRIBE VERIFICATION"].iter_rows()]
    assert su._fit_scribe_table(wb, 30, lambda *_: None) == 30   # a re-run changes nothing
    assert before == [[c.value for c in row] for row in wb["SCRIBE VERIFICATION"].iter_rows()]
    assert su._fit_scribe_table(wb, 0, lambda *_: None) == 0     # no parts: left alone
    bare = openpyxl.Workbook()                                   # no SCRIBE sheet at all
    assert su._fit_scribe_table(bare, 5, lambda *_: None) == 0
    bare.create_sheet("SCRIBE VERIFICATION")                     # a sheet with no table
    warned = []
    assert su._fit_scribe_table(bare, 5, warned.append) == 0 and warned
