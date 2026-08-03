"""Tests for 911 Setup's Generate Teams Cards stage (v1.8.0).

Every fixture string below is a REAL value copied off the live EB 922 Schedule
(CURRENT PIPELINE) or a 911 BATCH LIST on 2026-08-03 -- the point of these
tests is that the parsing keeps working on the data that actually arrives, not
on tidied-up samples.
"""

import datetime as dt
import importlib.util
import json
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[2] / "plugins" / "911_setup"


@pytest.fixture(scope="module")
def st():
    spec = importlib.util.spec_from_file_location(
        "st_911_setup", PLUGIN_DIR / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def template():
    with open(PLUGIN_DIR / "card_template.json", "r", encoding="utf-8") as fh:
        return json.load(fh)


# ── card_template.json contract ─────────────────────────────────────────────
def test_template_targets_the_d911_modeling_bucket(template):
    assert template["plan"] == "SOPO D911 PIPELINE"
    assert template["bucket"] == "MODELING"


def test_checklist_is_the_seven_items_in_order(template):
    assert template["checklist"] == [
        "Shop Prints", "Inspection Sheet", "Production Packets", "Program",
        "Cover Sheet", "Scribe Sheet", "Production",
    ]


def test_tube_only_items_are_real_checklist_items(template):
    """A typo in tube_only_checklist would silently never drop anything."""
    for item in template["tube_only_checklist"]:
        assert item in template["checklist"]


def test_label_map_slots_match_the_plans_label_order(template):
    """Plan label list top-to-bottom is category1..category5."""
    assert template["label_map"] == {
        "DIFFICULT": "category1",
        "MEDIUM": "category2",
        "SIMPLE": "category3",
        "SAW CUT": "category4",
        "TUBE LASER": "category5",
    }


# ── BATCH / NEST cell ───────────────────────────────────────────────────────
def test_batch_nest_splits_batch_first_nest_last(st):
    assert st._split_batch_nest("V092 503836") == ("V092", "503836")


def test_batch_nest_keeps_alphanumeric_nests(st):
    """'V085 S20085' -- a digits-only nest match drops these silently."""
    assert st._split_batch_nest("V085 S20085") == ("V085", "S20085")


def test_batch_nest_survives_extra_whitespace(st):
    assert st._split_batch_nest("  S043   504061 ") == ("S043", "504061")


@pytest.mark.parametrize("cell", ["", None, "478", 478])
def test_batch_nest_rejects_half_a_key(st, cell):
    """922 rows carry a bare batch number; those must not become cards."""
    assert st._split_batch_nest(cell) == (None, None)


# ── DATE cell -> due date ───────────────────────────────────────────────────
def test_due_date_formats_a_real_date(st):
    assert st._due_date_iso(dt.datetime(2026, 10, 30)) == "2026-10-30T00:00:00Z"


@pytest.mark.parametrize("cell", ["HOLD", "N/A", None, ""])
def test_non_dates_mean_no_due_date(st, cell):
    """The DATE column doubles as a status for unscheduled nests."""
    assert st._due_date_iso(cell) == ""


# ── NOTES -> SAW CUT / TUBE LASER ───────────────────────────────────────────
@pytest.mark.parametrize("notes,expected", [
    # explicit marker wins over the shape keyword
    ("HSS 3 X 3 X 0.250 TUBE (SAW)", "SAW CUT"),
    ("HSS 1.5 X 1.5 X 0.250 ANGLE (TL)", "TUBE LASER"),
    ("HSS FLAT 2.0 W X 0.375 THK (TL)", "TUBE LASER"),
    # unmarked -> first shape keyword decides
    ("HSS 2.5 X 2.5 X 0.313 TUBE", "TUBE LASER"),
    ("HSS 2.5X2.5X0.312 ANGLE", "TUBE LASER"),
    ("AL MC3X1.76 CHANNEL", "TUBE LASER"),
    ("SS CRES316 0.625 RD BAR", "SAW CUT"),
    ("HY-80 1.375 DIA ROUND", "SAW CUT"),
    ("HSS 0.500THK X 6.000W FLAT", "SAW CUT"),
    # batch-list Description fallback shape (used when NOTES is blank)
    ("TUBE ; STL ; 6.000 X 4.000 X 0.375 THK ; FT", "TUBE LASER"),
    ("BAR ; CRES 316L ; 0.625 DIA ; IN", "SAW CUT"),
])
def test_machine_label_from_material_text(st, template, notes, expected):
    assert st._resolve_machine(notes, template) == expected


def test_free_text_in_parens_does_not_beat_the_shape(st, template):
    """A real note: the parenthetical is a comment, not a machine marker --
    and it contains 'BARS', which must not out-rank the leading TUBE."""
    assert st._resolve_machine(
        "6.0 X 2.0 X 0.375 TUBE (NEED 2 MORE BARS/PATRIAL)",
        template) == "TUBE LASER"


@pytest.mark.parametrize("notes", ["", None, "AWAITING MATERIAL AND PO"])
def test_unknown_material_gets_no_machine_label(st, template, notes):
    """No guess: the card is created unlabelled and the run warns."""
    assert st._resolve_machine(notes, template) is None


@pytest.mark.parametrize("notes,is_tube", [
    ("HSS 6 X 4 X 0.375 TUBE", True),
    ("TUBE, SQUARE, MECHANICAL, STL, 3.000 X 3.000 X 0.250 THK", True),
    ("HSS 2.5X2.5X0.312 ANGLE", False),
    ("SS CRES316 0.625 RD BAR", False),
    ("", False),
])
def test_tube_detection(st, template, notes, is_tube):
    assert st._is_tube(notes, template) is is_tube


# ── whole-card assembly ─────────────────────────────────────────────────────
def _row(**kw):
    base = {"excel_row": 138, "raw_key": "V092 503836", "batch": "V092",
            "nest": "503836", "date": dt.datetime(2026, 10, 30),
            "notes": "HSS 6 X 4 X 0.375 TUBE", "difficulty": "SIMPLE"}
    base.update(kw)
    return base


def _label_map(st, template):
    return {st._norm_text(n): s for n, s in template["label_map"].items()}


def test_tube_card_is_built_end_to_end(st, template):
    warnings, unlabelled = [], []
    card, names = st._build_card(_row(), {"code": "218004493", "desc": ""},
                                 template, _label_map(st, template),
                                 warnings, unlabelled)
    assert card["title"] == "BATCH: V092 - NEST: 503836 (218004493)"
    assert card["bucket"] == "MODELING"
    assert card["dueDate"] == "2026-10-30T00:00:00Z"
    assert names == ["SIMPLE", "TUBE LASER"]
    assert card["labels"] == ["category3", "category5"]
    assert "Program" in card["checklist"]
    assert not warnings and not unlabelled


def test_program_is_dropped_on_non_tube_stock(st, template):
    warnings, unlabelled = [], []
    card, _ = st._build_card(_row(notes="HSS 2.5X2.5X0.312 ANGLE",
                                  difficulty="MEDIUM"),
                             {"code": "20-72-0540B", "desc": ""},
                             template, _label_map(st, template),
                             warnings, unlabelled)
    assert "Program" not in card["checklist"]
    assert card["checklist"] == ["Shop Prints", "Inspection Sheet",
                                 "Production Packets", "Cover Sheet",
                                 "Scribe Sheet", "Production"]
    # the rest of the card is untouched
    assert card["labels"] == ["category2", "category5"]


def test_missing_stock_code_falls_back_to_the_short_title(st, template):
    warnings, unlabelled = [], []
    card, _ = st._build_card(_row(), {"code": "", "desc": ""}, template,
                             _label_map(st, template), warnings, unlabelled)
    assert card["title"] == "BATCH: V092 - NEST: 503836"


def test_blank_notes_fall_back_to_the_batch_list_description(st, template):
    """6 of the 31 live NEED TEAMS/SETUP rows had an empty NOTES cell; the
    BATCH LIST description still resolves their machine + tube-ness."""
    warnings, unlabelled = [], []
    card, names = st._build_card(
        _row(notes=None, difficulty=None),
        {"code": "218019941", "desc": "TUBE ; STL ; 2.000 X 2.000 X 0.188 THK ; FT"},
        template, _label_map(st, template), warnings, unlabelled)
    assert names == ["TUBE LASER"]
    assert "Program" in card["checklist"]
    assert not unlabelled


def test_unresolvable_material_is_reported_not_guessed(st, template):
    warnings, unlabelled = [], []
    card, names = st._build_card(_row(notes="AWAITING MATERIAL"),
                                 {"code": "211076345", "desc": ""}, template,
                                 _label_map(st, template), warnings, unlabelled)
    assert names == ["SIMPLE"]
    assert card["labels"] == ["category3"]
    assert len(unlabelled) == 1 and "V092 503836" in unlabelled[0]


def test_unmapped_label_name_warns_instead_of_posting_a_bad_slot(st, template):
    warnings, unlabelled = [], []
    card, _ = st._build_card(_row(difficulty="CATASTROPHIC"),
                             {"code": "218004493", "desc": ""}, template,
                             _label_map(st, template), warnings, unlabelled)
    assert card["labels"] == ["category5"]   # machine label still applied
    assert any("CATASTROPHIC" in w for w in warnings)
