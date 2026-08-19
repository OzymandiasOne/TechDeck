"""922 Difficulty Stamper — the label match and the two-way stamp.

The label DriveWorks prints on a compound-cut part drawing is the bare word
DIFFICULT. The trap this test exists to pin down: a part NUMBER can contain the
same letters — the sample drawings that first exercised this app were literally
named 'CLEVISDIFFICULTY-4' and 'TUBEDIFFICULTY-4' — so a substring match flags
every part of any job whose name happens to contain it. The match is on the
WHOLE text span and must stay that way.

The stamp itself has to be idempotent in BOTH directions: re-running must not
print a second stamp, and an order whose parts are no longer difficult must have
its old stamp taken back off, so a packet self-corrects after a part is revised.
"""

import importlib.util
from pathlib import Path

import fitz
import pytest

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"


@pytest.fixture(scope="module")
def ds():
    spec = importlib.util.spec_from_file_location(
        "ds_run", PLUGINS / "922_difficulty_stamper" / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- the label match ---------------------------------------------------------

@pytest.mark.parametrize("text", [
    "DIFFICULT",
    " DIFFICULT ",
    "difficult",
    "Difficult",
])
def test_label_span_is_recognised(ds, text):
    assert ds._is_label_span(text)


@pytest.mark.parametrize("text", [
    "CLEVISDIFFICULTY",      # a real sample part number
    "TUBEDIFFICULTY-4",      # ditto
    "DIFFICULTY",            # the layer's name, not the label
    "DIFFICULT PARTS",
    "NOT DIFFICULT",
    "",
])
def test_part_numbers_are_not_the_label(ds, text):
    assert not ds._is_label_span(text)


# --- temp/lock files are never mistaken for real PDFs ------------------------

@pytest.mark.parametrize("name,is_real", [
    ("BK573366.pdf", True),
    ("BL344491 NOFORN.pdf", True),
    ("tmpab12cd34.pdf", False),      # python tempfile leftover
    ("~$BK573366.pdf", False),       # office lock file
])
def test_temp_files_are_not_real_pdfs(ds, name, is_real):
    assert ds._is_real_pdf(Path(name)) is is_real


def test_work_packet_prefers_the_order_numbered_pdf(ds, tmp_path):
    order = tmp_path / "BK573366-R8651569-H2"
    order.mkdir()
    (order / "AAA other.pdf").write_bytes(b"%PDF-1.4\n")
    (order / "BK573366.pdf").write_bytes(b"%PDF-1.4\n")
    # A stray temp PDF sorts first alphabetically but must never win.
    (order / "tmpzz99aa11.pdf").write_bytes(b"%PDF-1.4\n")

    assert ds.find_work_packet(order).name == "BK573366.pdf"


# --- the stamp, both directions ----------------------------------------------

def _make_pdf(path: Path) -> None:
    doc = fitz.open()
    doc.new_page(width=792, height=612)
    doc.save(str(path))
    doc.close()


def _stamp_count(path: Path) -> int:
    doc = fitz.open(str(path))
    try:
        return sum(
            1
            for block in doc[0].get_text("dict")["blocks"]
            for line in block.get("lines", [])
            for span in line["spans"]
            if span["text"].strip().upper() == "DIFFICULT"
        )
    finally:
        doc.close()


def test_stamp_is_applied_then_idempotent_then_removed(ds, tmp_path):
    packet = tmp_path / "BK573366.pdf"
    _make_pdf(packet)
    log = lambda *_: None

    assert ds.apply_stamp(packet, True, 18, 4.0, 6.5, log) == "stamped"
    assert _stamp_count(packet) == 1

    # Re-running must not print a second stamp next to the first.
    assert ds.apply_stamp(packet, True, 18, 4.0, 6.5, log) == "stamped"
    assert _stamp_count(packet) == 1

    # The part was fixed - the packet must stop claiming it is difficult.
    assert ds.apply_stamp(packet, False, 18, 4.0, 6.5, log) == "removed"
    assert _stamp_count(packet) == 0

    # Nothing to do and nothing to remove -> the file is not rewritten at all.
    before = packet.stat().st_mtime_ns
    assert ds.apply_stamp(packet, False, 18, 4.0, 6.5, log) == "unchanged"
    assert packet.stat().st_mtime_ns == before


# --- stripping the label off the drawing -------------------------------------

def _make_drawing(path: Path, with_label: bool = True) -> None:
    """A part drawing; the DriveWorks label is blue, unlike our red stamp."""
    doc = fitz.open()
    page = doc.new_page(width=792, height=612)
    if with_label:
        page.insert_text(fitz.Point(400, 300), "DIFFICULT",
                         fontsize=18, fontname="helv", fill=(0, 0, 1))
    doc.save(str(path))
    doc.close()


def test_strip_label_round_trip(ds, tmp_path):
    drawing = tmp_path / "262028652-175 BAR F.pdf"
    _make_drawing(drawing)
    log = lambda *_: None

    assert ds.inspect_drawing(drawing, log) == (True, False)
    assert ds.strip_label(drawing, log) == 1

    # The label is gone from the page...
    assert _stamp_count(drawing) == 0
    # ...but the drawing still reads as difficult, via the metadata marker -
    # without it a re-run would see a clean drawing and un-stamp the packet.
    assert ds.inspect_drawing(drawing, log) == (False, True)

    # Stripping an already-stripped drawing never rewrites the file.
    before = drawing.stat().st_mtime_ns
    assert ds.strip_label(drawing, log) == 0
    assert drawing.stat().st_mtime_ns == before


def test_fresh_clean_drawing_reads_clean(ds, tmp_path):
    # A regenerated drawing is a brand-new file: no label, no marker - so a
    # part revised to be non-difficult really does read as clean.
    drawing = tmp_path / "262028652-175 BAR.pdf"
    _make_drawing(drawing, with_label=False)
    assert ds.inspect_drawing(drawing, lambda *_: None) == (False, False)


def test_failed_write_leaves_no_stray_temp_pdf(ds, tmp_path, monkeypatch):
    """A stray tmp*.pdf in an order folder would be read as the work packet."""
    packet = tmp_path / "BK573366.pdf"
    _make_pdf(packet)

    import techdeck.core.plugin_sdk as sdk

    def boom(*_a, **_kw):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(sdk.os, "replace", boom)
    assert ds.apply_stamp(packet, True, 18, 4.0, 6.5, lambda *_: None) is None
    assert list(tmp_path.glob("tmp*.pdf")) == []
