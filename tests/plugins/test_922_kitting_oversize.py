"""922 Kitting — orders that outgrow the 10-row Component Checklist.

The 'Bin Label & Checklist' sheet only has rows 22-31 for parts, so an order
with more than ten silently printed the first ten and dropped the rest (Batch
490: FK328102 has 11). Those orders are re-printed off the hidden 'Larger Bin
Label' sheet (rows 22-36) and that page is SUBSTITUTED into the kitting PDF, so
the order keeps its place in the print order and prints all of its parts.

Excel COM is not available in CI, so the sheets are stubbed down to the one
call each helper makes: Range(addr).Value.
"""

import importlib.util
from pathlib import Path

import fitz
import pytest

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"


@pytest.fixture(scope="module")
def kit():
    spec = importlib.util.spec_from_file_location(
        "kit_run", PLUGINS / "922_kitting" / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- COM stubs ---------------------------------------------------------------

class _Range:
    def __init__(self, value):
        self.Value = value


class _Sheet:
    """Answers Range(addr).Value from a dict; anything else raises, the same
    way a real missing range would."""

    def __init__(self, ranges):
        self._ranges = ranges

    def Range(self, addr):
        if addr not in self._ranges:
            raise RuntimeError(f"no range {addr}")
        return _Range(self._ranges[addr])


class _Workbook:
    def __init__(self, sheets):
        self._sheets = sheets

    def Worksheets(self, name):
        if name not in self._sheets:
            raise RuntimeError(f"no sheet {name}")
        return self._sheets[name]


def _col(values):
    """A COM range value: a tuple of per-row tuples."""
    return tuple(tuple(row) if isinstance(row, (list, tuple)) else (row,)
                 for row in values)


def _index_sheet(orders, heading_row=44):
    """A kit sheet whose order index table sits under 'Order Numbers on PO'."""
    col_c: list = [None] * 120
    col_c[heading_row - 1] = "Order Numbers on PO"
    for i, order in enumerate(orders, start=1):
        if heading_row + i - 1 < len(col_c):
            col_c[heading_row + i - 1] = order
    table = [(i, order) for i, order in enumerate(orders, start=1)]
    table += [(None, None)] * (200 - len(table))
    return _Sheet({
        "C1:C120": _col(col_c),
        f"B{heading_row + 1}:C{heading_row + 200}": _col(table),
    })


def _po_info_sheet(kit, order_rows):
    padded = list(order_rows) + [None] * (905 - len(order_rows))
    return _Sheet({kit.PO_INFO_ORDER_RANGE: _col(padded)})


# --- part counts / index map -------------------------------------------------

def test_part_counts_by_order(kit):
    wb = _Workbook({kit.PO_INFO_SHEET: _po_info_sheet(
        kit, ["BM331336", "BM331336", "FK328102", "FK328102", None, ""])})
    counts = kit._part_counts_by_order(wb, lambda *a: None)
    assert counts == {"bm331336": 2, "fk328102": 2}


def test_part_counts_missing_sheet_is_empty(kit):
    counts = kit._part_counts_by_order(_Workbook({}), lambda *a: None)
    assert counts == {}


def test_order_index_map_finds_the_heading(kit):
    ws = _index_sheet(["BM331336", "FK328102", "FJ360715"])
    assert kit._order_index_map(ws, lambda *a: None) == {
        1: "BM331336", 2: "FK328102", 3: "FJ360715"}


def test_order_index_map_tolerates_a_different_heading_row(kit):
    # The larger sheet's own table starts four rows lower than the standard
    # sheet's - the heading is scanned for, never hardcoded.
    ws = _index_sheet(["BM331336", "FK328102"], heading_row=48)
    assert kit._order_index_map(ws, lambda *a: None) == {
        1: "BM331336", 2: "FK328102"}


def test_order_index_map_without_the_heading_is_empty(kit):
    ws = _Sheet({"C1:C120": _col([None] * 120)})
    assert kit._order_index_map(ws, lambda *a: None) == {}


# --- oversize detection ------------------------------------------------------

def test_finds_only_the_order_that_overflows(kit):
    orders = ["BM331336", "FK328102", "FJ360715"]
    rows = ["BM331336"] * 2 + ["FK328102"] * 11 + ["FJ360715"] * 10
    wb = _Workbook({kit.PO_INFO_SHEET: _po_info_sheet(kit, rows)})
    ws = _index_sheet(orders)
    # Exactly at capacity is fine; one over is not.
    assert kit._find_oversize_orders(wb, ws, lambda *a: None) == {
        2: ("FK328102", 11)}


def test_no_oversize_orders(kit):
    wb = _Workbook({kit.PO_INFO_SHEET: _po_info_sheet(kit, ["A"] * 10)})
    ws = _index_sheet(["A"])
    assert kit._find_oversize_orders(wb, ws, lambda *a: None) == {}


def test_capacities_match_the_sheets(kit):
    assert kit.STANDARD_CAPACITY == 10
    assert kit.LARGER_CAPACITY == 15


# --- merge substitution ------------------------------------------------------

def _pdf(path: Path, labels: list[str]) -> Path:
    doc = fitz.open()
    for label in labels:
        page = doc.new_page()
        page.insert_text((72, 72), label)
    doc.save(str(path))
    doc.close()
    return path


def _page_labels(path: Path) -> list[str]:
    doc = fitz.open(str(path))
    try:
        return [p.get_text("text").strip() for p in doc]
    finally:
        doc.close()


def test_merge_substitutes_the_larger_page(kit, tmp_path):
    iterations = [1, 3, 5]
    pdfs = [_pdf(tmp_path / f"p{i}.pdf", [f"order{n}", f"order{n + 1}"])
            for i, n in enumerate(iterations)]
    big = _pdf(tmp_path / "big02.pdf", ["BIG order2"])
    dest = tmp_path / "Kitting.pdf"

    kit._merge_kit_pages(pdfs, iterations, {2: big}, dest, lambda *a: None)

    # Order 2's page is replaced in place - every other order is untouched and
    # the page count is unchanged.
    assert _page_labels(dest) == [
        "order1", "BIG order2", "order3", "order4", "order5", "order6"]


def test_merge_without_any_oversize_order_is_a_plain_merge(kit, tmp_path):
    iterations = [1, 3]
    pdfs = [_pdf(tmp_path / f"p{i}.pdf", [f"order{n}", f"order{n + 1}"])
            for i, n in enumerate(iterations)]
    dest = tmp_path / "Kitting.pdf"
    kit._merge_kit_pages(pdfs, iterations, {}, dest, lambda *a: None)
    assert _page_labels(dest) == ["order1", "order2", "order3", "order4"]


def test_merge_substitutes_two_orders_on_the_same_page_pair(kit, tmp_path):
    iterations = [1]
    pdfs = [_pdf(tmp_path / "p0.pdf", ["order1", "order2"])]
    bigs = {1: _pdf(tmp_path / "b1.pdf", ["BIG order1"]),
            2: _pdf(tmp_path / "b2.pdf", ["BIG order2"])}
    dest = tmp_path / "Kitting.pdf"
    kit._merge_kit_pages(pdfs, iterations, bigs, dest, lambda *a: None)
    assert _page_labels(dest) == ["BIG order1", "BIG order2"]


def test_merge_warns_when_an_iteration_is_short_a_page(kit, tmp_path):
    iterations = [1]
    pdfs = [_pdf(tmp_path / "p0.pdf", ["order1"])]  # only one page exported
    dest = tmp_path / "Kitting.pdf"
    messages: list[str] = []
    kit._merge_kit_pages(pdfs, iterations, {}, dest, messages.append)
    assert _page_labels(dest) == ["order1"]
    assert any("no page to merge" in m for m in messages)
