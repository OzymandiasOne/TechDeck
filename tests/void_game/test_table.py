"""The table window, driven by hand: the clock is ticked, never run."""
import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt

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


def quiet(w: VoidTable):
    """Wave his dialogue through (rules wait for Space) so clicks reach the table."""
    for _ in range(20):
        w._tick()
        if not w.caption and not w.captions:
            return
        w.advance_dialogue()


def test_an_illegal_click_becomes_a_hint_not_a_crash(table):
    settle(table)
    quiet(table)
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


# ── dialogue and views (his playtest feedback) ────────────────────────────
def test_rules_wait_for_space_and_a_remark_lingers_then_goes(table):
    settle(table)
    assert table.caption and table.caption_key in ("welcome", "rules")
    for _ in range(600):                       # 20 s: a must-read line does not leave on its own
        table._tick()
    assert table.caption and table.caption_until == float("inf")
    shown_before = table.caption_shown
    assert table.advance_dialogue()            # first Space finishes the typing...
    assert table.caption_shown == len(table.caption) >= shown_before
    assert table.advance_dialogue()            # ...the next moves on
    table._tick()
    assert table.caption_key != "welcome" or table.caption == ""
    quiet(table)
    table.captions.append(("A passing remark.", "calm", "hit_you"))
    table._tick()
    assert table.caption == "A passing remark."
    for _ in range(int((1 + 6.0 + 2) * 30)):
        table._tick()
    assert table.caption == "", "a flavor line should leave by itself"


def test_a_click_while_he_talks_only_advances_him(table):
    settle(table)
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    assert table.caption
    votary = next(c for c in table.game.hand if c.defn.id == "votary")
    poly = next(p for k, p in table.hits if k == ("card", votary.uid))
    pt = poly.boundingRect().center()
    table._view = (0, 0, 1.0)
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(pt), Qt.MouseButton.LeftButton,
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    table.mousePressEvent(ev)
    assert table.selected is None


def press(w: VoidTable, key):
    from PySide6.QtGui import QKeyEvent
    w.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))


def test_w_looks_down_at_the_board_and_the_hand_tucks_away(table):
    from PySide6.QtCore import Qt as Q
    settle(table); quiet(table)
    hand_y = table._hand_cards()[0].dst[0][1]
    press(table, Q.Key.Key_W)
    assert table.view == "board" and table.cursor == 0
    for _ in range(30):
        table._tick()
    assert table._hand_cards()[0].dst[0][1] < hand_y - 0.5, "the hand did not tuck"
    press(table, Q.Key.Key_D); assert table.cursor == 1
    press(table, Q.Key.Key_A); press(table, Q.Key.Key_A); assert table.cursor == LANES - 1
    press(table, Q.Key.Key_S)
    assert table.view == "hand" and table.cursor is None


def test_d_leans_to_the_deck_and_a_comes_back(table):
    from PySide6.QtCore import Qt as Q
    settle(table); quiet(table)
    press(table, Q.Key.Key_D)
    assert table.view == "deck" and table.cursor == 0
    press(table, Q.Key.Key_D); assert table.cursor == 1
    press(table, Q.Key.Key_A); assert table.cursor == 0 and table.view == "deck"
    press(table, Q.Key.Key_A); assert table.view == "hand"


def test_space_on_a_cursor_lane_plays_the_chosen_card(table):
    from PySide6.QtCore import Qt as Q
    settle(table); quiet(table)
    votary = next(c for c in table.game.hand if c.defn.id == "votary")
    table._click(("card", votary.uid))
    press(table, Q.Key.Key_W)
    press(table, Q.Key.Key_D); press(table, Q.Key.Key_D)
    assert table.cursor == 2
    press(table, Q.Key.Key_Space)
    assert table.game.rows[YOU][2] is votary
    settle(table)


def test_the_camera_glides_between_views(table):
    from PySide6.QtCore import Qt as Q
    settle(table); quiet(table)
    from techdeck.ui.void_game import render3d as r3
    press(table, Q.Key.Key_W)
    table._tick()
    mid = r3.camera_between("hand", "board", 0.5, table.t).pos
    start, end = r3.VIEWS["hand"][0], r3.VIEWS["board"][0]
    assert start[1] < mid[1] < end[1]
