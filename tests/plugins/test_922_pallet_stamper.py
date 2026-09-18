"""922 Pallet Stamper — stamp the WORK PACKET, never the drawing binder.

A 922 order folder holds the order's work packet and, once the Batch Repeater
has run, the drawing binder exported alongside it. Windows lists 'Binder1.pdf'
BEFORE 'BK394153 NOFORN.pdf', so the old "first PDF in the folder" rule put the
red Batch/Pallet stamp on the drawing the floor reads and left the packet blank
(reported by a user 2026-08-20; found on 6 binders in Batches 486 and 489).

The packet is now identified by READING page 1 — a drawing carries the
title-block boilerplate, a packet never does — and a stray stamp already sitting
on a drawing is taken back off.
"""

import importlib.util
from pathlib import Path

import fitz
import pytest

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"

_DRAWING_TEXT = ["DO NOT SCALE DRAWING", "UNLESS OTHERWISE SPECIFIED",
                 "ENG APPR.", "MFG APPR.", "SHEET 1 OF 1"]
_PACKET_TEXT = ["QA FRM 922", "Work Instruction Description:",
                "Order#:  BK394153", "Lead Trade:  922"]


@pytest.fixture(scope="module")
def ps():
    spec = importlib.util.spec_from_file_location(
        "ps_run", PLUGINS / "922_pallet_stamper" / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_pdf(path: Path, lines, stamp: str = "") -> None:
    doc = fitz.open()
    page = doc.new_page(width=792, height=612)
    y = 72
    for line in lines:
        page.insert_text(fitz.Point(72, y), line, fontsize=10)
        y += 16
    if stamp:
        page.insert_text(fitz.Point(300, 400), stamp, fontsize=18,
                         fontname="helv", fill=(1, 0, 0))
    doc.save(str(path))
    doc.close()


def _stamp_count(path: Path) -> int:
    doc = fitz.open(str(path))
    try:
        return len(ps_module._find_all_stamp_rects(doc[0]))
    finally:
        doc.close()


ps_module = None


@pytest.fixture(autouse=True)
def _bind(ps):
    global ps_module
    ps_module = ps


def _order(tmp_path: Path) -> Path:
    order = tmp_path / "BK394153-R7924463-H9"
    order.mkdir()
    return order


# ── the reported bug ─────────────────────────────────────────────────────────

def test_the_binder_is_not_the_work_packet(ps, tmp_path):
    order = _order(tmp_path)
    _make_pdf(order / "Binder1.pdf", _DRAWING_TEXT)
    _make_pdf(order / "BK394153 NOFORN.pdf", _PACKET_TEXT)

    import techdeck.core.plugin_sdk as sdk
    assert sdk.find_work_packet(order).name == "BK394153 NOFORN.pdf"


def test_the_packet_gets_the_stamp_and_the_binder_stays_clean(ps, tmp_path):
    order = _order(tmp_path)
    binder = order / "Binder1.pdf"
    packet = order / "BK394153 NOFORN.pdf"
    _make_pdf(binder, _DRAWING_TEXT)
    _make_pdf(packet, _PACKET_TEXT)

    import techdeck.core.plugin_sdk as sdk
    found = sdk.find_work_packet(order)
    assert ps.stamp_single(str(found), "490", "3", 18, 4.0, 7.0, print) is True

    assert _stamp_count(packet) == 1
    assert _stamp_count(binder) == 0


# ── healing what the old behaviour already did ───────────────────────────────

def test_a_stray_stamp_is_taken_back_off_the_binder(ps, tmp_path):
    order = _order(tmp_path)
    binder = order / "Binder1.pdf"
    packet = order / "BK394153 NOFORN.pdf"
    _make_pdf(binder, _DRAWING_TEXT, stamp="Batch 489 Pallet 2")
    _make_pdf(packet, _PACKET_TEXT)
    assert _stamp_count(binder) == 1        # what a pre-fix run left behind

    removed = ps.unstamp_drawings(order, packet, print)

    assert removed == 1
    assert _stamp_count(binder) == 0
    assert _stamp_count(packet) == 0        # cleanup never stamps anything


def test_cleanup_leaves_a_clean_binder_alone(ps, tmp_path):
    order = _order(tmp_path)
    binder = order / "Binder1.pdf"
    packet = order / "BK394153 NOFORN.pdf"
    _make_pdf(binder, _DRAWING_TEXT)
    _make_pdf(packet, _PACKET_TEXT)
    before = binder.read_bytes()

    assert ps.unstamp_drawings(order, packet, print) == 0
    assert binder.read_bytes() == before    # never rewritten with nothing to do


def test_cleanup_never_touches_the_work_packets_own_stamp(ps, tmp_path):
    """The packet is the one file that is SUPPOSED to carry the stamp."""
    order = _order(tmp_path)
    packet = order / "BK394153 NOFORN.pdf"
    _make_pdf(packet, _PACKET_TEXT, stamp="Batch 489 Pallet 2")

    import techdeck.core.plugin_sdk as sdk
    found = sdk.find_work_packet(order)
    assert ps.unstamp_drawings(order, found, print) == 0
    assert _stamp_count(packet) == 1


def test_cleanup_runs_even_when_the_folder_has_no_packet(ps, tmp_path):
    """A drawing-only folder can still be carrying a stray stamp."""
    order = _order(tmp_path)
    binder = order / "Binder1.pdf"
    _make_pdf(binder, _DRAWING_TEXT, stamp="Batch 489 Pallet 2")

    assert ps.unstamp_drawings(order, None, print) == 1
    assert _stamp_count(binder) == 0
