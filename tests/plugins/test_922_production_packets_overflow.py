"""A source material that spills onto the next pallet gets a sheet per pallet.

The Pallet Organizer lists a material under EVERY pallet that needs it, so a
size whose parts fill pallet 1 and run onto 2 and 3 appears three times. v1.0 -
v1.4 kept only the first listing and dropped the rest, which filed every tube
of that material under one pallet, named one packet, and under-reported the
pallet count (batch 506 said "2 pallets" with three on the sheet).

Fixed in v1.5.0: one sheet and one binder per (material, pallet), with a tube's
own ORDER deciding which pallet it belongs to.
"""
import importlib.util
import pathlib

import pytest

PLUGIN = (pathlib.Path(__file__).resolve().parents[2]
          / "plugins" / "922_production_packets" / "run.py")


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("pp_run_test", PLUGIN)
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _organizer(tmp_path, blocks, orders):
    """A stand-in Pallet Organizer sheet, laid out like the real one.

    `blocks` is {pallet: [material text, ...]}, `orders` is {pallet: [order]}.
    Each pallet is a column group: the PALLET title, then its order rows, then
    MATERIAL REQUIRED and the numbered materials.
    """
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Pallet Organizer"
    ws["B2"] = "BATCH 900"
    for i, pallet in enumerate(sorted(blocks)):
        col = 2 + i * 3                       # B, E, H - as the real sheet
        ws.cell(3, col, f"PALLET {pallet}")
        for j, order in enumerate(orders.get(pallet, [])):
            ws.cell(5 + j, col - 1, int(pallet))
            ws.cell(5 + j, col, order)
        ws.cell(24, col, f"MATERIAL REQUIRED: {len(blocks[pallet])}")
        for j, text in enumerate(blocks[pallet]):
            ws.cell(25 + j, col, j + 1)
            ws.cell(25 + j, col + 1, text)
    dest = tmp_path / "PO H900 Pallet & Rod Organizer.xlsx"
    wb.save(dest)
    return dest


SPLIT = "HSS 2.0 X 2.0 X 0.188 NOM"
BLOCKS = {
    "1": ["HSS 5.0 X 5.0 X 0.50 NOM (SAW CUT)",
          "HSS 3.5 X 3.5 X 0.25 NOM",
          SPLIT],
    "2": ["HSS 2.5 X 2.5 X 0.188 NOM", SPLIT],
    "3": [SPLIT],
}
ORDERS = {"1": ["AA100", "AA101"], "2": ["BB200"], "3": ["CC300"]}


def test_every_pallet_listing_is_kept(mod, tmp_path):
    path = _organizer(tmp_path, BLOCKS, ORDERS)
    pallet_map, order_pallets = mod._read_pallets(path, lambda *_a: None)

    key = mod._norm_material(SPLIT)
    assert [e["pallet"] for e in pallet_map[key]] == ["1", "2", "3"]
    # the materials listed on one pallet only are untouched
    assert len(pallet_map[mod._norm_material("HSS 3.5 X 3.5 X 0.25 NOM")]) == 1
    # every order is filed under exactly one pallet
    assert order_pallets == {"AA100": "1", "AA101": "1",
                             "BB200": "2", "CC300": "3"}


def test_the_same_material_twice_on_one_pallet_is_one_entry(mod, tmp_path):
    blocks = dict(BLOCKS, **{"1": BLOCKS["1"] + [SPLIT]})
    path = _organizer(tmp_path, blocks, ORDERS)
    pallet_map, _orders = mod._read_pallets(path, lambda *_a: None)
    assert [e["pallet"] for e in pallet_map[mod._norm_material(SPLIT)]] == \
        ["1", "2", "3"]


def test_a_packet_name_per_pallet(mod, tmp_path):
    path = _organizer(tmp_path, BLOCKS, ORDERS)
    pallet_map, _orders = mod._read_pallets(path, lambda *_a: None)
    names = mod._packet_names(pallet_map)

    key = mod._norm_material(SPLIT)
    assert names[(key, "1")] == "1.2"      # the saw material is not numbered 1.x
    assert names[(key, "2")] == "2.2"
    assert names[(key, "3")] == "3.1"
    saw = mod._norm_material("HSS 5.0 X 5.0 X 0.50 NOM (SAW CUT)")
    assert names[(saw, "SAW")] == "SAW.1"


def test_a_saw_material_is_never_split(mod, tmp_path):
    saw_text = "HSS 5.0 X 5.0 X 0.50 NOM (SAW CUT)"
    blocks = {"1": [saw_text], "2": [saw_text]}
    path = _organizer(tmp_path, blocks, {"1": ["AA100"], "2": ["BB200"]})
    pallet_map, orders = mod._read_pallets(path, lambda *_a: None)
    names = mod._packet_names(pallet_map)

    key = mod._norm_material(saw_text)
    assert list(names) == [(key, "SAW")], "one SAW group, not one per pallet"
    for order in ("AA100", "BB200"):
        assert mod._pallet_of("218002101", "5.0 X 5.0 X 0.50 NOM",
                              pallet_map, orders, order) == "SAW"


def test_a_tubes_order_picks_its_pallet(mod, tmp_path):
    path = _organizer(tmp_path, BLOCKS, ORDERS)
    pallet_map, orders = mod._read_pallets(path, lambda *_a: None)

    desc = "2.0 X 2.0 X 0.188 NOM"
    assert mod._pallet_of("218019941", desc, pallet_map, orders, "AA101") == "1"
    assert mod._pallet_of("218019941", desc, pallet_map, orders, "BB200") == "2"
    assert mod._pallet_of("218019941", desc, pallet_map, orders, "CC300") == "3"
    # an order nobody lists falls back to the material's first pallet rather
    # than inventing one
    assert mod._pallet_of("218019941", desc, pallet_map, orders, "ZZ999") == "1"
    # a material on ONE pallet ignores the order entirely - the organizer's
    # explicit listing wins, which keeps the 8 non-overflow batches unchanged
    assert mod._pallet_of("218002867", "3.5 X 3.5 X 0.25 NOM",
                          pallet_map, orders, "CC300") == "1"


def test_tubes_are_split_into_a_sheet_per_pallet(mod, tmp_path):
    path = _organizer(tmp_path, BLOCKS, ORDERS)
    pallet_map, orders = mod._read_pallets(path, lambda *_a: None)

    tubes = []
    for order, n in (("AA101", 1), ("BB200", 9), ("CC300", 21)):
        for i in range(n):
            tubes.append({"part": f"H900000-{order}-{i}", "order": order,
                          "serial": "218019941",
                          "desc": "2.0 X 2.0 X 0.188 NOM", "qty": 1,
                          "length": 10.0 + i, "review": False})
    for t in tubes:
        t["pallet"] = mod._pallet_of(t["serial"], t["desc"], pallet_map,
                                     orders, t["order"])

    # root_922=None -> no tracker, so this exercises the grouping alone
    materials = mod._group_materials(tubes, pallet_map, None, "900",
                                     lambda *_a: None)
    got = {e[0]["packet"]: (e[0]["org_pallet"], len(e))
           for _serial, e in materials}
    assert got == {"1.2": ("1", 1), "2.2": ("2", 9), "3.1": ("3", 21)}
    # one serial, three sheets - and every sheet says so at the top
    assert {s for s, _e in materials} == {"218019941"}
    for _serial, entries in materials:
        assert entries[0]["mat_text"] == SPLIT
