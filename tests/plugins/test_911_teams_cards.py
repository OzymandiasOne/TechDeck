"""Tests for 911 Setup's Generate Teams Cards stage (v1.8.0).

Every fixture string below is a REAL value copied off the live EB 922 Schedule
(CURRENT PIPELINE) or a 911 BATCH LIST on 2026-08-03 -- the point of these
tests is that the parsing keeps working on the data that actually arrives, not
on tidied-up samples.
"""

import datetime as dt
import importlib.util
import json
import threading
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
    # The Teams TAB reads "SOPO D911 PIPELINE", but the Planner PLAN the
    # connector resolves is named "EB SOPO D911" -- flow #3 is bound to that.
    assert template["plan"] == "EB SOPO D911"
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
    """Plan label list top-to-bottom: slot 1 is the unnamed Pink default,
    the named labels start at category2. The first live post (2026-08-04)
    shipped a map that started at category1 and every card came out one
    slot off -- SAW CUT lit up SIMPLE, so cards showed two difficulties."""
    assert template["label_map"] == {
        "DIFFICULT": "category2",
        "MEDIUM": "category3",
        "SIMPLE": "category4",
        "SAW CUT": "category5",
        "TUBE LASER": "category6",
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
    # 1. says TUBE -> it IS a tube -> tube laser, marker or not
    ("HSS 2.5 X 2.5 X 0.313 TUBE", "TUBE LASER"),
    ("HSS 2 X 2 X 0.188 TUBE (TL)", "TUBE LASER"),
    # 2. not a tube, but flagged (TL) -> going on the tube laser anyway
    ("HSS 1.5 X 1.5 X 0.250 ANGLE (TL)", "TUBE LASER"),
    ("HSS FLAT 2.0 W X 0.375 THK (TL)", "TUBE LASER"),
    ("AL CHAN MC3 X 1.76 (TL)", "TUBE LASER"),
    # 3. everything else saws -- shape does NOT imply the tube laser
    ("HSS 2.5X2.5X0.312 ANGLE", "SAW CUT"),
    ("AL MC3X1.76 CHANNEL", "SAW CUT"),
    ("SS CRES316 0.625 RD BAR", "SAW CUT"),
    ("HY-80 1.375 DIA ROUND", "SAW CUT"),
    ("HSS 0.500THK X 6.000W FLAT", "SAW CUT"),
    ("AWAITING MATERIAL AND PO", "SAW CUT"),
    # batch-list Description fallback wording (used when NOTES is blank)
    ("TUBE ; STL ; 6.000 X 4.000 X 0.375 THK ; FT", "TUBE LASER"),
    ("BAR ; CRES 316L ; 0.625 DIA ; IN", "SAW CUT"),
    ("ANGLE ; STL ; 2.000 X 2.000 X 0.500 THK ; FT", "SAW CUT"),
])
def test_machine_label_from_material_text(st, template, notes, expected):
    assert st._resolve_machine(notes, template) == expected


def test_free_text_in_parens_is_not_a_marker(st, template):
    """A real note whose parenthetical is a comment, not a machine flag."""
    assert st._resolve_machine(
        "6.0 X 2.0 X 0.375 TUBE (NEED 2 MORE BARS/PATRIAL)",
        template) == "TUBE LASER"


@pytest.mark.parametrize("notes", ["", None, "   "])
def test_no_material_text_at_all_gets_no_machine_label(st, template, notes):
    """Only a truly empty cell is unlabelled -- and the run warns about it."""
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
    assert card["labels"] == ["category4", "category6"]
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
    # the rest of the card is untouched (MEDIUM + SAW CUT)
    assert card["labels"] == ["category3", "category5"]


def test_unscheduled_nest_omits_duedate_entirely(st, template):
    """HOLD / N/A in the DATE column must leave the key OUT, not send "" --
    the flow feeds it straight into Planner's Due Date Time, where an empty
    string fails the action but an absent key means no due date."""
    warnings, unlabelled = [], []
    card, _ = st._build_card(_row(date="HOLD"), {"code": "218004493", "desc": ""},
                             template, _label_map(st, template),
                             warnings, unlabelled)
    assert "dueDate" not in card


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


def test_no_material_anywhere_is_reported_not_guessed(st, template):
    """Blank NOTES *and* no batch-list description -> no machine label, and
    the nest is named in the end-of-run warning."""
    warnings, unlabelled = [], []
    card, names = st._build_card(_row(notes=None),
                                 {"code": "211076345", "desc": ""}, template,
                                 _label_map(st, template), warnings, unlabelled)
    assert names == ["SIMPLE"]
    assert card["labels"] == ["category4"]
    assert len(unlabelled) == 1 and "V092 503836" in unlabelled[0]


def test_unmapped_label_name_warns_instead_of_posting_a_bad_slot(st, template):
    warnings, unlabelled = [], []
    card, _ = st._build_card(_row(difficulty="CATASTROPHIC"),
                             {"code": "218004493", "desc": ""}, template,
                             _label_map(st, template), warnings, unlabelled)
    assert card["labels"] == ["category6"]   # machine label still applied
    assert any("CATASTROPHIC" in w for w in warnings)


# ── stage-level: what gets skipped, and re-run duplicate protection ─────────
SCHEDULE = [
    # a normal, fully-specified nest
    {"excel_row": 138, "raw_key": "V092 503836", "batch": "V092",
     "nest": "503836", "date": dt.datetime(2026, 10, 30),
     "notes": "HSS 6 X 4 X 0.375 TUBE", "difficulty": "SIMPLE"},
    # NOTES not filled in yet -> no card
    {"excel_row": 163, "raw_key": "S033 503810", "batch": "S033",
     "nest": "503810", "date": dt.datetime(2026, 11, 20),
     "notes": None, "difficulty": None},
    # BATCH LIST code unreadable -> no card (would duplicate later)
    {"excel_row": 144, "raw_key": "V094 503893", "batch": "V094",
     "nest": "503893", "date": dt.datetime(2026, 11, 6),
     "notes": "HSS 1.5 X 1.5 X 0.250 ANGLE (TL)", "difficulty": "MEDIUM"},
]
MATERIALS = {
    "V092": {"503836": {"code": "218004493", "desc": ""}},
    "S033": {"503810": {"code": "218019941", "desc": "TUBE ; STL ; 2.000"}},
    "V094": {},          # nest absent -> no code
}


def _stage(st, tmp_path, monkeypatch, settings=None):
    """Run the stage with the schedule + BATCH LISTs stubbed out, capturing
    the payload that would be POSTed. Returns (posted_payloads, log_lines)."""
    posted, lines = [], []
    monkeypatch.setattr(st, "_read_schedule_rows",
                        lambda *a, **k: ([dict(r) for r in SCHEDULE], ""))
    monkeypatch.setattr(st, "_read_batch_list_materials",
                        lambda root, batch, log: (MATERIALS.get(batch, {}), ""))
    monkeypatch.setattr(st, "_ledger_path",
                        lambda: tmp_path / "911_setup_posted_cards.json")
    monkeypatch.setattr(st.sdk, "post_webhook",
                        lambda url, payload, log: posted.append(payload) or True)
    params = {"log": lines.append, "console": None,
              "settings": settings if settings is not None else {}}
    st._run_teams_cards(params, lambda v: None, threading.Event(), "")
    return posted, lines


def test_blank_notes_and_missing_code_are_both_skipped(st, tmp_path, monkeypatch):
    posted, lines = _stage(st, tmp_path, monkeypatch)
    assert len(posted) == 1
    titles = [t["title"] for t in posted[0]["tasks"]]
    assert titles == ["BATCH: V092 - NEST: 503836 (218004493)"]
    blob = "\n".join(lines)
    # both skips are REPORTED, not silent
    assert "S033 503810" in blob and "NOTES" in blob
    assert "V094 503893" in blob and "Material" in blob


def test_rerun_does_not_repost_what_it_already_created(st, tmp_path, monkeypatch):
    first, _ = _stage(st, tmp_path, monkeypatch)
    assert len(first[0]["tasks"]) == 1
    second, lines = _stage(st, tmp_path, monkeypatch)
    assert second == []                      # nothing POSTed at all
    assert "Already carded" in "\n".join(lines)


def test_a_failed_post_stays_reofferable(st, tmp_path, monkeypatch):
    """The ledger records a 2xx only -- a webhook failure must not make the
    nest look done."""
    monkeypatch.setattr(st, "_read_schedule_rows",
                        lambda *a, **k: ([dict(r) for r in SCHEDULE], ""))
    monkeypatch.setattr(st, "_read_batch_list_materials",
                        lambda root, batch, log: (MATERIALS.get(batch, {}), ""))
    monkeypatch.setattr(st, "_ledger_path",
                        lambda: tmp_path / "911_setup_posted_cards.json")
    monkeypatch.setattr(st.sdk, "post_webhook", lambda url, payload, log: False)
    st._run_teams_cards({"log": lambda m: None, "console": None, "settings": {}},
                        lambda v: None, threading.Event(), "")
    assert st._load_posted_titles(lambda m: None) == set()

    posted, _ = _stage(st, tmp_path, monkeypatch)
    assert len(posted[0]["tasks"]) == 1      # re-offered on the next run


def test_ledger_survives_a_bom(st, tmp_path, monkeypatch):
    """The ledger is documented as user-editable, and anything on Windows that
    rewrites it (Notepad, PowerShell Out-File -Encoding utf8) adds a BOM.
    Plain utf-8 rejects that and the whole ledger silently stops suppressing --
    caught live, 2026-08-03."""
    led = tmp_path / "911_setup_posted_cards.json"
    monkeypatch.setattr(st, "_ledger_path", lambda: led)
    led.write_text('{"titles": ["BATCH: V092 - NEST: 503836 (218004493)"]}',
                   encoding="utf-8-sig")
    assert st._load_posted_titles(lambda m: None) == {
        "BATCH: V092 - NEST: 503836 (218004493)"}


def test_dry_run_never_writes_the_ledger(st, tmp_path, monkeypatch):
    posted, _ = _stage(st, tmp_path, monkeypatch, settings={"card_dry_run": True})
    assert posted == []
    assert not (tmp_path / "911_setup_posted_cards.json").exists()
    # ...so the real run still offers the card
    posted2, _ = _stage(st, tmp_path, monkeypatch)
    assert len(posted2[0]["tasks"]) == 1
