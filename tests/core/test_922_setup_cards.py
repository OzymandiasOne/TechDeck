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


# ── repeat cards (v2.6.0): straight into MODEL CHECK at creation ────────────
# Repeats are detected by the "Fill Out MPL + Find Repeats" stage before the
# cards are built; _build_cards then buckets them into repeat_bucket_format
# with the REPEAT slot appended. The flow-#2 tag pass is the second pass.

def test_repeat_folder_gets_model_check_bucket_and_repeat_label():
    mod = _load()
    cards = mod._build_cards(
        _TEMPLATE, "483", ["AAA-1", "BBB-2"], {"BBB-2": ["category3"]},
        repeat_folders={"BBB-2"}, repeat_slot="category19")
    by_title = {c["title"]: c for c in cards}
    rep = by_title["BATCH 483: BBB-2"]
    assert rep["bucket"] == "BATCH 483: MODEL CHECK"   # fallback format
    assert rep["labels"] == ["category3", "category19"]
    plain = by_title["BATCH 483: AAA-1"]
    assert plain["bucket"] == "BATCH 483"
    assert plain["labels"] == []


def test_no_repeat_args_matches_legacy_behavior():
    # The default call (no repeat args) must build byte-identical cards to a
    # call with an empty repeat set — pre-2.6.0 callers/tests stay valid.
    mod = _load()
    legacy = mod._build_cards(_TEMPLATE, "483", ["AAA-1"], {"AAA-1": ["category2"]})
    explicit = mod._build_cards(_TEMPLATE, "483", ["AAA-1"],
                                {"AAA-1": ["category2"]},
                                repeat_folders=set(), repeat_slot="category19")
    assert legacy == explicit
    assert legacy[0]["bucket"] == "BATCH 483"


def test_repeat_slot_not_duplicated():
    mod = _load()
    cards = mod._build_cards(
        _TEMPLATE, "483", ["AAA-1"], {"AAA-1": ["category19"]},
        repeat_folders={"AAA-1"}, repeat_slot="category19")
    assert cards[0]["labels"] == ["category19"]


def test_repeat_bucket_comes_from_template_key():
    mod = _load()
    tpl = dict(_TEMPLATE, repeat_bucket_format="BATCH {batch}: CHECKING")
    cards = mod._build_cards(tpl, "483", ["AAA-1"], {},
                             repeat_folders={"AAA-1"}, repeat_slot="category19")
    assert cards[0]["bucket"] == "BATCH 483: CHECKING"


def test_payload_contract_unchanged_with_repeats():
    # The repeat bucket rides inside the EXISTING per-task `bucket` key — the
    # payload shape the flow parses does not change at all.
    mod = _load()
    cards = mod._build_cards(_BUCKET_TEMPLATE, "488", ["AAA-1", "BBB-2"], {},
                             repeat_folders={"AAA-1"}, repeat_slot="category19")
    payload, _ = mod._build_payload(_BUCKET_TEMPLATE, "488", cards)
    assert set(payload) == {"plan", "batch", "buckets", "tasks"}
    for t in payload["tasks"]:
        assert set(t) == {"title", "bucket", "priority", "status",
                          "checklist", "labels"}


def test_real_template_repeat_bucket_is_in_buckets_list():
    # repeat_bucket_format must stay a member of `buckets`, or the flow would
    # never have created the bucket before a repeat task needs it.
    with open(_PLUGINS / "922_setup" / "card_template.json",
              encoding="utf-8") as fh:
        template = json.load(fh)
    fmt = template.get("repeat_bucket_format")
    assert fmt, "card_template.json lost its repeat_bucket_format key"
    formatted = [b.format(batch="488") for b in template["buckets"]]
    assert fmt.format(batch="488") in formatted
    assert template["label_map"].get("REPEAT"), \
        "card_template.json lost its REPEAT label_map entry"


def test_922_setup_hands_repeater_every_stage_option_key():
    # The consolidated run must keep telling the Repeater what already
    # happened (tag off by default, MPL halves skipped when Setup did them).
    src = (_PLUGINS / "922_setup" / "run.py").read_text(encoding="utf-8")
    assert "stage_options={" in src
    window = src.split("stage_options={", 1)[1][:400]
    for key in ('"distribute"', '"tag"', '"mpl_matrix"', '"master_parts"'):
        assert key in window, f"922 Setup stopped passing {key} to the Repeater"


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


def test_911_teams_cards_payload_contract_keys_exist_in_source():
    # Flow #3 reads plan / bucket / tasks. The payload moved out of 911_setup
    # into its own plugin on 2026-08-10 -- 911 Setup now imports it.
    window = _payload_window("911_teams_cards")
    for key in ('"plan"', '"bucket"', '"tasks"'):
        assert key in window, f"flow #3 payload lost its {key} key"


# ── BATCH PROGRESS card (v2.7.0): one per batch, top of the batch bucket ────
# The office hand-made the same batch-prep to-do card on every batch. It now
# rides in the flow #1 payload as the LAST task so Planner's top-insert puts
# it above the A-Z order cards in the plain 'BATCH {n}' bucket.

_PROGRESS_CHECKLIST = [
    "PO Download", "PO Setup", "Quote", "TechDeck - Pallet stamper",
    "TechDeck- Repeats", "Teams Cards", "Move Files over (M: Drive -> 922)",
    "Repeats", "Send Issues", "Rod Tags", "Forming Paperwork",
    "Kitting Paperwork", "Saw & TL Production Packets", "TechDeck LST Grabber",
]


def test_progress_card_is_posted_last_in_batch_bucket():
    mod = _load()
    tpl = dict(_BUCKET_TEMPLATE, progress_card={
        "title_format": "BATCH {batch} PROGRESS",
        "checklist": ["PO Download", "PO Setup"]})
    cards = mod._build_cards(tpl, "494", ["AAA-1", "BBB-2"], {},
                             repeat_folders={"BBB-2"}, repeat_slot="category19")
    payload, _ = mod._build_payload(tpl, "494", cards)
    assert [t["title"] for t in payload["tasks"]] == [
        "BATCH 494: BBB-2", "BATCH 494: AAA-1", "BATCH 494 PROGRESS"]
    progress = payload["tasks"][-1]
    # Same per-task keys as an order card: flow #1 parses it unchanged.
    assert set(progress) == {"title", "bucket", "priority", "status",
                             "checklist", "labels"}
    assert progress["bucket"] == "BATCH 494"          # never MODEL CHECK
    assert progress["labels"] == []
    assert progress["checklist"] == ["PO Download", "PO Setup"]
    assert progress["priority"] == "Medium"
    assert progress["status"] == "Not started"
    # The order cards are untouched by the extra task.
    assert len(cards) == 2


def test_no_progress_card_when_template_lacks_the_block():
    mod = _load()
    cards = mod._build_cards(_BUCKET_TEMPLATE, "494", ["AAA-1"], {})
    payload, _ = mod._build_payload(_BUCKET_TEMPLATE, "494", cards)
    assert [t["title"] for t in payload["tasks"]] == ["BATCH 494: AAA-1"]
    assert mod._build_progress_card(_BUCKET_TEMPLATE, "494") is None


def test_real_template_progress_card_matches_the_office_card():
    # The shipped checklist must be the office's 14 items in the exact order
    # they work them (screenshot of the hand-made Batch 494 card, 2026-09-11).
    mod = _load()
    with open(_PLUGINS / "922_setup" / "card_template.json",
              encoding="utf-8") as fh:
        template = json.load(fh)
    progress = mod._build_progress_card(template, "494")
    assert progress is not None, "card_template.json lost its progress_card"
    assert progress["title"] == "BATCH 494 PROGRESS"
    # v2.7.2 (C.D. 2026-09-16): the card lives on its own in the HOLD bucket.
    # It must be one of the buckets the flow find-or-creates, or the flow's
    # fallback would quietly drop it back into the plain batch bucket.
    assert progress["bucket"] == "BATCH 494: HOLD"
    assert progress["bucket"] in [b.format(batch="494") for b in template["buckets"]]
    assert progress["checklist"] == _PROGRESS_CHECKLIST
    assert len(progress["checklist"]) <= 20, "Planner caps a checklist at 20"
    # Wired into the real payload, last so it lands on top.
    cards = mod._build_cards(template, "494", ["AAA-1"], {})
    payload, _ = mod._build_payload(template, "494", cards)
    assert payload["tasks"][-1]["title"] == "BATCH 494 PROGRESS"
