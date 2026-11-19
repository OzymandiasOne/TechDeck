"""911 Setup v2.6.0 - the inspection sheet's Part Description (F.T. 2026-11-19).

"THIS HASNT BEEN FILLING OUT FOR THE 911 SETUP (i put it in there)" - the Part
Description cell on every QF-QU-09 inspection tab, which she had typed by hand
as the material code over its size.

The app never wrote that cell. Two formulas in the template tab did: D16 looked
the material up by PO LINE (`VLOOKUP(BB14, NEST!B4:H33, 7)`), D17 looked its
size up in SOURCE MATERIAL INFO. Both SACO templates were re-saved on 2026-10-23
with the Rev C form, which made D16:G17 one merged cell with nothing in it, so
the cell came out blank on every sheet from then on and no run said so.

The app owns the cell now. Each part gets ITS OWN row's material rather than the
first row sharing its PO line, and nothing depends on the forecast having filled
the PO columns. Verified through live Excel on copies of both real templates
(shape and plate), 2026-11-19: `code / size` on two lines in slot 1, mirrored
into every duplicate slot, with NEST A:C left blank.

The Excel half needs COM, so it is pinned here at the source level; the lookup
half is plain openpyxl and is tested for real.
"""

import importlib.util
import inspect
from pathlib import Path

import openpyxl
import pytest

PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "911_setup" / "run.py"


@pytest.fixture(scope="module")
def su():
    spec = importlib.util.spec_from_file_location("su_911_setup_partdesc", PLUGIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _workbook(parts, table=None, table_headers=("SOURCE", "MATERIAL", "SIZE",
                                                "DESCRIPTION", "MIL SPEC", "FORM"),
              with_table=True):
    """A NEST tab with `parts` = (work order, dypn, material, qty) from row 4."""
    wb = openpyxl.Workbook()
    nest = wb.active
    nest.title = "NEST"
    for i, (wo, dypn, material, qty) in enumerate(parts):
        r = 4 + i
        nest.cell(r, 6).value, nest.cell(r, 7).value = wo, dypn
        nest.cell(r, 8).value, nest.cell(r, 9).value = material, qty
    if with_table:
        src = wb.create_sheet("SOURCE MATERIAL INFO")
        src.append(list(table_headers))
        for row in (table or []):
            src.append(list(row))
    return wb


TABLE = [
    (218100081, "HSS", "18.875HX16.625FLGX40LX165LB", "WT18 X 165", "MIL-S-22698", "BEAM"),
    ("20-76-0144", "HSS", "12.250 X 10.000 X 58.000LB", "W12 X 58", "MIL-S-22698", "BEAM"),
]


def test_each_part_gets_its_own_rows_material(su):
    """The old formula gave every sheet the FIRST row's material."""
    wb = _workbook([("FM1", "H7190602-72", 218100081, 1),
                    ("X82", "H4112830-35", "20-76-0144", 3)], TABLE)
    assert su._part_descriptions(wb, wb["NEST"], lambda *_: None) == [
        ("218100081", "18.875HX16.625FLGX40LX165LB"),
        ("20-76-0144", "12.250 X 10.000 X 58.000LB"),
    ]


def test_it_lines_up_with_the_part_rows(su):
    """Parallel to _get_dypn_rows: a row with no DYPN is skipped by both."""
    wb = _workbook([("FM1", "H7190602-72", 218100081, 1),
                    ("", "", "IGNORED", 1),
                    ("X82", "H4112830-35", "20-76-0144", 3)], TABLE)
    parts = su._get_dypn_rows(wb["NEST"])
    descs = su._part_descriptions(wb, wb["NEST"], lambda *_: None)
    assert len(parts) == len(descs) == 2
    assert [d[0] for d in descs] == ["218100081", "20-76-0144"]


@pytest.mark.parametrize("nest_value,table_value", [
    (218100081, "218100081"),        # a number on NEST, text in the table
    ("218100081", 218100081),        # and the other way round
    (218100081.0, 218100081),        # a float, as Excel/pandas hand numbers back
    (" 20-76-0144 ", "20-76-0144"),  # stray spaces
    ("20-76-0144alt", "20-76-0144ALT"),
])
def test_a_code_matches_however_it_was_typed(su, nest_value, table_value):
    wb = _workbook([("FM1", "H1-1", nest_value, 1)],
                   [(table_value, "HSS", "THE SIZE", "", "", "")])
    (code, size), = su._part_descriptions(wb, wb["NEST"], lambda *_: None)
    assert size == "THE SIZE"
    assert not code.endswith(".0")


def test_a_material_missing_from_the_table_gets_its_code_and_a_note(su):
    """Faith's own part: 218032631F is not in the table. Never guess the size."""
    said = []
    wb = _workbook([("FK376940", "H6456301-6", "218032631F", 1)], TABLE)
    assert su._part_descriptions(wb, wb["NEST"], said.append) == [("218032631F", "")]
    assert any("218032631F" in m and "code only" in m for m in said), said


def test_the_note_names_each_missing_material_once(su):
    said = []
    wb = _workbook([("A", "H1-1", "NOPE1", 1), ("B", "H1-2", "NOPE1", 1),
                    ("C", "H1-3", "NOPE2", 1)], TABLE)
    su._part_descriptions(wb, wb["NEST"], said.append)
    notes = [m for m in said if "code only" in m]
    assert len(notes) == 1 and notes[0].count("NOPE1") == 1 and "NOPE2" in notes[0]


def test_the_size_column_is_found_by_header_name(su):
    """Hard Rule 1: a table whose columns moved still gives the SIZE."""
    wb = _workbook([("FM1", "H1-1", "ABC", 1)],
                   [("x", "THE SIZE", "y", "ABC")],
                   table_headers=("FORM", "SIZE", "MIL SPEC", "SOURCE"))
    assert su._part_descriptions(wb, wb["NEST"], lambda *_: None) == [("ABC", "THE SIZE")]


def test_no_table_at_all_still_gives_the_code(su):
    said = []
    wb = _workbook([("FM1", "H1-1", "ABC", 1)], with_table=False)
    assert su._part_descriptions(wb, wb["NEST"], said.append) == [("ABC", "")]
    assert any("SOURCE MATERIAL INFO" in m for m in said), said


def test_a_blank_material_is_left_blank(su):
    wb = _workbook([("FM1", "H1-1", None, 1)], TABLE)
    assert su._part_descriptions(wb, wb["NEST"], lambda *_: None) == [("", "")]


# ── the Excel half, pinned at the source ────────────────────────────────────
def test_the_run_hands_the_descriptions_to_the_builder(su):
    src = inspect.getsource(su)
    assert "part_descs = _part_descriptions(wb, nest_ws, log)" in src
    assert "_build_inspection_sheets_via_excel(nest_excel, part_rows, log,\n" in src
    assert "descriptions" in inspect.signature(
        su._build_inspection_sheets_via_excel).parameters


def test_the_builder_writes_slot_one_and_handles_both_layouts(su):
    """Rev C = one merged cell; the older template = code over size, two cells."""
    src = inspect.getsource(su._build_inspection_sheets_via_excel)
    assert 'desc_cell = new_sheet.Range("D16")' in src
    assert "MergeArea.Rows.Count >= 2" in src            # which layout is this?
    assert 'new_sheet.Range("D17").Value = size' in src   # the older two-cell one


def test_a_duplicate_slot_in_the_single_cell_layout_only_mirrors_slot_one(su):
    """'=D$17' aimed inside Rev C's merge is dropped by COM without a word."""
    src = inspect.getsource(su._build_inspection_sheets_via_excel)
    single = src.index("if single_cell:\n                        mirror")
    rebuild = src.index("xlPasteFormats = -4122")
    assert single < rebuild, "the single-cell branch must leave before the rebuild"
    assert "continue" in src[single:rebuild]
    assert "'=IF(D$16=\"\",\"\",D$16)'" in src
