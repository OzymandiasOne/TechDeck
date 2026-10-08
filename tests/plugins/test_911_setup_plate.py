"""911 Setup PLATE mode (v2.1.0, coworker feedback 2026-09-03).

The plugin was tailored exclusively to SHAPE batches; plate batches were set
up by hand. The three reported inaccuracies these tests pin down:

1. MIL SPEC must be the literal 'N/A' for FERROUS (carbon) plate — decided
   by the packet's own MOVE TICKET 'FERROUS:' flag ('F'), never a keyword
   guess. Non-ferrous plate ('N': CRES/IN625/MONEL/CUNI/BRASS, 'A': aluminum)
   is left BLANK for a person to fill in (v2.3.0; it kept the packet's spec
   before). SHAPE runs are byte-for-byte unaffected.
2. The SCRIBE sheet's UNIQUE - TRACE column is real data on plate (manually
   entered from the forecast today, hardcoded to "N/A" by the SHAPE
   template's formulas) — plate runs fill it from the forecast's TRACE/MIC
   column, and a blank forecast leaves it blank, never "N/A".
3. Plate runs must use the plate templates: '911 PLATE BATCH _.xlsx' and the
   PLATES scribe form, both of which already lived in the SACO dir but were
   unreachable — the finder's '911 BATCH' prefix can never match them.
"""

import importlib.util
from pathlib import Path

import openpyxl
import pytest

PLUGIN = (Path(__file__).resolve().parents[2]
          / "plugins" / "911_setup" / "run.py")


@pytest.fixture(scope="module")
def su():
    spec = importlib.util.spec_from_file_location("su_911_setup", PLUGIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── template finder: the two prefixes must never cross-match ────────────────
@pytest.fixture
def saco(tmp_path):
    """A SACO template dir with both workbook templates, as on the real share."""
    (tmp_path / "911 BATCH _.xlsx").write_bytes(b"shape")
    (tmp_path / "911 PLATE BATCH _.xlsx").write_bytes(b"plate")
    return tmp_path


def test_shape_run_finds_the_shape_template(su, saco):
    assert su._find_template_911(saco).name == "911 BATCH _.xlsx"


def test_plate_run_finds_the_plate_template(su, saco):
    assert su._find_template_911(saco, plate=True).name == \
        "911 PLATE BATCH _.xlsx"


def test_shape_prefix_cannot_grab_the_plate_template(su, tmp_path):
    """Only the plate template present: a SHAPE run must fail loudly, not
    silently set a shape batch up on the plate workbook."""
    (tmp_path / "911 PLATE BATCH _.xlsx").write_bytes(b"plate")
    with pytest.raises(FileNotFoundError, match="911 BATCH"):
        su._find_template_911(tmp_path)


def test_missing_plate_template_names_the_plate_pattern(su, tmp_path):
    (tmp_path / "911 BATCH _.xlsx").write_bytes(b"shape")
    with pytest.raises(FileNotFoundError, match="911 PLATE BATCH"):
        su._find_template_911(tmp_path, plate=True)


# ── MIL SPEC: the packet's own FERROUS flag decides ─────────────────────────
# Real observed flag values: F (STL/HSS/OSS/HY-80/HY-100), N (CRES304/316L,
# CRES 2205, IN625, K-MONEL, CUNI, BRASS), A (AL).
@pytest.mark.parametrize("mil, ferrous, plate, expected", [
    ("MIL-S-22698", "F", True, "N/A"),          # carbon plate -> N/A
    ("MIL-S-22698", "f", True, "N/A"),          # case-tolerant
    # v2.3.0 (floor feedback 2026-09-18): non-ferrous plate is left BLANK - it
    # DOES need a spec, and a blank says "fill me in" where a wrong value has
    # to be noticed before it can be overridden. (v2.1.0 kept the packet's.)
    ("ASTM-A240", "N", True, None),             # stainless plate -> blank
    ("ASTM-B209", "A", True, None),             # aluminum plate -> blank
    ("ASTM-B209", "n", True, None),             # case-tolerant
    ("ASTM-A240", "N", False, "ASTM-A240"),     # SHAPE untouched, non-ferrous too
    # no flag -> the app cannot tell carbon from non-ferrous, so it does not
    # guess: blank (maintainer's rule 2026-09-21). 212 of 212 real packets
    # carry the flag, so this is the rare case, not the normal one.
    ("MIL-S-22698", None, True, None),
    ("MIL-S-22698", "", True, None),
    ("MIL-S-22698", None, False, "MIL-S-22698"),  # SHAPE untouched without a flag too
    ("MIL-S-22698", "F", False, "MIL-S-22698"), # SHAPE untouched, even ferrous
    (None, "F", True, "N/A"),                   # carbon plate, blank spec field
    (None, "N", True, None),                    # nothing to write
])
def test_effective_mil_spec(su, mil, ferrous, plate, expected):
    assert su._effective_mil_spec(mil, ferrous, plate) == expected


def test_ferrous_flag_reads_from_real_move_ticket_layout(su):
    """The flag sits mid-line on the MOVE TICKET ('FERROUS:' then the value
    on the next extracted line) — same labeled-field read as MIL SPEC."""
    text = "LEVEL: N\nSUBSAFE:\nN\nFERROUS:\nF\nPART WT:\n41\n"
    assert su._labeled_value(text, "FERROUS") == "F"


# ── scribe doc: plate form for plate runs ───────────────────────────────────
def test_scribe_doc_filename_per_mode(su):
    assert "SHAPES" in su._scribe_doc_filename(False)
    assert "PLATES" in su._scribe_doc_filename(True)
    assert su._scribe_doc_filename(True) == \
        "QF-QU-15 REV B - SCRIBE VERIFICATION - PLATES.docx"


# ── UNIQUE - TRACE: forecast TRACE/MIC -> plate SCRIBE sheet ────────────────
def _plate_workbook():
    """A workbook with the plate template's SCRIBE header row (PART ID shifts
    UNIQUE - TRACE to col G — the writer must find it by NAME, not position)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SCRIBE VERIFICATION"
    for col, hdr in enumerate(["PART ID", "QTY", "DYPN", "HULL CODE",
                               "MILL - SPEC", "MAT TYPE", "UNIQUE - TRACE"], 1):
        ws.cell(1, col).value = hdr
    return wb


def test_trace_fills_every_part_row_from_one_forecast_row(su):
    """The usual case: one forecast row per nest, several part rows — the
    trace replicates down exactly like _fill_nest_part_rows does for A-E."""
    wb = _plate_workbook()
    rows = [("PO1", 1, "V092", "DL34270")]
    su._fill_scribe_trace(wb, rows, num_parts=3, log=lambda *a: None)
    ws = wb["SCRIBE VERIFICATION"]
    assert [ws.cell(r, 7).value for r in (2, 3, 4)] == ["DL34270"] * 3


def test_trace_keeps_per_row_values_when_forecast_has_several(su):
    wb = _plate_workbook()
    rows = [("PO1", 1, "V092", "DL34270"), ("PO1", 2, "V092", "XL30183")]
    su._fill_scribe_trace(wb, rows, num_parts=2, log=lambda *a: None)
    ws = wb["SCRIBE VERIFICATION"]
    assert ws.cell(2, 7).value == "DL34270"
    assert ws.cell(3, 7).value == "XL30183"


def test_blank_forecast_trace_stays_blank_for_manual_entry(su):
    """The reported hazard is 'N/A' being overlooked — a blank forecast must
    leave the column EMPTY, never invent a value."""
    wb = _plate_workbook()
    rows = [("PO1", 1, "V092", None), ("PO1", 2, "V092", "")]
    su._fill_scribe_trace(wb, rows, num_parts=2, log=lambda *a: None)
    ws = wb["SCRIBE VERIFICATION"]
    assert ws.cell(2, 7).value is None
    assert ws.cell(3, 7).value is None


def test_trace_write_survives_a_workbook_without_the_column(su):
    """An older/edited template: warn and skip, never crash the batch run."""
    wb = openpyxl.Workbook()
    wb.active.title = "SCRIBE VERIFICATION"      # headerless sheet
    logs = []
    su._fill_scribe_trace(wb, [("a", "b", "c", "T1")], 1, logs.append)
    assert any("UNIQUE - TRACE" in m for m in logs)


# ── forecast reader carries the trace column through ────────────────────────
def test_copy_forecast_rows_reads_the_trace_column(su):
    wb = openpyxl.Workbook()
    ws = wb.active
    for col, hdr in enumerate(["PO", "Line", "Batch /DR", "NEST",
                               "TRACE/MIC"], 1):
        ws.cell(1, col).value = hdr
    ws.append(["PO9", 4, "V092", "503836", "DL28965"])
    rows = su._copy_forecast_rows(ws, 1, 4, (1, 2, 3, 5), "503836")
    assert rows == [("PO9", 4, "V092", "DL28965")]


def test_copy_forecast_rows_tolerates_a_forecast_without_trace(su):
    """trace_col None (no TRACE/MIC header found) must not break SHAPE runs."""
    wb = openpyxl.Workbook()
    ws = wb.active
    for col, hdr in enumerate(["PO", "Line", "Batch /DR", "NEST"], 1):
        ws.cell(1, col).value = hdr
    ws.append(["PO9", 4, "V092", "503836"])
    rows = su._copy_forecast_rows(ws, 1, 4, (1, 2, 3, None), "503836")
    assert rows == [("PO9", 4, "V092", None)]


# ── the toggle itself: defaults SHAPE, never sticky ─────────────────────────
def test_plate_toggle_declares_no_memory_and_defaults_off(su):
    g = next(x for x in su._dialog_groups() if x["key"] == "plate_batch")
    assert g["checked"] is False          # SHAPE is the default, every run
    assert g["remember"] is False         # and memory may never change that


# ── non-ferrous plate: each part's MIL spec comes off its PART SKETCH page ──
# (v2.3.0, maintainer 2026-09-21). Every sketch page ends in a 'FOR LABELING
# INFORMATION ONLY' block: NC PROG / HULL / PART / MIL-SPEC headers, then the
# four values. The line sequences below are REAL text-layer reads.

def _sketch_pdf(tmp_path, pages):
    fitz = pytest.importorskip("fitz")
    pdf = tmp_path / "503856.pdf"
    doc = fitz.open()
    for lines in pages:
        page = doc.new_page()
        for k, ln in enumerate(lines):
            page.insert_text((60, 50 + 13 * k), ln, fontsize=8)
    doc.save(pdf)
    doc.close()
    return pdf


def _sketch(part, fer, values):
    return (["3 / 16", "FK370129", "PART SKETCH", "X503856S", f"PART: {part}",
             "REV/SEQ: A/01", "QTY: 3", "NOUN: CHANNEL", "MATL:", f"FER: {fer}",
             "130 CUT AND STAMP PART PER SCD AND PART SKETCH", "1", "NOT TO SCALE",
             "FOR LABELING INFORMATION ONLY", "FINAL-INSP:",
             "NC PROG", "HULL", "PART", "MIL-SPEC"] + values)


def test_sketch_label_block_gives_each_part_its_own_spec(su, tmp_path):
    pdf = _sketch_pdf(tmp_path, [
        ["MOVE TICKET", "MIL SPEC: ASTM-B221", "FERROUS: A"],            # not a sketch page
        _sketch("H4146707-1", "A", ["H4146707-1.A.01", "FJ", "H4146707-1", "ASTM-B221"]),
        _sketch("H5532004-15-4", "N", ["H5532004-15-4.A.01", "X5", "H5532004-15-4", "QQ-N-281"]),
        # a note-only sketch page: no PART:, no block (99 of 1,735 real pages)
        ["13 / 16", "X8386369", "PART SKETCH", "X504197S", "8001 THE ER ON THIS OPERATION ..."],
    ])
    assert su._parse_sketch_mil_specs(pdf) == {
        "H4146707-1": ("ASTM-B221", "A"),
        "H5532004-15-4": ("QQ-N-281", "N"),
    }


def test_a_missing_value_never_shifts_another_field_into_the_spec(su, tmp_path):
    pdf = _sketch_pdf(tmp_path, [
        # no HULL printed: the spec is still the line after the PART value
        _sketch("H1000000-1", "N", ["H1000000-1.A.01", "H1000000-1", "QQ-S-763"]),
        # no MIL-SPEC printed: blank - NOT the hull, NOT the next page's counter
        _sketch("H1000000-2", "N", ["H1000000-2.A.01", "FK", "H1000000-2"]),
        _sketch("H1000000-3", "N", ["H1000000-3.A.01", "FK", "H1000000-3", "10 / 37"]),
    ])
    got = su._parse_sketch_mil_specs(pdf)
    assert got["H1000000-1"] == ("QQ-S-763", "N")
    assert got["H1000000-2"] == ("", "N")
    assert got["H1000000-3"] == ("", "N")


def test_part_rows_get_their_own_spec_and_unknown_parts_stay_blank(su):
    ws = openpyxl.Workbook().active
    for r in (4, 5, 6):
        ws.cell(r, 4).value = "STALE-SPEC"          # what an older run wrote down every row
    rows = [("X1", "H4146707-1", "AL", 3, "503856", "CUT"),
            ("X2", "h5532004-15-4", "NICU", 1, "503856", "CUT"),   # case-tolerant
            ("X3", "H9999999-9", "AL", 1, "503856", "CUT")]        # no sketch page
    logged = []
    filled, blank = su._fill_part_mil_specs(
        ws, rows, {"H4146707-1": ("ASTM-B221", "A"), "H5532004-15-4": ("QQ-N-281", "N")},
        logged.append)
    assert (filled, blank) == (2, ["H9999999-9"])
    assert [ws.cell(r, 4).value for r in (4, 5, 6)] == ["ASTM-B221", "QQ-N-281", None]
    assert any("H9999999-9" in ln and "BLANK" in ln for ln in logged)
