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
    w.close()
    w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


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
    press(w, Qt.Key.Key_Space)             # his last word is out: on to the road
    w._tick()
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
    quiet(table); press(table, Qt.Key.Key_Space); table._tick(); quiet(table)
    assert table.scene == "road"


def test_the_forge_makes_a_deathcard_and_he_keeps_it(table):
    table.run.candles = 1
    ready(table)
    rig_end(table, False)
    assert table.run.dead
    quiet(table); press(table, Qt.Key.Key_Space); table._tick(); quiet(table)
    assert table.scene == "forge" and table.forge_step == 0
    for _ in range(3):
        press(table, Qt.Key.Key_Space)
    assert table.forge_step == 3
    for ch in "Ant hony":
        press(table, Qt.Key.Key_A, ch)
    assert table.forge_name == "ANT HONY"
    press(table, Qt.Key.Key_Backspace)
    press(table, Qt.Key.Key_Return)
    assert table.scene == "digitize" and table.run.deathcard is not None
    assert table.run.deathcard.name == "ANT HON"
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
    quiet(table)
    assert table.scene == "road"


def test_the_fire_and_tab_to_leave(table):
    to_road(table)
    table.run.offers = [table.run._stop("fire")] * 3
    press(table, Qt.Key.Key_Space); quiet(table)
    assert table.scene == "fire"
    card = table.run.deck[0]
    press(table, Qt.Key.Key_Space); quiet(table)
    assert card.power + card.health > 0 or card not in table.run.deck
    press(table, Qt.Key.Key_Tab); quiet(table)
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
    quiet(table)
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
