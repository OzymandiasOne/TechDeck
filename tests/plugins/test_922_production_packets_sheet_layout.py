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


def test_the_x_moved_to_f_and_still_watches_column_a(book, mod):
    ws = book["SAW.1"]
    assert ws["E1"].value is None, "E1 is part of the header band, not the X"
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
