"""The table window, driven by hand: the clock is ticked, never run."""
import pytest
from PySide6.QtCore import QCoreApplication, QEvent

from techdeck.ui.void_game.rules import LANES, YOU
from techdeck.ui.void_game.window import VoidTable


@pytest.fixture
def table(qapp):
    w = VoidTable(seed=3)
    w.timer.stop()
    yield w
    w.close()
    w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def settle(w: VoidTable, limit: int = 900):
    for _ in range(limit):
        w._tick()
        if not w.busy():
            return
    raise AssertionError("the table never settled")


def greedy(w: VoidTable):
    """One turn the way a simple player would: draw, play what pays, ring."""
    g = w.game
    if g.phase == "draw":
        w._click(("votary",) if not any(c.defn.cost == 0 for c in g.hand) and g.votaries else ("deck",))
        settle(w)
    for card in sorted(list(g.hand), key=lambda c: (c.defn.cost > 0, -c.power)):
        if g.phase != "play" or not g.can_afford(card.uid) or w.over:
            continue
        w._click(("card", card.uid))
        if w.selected != card.uid:
            continue
        d = card.defn
        if d.cost_kind == "offer" and d.cost:
            worth = 0
            for lane, c in enumerate(g.rows[YOU]):
                if c is not None and worth < d.cost:
                    w._click(("card", c.uid)); worth += g.offering_worth(c)
            if card.power <= sum(g.rows[YOU][l].power for l in w.sacrifices):
                w._click(("card", card.uid))          # deselect: not worth it
                continue
        free = [l for l in range(LANES) if g.rows[YOU][l] is None or l in w.sacrifices]
        if not free:
            w._click(("card", card.uid))
            continue
        w._click(("slot", free[0]))
        settle(w)
    if not w.over:
        w._click(("bell",))
        settle(w)


def test_the_opening_deals_four_cards_and_he_speaks(table):
    settle(table)
    assert len(table._hand_cards()) == 4
    assert table.caption, "his welcome never showed"
    assert table.frame is not None and table.frame.width() == 960


def test_every_card_on_the_table_is_clickable(table):
    settle(table)
    kinds = {k[0] for k, _ in table.hits}
    assert {"card", "bell", "deck", "votary"} <= kinds


def test_a_played_card_travels_to_its_lane(table):
    settle(table)
    votary = next(c for c in table.game.hand if c.defn.id == "votary")
    table._click(("card", votary.uid))
    assert table.selected == votary.uid
    table._click(("slot", 2))
    assert table.game.rows[YOU][2] is votary
    settle(table)
    vc = table.vcards[votary.uid]
    assert vc.where == "you" and vc.lane == 2
    assert abs(vc.pose[0][2] - 2.55) < 1e-6, "it did not land on your row"


def test_an_illegal_click_becomes_a_hint_not_a_crash(table):
    settle(table)
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    big = next(c for c in table.game.hand if c.defn.cost >= 2)
    poly = next(p for k, p in table.hits if k == ("card", big.uid))
    pt = poly.boundingRect().center()
    ox, oy, k = 0, 0, 1.0
    table._view = (ox, oy, k)
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(pt), Qt.MouseButton.LeftButton,
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    table.mousePressEvent(ev)
    assert table.selected is None
    assert "DEMANDS" in table.hint


def test_a_whole_game_plays_through_to_the_end(table):
    settle(table)
    for _ in range(40):
        if table.over:
            break
        greedy(table)
    assert table.over
    assert table.game.winner in ("you", "him")
    settle(table)
    assert table.caption or table.captions, "no last word from him"
    assert all(v.where != "gone" or v.opacity > 0 for v in table.vcards.values())


def test_the_clock_keeps_going_with_the_lines_file_missing(qapp, tmp_path):
    from techdeck.ui.void_game.dialogue import Dialogue
    w = VoidTable(seed=1, dialogue=Dialogue(tmp_path / "nowhere.txt"))
    w.timer.stop()
    try:
        settle(w)
        assert w.caption == "" and not w.captions
    finally:
        w.close(); w.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
