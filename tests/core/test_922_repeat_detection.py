"""922 repeat detection — the function 922 Setup and the Batch Repeater share.

`find_repeat_orders` was extracted from the Repeater's inline loop (v2.6.0) so
922 Setup's "Fill Out MPL + Find Repeats" stage can know the repeats BEFORE the
cards are generated. The properties pinned here:

  - the HIGHEST prior PO column wins (most recent prior batch);
  - columns at/after the new PO are never consulted;
  - the orders iterable is CALLER-SUPPLIED — 922 Setup feeds folder PPNs, so
    an order absent from the MPL's new column is still detected (a locked MPL
    that couldn't take the new column can't hide repeats);
  - matching is strip/case-insensitive on both sides;
  - `_repeat_folder_names` maps orders onto folders through the Repeater's
    EXACT `_order_matches_folder` — a '-H1' order must never claim '-H11'.
"""

import importlib.util
from pathlib import Path

import pandas as pd

_PLUGINS = Path(__file__).resolve().parents[2] / "plugins"


def _load(plugin: str, name: str):
    spec = importlib.util.spec_from_file_location(name, _PLUGINS / plugin / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _repeater():
    return _load("922_batch_repeater", "repeater_detect_test")


_DF = pd.DataFrame({
    "PO 480": ["H100-H1", "H200-H2", None],
    "PO 481": ["H100-H1", None, None],
    "PO 484": ["H400-H4", None, None],
})
_PO_COLUMNS = {480: "PO 480", 481: "PO 481", 484: "PO 484"}


def test_highest_prior_po_wins():
    mod = _repeater()
    repeats = mod.find_repeat_orders(_DF, _PO_COLUMNS, 483, ["H100-H1"])
    assert repeats == {"H100-H1": 481}          # 481 beats 480


def test_order_not_in_any_prior_column_is_not_a_repeat():
    mod = _repeater()
    assert mod.find_repeat_orders(_DF, _PO_COLUMNS, 483, ["H999-H9"]) == {}


def test_columns_at_or_after_the_new_po_are_ignored():
    mod = _repeater()
    # H400-H4 only exists in PO 484, which is NOT prior to 483.
    assert mod.find_repeat_orders(_DF, _PO_COLUMNS, 483, ["H400-H4"]) == {}
    # ...but for batch 485 it IS prior, so it counts.
    assert mod.find_repeat_orders(_DF, _PO_COLUMNS, 485, ["H400-H4"]) == {
        "H400-H4": 484}


def test_caller_supplied_orders_detected_without_a_new_po_column():
    # 922 Setup's property: the orders come from the batch's FOLDER PPNs, so
    # detection works even when the MPL has no 'PO 483' column at all.
    mod = _repeater()
    assert 483 not in _PO_COLUMNS
    repeats = mod.find_repeat_orders(_DF, _PO_COLUMNS, 483,
                                     ["H100-H1", "H200-H2", "H999-H9"])
    assert repeats == {"H100-H1": 481, "H200-H2": 480}


def test_matching_is_case_and_whitespace_insensitive():
    mod = _repeater()
    repeats = mod.find_repeat_orders(_DF, _PO_COLUMNS, 483, ["  h100-h1  "])
    # Keys are the CALLER's orders (stripped, case kept) — 922 Setup matches
    # them back onto its own folder names, so the caller's spelling must win.
    assert repeats == {"h100-h1": 481}


def test_empty_inputs_yield_no_repeats():
    mod = _repeater()
    assert mod.find_repeat_orders(pd.DataFrame(), {}, 483, ["H100-H1"]) == {}
    assert mod.find_repeat_orders(_DF, _PO_COLUMNS, 483, []) == {}
    assert mod.find_repeat_orders(_DF, _PO_COLUMNS, 483, ["", "   "]) == {}


# ── order -> folder mapping (922 Setup side, Repeater's exact matcher) ───────

def test_repeat_folder_names_uses_exact_ppn_match():
    setup = _load("922_setup", "setup922_detect_test")
    rep = _repeater()
    folders = ["X744-H7921467-H1", "X744-H7921467-H11", "Y100-H5555555-H2"]
    repeats = setup._repeat_folder_names(
        folders, {"H7921467-H1": 481}, rep._order_matches_folder)
    # -H1 claims exactly its own folder — never the -H11 prefix collision.
    assert repeats == {"X744-H7921467-H1"}


def test_repeat_folder_names_accepts_whole_folder_name_orders():
    setup = _load("922_setup", "setup922_detect_test2")
    rep = _repeater()
    repeats = setup._repeat_folder_names(
        ["X744-H7921467-H1"], {"X744-H7921467-H1": 480},
        rep._order_matches_folder)
    assert repeats == {"X744-H7921467-H1"}
