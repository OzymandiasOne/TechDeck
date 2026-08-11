"""The nest picker — choose which queued nests get a Teams card.

C.D. 2026-08-06: "Sometimes I want to make only a couple Teams cards. Ideally
I'd be able to select which of the orders in the schedule I want and only make
those."

It lives in the shared card engine (`911_teams_cards`), so BOTH entry points
get it: the standalone app and 911 Setup's optional Teams Cards stage. These
tests drive the engine directly, which is exactly what 911 Setup calls.

The picker deliberately runs LAST — after the blank-NOTES/no-stock-code skips
and after the already-carded ledger — so every row on screen is a nest that
would genuinely have been posted.
"""

import datetime as dt
import importlib.util
import threading
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[2] / "plugins" / "911_teams_cards"


@pytest.fixture(scope="module")
def st():
    spec = importlib.util.spec_from_file_location(
        "st_911_teams_cards_picker", PLUGIN_DIR / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Two fully-cardable nests, so there is something to choose BETWEEN.
PICKABLE = [
    {"excel_row": 138, "raw_key": "V092 503836", "batch": "V092",
     "nest": "503836", "date": dt.datetime(2026, 10, 30),
     "notes": "HSS 6 X 4 X 0.375 TUBE", "difficulty": "SIMPLE"},
    {"excel_row": 140, "raw_key": "V093 503840", "batch": "V093",
     "nest": "503840", "date": dt.datetime(2026, 11, 6),
     "notes": "HSS 2.5X2.5X0.312 ANGLE", "difficulty": "DIFFICULT"},
]
MATERIALS = {
    "V092": {"503836": {"code": "218004493", "desc": ""}},
    "V093": {"503840": {"code": "218004494", "desc": ""}},
}


class _Picker:
    """A console offering only request_selection. ``choose`` maps the offered
    labels to what the user ticked; returning None means they cancelled."""

    def __init__(self, choose):
        self._choose = choose
        self.offered = None
        self.kwargs = None

    def request_selection(self, items, done_items=None, **kwargs):
        self.offered = list(items)
        self.kwargs = kwargs
        return self._choose(list(items))


def _stage(st, tmp_path, monkeypatch, choose, rows_in=None, settings=None):
    """Run the card stage with a picking console. Everything that touches the
    real schedule or the network is stubbed; the picker logic is real."""
    schedule = rows_in if rows_in is not None else PICKABLE
    posted, lines, writes = [], [], []
    monkeypatch.setattr(st, "_read_schedule_rows",
                        lambda *a, **k: ([dict(r) for r in schedule], ""))
    monkeypatch.setattr(st, "_read_batch_list_materials",
                        lambda root, batch, log: (MATERIALS.get(batch, {}), ""))
    monkeypatch.setattr(st, "_ledger_path",
                        lambda: tmp_path / "911_setup_posted_cards.json")
    monkeypatch.setattr(st.sdk, "post_webhook",
                        lambda url, payload, log: posted.append(payload) or True)
    status_rows = [{"excel_row": r["excel_row"], "batch": r["batch"],
                    "nest": r["nest"], "status": "NEED TEAMS/SETUP"}
                   for r in schedule]
    monkeypatch.setattr(st, "_schedule_status_rows",
                        lambda *a, **k: (Path("s.xlsx"), 6, status_rows, ""))
    monkeypatch.setattr(st, "_write_schedule_statuses",
                        lambda p, c, u: (writes.extend(u) or (len(u), "")))
    picker = _Picker(choose)
    ev = threading.Event()
    ok = st._run_teams_cards(
        {"log": lines.append, "console": picker,
         "settings": settings or {}, "cancel_event": ev},
        lambda v: None, ev, "")
    return {"posted": posted, "lines": lines, "writes": writes,
            "picker": picker, "ok": ok, "event": ev}


def _titles(res):
    return [t["title"] for p in res["posted"] for t in p["tasks"]]


# ── what gets offered ───────────────────────────────────────────────────────
def test_every_queued_nest_is_offered_and_ticked_by_default(st, tmp_path, monkeypatch):
    res = _stage(st, tmp_path, monkeypatch, choose=lambda items: items)
    assert len(res["picker"].offered) == 2
    assert len(_titles(res)) == 2      # the common case is still one click


def test_the_row_says_what_you_need_to_decide(st, tmp_path, monkeypatch):
    res = _stage(st, tmp_path, monkeypatch, choose=lambda items: items)
    row = next(r for r in res["picker"].offered if "503836" in r)
    assert "V092 503836" in row                      # how the schedule reads
    assert "SIMPLE" in row and "TUBE LASER" in row   # the labels it will carry
    assert "2026-10-30" in row
    assert "218004493" not in row                    # stock code is title-only


def test_the_dialog_is_labelled_for_nests_not_generic_items(st, tmp_path, monkeypatch):
    res = _stage(st, tmp_path, monkeypatch, choose=lambda items: items)
    kw = res["picker"].kwargs
    assert kw["noun"] == "nest"
    assert "Card" in kw["run_button_text"]
    assert "queued" in kw["prompt_note"]


# ── what picking actually does ──────────────────────────────────────────────
def test_unticking_a_nest_cards_only_the_other(st, tmp_path, monkeypatch):
    res = _stage(st, tmp_path, monkeypatch,
                 choose=lambda items: [i for i in items if "503836" in i])
    assert _titles(res) == ["BATCH: V092 - NEST: 503836 (218004493)"]
    assert "Skipping 1 nest(s) you unticked" in "\n".join(res["lines"])


def test_an_unticked_nest_stays_queued_on_the_schedule(st, tmp_path, monkeypatch):
    """The important half. Skipping a card must NOT advance that nest's
    STATUS — otherwise it silently leaves the queue having never been carded,
    and nothing would ever offer it again."""
    res = _stage(st, tmp_path, monkeypatch,
                 choose=lambda items: [i for i in items if "503836" in i])
    assert [w[0] for w in res["writes"]] == [138]    # only the carded row moved
    assert all(w[1] == "NEED SETUP" for w in res["writes"])


def test_cancelling_cards_nothing_and_flags_the_run(st, tmp_path, monkeypatch):
    res = _stage(st, tmp_path, monkeypatch, choose=lambda items: None)
    assert res["posted"] == [] and res["writes"] == []
    assert res["ok"] is False
    assert res["event"].is_set(), (
        "a cancelled picker must not score a ticket-earning success")
    assert "cancelled" in "\n".join(res["lines"]).lower()


def test_ticking_nothing_is_not_a_cancel(st, tmp_path, monkeypatch):
    """An empty submit means 'not right now', not 'abort'. Nothing posts, but
    the run is a clean success and no schedule row moves."""
    res = _stage(st, tmp_path, monkeypatch, choose=lambda items: [])
    assert res["posted"] == [] and res["writes"] == []
    assert res["ok"] is True and not res["event"].is_set()
    assert "No nests selected" in "\n".join(res["lines"])


# ── where the picker sits in the pipeline ───────────────────────────────────
def test_nothing_already_carded_is_ever_offered(st, tmp_path, monkeypatch):
    """It runs AFTER the ledger, so the list is exactly what would be posted —
    never a nest that was going to be suppressed anyway."""
    _stage(st, tmp_path, monkeypatch, choose=lambda items: items)
    again = _stage(st, tmp_path, monkeypatch, choose=lambda items: items)
    assert again["picker"].offered is None, "second run had nothing to offer"


def test_a_nest_with_no_source_material_is_never_offered(st, tmp_path, monkeypatch):
    """Blank NOTES already means no card. Offering it would be a row you can
    tick that then does nothing."""
    rows = [dict(PICKABLE[0]), dict(PICKABLE[1], notes=None)]
    res = _stage(st, tmp_path, monkeypatch, choose=lambda items: items,
                 rows_in=rows)
    assert len(res["picker"].offered) == 1
    assert "503840" not in " ".join(res["picker"].offered)


def test_a_dry_run_still_lets_you_pick(st, tmp_path, monkeypatch):
    res = _stage(st, tmp_path, monkeypatch,
                 choose=lambda items: [i for i in items if "503840" in i],
                 settings={"card_dry_run": True})
    assert res["picker"].offered is not None
    assert res["posted"] == []                      # dry run posts nothing
    assert res["writes"] == []                      # ...and advances nothing


# ── round-trip safety ───────────────────────────────────────────────────────
def test_duplicate_schedule_rows_both_survive(st, tmp_path, monkeypatch):
    """SelectionDialog hands back the chosen STRINGS, so two identical rows
    would be indistinguishable coming back. A duplicated batch+nest is a
    schedule data error, not a reason to crash — number them, keep both."""
    dupe = [dict(PICKABLE[0]), dict(PICKABLE[0])]
    res = _stage(st, tmp_path, monkeypatch, choose=lambda items: items,
                 rows_in=dupe)
    assert len(res["picker"].offered) == 2
    assert len(set(res["picker"].offered)) == 2, "duplicates collapsed into one"


def test_a_headless_run_cards_everything_without_a_dialog(st, tmp_path, monkeypatch):
    """Scheduled/CLI runs have no console. That must not hang, and must not
    silently drop nests either — no dialog means run them all."""
    posted, writes = [], []
    monkeypatch.setattr(st, "_read_schedule_rows",
                        lambda *a, **k: ([dict(r) for r in PICKABLE], ""))
    monkeypatch.setattr(st, "_read_batch_list_materials",
                        lambda root, batch, log: (MATERIALS.get(batch, {}), ""))
    monkeypatch.setattr(st, "_ledger_path", lambda: tmp_path / "led.json")
    monkeypatch.setattr(st.sdk, "post_webhook",
                        lambda url, payload, log: posted.append(payload) or True)
    monkeypatch.setattr(st, "_schedule_status_rows",
                        lambda *a, **k: (Path("s.xlsx"), 6, [], ""))
    monkeypatch.setattr(st, "_write_schedule_statuses",
                        lambda p, c, u: (writes.extend(u) or (len(u), "")))
    ev = threading.Event()
    st._run_teams_cards({"log": lambda m: None, "console": None,
                         "settings": {}, "cancel_event": ev},
                        lambda v: None, ev, "")
    assert len([t for p in posted for t in p["tasks"]]) == 2
    assert not ev.is_set()
