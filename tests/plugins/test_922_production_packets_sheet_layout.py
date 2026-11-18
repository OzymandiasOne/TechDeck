"""The cutting list sheet's columns, in the order Carrie's format puts them.

`Order` was added as column E in v1.6.0 (Anthony, 2026-10-30), AFTER Quantity, so
`Parts Id.` / `Length` / `Quantity` keep the letters Carrie laid them out in. That
pushes the X to `F1` and widens row 2's merge to `A2:F2`, both of which are easy to
miss by hand - hence this test.
"""
import importlib.util
import pathlib

import pytest

PLUGIN = (pathlib.Path(__file__).resolve().parents[2]
          / "plugins" / "922_production_packets" / "run.py")


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("pp_layout_test", PLUGIN)
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def book(mod, tmp_path_factory):
    import openpyxl
    entries = [
        {"part": "R7212587-H11-4B", "order": "BL416619", "serial": "218002101",
         "desc": "5.0 X 5.0 X 0.50 NOM", "qty": 1, "length": 26.5,
         "review": False, "packet": "SAW.1", "org_pallet": "1",
         "pallet": "SAW", "mat_text": "HSS 5.0 X 5.0 X 0.50 NOM (SAW CUT)"},
        {"part": "R7212587-H14-4A", "order": "BL416616", "serial": "218002101",
         "desc": "5.0 X 5.0 X 0.50 NOM", "qty": 2, "length": None,
         "review": True, "packet": "SAW.1", "org_pallet": "1",
         "pallet": "SAW", "mat_text": "HSS 5.0 X 5.0 X 0.50 NOM (SAW CUT)"},
    ]
    dest = tmp_path_factory.mktemp("pp") / "900 Tubes (TechDeck).xlsx"
    mod._write_workbook(dest, "900", [("218002101", entries)],
                        lambda *_a: None)
    return openpyxl.load_workbook(dest)


def test_the_headers_and_their_order(book):
    ws = book["SAW.1"]
    assert [ws.cell(4, c).value for c in range(1, 7)] == [
        "Problem?", "Parts Id.", "Length", "Quantity", "Order", None]


def test_each_row_carries_its_own_order_number(book):
    ws = book["SAW.1"]
    assert [ws.cell(r, 5).value for r in (5, 6)] == ["BL416619", "BL416616"]
    # the rest of the row did not shift
    assert [ws.cell(5, c).value for c in (2, 3, 4)] == \
        ["R7212587-H11-4B", 26.5, 1]
    # a blank length still writes the quantity and the order beside it
    assert [ws.cell(6, c).value for c in (2, 3, 4, 5)] == \
        ["R7212587-H14-4A", None, 2, "BL416616"]


def test_e1_totals_length_times_quantity(book, mod):
    """Carrie, 2026-11-17: E1 shows the total length the sheet needs - every
    length times its quantity, added up. A live formula over the same 5:100
    rows the X watches, so a length she fills in by hand (a tube with no
    drawing leaves Length blank) rolls into the total the moment she types
    it."""
    ws = book["SAW.1"]
    assert ws["E1"].value == mod.TOTAL_FORMULA
    assert mod.TOTAL_FORMULA == "=SUMPRODUCT(C5:C100,D5:D100)"
    assert ws["E1"].number_format == "0.0"


def test_the_x_moved_to_f_and_still_watches_column_a(book, mod):
    ws = book["SAW.1"]
    assert ws["F1"].value == mod.X_FORMULA
    assert "A5:A100" in mod.X_FORMULA, "the arrow column is still A"
    assert ws["F1"].font.name == "Aharoni"
    # both flagged rows above put an arrow in A, so the X would fire
    assert ws["A6"].value == mod.ARROW


def test_the_merges_and_widths_span_the_new_column(book):
    ws = book["SAW.1"]
    merged = {str(m) for m in ws.merged_cells.ranges}
    assert merged == {"C1:D1", "A2:F2"}
    assert {k: v.width for k, v in ws.column_dimensions.items()} == {
        "A": 12.43, "B": 20.71, "C": 10.86, "D": 13.14, "E": 13.14,
        "F": 10.71}


def test_the_table_is_still_open_on_both_edges(book):
    """Carrie's table draws only its INNER lines - no outer left or right."""
    ws = book["SAW.1"]

    def sides(cell):
        return {k for k in ("left", "right")
                if getattr(cell.border, k) is not None
                and getattr(cell.border, k).style}

    assert sides(ws["A4"]) == {"right"}, "Problem? has no outer left line"
    assert sides(ws["E4"]) == {"left"}, "Order is the new outer right edge"
    assert sides(ws["A5"]) == {"right"}
    assert sides(ws["E5"]) == {"left"}
    for col in ("B", "C", "D"):
        assert sides(ws[f"{col}4"]) == {"left", "right"}
        assert sides(ws[f"{col}5"]) == {"left", "right"}


# ─────────────────────────────────────────────── the tabs are in order

def test_the_tabs_sort_saw_first_then_each_pallet_in_number_order(mod):
    """Carrie, 2026-11-18, batch 513: the tabs read SAW.1, SAW.2, 1.1, 1.4,
    1.5, 1.2, 1.6, 1.7, 1.3, 2.1, 3.1 - the tracker's row order. "instead,
    I WOULD LIKE this order, i'd like SAW.1 , SAW.2 , 1.1, 1.2, 1.3, 1.4,
    1.5, 1.6, 1.7, 2.1, 3.1"."""
    batch_513 = ["SAW.1", "SAW.2", "1.1", "1.4", "1.5", "1.2", "1.6", "1.7",
                 "1.3", "2.1", "3.1"]
    assert sorted(batch_513, key=mod._packet_sort_key) == [
        "SAW.1", "SAW.2", "1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7",
        "2.1", "3.1"]
    # double digits sort as numbers, and an UNKNOWN pallet's sheet lands last
    assert sorted(["1.10", "1.2", "SAW.10", "SAW.9", "UNKNOWN.1", "1.9"],
                  key=mod._packet_sort_key) == [
        "SAW.9", "SAW.10", "1.2", "1.9", "1.10", "UNKNOWN.1"]


def test_a_jumbled_tracker_no_longer_reorders_the_sheets(mod, tmp_path):
    """The Material Use Tracker's row order used to BE the sheet order,
    which is exactly what jumbled batch 513's tabs. It is a cross-check
    now; the packets keep their numbered order whatever the tracker says."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Pallet Organizer"
    ws["B3"] = "PALLET 1"
    ws["B5"] = "AA100"
    ws["B24"] = "MATERIAL REQUIRED: 3"
    for j, text in enumerate(["HSS 5.0 X 5.0 X 0.50 NOM (SAW CUT)",
                              "HSS 2.5 X 2.5 X 0.25 NOM",
                              "HSS 2.0 X 2.0 X 0.188 NOM"]):
        ws.cell(25 + j, 2, j + 1)
        ws.cell(25 + j, 3, text)
    info = wb.create_sheet("PO Info Drop")
    for c, head in enumerate(("ORDER", "DYPN", "SOURCE MATERIAL", "QTY",
                              "Base Material"), start=1):
        info.cell(1, c, head)
    for r, row in enumerate([
            ("AA100", "H900000-H1-4", "218002101", 1, "5.0 X 5.0 X 0.50 NOM"),
            ("AA100", "H900000-H2-4", "218003092", 1, "2.5 X 2.5 X 0.25 NOM"),
            ("AA100", "H900000-H3-4", "218019941", 1,
             "2.0 X 2.0 X 0.188 NOM")], start=2):
        for c, value in enumerate(row, start=1):
            info.cell(r, c, value)
    org = tmp_path / "PO H900 Pallet & Rod Organizer.xlsx"
    wb.save(org)

    # the tracker lists them BACKWARDS: 1.2's material, then SAW.1's, then 1.1's
    tr = Workbook()
    ts = tr.active
    assert ts is not None
    ts.title = "900"
    ts["A1"], ts["B1"] = "PALLET", "ITEM"
    for r, (pallet, item) in enumerate(
            [(1, 218019941), (1, 218002101), (1, 218003092)], start=2):
        ts.cell(r, 1, pallet)
        ts.cell(r, 2, item)
    planning = tmp_path / "2 - Planning"
    planning.mkdir()
    tr.save(planning / "EB 922 Material Use Tracker.xlsx")

    tubes, _sk, _all = mod._read_tubes(org, lambda *_a: None)
    pallet_map, orders = mod._read_pallets(org, lambda *_a: None)
    for t in tubes:
        t["length"], t["review"] = 10.0, False
        t["pallet"] = mod._pallet_of(t["serial"], t["desc"], pallet_map,
                                     orders, t["order"])
    materials = mod._group_materials(tubes, pallet_map, tmp_path, "900",
                                     lambda *_a: None)
    assert [e[1][0]["packet"] for e in materials] == ["SAW.1", "1.1", "1.2"]


# ──────────────────────────────────────────── no padding in the title cells

def test_tidy_strips_padding_and_collapses_runs(mod):
    """Carrie, 2026-10-30: "in cell A2 ... there's a bunch of spaces in the
    cell after the last word." Her own hand-built 505 sheet `2.5` really does
    hold `HSS 2.5 X 2.5 X 0.25 NOM ` with the trailing space."""
    assert mod._tidy("HSS 2.5 X 2.5 X 0.25 NOM ") == "HSS 2.5 X 2.5 X 0.25 NOM"
    assert mod._tidy("  HSS 2.0  X 2.0 X 0.188\xa0") == "HSS 2.0 X 2.0 X 0.188"
    assert mod._tidy("HSS 3.0 X 3.0\nNOM") == "HSS 3.0 X 3.0 NOM"
    assert mod._tidy(None) == ""
    assert mod._tidy(218019941) == "218019941"


def test_a_padded_organizer_wording_reaches_a2_clean(mod, tmp_path):
    import openpyxl
    entries = [{"part": "R7212587-H11-4B", "order": "BL416619",
                "serial": "218002101  ", "desc": "5.0 X 5.0 X 0.50 NOM",
                "qty": 1, "length": 26.5, "review": False, "packet": "SAW.1",
                "org_pallet": "1", "pallet": "SAW",
                "mat_text": "  HSS 5.0 X 5.0 X 0.50 NOM (SAW CUT)   "}]
    dest = tmp_path / "900 Tubes (TechDeck).xlsx"
    mod._write_workbook(dest, "900", [("218002101", entries)],
                        lambda *_a: None)
    ws = openpyxl.load_workbook(dest)["SAW.1"]
    assert ws["A2"].value == "HSS 5.0 X 5.0 X 0.50 NOM (SAW CUT)"
    assert ws["A1"].value == 218002101, "a padded serial is still a number"
