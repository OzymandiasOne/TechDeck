"""The road on screen: doors, cards, fire, altar, the forge, the book."""
import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QKeyEvent

from techdeck.ui.void_game.rules import HIM, YOU
from techdeck.ui.void_game.window import VoidTable
from tests.void_game.test_table import quiet, ready, settle


@pytest.fixture
def table(qapp, tmp_path, monkeypatch):
    import techdeck.ui.void_game.window as win
    monkeypatch.setattr(win, "settings_path", lambda: str(tmp_path / "void_game.json"))
    w = VoidTable(seed=3)
    w.timer.stop()
    yield w
    w.close()            # no app-wide DeferredDelete flush: it ran other suites' stale deletes too (crashed the full run, 2026-10-05)


def press(w, key, text=""):
    w.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, text))


def rig_end(w: VoidTable, you_win: bool):
    """End the fight by decree, then let the table notice."""
    g = w.game
    g.phase, g.winner, g.scale = "over", (YOU if you_win else HIM), (6 if you_win else -5)
    w.enqueue([type("E", (), {"kind": "game_over", "data": {"winner": g.winner}, "__getitem__": lambda s, k: s.data[k], "get": lambda s, k, d=None: s.data.get(k, d)})()])
    settle(w)


def to_road(w: VoidTable):
    ready(w)
    rig_end(w, True)
    quiet(w)
    press(w, Qt.Key.Key_Space)             # his last word is out: the wipe, then the road
    settle(w)
    quiet(w)


def test_the_first_door_opens_itself_onto_the_table(table):
    assert table.scene == "fight" and table.game is not None
    assert table.run.step == 1


def test_a_win_leads_to_three_doors_and_a_lit_lamp(table):
    to_road(table)
    assert table.scene == "road" and len(table.run.offers) == 3
    assert table.run.step == 1
    assert table.frame is not None
    kinds = {k[0] for k, _ in table.hits}
    assert "door" in kinds


def test_a_lost_fight_costs_a_candle_and_the_road_goes_on(table):
    ready(table)
    rig_end(table, False)
    assert table.run.candles == 1
    quiet(table); press(table, Qt.Key.Key_Space); settle(table); quiet(table)
    assert table.scene == "road"


def test_the_forge_makes_a_deathcard_and_he_keeps_it(table):
    table.run.candles = 1
    ready(table)
    rig_end(table, False)
    assert table.run.dead
    quiet(table); press(table, Qt.Key.Key_Space); settle(table)
    assert table.scene == "forge" and table.forge_step == 0
    assert table.forge_first, "the first death of all: the guided forge"
    said = [table.caption_key] + [c[2] for c in table.captions]
    assert "deathcard_first_time" in said and "deathcard_cost_first_time" in said
    for step in range(3):
        quiet(table)                                   # his question waits for a key...
        press(table, Qt.Key.Key_Space)                 # ...then Space picks the card
        assert table.forge_step == step + 1
    said = [table.caption_key] + [c[2] for c in table.captions]
    assert "deathcard_before_named_first_time" in said
    quiet(table)
    assert table.forge_step == 3
    for ch in "Ant hony":
        press(table, Qt.Key.Key_A, ch)
    assert table.forge_name == "ANT HONY"
    press(table, Qt.Key.Key_Backspace)
    press(table, Qt.Key.Key_Return)
    assert table.scene == "digitize" and table.run.deathcard is not None
    assert table.run.deathcard.name == "ANT HON"
    said = [table.caption_key] + [c[2] for c in table.captions]
    assert "deathcard_post_named" in said and "digitize" in said
    assert table.settings["memory"]["deathcards"][0]["name"] == "ANT HON"
    for _ in range(40):
        table._tick()
    assert table.frame is not None


def test_a_card_choice_adds_to_the_deck(table):
    to_road(table)
    table.run.offers = [table.run._stop("choice")] * 3
    press(table, Qt.Key.Key_Space)
    quiet(table)
    assert table.scene == "pick"
    n = len(table.run.deck)
    press(table, Qt.Key.Key_D)
    press(table, Qt.Key.Key_Space)
    assert len(table.run.deck) == n + 1
    settle(table); quiet(table)                          # the card flicks into you, the scene sweeps
    assert table.scene == "road"


def test_the_fire_and_tab_to_leave(table):
    to_road(table)
    table.run.offers = [table.run._stop("fire")] * 3
    press(table, Qt.Key.Key_Space); quiet(table)
    assert table.scene == "fire"
    card = table.run.deck[0]
    press(table, Qt.Key.Key_Space); quiet(table)
    assert card.power + card.health > 0 or card not in table.run.deck
    settle(table); quiet(table)                          # one rest, no second offered: the card departs
    assert table.scene == "road"


def test_the_altar_takes_one_and_marks_another(table):
    to_road(table)
    table.run.offers = [table.run._stop("altar")] * 3
    press(table, Qt.Key.Key_Space); quiet(table)
    assert table.scene == "altar"
    n = len(table.run.deck)
    press(table, Qt.Key.Key_Space)                       # giver
    press(table, Qt.Key.Key_D); press(table, Qt.Key.Key_Space)   # taker
    assert len(table.run.deck) == n - 1
    settle(table); quiet(table)                          # the marked card flicks into you
    assert table.scene == "road"


def test_s_raises_the_hand_then_opens_the_book(table):
    ready(table)
    assert table.view == "hand_low"                 # after a draw the hand rests low
    press(table, Qt.Key.Key_S)
    assert table.view == "hand_high" and table.book is None
    press(table, Qt.Key.Key_W)
    assert table.view == "hand_low" and table.book is None
    press(table, Qt.Key.Key_S); press(table, Qt.Key.Key_S)
    assert table.book == 0
    press(table, Qt.Key.Key_D)
    assert table.book == 1
    press(table, Qt.Key.Key_A)
    assert table.book == 0
    press(table, Qt.Key.Key_W)
    assert table.book is None
    table._tick()


def test_q_opens_the_book_at_the_raised_cards_mark(table):
    ready(table)
    from techdeck.ui.void_game.cards import SIGILS
    g = table.game
    huginn = next((c for c in g.hand if c.defn.sigils and g.can_afford(c.uid)), None)
    if huginn is None:
        return
    table._click(("card", huginn.uid))
    press(table, Qt.Key.Key_Q)
    keys = list(SIGILS)
    assert table.book == keys.index(huginn.defn.sigils[0]) // 8


def test_he_minds_his_hound(table):
    ready(table)
    from tests.void_game.test_rules import put
    g = table.game
    g.incoming = [None] * 4
    put(g, "hound", HIM, 0)
    sleeper = put(g, "sleeper", YOU, 0)
    table.vcards.clear()
    quiet(table)
    table.enqueue(g.ring_bell())
    settle(table)
    said = [table.caption_key] + [c[2] for c in table.captions]
    assert "pet_dies" in said or table.game.rows[HIM][0] is None


def test_the_fire_refuses_a_second_rest_until_five_deaths_and_narrates_leaving(table):
    to_road(table)
    table.run.offers = [table.run._stop("fire")] * 3
    press(table, Qt.Key.Key_Space); quiet(table)
    card = table.run.deck[0]
    table.run.memory["deaths"] = 5                                     # only then is a second rest on offer
    press(table, Qt.Key.Key_Space); quiet(table)                      # the first rest is free; the card stays
    assert table.scene == "fire" and not table.busy()
    rests = table.run.stop.rests.get(0, 0)
    press(table, Qt.Key.Key_Space)
    said = [table.caption_key] + [c[2] for c in table.captions]
    assert "fire_again" in said
    quiet(table)
    assert table.run.stop.rests.get(0, 0) == rests + 1 or card not in table.run.deck
    if card in table.run.deck:
        press(table, Qt.Key.Key_Tab)
        said = [table.caption_key] + [c[2] for c in table.captions]
        assert "fire_leave" in said


def test_the_road_opens_with_his_recollection_once(table):
    to_road(table)
    assert table.caption_key == "scene_road_first" or any(c[2] == "scene_road_first" for c in table.captions) or table.caption_key == ""
    assert table.road_opened


def test_a_later_death_gets_the_plain_forge(table):
    table.run.memory["deaths"] = 3
    table.run.candles = 1
    ready(table)
    rig_end(table, False)
    quiet(table); press(table, Qt.Key.Key_Space); settle(table)
    assert table.scene == "forge" and not table.forge_first
    said = [table.caption_key] + [c[2] for c in table.captions]
    assert "deathcard" in said and "deathcard_cost" in said and "deathcard_first_time" not in said


def test_quitting_mid_road_brings_you_back_to_the_same_doors(table, tmp_path):
    import json
    to_road(table)
    assert table.scene == "road" and len(table.run.offers) == 3
    doors = [(s.kind, list(s.cards), s.fire) for s in table.run.offers]
    step, candles, runs = table.run.step, table.run.candles, table.run.memory["runs"]
    deck = [c.to_dict() for c in table.run.deck]
    table.road_pick()                                   # into the next stop...
    saved = json.loads((tmp_path / "void_game.json").read_text(encoding="utf-8"))
    assert saved["run"]["step"] == step, "the save is from the doors, not the stop"
    again = VoidTable()                                 # ...quit, and open the table anew
    again.timer.stop()
    try:
        assert again.scene == "road"
        assert [(s.kind, list(s.cards), s.fire) for s in again.run.offers] == doors
        assert (again.run.step, again.run.candles) == (step, candles)
        assert [c.to_dict() for c in again.run.deck] == deck
        assert again.run.memory["runs"] == runs, "the same run, not a new one"
    finally:
        again.close()


def test_the_run_slot_is_cleared_when_you_die(table, tmp_path):
    import json
    ready(table)
    table.run.candles = 1
    rig_end(table, False)
    saved = json.loads((tmp_path / "void_game.json").read_text(encoding="utf-8"))
    assert saved.get("run") is None


def test_a_match_ends_with_a_wipe_and_the_road_grows_in(table):
    from techdeck.ui.void_game import render3d as r3
    from techdeck.ui.void_game.window import WIPE_S, GROW_S
    ready(table)
    rig_end(table, True)
    quiet(table)
    press(table, Qt.Key.Key_Space)
    assert table.scene == "fight" and table.wipe_t0 >= 0, "the board is being swept first"
    w = table._warp()
    assert w is not None and w((1.0, 0.5, 0.0))[0] >= 1.0
    press(table, Qt.Key.Key_Space)                       # a second press while sweeping: nothing
    assert table.scene == "fight"
    settle(table)
    assert table.scene == "road" and table.wipe_t0 < 0
    assert table.t - table.scene_t0 < GROW_S, "the road has just begun to grow"
    g = table._warp()
    assert g is not None and 0.0 <= g((0.0, 2.0, 0.0))[1] < 2.0, "heights start from the floor"
    for _ in range(int(GROW_S * 30) + 2):
        table._tick()
    assert table._warp() is None, "and the grow is done"


def test_wipe_and_grow_warps_move_only_as_meant():
    from techdeck.ui.void_game import render3d as r3
    assert r3.warp_wipe(0.0)((1.0, 2.0, 3.0)) == (1.0, 2.0, 3.0)
    far = r3.warp_wipe(1.0)((1.0, 2.0, 3.0))
    assert far[0] > 10 and far[2] == 3.0
    assert r3.warp_grow(0.0)((1.0, 2.0, 3.0)) == (1.0, 0.0, 3.0)
    assert r3.warp_grow(1.0)((1.0, 2.0, 3.0)) == (1.0, 2.0, 3.0)


def _to_pick(w):
    """To a THREE CARDS stop (rig the doors so one is a choice)."""
    from techdeck.ui.void_game.run import Stop
    to_road(w)
    w.run.offers = [Stop("choice", cards=["scarab", "hound", "huginn"]), Stop("fire", fire="power"), Stop("fight")]
    w.pick = 0
    w.road_pick(); settle(w); quiet(w)
    assert w.scene == "pick"


def test_the_book_opens_from_any_event_at_the_picked_cards_mark(table):
    from techdeck.ui.void_game.cards import CARDS, SIGILS
    _to_pick(table)
    press(table, Qt.Key.Key_Q)
    assert table.book is not None
    first = CARDS[table.run.stop.cards[table.pick]].sigils
    if first:
        assert table.book == list(SIGILS).index(first[0]) // 8
    press(table, Qt.Key.Key_Q)
    assert table.book is None and table.scene == "pick", "closing the book leaves you where you were"


def test_w_lays_the_deck_out_and_s_on_the_bottom_row_brings_the_scene_back(table):
    from techdeck.ui.void_game.run import DeckCard
    from techdeck.ui.void_game.scenes import DECK_SPLIT_AT
    _to_pick(table)
    while len(table.run.deck) < DECK_SPLIT_AT + 1:               # nine: five on top, four below
        table.run.deck.append(DeckCard("scarab"))
    press(table, Qt.Key.Key_W)
    assert table.wipe_t0 >= 0 and not table.deck_view, "the scene is swept first"
    settle(table)
    assert table.deck_view and table.scene == "pick"
    top, bottom = table.deck_rows()
    assert len(top) == 5 and len(bottom) == 4, "odd one to the top row"
    assert table.deck_cursor == 0 and table.deck_cursor in top
    press(table, Qt.Key.Key_D); assert table.deck_cursor == 1 and table.deck_prev == 0
    press(table, Qt.Key.Key_S); assert table.deck_cursor == bottom[1], "down to the row below"
    press(table, Qt.Key.Key_W); assert table.deck_cursor == top[1], "and back up"
    press(table, Qt.Key.Key_S)
    press(table, Qt.Key.Key_Q); assert table.book is not None; press(table, Qt.Key.Key_Q)
    press(table, Qt.Key.Key_S)                                     # on the bottom row: back
    assert table.wipe_t0 >= 0
    settle(table)
    assert not table.deck_view and table.scene == "pick"
    table.run.deck[:] = table.run.deck[:7]                         # seven: one row
    assert table.deck_rows() == ([], list(range(7)))


def test_wasd_can_always_leave_the_deck_view(table):
    """From every card the deck view can hold - one row or two - S (at most
    twice) brings the scene back; W from the scene re-enters; keys pressed
    mid-sweep wait."""
    from techdeck.ui.void_game.run import DeckCard
    _to_pick(table)
    for n in (6, 9):
        while len(table.run.deck) < n:
            table.run.deck.append(DeckCard("scarab"))
        press(table, Qt.Key.Key_W)
        press(table, Qt.Key.Key_Space)                             # mid-sweep: nothing happens
        settle(table)
        assert table.deck_view and table.scene == "pick"
        for i in range(n):
            table._deck_move_to(i)
            presses = 0
            while table.deck_view and presses < 3:
                press(table, Qt.Key.Key_S); presses += 1
                settle(table)
            assert not table.deck_view and table.scene == "pick", f"stuck at card {i} of {n}"
            assert presses <= 2
            press(table, Qt.Key.Key_W); settle(table)
            assert table.deck_view
        press(table, Qt.Key.Key_S)
        if table.deck_view:
            press(table, Qt.Key.Key_S)
        settle(table)
        assert not table.deck_view


def test_taking_a_card_flicks_it_into_you_then_sweeps_the_scene(table):
    from techdeck.ui.void_game.scenes import FLICK_S
    _to_pick(table)
    n = len(table.run.deck)
    press(table, Qt.Key.Key_Space)
    assert len(table.run.deck) == n + 1 and table.scene == "pick"
    for _ in range(3):
        table._tick()
    assert table.flick is not None and table.wipe_t0 < 0, "the card is on its way first"
    press(table, Qt.Key.Key_Space)                                  # nothing lands mid-flick
    assert len(table.run.deck) == n + 1
    for _ in range(int(FLICK_S * 30) + 2):
        table._tick()
    assert table.wipe_t0 >= 0, "then the sweep"
    settle(table)
    assert table.scene == "road" and table.flick is None and table.wipe_t0 < 0


def test_dev_jumps_open_straight_at_an_event(qapp, tmp_path, monkeypatch):
    import techdeck.ui.void_game.window as win
    from techdeck.ui.void_game.scenes import JUMPS
    monkeypatch.setattr(win, "settings_path", lambda: str(tmp_path / "void_game.json"))
    want = {"tutorial": "fight", "fresh": "fight", "road": "road", "pick": "pick", "rare": "pick",
            "fire": "fire", "altar": "altar", "boss": "fight", "forge": "forge"}
    assert set(want) == set(JUMPS)
    for where, scene in want.items():
        w = VoidTable(jump=where); w.timer.stop()
        try:
            settle(w)
            assert w.scene == scene, where
            assert w._tutorial() == (where == "tutorial"), where
            if where == "boss":
                assert w.run.stop and w.run.stop.kind == "boss"
        finally:
            w.close()
