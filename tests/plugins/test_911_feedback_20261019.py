"""The 2026-10-19 floor feedback, four tickets in one message. One file so the
whole batch of asks is pinned together and a regression names the ticket.

  1. 911 Setup   - a nest missing from the Working Forecast List must be
                   flagged IN the workbook (yellow A4:C4 + a note), not just
                   warned about in a console nobody reads.
  2. 911 Setup   - 'Linear Inch Calcs\\NC_DSTV': every NC file EB shipped for a
                   nest, copied flat out of the batch's DSTV FILES tree,
                   never overwriting on a name clash.
  3. Remove Tkt  - the orphan '8000 THE ER ON THIS OPERATION...' continuation
                   page goes; a real sketch page that merely LISTS 8000 as a
                   second operation stays. This is the whole ticket: on 394
                   real packets, 195 of the 243 pages carrying that phrase
                   were real sketches.
  4. Baked Beans - a DYPN with a trailing letter ('H4524555-12M') is a DYPN.
"""
import importlib.util
from pathlib import Path

import pytest
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[2]


def _load(plugin_id):
    spec = importlib.util.spec_from_file_location(
        f"_t_{plugin_id}", ROOT / "plugins" / plugin_id / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def setup_mod():
    return _load("911_setup")


@pytest.fixture(scope="module")
def ticket_mod():
    return _load("911_remove_ticket")


@pytest.fixture(scope="module")
def beans_mod():
    return _load("911_baked_beans_wild_ride")


# ---------------------------------------------------------------------------
# 1. Forecast gap is carried by the workbook
# ---------------------------------------------------------------------------

def test_forecast_gap_is_flagged_in_the_workbook(setup_mod):
    wb = Workbook()
    ws = wb.active
    setup_mod._flag_forecast_gap(ws, "504114", "911 Forecast", lambda *a: None)

    for col in (1, 2, 3):                       # A4:C4
        cell = ws.cell(4, col)
        assert cell.fill.fgColor.rgb.endswith("FFFF00"), \
            f"column {col} row 4 is not highlighted"

    note = ws.cell(4, 1).comment
    assert note is not None, "no note on A4 explaining the gap"
    assert "504114" in note.text
    assert "911 Forecast" in note.text
    # The note has to say what to DO, not just what happened.
    assert "Nest Workbook Data" in note.text


def test_forecast_gap_flag_does_not_write_values(setup_mod):
    """The columns stay BLANK - the app never guesses a PO."""
    wb = Workbook()
    ws = wb.active
    setup_mod._flag_forecast_gap(ws, "504114", "911 Forecast", lambda *a: None)
    assert [ws.cell(4, c).value for c in (1, 2, 3)] == [None, None, None]


def test_forecast_gap_flag_is_idempotent(setup_mod):
    """A re-run must not stack a second comment on the same cell."""
    wb = Workbook()
    ws = wb.active
    for _ in range(3):
        setup_mod._flag_forecast_gap(ws, "504114", "911 Forecast", lambda *a: None)
    assert ws.cell(4, 1).comment is not None
    assert ws.cell(4, 1).comment.text.count("504114") == 1


# ---------------------------------------------------------------------------
# 2. Linear Inch Calcs\NC_DSTV
# ---------------------------------------------------------------------------

def _make_batch(tmp_path, dstv_name="DTSV FILES"):
    batch = tmp_path / "V100"
    nest_src = batch / dstv_name / "X504047S"
    (nest_src / "x4681991").mkdir(parents=True)
    (nest_src / "x4681991" / "h4139818-97.a.1.NC").write_text("ONE")
    (nest_src / "x4682024").mkdir()
    (nest_src / "x4682024" / "h4139818-287.a.1.NC").write_text("TWO")
    (nest_src / "yard").mkdir()
    (nest_src / "yard" / "Rem. Sq..NC").write_text("REMNANT")
    # Non-NC siblings that must NOT come across.
    (nest_src / "X504047S_1.ba").write_text("ba")
    (nest_src / "X504047S_1").mkdir()
    (nest_src / "X504047S_1" / "X504047S_1.jpg").write_bytes(b"\xff\xd8jpg")
    return batch


def _dest(batch, nest="504047"):
    return batch / nest / "Linear Inch Calcs" / "NC_DSTV"


def test_nc_files_are_copied_flat(tmp_path, setup_mod):
    batch = _make_batch(tmp_path)
    root = setup_mod._find_dstv_root(batch)
    copied = setup_mod._extract_nest_nc_files(
        batch, "504047", root, lambda *a: None)

    dest = _dest(batch)
    assert dest.is_dir()
    names = sorted(p.name for p in dest.iterdir())
    assert names == ["h4139818-287.a.1.NC", "h4139818-97.a.1.NC"]
    assert copied == 2
    # the work-order folders themselves are NOT recreated
    assert not (dest / "x4681991").exists()


def test_ebs_own_file_names_are_kept(tmp_path, setup_mod):
    """Requester, 2026-10-21: "Keeping EB's file names is fine, we use changing
    it as a way to track work progress." Renaming them to the work order -- the
    way the hand-made DSTVs folder does -- would destroy that signal."""
    batch = _make_batch(tmp_path)
    setup_mod._extract_nest_nc_files(
        batch, "504047", setup_mod._find_dstv_root(batch), lambda *a: None)
    names = sorted(p.name for p in _dest(batch).iterdir())
    assert names == ["h4139818-287.a.1.NC", "h4139818-97.a.1.NC"]


def test_the_yard_remnant_is_left_behind(tmp_path, setup_mod):
    """Requester, 2026-10-21, asked whether the yard remnant should come too:
    "Negative, we do not use that file for anything as far as I know."

    Matched on the FOLDER, not the file name. Surveying 60 live batches /
    3,635 .NC files found 150 under a 'yard' folder and the same 150 named
    'Rem. Sq..NC', so the two rules pick identically today -- but the folder is
    the structural fact, and a name rule could one day drop a real part whose
    name happens to contain "rem".
    """
    batch = _make_batch(tmp_path)
    nest_src = batch / "DTSV FILES" / "X504047S"
    # A real part that would be caught by a name rule, and a remnant that
    # would be missed by one.
    (nest_src / "x4681991" / "h999-REMOTE-BRACKET.NC").write_text("REAL")
    (nest_src / "yard" / "offcut.NC").write_text("ALSO A REMNANT")

    copied = setup_mod._extract_nest_nc_files(
        batch, "504047", setup_mod._find_dstv_root(batch), lambda *a: None)

    names = sorted(p.name for p in _dest(batch).iterdir())
    assert "Rem. Sq..NC" not in names
    assert "offcut.NC" not in names, "everything under yard stays behind"
    assert "h999-REMOTE-BRACKET.NC" in names, "a real part is not a remnant"
    assert copied == 3


def test_the_skipped_remnant_is_reported(tmp_path, setup_mod):
    """Left behind on purpose is still worth saying out loud -- otherwise the
    count in the log does not match what is in the source folder."""
    batch = _make_batch(tmp_path)
    lines = []
    setup_mod._extract_nest_nc_files(
        batch, "504047", setup_mod._find_dstv_root(batch), lines.append)
    assert any("yard remnant" in line for line in lines), lines


def test_only_nc_files_come_across(tmp_path, setup_mod):
    batch = _make_batch(tmp_path)
    setup_mod._extract_nest_nc_files(
        batch, "504047", setup_mod._find_dstv_root(batch), lambda *a: None)
    suffixes = {p.suffix.lower() for p in _dest(batch).iterdir()}
    assert suffixes == {".nc"}


def test_a_name_clash_never_overwrites(tmp_path, setup_mod):
    """353 of 380 real same-name pairs are DIFFERENT files. Both must survive."""
    batch = tmp_path / "V100"
    nest_src = batch / "DTSV FILES" / "X504047S"
    for wo, body in (("x4681991", "FIRST"), ("x4682024", "SECOND")):
        (nest_src / wo).mkdir(parents=True)
        (nest_src / wo / "H7190602-73.A.1.NC").write_text(body)

    setup_mod._extract_nest_nc_files(
        batch, "504047", setup_mod._find_dstv_root(batch), lambda *a: None)

    bodies = sorted(p.read_text() for p in _dest(batch).iterdir())
    assert bodies == ["FIRST", "SECOND"], "a differing NC file was overwritten"
    assert len(list(_dest(batch).iterdir())) == 2


def test_an_identical_duplicate_is_not_duplicated(tmp_path, setup_mod):
    batch = tmp_path / "V100"
    nest_src = batch / "DTSV FILES" / "X504047S"
    for wo in ("x4681991", "x4682024"):
        (nest_src / wo).mkdir(parents=True)
        (nest_src / wo / "H7190602-73.A.1.NC").write_text("SAME")
    setup_mod._extract_nest_nc_files(
        batch, "504047", setup_mod._find_dstv_root(batch), lambda *a: None)
    assert len(list(_dest(batch).iterdir())) == 1


def test_rerun_copies_nothing_new(tmp_path, setup_mod):
    batch = _make_batch(tmp_path)
    root = setup_mod._find_dstv_root(batch)
    setup_mod._extract_nest_nc_files(batch, "504047", root, lambda *a: None)
    again = setup_mod._extract_nest_nc_files(batch, "504047", root, lambda *a: None)
    assert again == 0
    assert len(list(_dest(batch).iterdir())) == 2


@pytest.mark.parametrize("folder", ["DTSV FILES", "DSTV FILES",
                                    "DSTV FILES-COMPLETE"])
def test_every_real_spelling_of_the_dstv_folder_is_found(tmp_path, setup_mod, folder):
    """Seen in the wild: DTSV FILES (68 batches), DSTV FILES (4),
    DSTV FILES-COMPLETE (4). A literal name would miss most of them."""
    batch = _make_batch(tmp_path, dstv_name=folder)
    root = setup_mod._find_dstv_root(batch)
    assert root is not None and root.name == folder


def test_plain_folder_wins_over_the_complete_archive(tmp_path, setup_mod):
    batch = tmp_path / "V100"
    (batch / "DTSV FILES").mkdir(parents=True)
    (batch / "DSTV FILES-COMPLETE").mkdir()
    assert setup_mod._find_dstv_root(batch).name == "DTSV FILES"


@pytest.mark.parametrize("nest,folder", [("504047", "X504047S"),
                                         ("P07819", "XP07819S"),
                                         ("S20085", "XS20085S")])
def test_lettered_nests_resolve(tmp_path, setup_mod, nest, folder):
    batch = tmp_path / "V100"
    (batch / "DTSV FILES" / folder / "wo").mkdir(parents=True)
    (batch / "DTSV FILES" / folder / "wo" / "p.NC").write_text("x")
    assert setup_mod._extract_nest_nc_files(
        batch, nest, setup_mod._find_dstv_root(batch), lambda *a: None) == 1


def test_a_nest_with_no_nc_files_still_gets_the_folder(tmp_path, setup_mod):
    """He asked for the folder as much as the files."""
    batch = tmp_path / "V100"
    (batch / "DTSV FILES").mkdir(parents=True)
    lines = []
    assert setup_mod._extract_nest_nc_files(
        batch, "504047", setup_mod._find_dstv_root(batch), lines.append) == 0
    assert _dest(batch).is_dir()
    assert any("WARNING" in l for l in lines)


def test_no_dstv_folder_at_all_is_a_warning_not_a_crash(tmp_path, setup_mod):
    batch = tmp_path / "V100"
    batch.mkdir()
    assert setup_mod._find_dstv_root(batch) is None
    lines = []
    assert setup_mod._extract_nest_nc_files(batch, "504047", None, lines.append) == 0
    assert _dest(batch).is_dir()


def test_the_stage_is_in_the_toggle_window(setup_mod):
    keys = [g["key"] for g in setup_mod._dialog_groups()]
    assert "nc_dstv" in keys
    group = next(g for g in setup_mod._dialog_groups() if g["key"] == "nc_dstv")
    assert group["checked"] is True


# ---------------------------------------------------------------------------
# 3. The orphan 8000 operation page
# ---------------------------------------------------------------------------

_ORPHAN = ("4 / 41\nFM311001\nPART SKETCH\nX504376S\n"
           "8000 THE ER ON THIS OPERATION IS EMBEDDED IN THE WORK PACKAGE "
           "DRAWING. BY\n")

_REAL_SKETCH_LISTING_8000 = (
    "3 / 6\nFM310297\nPART SKETCH\nX504092S\nPART: H4139808-131\n"
    "REV/SEQ: D/01\nNOUN: TUBE\nFER: F\n"
    "130 CUT NEAT AND STAMP PART PER SKETCH.\n"
    "8000 THE ER ON THIS OPERATION IS EMBEDDED IN THE WORK PACKAGE "
    "DRAWING. BY\nMIL-SPEC\nASTM-A500\n")

_PLAIN_SKETCH = ("3 / 41\nPART SKETCH\nX504376S\nPART: H4133380-89\n"
                 "130 CUT AND STAMP PART PER PART SKETCH\n")


def test_orphan_operation_page_is_removed(ticket_mod):
    assert ticket_mod._is_orphan_operation_page(_ORPHAN.upper())


def test_a_real_sketch_listing_8000_is_kept(ticket_mod):
    """195 of the 243 real pages carrying that phrase are THESE. Deleting on
    the phrase alone would throw away four out of every five."""
    assert not ticket_mod._is_orphan_operation_page(
        _REAL_SKETCH_LISTING_8000.upper())


def test_an_ordinary_sketch_is_untouched(ticket_mod):
    assert not ticket_mod._is_orphan_operation_page(_PLAIN_SKETCH.upper())


def test_scan_document_reports_orphans_separately(ticket_mod):
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    for text in (_PLAIN_SKETCH, _ORPHAN, "MOVE TICKET\nMATERIAL: HSS\n",
                 _REAL_SKETCH_LISTING_8000):
        page = doc.new_page()
        page.insert_text((40, 60), text, fontsize=8)
    try:
        remove, _materials, orphans = ticket_mod._scan_document(doc)
        assert orphans == 1
        assert 1 in remove, "the orphan page was not marked for removal"
        assert 2 in remove, "the move ticket page was not marked for removal"
        assert 0 not in remove and 3 not in remove, "a real sketch was removed"
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# 4. DYPNs with a trailing letter
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dypn", [
    "H4139818-97",        # the plain shape
    "H4524555-12M",       # THE REPORTED MISS (V103 504123)
    "H4524555-38M",
    "263514501-426M",     # no letter prefix
    "H7376008-P001E",     # letter inside the segment after the dash
    "H6761001-15-10A",    # two dash segments
    "H7212563H352-13",    # letter group inside the stem
])
def test_real_dypns_are_recognised(dypn):
    from techdeck.core import plugin_sdk as sdk
    assert sdk.is_dypn(dypn), f"{dypn} is a real DYPN off a live BATCH LIST"


@pytest.mark.parametrize("junk", [
    "SSPO", "TOTALS", "NEST", "", "MIL-S-22698", "ASTM-A500", "X504047S",
    "2026-10-20",         # the reason the stem needs 5+ digits
    "EB218001124CP12",    # a plate material code, not a DYPN
])
def test_junk_is_not_a_dypn(junk):
    from techdeck.core import plugin_sdk as sdk
    assert not sdk.is_dypn(junk)


def test_baked_beans_uses_the_sdk_pattern(beans_mod):
    """Hard Rule 3's contract: one home for the shape, aliased never retyped."""
    from techdeck.core import plugin_sdk as sdk
    assert beans_mod._DYPN_RE is sdk.DYPN_ID_RE


def test_trailing_letter_dypns_sort_naturally(beans_mod):
    order = sorted(["H4524555-250", "H4524555-12M", "H4524555-100M",
                    "H4524555-42", "H4524555-9"], key=beans_mod._dypn_sort_key)
    assert order == ["H4524555-9", "H4524555-12M", "H4524555-42",
                     "H4524555-100M", "H4524555-250"]


def test_a_labeled_part_cell_with_an_m_suffix_is_read(beans_mod):
    """End to end: this is what produced 'DYPN cell not found - used file
    name' on every -NNM part in the consolidated list."""
    wb = Workbook()
    ws = wb.active
    ws.cell(3, 2).value = "Batch/Nest"
    ws.cell(3, 3).value = "  V103 504123"
    ws.cell(6, 2).value = "Part #"
    ws.cell(6, 3).value = "H4524555-12M"
    dypn, batch, nest, _totals, notes = beans_mod._extract_part(ws, "H4524555-12M")
    assert dypn == "H4524555-12M"
    assert (batch, nest) == ("V103", "504123")
    assert not any("DYPN cell not found" in n for n in notes)
