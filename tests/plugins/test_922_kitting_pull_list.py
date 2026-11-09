"""The material pull list - the kitting PDF's cover sheet (v1.5.0).

Written from Carrie's own outline ("How to make a pull list for EB batches",
2026-11-10). The COM fill and export are not tested here (they need Excel);
everything that decides WHAT lands on the form is pure and is.
"""
import importlib.util
import pathlib

import pytest

PDIR = (pathlib.Path(__file__).resolve().parents[2]
        / "plugins" / "922_kitting")


@pytest.fixture(scope="module")
def pl():
    spec = importlib.util.spec_from_file_location("pl_test",
                                                  PDIR / "pull_list.py")
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _material_qty(tmp_path, rows, header=("Source Material", "Sum of QTY")):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Material QTY"
    ws["A3"], ws["B3"] = header
    for i, (mid, qty) in enumerate(rows, start=4):
        ws.cell(i, 1, mid)
        ws.cell(i, 2, qty)
    dest = tmp_path / "organizer.xlsx"
    wb.save(dest)
    return dest


def test_the_qty_tab_is_read_in_order_and_grand_total_is_not_a_material(
        pl, tmp_path):
    path = _material_qty(tmp_path, [
        (211031592, 2), (218019941, 38), ("262028653-12", 54),
        ("Grand Total", 94), ("junk below the pivot", 1)])
    rows = pl.read_material_qty(path, lambda *_a: None)
    assert rows == [("211031592", 2), ("218019941", 38),
                    ("262028653-12", 54)]


def test_a_missing_qty_tab_is_none_not_a_crash(pl, tmp_path):
    from openpyxl import Workbook
    wb = Workbook()
    assert wb.active is not None
    wb.active.title = "PO Info Drop"
    dest = tmp_path / "organizer.xlsx"
    wb.save(dest)
    assert pl.read_material_qty(dest, lambda *_a: None) is None


def test_the_split_is_by_what_the_id_looks_like(pl):
    """A bare numeric serial is warehouse stock - the Tube Pull List, the OSS
    plate 211031592 included (that is where Carrie's own 511 copy puts it).
    Anything else is a mount-kit item - the Plate-Rod Pull List."""
    tubes, plates = pl.split_materials([
        ("218019941", 38), ("211031592", 2), ("262028653-12", 54),
        ("40-00-2020", 1)])
    assert tubes == [("218019941", 38), ("211031592", 2)]
    assert plates == [("262028653-12", 54), ("40-00-2020", 1)]


def test_plan_rows_formula_fallback_and_hand_fill(pl):
    """Known id -> the template's own VLOOKUP (desc None); unknown with the
    organizer's wording -> that text; unknown to BOTH -> the row still lands,
    with its quantity, and the id is named for a hand fill."""
    plan, overflow, hand = pl.plan_rows(
        [("A", 1), ("B", 2), ("C", 3)],
        known={"A"}, fallback={"B": "OSS 0.375 THK"}, slots=19)
    assert plan == [("A", 1, None), ("B", 2, "OSS 0.375 THK"), ("C", 3, "")]
    assert overflow == []
    assert hand == ["C"]


def test_a_material_that_does_not_fit_is_named_never_dropped_quietly(pl):
    plan, overflow, _hand = pl.plan_rows(
        [("A", 1), ("B", 2), ("C", 3)], known={"A", "B", "C"},
        fallback={}, slots=2)
    assert [m for m, _q, _d in plan] == ["A", "B"]
    assert overflow == ["C"]


def _template(tmp_path, dirty_id=False):
    """A mini QF-PR-10: both pull sheets with the real anchors at MADE-UP
    rows, so the test fails if anything is found by position instead of by
    text."""
    from openpyxl import Workbook
    wb = Workbook()
    tube = wb.active
    assert tube is not None
    tube.title = "Tube Pull List"
    tube["F4"] = "BATCH #:"
    tube["B11"] = "SOURCE MATERIAL "
    tube["D11"] = "QTY"
    tube["E11"] = "SIZE"
    tube["A30"] = "Section 2 - Warehouse Use"
    plate = wb.create_sheet("Plate-Rod Pull List")
    plate["F6"] = "BATCH #:"
    plate["A9"] = "MW ITEM #"
    plate["B9"] = "SOURCE MATERIAL "
    plate["D9"] = "DESCRIPTION "
    plate["H9"] = "QTY"
    plate["A26"] = "Section 2 - Warehouse Use"
    tl = wb.create_sheet("Tube Material List")
    tl["A1"] = "MW#"
    tl["A2"] = 218019941
    tl["A3"] = "218002642\t" if dirty_id else 218002642
    pr = wb.create_sheet("Plate-Rod Material List")
    pr["B1"] = "SOURCE MATERIAL "
    pr["B2"] = "262028653-37\t" if dirty_id else "262028653-37"
    pr["B3"] = "262028653-12"
    dest = tmp_path / "QF-PR-10 - Material Pull List - Electric Boat.xlsx"
    wb.save(dest)
    return dest


def test_the_template_anchors_are_found_by_text_not_position(pl, tmp_path):
    info = pl.read_template(_template(tmp_path), lambda *_a: None)
    a = info["Tube Pull List"]["anchors"]
    assert a["batch"] == "G4"
    assert (a["row0"], a["row1"]) == (12, 29)
    assert a["cols"]["SOURCE MATERIAL"] == "B"
    b = info["Plate-Rod Pull List"]["anchors"]
    assert b["batch"] == "G6"
    assert (b["row0"], b["row1"]) == (10, 25)
    assert b["cols"]["QTY"] == "H"


def test_a_whitespace_polluted_lookup_id_is_not_trusted(pl, tmp_path):
    """The real list holds '262028653-37' with a trailing TAB, so Excel's
    exact-match VLOOKUP misses it and prints #N/A - the wall Carrie's own
    filled copies hit. A polluted id must fall back to the organizer's
    wording instead of the formula."""
    clean = pl.read_template(_template(tmp_path), lambda *_a: None)
    dirty = pl.read_template(_template(tmp_path, dirty_id=True),
                             lambda *_a: None)
    assert "262028653-37" in clean["Plate-Rod Pull List"]["known"]
    assert "262028653-37" not in dirty["Plate-Rod Pull List"]["known"]
    assert "218002642" in clean["Tube Pull List"]["known"]
    assert "218002642" not in dirty["Tube Pull List"]["known"]


def test_desc_maps_read_the_batch_s_own_wording(pl, tmp_path):
    from openpyxl import Workbook
    wb = Workbook()
    info = wb.active
    assert info is not None
    info.title = "PO Info Drop"
    for c, head in enumerate(("ORDER", "DYPN", "SOURCE MATERIAL", "QTY",
                              "Base Material"), start=1):
        info.cell(1, c, head)
    info.append(("AA100", "H1-4", 218019941, 1, "2.0 X 2.0 X 0.188  NOM"))
    src = wb.create_sheet("Source Material Info")
    src["A1"], src["G1"] = "Material ", "SCRIBE DESCRIPTION "
    src["A2"], src["G2"] = "262028653-37", "OSS 0.375 THK\t\t\t"
    dest = tmp_path / "organizer.xlsx"
    wb.save(dest)
    tubes, plates = pl.desc_maps(dest, lambda *_a: None)
    assert tubes == {"218019941": "2.0 X 2.0 X 0.188 NOM"}
    assert plates == {"262028653-37": "OSS 0.375 THK"}


def test_the_mount_variant_template_is_never_matched(pl, tmp_path):
    folder = tmp_path / "Notes" / "Pull list"
    folder.mkdir(parents=True)
    (folder / "QF-PR-10 - Mount Material Pull List - Electric Boat.xlsx"
     ).write_bytes(b"x")
    assert pl.find_template(tmp_path) is None
    (folder / "QF-PR-10 - Material Pull List - Electric Boat.xlsx"
     ).write_bytes(b"x")
    assert pl.find_template(tmp_path).name == \
        "QF-PR-10 - Material Pull List - Electric Boat.xlsx"
