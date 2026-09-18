"""Regression tests for which folder 911 Inspection Dimensions agrees to read.

Discovery used to scan one level down and, if that found nothing, sweep up every
loose PDF in the picked folder. Pointed at the 911 QTDR ROOT that last branch
fired -- the order folders one level down hold no packet of their own, so the
stray QC PDFs sitting beside them became jobs and the run started across the
whole program (reported 2026-09-01).

The shape is now decided structurally, and the root is refused outright:

    911 QTDR\\           <- "too_high", never accepted
      3X009\\            <- "order", the user ticks which nests to read
        5CDAQN\\         <- "nest", read straight off with no dialog
          5CDAQN MOVE TICKET OMIT.pdf
          911 BATCH 3X009 5CDAQN.xlsx
"""

import importlib.util
from pathlib import Path

import pytest

PLUGIN = (Path(__file__).resolve().parents[2]
          / "plugins" / "911_inspection_dimensions" / "run.py")


@pytest.fixture(scope="module")
def rt():
    spec = importlib.util.spec_from_file_location("rt_911_inspection", PLUGIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _nest(parent: Path, name: str, workbook: bool = True) -> Path:
    nest = parent / name
    nest.mkdir(parents=True)
    (nest / f"{name} MOVE TICKET OMIT.pdf").write_bytes(b"%PDF-1.4\n")
    if workbook:
        (nest / f"911 BATCH {parent.name} {name}.xlsx").write_bytes(b"PK\x03\x04")
    return nest


@pytest.fixture
def qtdr(tmp_path):
    """A miniature 911 QTDR tree, shaped like the real one."""
    root = tmp_path / "911 QTDR"
    order = root / "3X009"
    _nest(order, "5CDAQN")
    _nest(order, "5CDAQO")
    _nest(order, "5CDAQP", workbook=False)
    # the stray QC PDFs that used to be swept up as jobs
    root.mkdir(exist_ok=True)
    (root / "9FANIW QC FINAL.pdf").write_bytes(b"%PDF-1.4\n")
    (root / "9FANHE COC CORRECTED.pdf").write_bytes(b"%PDF-1.4\n")
    # order folders carry loose PDFs of their own too
    (order / "CUI -NNPI- READ ME.pdf").write_bytes(b"%PDF-1.4\n")
    return root


def test_program_root_is_refused(rt, qtdr):
    """THE bug: the 911 QTDR root must never become a run."""
    assert rt.classify_pick(str(qtdr)) == "too_high"
    assert rt.discover_jobs(str(qtdr), "too_high") == []


def test_root_stray_pdfs_are_not_jobs(rt, qtdr):
    """The stray QC PDFs beside the order folders are not nest packages."""
    jobs = rt.discover_jobs(str(qtdr))
    assert jobs == []


def test_order_folder_lists_every_nest(rt, qtdr):
    order = qtdr / "3X009"
    assert rt.classify_pick(str(order)) == "order"
    jobs = rt.discover_jobs(str(order))
    assert [j["label"] for j in jobs] == ["5CDAQN", "5CDAQO", "5CDAQP"]
    # the order folder's own loose PDF is never one of them
    assert all("READ ME" not in j["pdf"] for j in jobs)


def test_order_folder_flags_the_nest_with_no_workbook(rt, qtdr):
    jobs = {j["label"]: j for j in rt.discover_jobs(str(qtdr / "3X009"))}
    assert jobs["5CDAQN"]["workbook"] is not None
    assert jobs["5CDAQP"]["workbook"] is None


def test_single_nest_folder_needs_no_picker(rt, qtdr):
    nest = qtdr / "3X009" / "5CDAQN"
    assert rt.classify_pick(str(nest)) == "nest"
    jobs = rt.discover_jobs(str(nest))
    assert len(jobs) == 1
    assert jobs[0]["label"] == "5CDAQN"


def test_plain_leaf_folder_of_pdfs_still_works(rt, tmp_path):
    """The read-only report shape survives - but only as a LEAF."""
    leaf = tmp_path / "loose packets"
    leaf.mkdir()
    (leaf / "a packet.pdf").write_bytes(b"%PDF-1.4\n")
    (leaf / "b packet.pdf").write_bytes(b"%PDF-1.4\n")
    assert rt.classify_pick(str(leaf)) == "loose"
    assert [j["label"] for j in rt.discover_jobs(str(leaf))] == ["a packet", "b packet"]


def test_folder_of_pdfs_above_more_pdfs_is_refused(rt, tmp_path):
    """A PDF-holding folder whose subfolders also hold PDFs is above the work."""
    high = tmp_path / "some root"
    (high / "an order").mkdir(parents=True)
    (high / "stray.pdf").write_bytes(b"%PDF-1.4\n")
    (high / "an order" / "also stray.pdf").write_bytes(b"%PDF-1.4\n")
    assert rt.classify_pick(str(high)) == "too_high"


def test_named_roots_are_refused_even_when_empty(rt, tmp_path):
    for name in ("911 QTDR", "Pilot Program"):
        root = tmp_path / name
        root.mkdir()
        (root / "stray.pdf").write_bytes(b"%PDF-1.4\n")
        assert rt.classify_pick(str(root)) == "too_high", name
