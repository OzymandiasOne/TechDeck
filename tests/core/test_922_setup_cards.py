"""922 Setup — Teams card ordering.

Planner's "Create a task" top-inserts each new card, so posting order folders in
natural A-Z made the bucket read Z-A (user report, 2026-07-27). Cards are built
A-Z but POSTED in reverse (`_order_for_planner`) so the alphabetically-first card
is created last, lands on top, and the bucket reads A-Z top-to-bottom.
"""

import importlib.util
from pathlib import Path

_RUN_PY = Path(__file__).resolve().parents[2] / "plugins" / "922_setup" / "run.py"


def _load():
    spec = importlib.util.spec_from_file_location("run922_test", _RUN_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_TEMPLATE = {
    "title_format": "BATCH {batch}: {folder}",
    "bucket_format": "BATCH {batch}",
    "priority": "Medium",
    "status": "Not started",
    "checklist": ["TL Print", "Saw Print"],
}


def test_build_cards_preserves_folder_order():
    mod = _load()
    folders = ["AAA-1", "BBB-2", "CCC-3"]
    cards = mod._build_cards(_TEMPLATE, "483", folders, {})
    assert [c["title"] for c in cards] == [
        "BATCH 483: AAA-1", "BATCH 483: BBB-2", "BATCH 483: CCC-3"]


def test_cards_posted_in_reverse_so_bucket_reads_az():
    mod = _load()
    folders = ["AAA-1", "BBB-2", "CCC-3"]           # already A-Z (sorted iterdir)
    posted = mod._order_for_planner(mod._build_cards(_TEMPLATE, "483", folders, {}))
    # Post order is reversed: first-posted (Z) ends at the bottom, last-posted (A)
    # lands on top => the bucket reads A-Z top-to-bottom.
    assert [c["title"] for c in posted] == [
        "BATCH 483: CCC-3", "BATCH 483: BBB-2", "BATCH 483: AAA-1"]


def test_order_for_planner_does_not_mutate_input():
    mod = _load()
    cards = mod._build_cards(_TEMPLATE, "483", ["A-1", "B-2"], {})
    original = list(cards)
    mod._order_for_planner(cards)
    assert cards == original                         # returns a new list


def test_order_for_planner_preserves_card_content():
    mod = _load()
    cards = mod._build_cards(
        _TEMPLATE, "483", ["A-1"], {"A-1": ["category2"]})
    posted = mod._order_for_planner(cards)
    assert posted[0]["labels"] == ["category2"]
    assert posted[0]["checklist"] == ["TL Print", "Saw Print"]
    assert posted[0]["bucket"] == "BATCH 483"
