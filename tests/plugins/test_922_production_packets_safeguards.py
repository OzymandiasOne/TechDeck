"""Nothing slips through: the checks on unknown and new tube materials.

Added in v1.7.0 alongside dropping `_Everything Else.pdf`, which until then was
the only thing that accounted for every sheet in the batch (Anthony,
2026-10-30). Three holes were open and silent:

  * a tube serial on NEITHER `sdk` tube-material list - batch 495 carries
    `211002778`, one digit off the `218002778` that IS listed;
  * a material the Pallet Organizer does not list at all, filed from
    `sdk.tube_class` instead of from the paperwork;
  * a PO Info Drop row with a tube serial but no `Base Material` - that column
    is the only thing marking a row as a tube, so the part reached no sheet and
    no binder. Batch 503 has 61 of them.
"""
import importlib.util
import pathlib

import pytest

PLUGIN = (pathlib.Path(__file__).resolve().parents[2]
          / "plugins" / "922_production_packets" / "run.py")
PACKETS = PLUGIN.parent / "packets.py"

KNOWN_SAW = "218002101"        # 5.0 X 5.0 X 0.50, on OVERSIZED_TUBE_MATERIALS
KNOWN_LASER = "218019941"      # 2.0 X 2.0 X 0.188, on STANDARD
NEVER_SEEN = "211002778"       # batch 495's real one, on neither list


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("pp_safe_test", PLUGIN)
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _organizer(tmp_path, info_rows, materials=("HSS 2.0 X 2.0 X 0.188 NOM",)):
    """A stand-in organizer: a PO Info Drop plus one pallet's material list.

    `info_rows` are (order, dypn, source material, qty, base material) tuples -
    a blank base material is the case under test.
    """
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Pallet Organizer"
    ws["B3"] = "PALLET 1"
    ws["B5"] = "AA100"
    ws["B24"] = f"MATERIAL REQUIRED: {len(materials)}"
    for j, text in enumerate(materials):
        ws.cell(25 + j, 2, j + 1)
        ws.cell(25 + j, 3, text)

    info = wb.create_sheet("PO Info Drop")
    for c, head in enumerate(("ORDER", "DYPN", "SOURCE MATERIAL", "QTY",
                              "Base Material"), start=1):
        info.cell(1, c, head)
    for r, row in enumerate(info_rows, start=2):
        for c, value in enumerate(row, start=1):
            info.cell(r, c, value)
    dest = tmp_path / "PO H900 Pallet & Rod Organizer.xlsx"
    wb.save(dest)
    return dest


def test_a_tube_row_with_no_base_material_is_reported_not_dropped(mod,
                                                                  tmp_path):
    path = _organizer(tmp_path, [
        ("AA100", "H900000-H1-4", KNOWN_LASER, 1, "2.0 X 2.0 X 0.188 NOM"),
        ("AA100", "H900000-H2-4", KNOWN_LASER, 1, None),      # the hole
    ])
    tubes, skipped = mod._read_tubes(path, lambda *_a: None)
    assert [t["part"] for t in tubes] == ["H900000-H1-4"]
    assert [(e["part"], e["serial"]) for e in skipped] == \
        [("H900000-H2-4", KNOWN_LASER)]


def test_a_plate_row_with_no_base_material_is_not_reported(mod, tmp_path):
    """Plate and rod rows legitimately have no Base Material - stay quiet."""
    path = _organizer(tmp_path, [
        ("AA100", "H900000-H1-4", KNOWN_LASER, 1, "2.0 X 2.0 X 0.188 NOM"),
        ("AA100", "H900000-H1-2", "262028653-11", 1, None),   # a plate
        ("AA100", "H900000-H1-3", "211031592", 1, None),      # a rod
    ])
    tubes, skipped = mod._read_tubes(path, lambda *_a: None)
    assert len(tubes) == 1
    assert skipped == [], "a plate is not a dropped tube"


def test_a_serial_on_neither_sdk_list_is_flagged(mod, tmp_path):
    path = _organizer(
        tmp_path,
        [("AA100", "H900000-H1-4", NEVER_SEEN, 1, "6.0 X 8.0 X 0.50 NOM")],
        materials=("HSS 6.0 X 8.0 X 0.50 NOM",))
    tubes, _skipped = mod._read_tubes(path, lambda *_a: None)
    pallet_map, orders = mod._read_pallets(path, lambda *_a: None)
    for t in tubes:
        t["length"], t["review"] = 10.0, False
        t["pallet"] = mod._pallet_of(t["serial"], t["desc"], pallet_map,
                                     orders, t["order"])
    materials = mod._group_materials(tubes, pallet_map, None, "900",
                                     lambda *_a: None)
    entry = materials[0][1][0]
    assert entry["new_material"] is True
    # the organizer DID place it, so the cutting list is still right
    assert entry["off_organizer"] is False
    assert entry["pallet"] == "1"


def test_a_known_material_is_not_flagged(mod, tmp_path):
    path = _organizer(
        tmp_path,
        [("AA100", "H900000-H1-4", KNOWN_LASER, 1, "2.0 X 2.0 X 0.188 NOM")])
    tubes, _skipped = mod._read_tubes(path, lambda *_a: None)
    pallet_map, orders = mod._read_pallets(path, lambda *_a: None)
    for t in tubes:
        t["length"], t["review"] = 10.0, False
        t["pallet"] = mod._pallet_of(t["serial"], t["desc"], pallet_map,
                                     orders, t["order"])
    materials = mod._group_materials(tubes, pallet_map, None, "900",
                                     lambda *_a: None)
    entry = materials[0][1][0]
    assert entry["new_material"] is False
    assert entry["off_organizer"] is False


def test_a_material_the_organizer_does_not_list_is_flagged(mod, tmp_path):
    """The silent path: the organizer is quiet, sdk.tube_class files it SAW."""
    path = _organizer(
        tmp_path,
        [("AA100", "H900000-H1-4", KNOWN_SAW, 1, "5.0 X 5.0 X 0.50 NOM")],
        materials=("HSS 2.0 X 2.0 X 0.188 NOM",))   # a DIFFERENT material
    tubes, _skipped = mod._read_tubes(path, lambda *_a: None)
    pallet_map, orders = mod._read_pallets(path, lambda *_a: None)
    for t in tubes:
        t["length"], t["review"] = 10.0, False
        t["pallet"] = mod._pallet_of(t["serial"], t["desc"], pallet_map,
                                     orders, t["order"])
    materials = mod._group_materials(tubes, pallet_map, None, "900",
                                     lambda *_a: None)
    entry = materials[0][1][0]
    assert entry["pallet"] == "SAW", "tube_class is still the fallback"
    assert entry["off_organizer"] is True, "but it no longer happens quietly"
    assert entry["new_material"] is False


def test_the_everything_else_binder_is_gone():
    """It was 206 pages and 28MB on batch 506 and nobody opened it.

    Checked against the CODE only - the comment explaining why it went, and
    what replaced it, is meant to stay.
    """
    import ast
    tree = ast.parse(PACKETS.read_text(encoding="utf-8"))
    # every string the module actually evaluates, docstrings excluded
    docstrings = {ast.get_docstring(n) for n in ast.walk(tree)
                  if isinstance(n, (ast.Module, ast.FunctionDef,
                                    ast.AsyncFunctionDef, ast.ClassDef))}
    literals = {n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and n.value not in docstrings}
    assert "_Everything Else.pdf" not in literals
    assert "_Problem Drawings.pdf" in literals, "this one stays"
