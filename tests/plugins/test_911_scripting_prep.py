"""Regression tests for 911 Scripting Prep's PO Data input block + division map.

Both behaviours are user-requested contracts (A.T., 2026-09-03) with exact
shapes her downstream work depends on:

1. The PO Data T/U input block and the ``=$U$n`` formulas in columns
   A/B/C/G/L/M. Which U row holds which value is fixed by her reference
   workbook (``SSPO SCRIPTING - 1000129724 SSPO Award 14``), row-6 gap
   included -- moving a row silently rewires every formula on the sheet.
2. DIVISION 2 mapping the planner's ``SOPO`` shorthand to Mie Trak's exact,
   case-sensitive ``SOUTH PORTLAND``.
"""

import importlib.util
from pathlib import Path

import pytest
from openpyxl import load_workbook

PLUGIN = (Path(__file__).resolve().parents[2]
          / "plugins" / "911_scripting_prep" / "run.py")


@pytest.fixture(scope="module")
def sp():
    spec = importlib.util.spec_from_file_location("sp_911_scripting_prep", PLUGIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AWARD_ROWS = [
    {"order": "L031", "nest": "5CDBEY", "source": "EB218001123",
     "pcs": "56", "orders": "27", "division": "SOPO"},
    {"order": "L031", "nest": "5CDBFK", "source": "EB218001957",
     "pcs": "16", "orders": "6", "division": "SACO"},
    {"order": "V115", "nest": "504394", "source": "EB218001123",
     "pcs": "1", "orders": "1", "division": "sopo"},
]
INVENTORY = {"EB218001123": ("DH-36", "0.25"), "EB218001957": ("OSS", "0.25")}
FILLS = {"part_rev": "OFLD-PLTFORM-REV 108",
         "standard_clauses": "the clauses",
         "ship_to": "911 QTDR OFFLOAD"}


@pytest.fixture(scope="module")
def workbook(sp, tmp_path_factory):
    out = tmp_path_factory.mktemp("scripting") / "out.xlsx"
    po_rows, part_rows, unresolved = sp.build_records(AWARD_ROWS, INVENTORY)
    sp.write_output(out, po_rows, part_rows, unresolved, len(AWARD_ROWS),
                    FILLS, "1000129724", lambda *_: None)
    return load_workbook(out, data_only=False)


def test_input_formulas_on_every_data_row(workbook):
    po = workbook["PO Data"]
    for col, formula in (("A", "=$U$1"), ("B", "=$U$2"), ("C", "=$U$7"),
                         ("G", "=$U$3"), ("L", "=$U$4"), ("M", "=$U$5")):
        for row in (2, 3, 4):
            assert po["%s%d" % (col, row)].value == formula
    # Formulas stop at the last data row.
    assert po["A5"].value is None


def test_input_block_layout_matches_the_reference_workbook(workbook):
    po = workbook["PO Data"]
    assert po["T1"].value == "PO"
    assert po["T2"].value == "LINE"
    assert po["T3"].value == "PART REV"
    assert po["T4"].value == "STD CLAUSES"
    assert po["T5"].value == "SHIP TO"
    assert po["T6"].value is None          # the reference's deliberate gap
    assert po["T7"].value == "PROMISE DATE"
    assert po["U7"].number_format == "mm-dd-yy"
    assert po["C2"].number_format == "mm-dd-yy"


def test_input_block_seeding(workbook):
    po = workbook["PO Data"]
    # PO number parsed off the award name, red = app-derived, verify it.
    assert po["U1"].value == 1000129724
    assert po["U1"].font.color.rgb == "FFFF0000"
    # Settings values land in their U cells, black (the user's own text).
    assert po["U3"].value == FILLS["part_rev"]
    assert po["U4"].value == FILLS["standard_clauses"]
    assert po["U5"].value == FILLS["ship_to"]
    # No setting, no seed: LINE and PROMISE DATE stay for hand entry.
    assert po["U2"].value is None
    assert po["U7"].value is None


def test_division_2_maps_sopo_to_south_portland(workbook):
    part = workbook["Part Data"]
    assert part["Q2"].value == "SOUTH PORTLAND"
    assert part["Q3"].value == "SACO"                 # unmapped passes through
    assert part["Q4"].value == "SOUTH PORTLAND"       # case-insensitive match
