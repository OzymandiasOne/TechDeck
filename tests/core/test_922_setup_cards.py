"""922 Setup — Teams card ordering + the flow #1 payload contract.

Planner's "Create a task" top-inserts each new card, so posting order folders in
natural A-Z made the bucket read Z-A (user report, 2026-07-27). Cards are built
A-Z but POSTED in reverse (`_order_for_planner`) so the alphabetically-first card
is created last, lands on top, and the bucket reads A-Z top-to-bottom.

The payload-contract tests exist because that very v2.3.3 edit rewrote the
payload dict inline and dropped the `buckets` key — the flow's For_each_bucket
foreach'd Null and hard-failed in 858ms while TechDeck logged DONE (HTTP 202 is
"accepted", not "succeeded"; bit C.D., Batch 488, 2026-08-05). Every key
the Power Automate flows read is asserted here so it can't silently vanish.
"""

import importlib.util
import json
from pathlib import Path

_PLUGINS = Path(__file__).resolve().parents[2] / "plugins"
_RUN_PY = _PLUGINS / "922_setup" / "run.py"


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


# ── flow #1 payload contract ────────────────────────────────────────────────
# Every key the 'TechDeck 922 Setup - Create Production Cards' flow reads.
# The regression these pin down: v2.3.3 rewrote the payload dict inline and
# dropped 'buckets' — the flow foreach'd Null and hard-failed on every
# 0.8.6.11 run while TechDeck logged DONE (Batch 488, 2026-08-05).

_BUCKET_TEMPLATE = dict(_TEMPLATE, plan="D922 PIPELINE", buckets=[
    "BATCH {batch}: HOLD", "BATCH {batch}", "BATCH {batch}: MODEL CHECK",
    "BATCH {batch}: 7000", "BATCH {batch}: SHOP READY"])


def test_payload_carries_every_flow_contract_key():
    mod = _load()
    cards = mod._build_cards(_BUCKET_TEMPLATE, "488", ["AAA-1", "BBB-2"], {})
    payload, buckets = mod._build_payload(_BUCKET_TEMPLATE, "488", cards)

    assert set(payload) == {"plan", "batch", "buckets", "tasks"}
    assert payload["plan"] == "D922 PIPELINE"
    assert payload["batch"] == "488"
    # buckets: the ordered left-to-right set, batch formatted in, and the SAME
    # list the caller logs — never a second divergent copy.
    assert payload["buckets"] == [
        "BATCH 488: HOLD", "BATCH 488", "BATCH 488: MODEL CHECK",
        "BATCH 488: 7000", "BATCH 488: SHOP READY"]
    assert payload["buckets"] is buckets
    # tasks: reverse-posted, each card carrying the keys the flow reads.
    assert [t["title"] for t in payload["tasks"]] == [
        "BATCH 488: BBB-2", "BATCH 488: AAA-1"]
    assert set(payload["tasks"][0]) == {
        "title", "bucket", "priority", "status", "checklist", "labels"}


def test_payload_buckets_never_empty_without_template_list():
    # A template with no buckets list still yields the single card bucket —
    # the foreach must always get a real array.
    mod = _load()
    cards = mod._build_cards(_TEMPLATE, "488", ["AAA-1"], {})
    payload, _ = mod._build_payload(_TEMPLATE, "488", cards)
    assert payload["buckets"] == ["BATCH 488"]


def test_real_template_matches_the_payload_contract():
    # The shipped card_template.json must feed the contract, not just fixtures.
    mod = _load()
    with open(_PLUGINS / "922_setup" / "card_template.json",
              encoding="utf-8") as fh:
        template = json.load(fh)
    cards = mod._build_cards(template, "488", ["AAA-1"], {})
    payload, _ = mod._build_payload(template, "488", cards)
    assert payload["plan"] == "D922 PIPELINE"
    assert "BATCH 488" in payload["buckets"]
    assert len(payload["buckets"]) == 5


# ── sibling flow payload contracts (same defect class) ──────────────────────

def _payload_window(plugin: str) -> str:
    """The source right after `payload = {` — wide enough to hold the whole
    dict literal (splitting on the first `}` truncates at an f-string brace)."""
    src = (_PLUGINS / plugin / "run.py").read_text(encoding="utf-8")
    assert "payload = {" in src, f"{plugin} no longer builds a payload dict"
    return src.split("payload = {", 1)[1][:600]


def test_repeat_tagger_payload_contract_keys_exist_in_source():
    # Flow #2's payload is built inline in 922_batch_repeater; assert the
    # source still assigns every key the flow reads.
    window = _payload_window("922_batch_repeater")
    for key in ('"plan"', '"batch"', '"bucket"', '"label"', '"titles"'):
        assert key in window, f"flow #2 payload lost its {key} key"


def test_911_setup_payload_contract_keys_exist_in_source():
    # Flow #3 reads plan / bucket / tasks.
    window = _payload_window("911_setup")
    for key in ('"plan"', '"bucket"', '"tasks"'):
        assert key in window, f"flow #3 payload lost its {key} key"
