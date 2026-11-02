"""Every material binder is built the same way, laser or saw.

Carrie, 2026-10-30: "IT'S CURRENTLY NOT PULLING THE ASSEMBLY DRAWINGS INTO THE
MATERIAL BINDERS FOR PALLETS 1-3 (IT IS WORKING CORRECTLY FOR SAW TUBES). CAN
YOU PLEASE HAVE IT BIND THE TUBE LASER TUBES THE SAME AS IT DOES THE SAW
TUBES?"

Until v1.10.0 the assembly sheet and the order stamp were gated on the pallet
being SAW, because the hand-built packets we matched page for page were all saw
ones. A laser binder was therefore tube sheets only.
"""
import importlib.util
import pathlib

import fitz
import pytest

PDIR = (pathlib.Path(__file__).resolve().parents[2]
        / "plugins" / "922_production_packets")

ASM = "H900000-H1"
TUBES = (f"{ASM}-4", f"{ASM}-6")


@pytest.fixture(scope="module")
def pk():
    spec = importlib.util.spec_from_file_location("pk_binders",
                                                  PDIR / "packets.py")
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _sheet(dest, *names):
    """A one-page PDF whose text names the given parts."""
    doc = fitz.open()
    page = doc.new_page()
    for i, name in enumerate(names):
        page.insert_text((72, 100 + 20 * i), name, fontsize=11)
    doc.save(str(dest))
    doc.close()
    return dest


@pytest.fixture
def batch(tmp_path):
    """One assembly sheet plus one sheet per tube, and the survey rows."""
    asm = _sheet(tmp_path / "asm.pdf", *TUBES)
    drawings = [(asm, 0, "assembly", list(TUBES))]
    for part in TUBES:
        drawings.append((_sheet(tmp_path / f"{part}.pdf", part), 0,
                         "tube", [part]))
    return drawings


def _materials(pallet, packet):
    entries = [{"part": part, "order": "AA100", "serial": "218019941",
                "desc": "2.0 X 2.0 X 0.188 NOM", "qty": 1, "length": 10.0,
                "review": False, "pallet": pallet, "packet": packet}
               for part in TUBES]
    return [("218019941", entries)]


def _text(path):
    doc = fitz.open(str(path))
    try:
        return "\n".join(doc[i].get_text() for i in range(doc.page_count))
    finally:
        doc.close()


@pytest.mark.parametrize("pallet,packet", [("1", "1.1"), ("SAW", "SAW.1")])
def test_a_binder_carries_the_assembly_sheet_and_the_order_stamp(
        pk, tmp_path, batch, pallet, packet):
    out = tmp_path / "out"
    written, no_sheet = pk.build(out, "900", _materials(pallet, packet),
                                 batch, lambda *_a: None)
    assert no_sheet == []
    assert [p.name for p, _n in written] == \
        [f"{packet}_2.0 SQ X 0.188.pdf"]
    dest, pages = written[0]
    # the assembly sheet once, then each tube's own sheet
    assert pages == 3, "assembly + 2 tubes"
    body = _text(dest)
    assert body.count("ORDER: AA100") == 3, "every page is stamped"
    for part in TUBES:
        assert part in body


def test_the_assembly_sheet_is_bound_once_per_binder(pk, tmp_path, batch):
    """Both tubes share one assembly, and it must not be bound twice."""
    out = tmp_path / "out"
    written, _no_sheet = pk.build(out, "900", _materials("2", "2.1"),
                                  batch, lambda *_a: None)
    doc = fitz.open(str(written[0][0]))
    try:
        # page 1 names both tubes (the assembly), pages 2-3 name one each
        naming_both = sum(all(p in doc[i].get_text() for p in TUBES)
                          for i in range(doc.page_count))
    finally:
        doc.close()
    assert naming_both == 1


# ───────────────────────────────────────────── where the order stamp lands

def _page_with_ink(doc, ink_rect):
    page = doc.new_page(width=612, height=792)
    page.draw_rect(fitz.Rect(4, 4, 608, 788))      # the sheet's own border
    page.draw_rect(ink_rect, fill=(0.3, 0.3, 0.3))
    return page


def test_the_stamp_moves_off_the_drawing(pk):
    """Laser sheets put their detail view where the saw sheets leave paper, so
    the fixed hand-stamp spot printed `ORDER:` across the Detail A geometry
    (batch 508, `1.1` page 1). v1.10.0 looks for blank paper instead."""
    doc = fitz.open()
    default = (612 * pk.STAMP_SPOTS[0][0], 792 * pk.STAMP_SPOTS[0][1])

    # a clear sheet keeps the hand position, so saw packets do not move
    clear = _page_with_ink(doc, fitz.Rect(60, 400, 300, 600))
    assert pk._stamp_spot(clear, clear.get_text("words"), "X1") == default

    # ink ON the hand position pushes the stamp to another blank spot
    busy = _page_with_ink(doc, fitz.Rect(330, 110, 580, 260))
    spot = pk._stamp_spot(busy, busy.get_text("words"), "X1")
    assert spot != default
    assert fitz.Rect(spot[0] - 2, spot[1] - pk.STAMP_SIZE - 2,
                     spot[0] + 60, spot[1] + 4).x1 <= 612
    doc.close()


def test_the_border_rect_alone_does_not_push_the_stamp(pk):
    """The regression this replaced: every sheet is drawn inside a border whose
    bounding box covers the page, so a bbox test called all seven spots taken
    and the stamp never moved at all."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.draw_rect(fitz.Rect(4, 4, 608, 788))
    assert pk._stamp_spot(page, page.get_text("words"), "X1") == \
        (612 * pk.STAMP_SPOTS[0][0], 792 * pk.STAMP_SPOTS[0][1])
    doc.close()
