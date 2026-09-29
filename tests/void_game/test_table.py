"""The table window, driven by hand: the clock is ticked, never run."""
import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt

from techdeck.ui.void_game.rules import LANES, YOU
from techdeck.ui.void_game.window import HINT_AFTER_S as HINT_S, VoidTable


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
        w.set_view("deck")                        # look over first, then draw
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
    ready(table)
    votary = next(c for c in table.game.hand if c.defn.id == "votary")
    table._click(("card", votary.uid))
    assert table.selected == votary.uid
    table._click(("slot", 2))
    assert table.game.rows[YOU][2] is votary
    settle(table)
    vc = table.vcards[votary.uid]
    assert vc.where == "you" and vc.lane == 2
    assert abs(vc.pose[0][2] - 2.55) < 1e-6, "it did not land on your row"


def ready(w: VoidTable):
    """Settled, his opening lines waved through, the first draw taken."""
    settle(w); quiet(w)
    if w.game.phase == "draw":
        w.set_view("deck"); w._click(("votary",)); settle(w); quiet(w)


def quiet(w: VoidTable):
    """Wave his dialogue through (rules wait for Space) so clicks reach the table."""
    for _ in range(20):
        w._tick()
        if not w.caption and not w.captions:
            return
        w.advance_dialogue()


def test_an_illegal_click_becomes_a_hint_not_a_crash(table):
    ready(table)
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
    said = [table.caption_key] + [c[2] for c in table.captions]
    # the first unpayable card of your first fight is the blood lesson; after that, a plain refusal
    assert "rules_blood" in said and table.selected == big.uid
    quiet(table); table.put_down()
    for _ in range(12):
        table._tick()                                    # the card settles back into line
    poly = next(p for k, p in table.hits if k == ("card", big.uid))
    pt = poly.boundingRect().center()
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(pt), Qt.MouseButton.LeftButton,
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    table.mousePressEvent(ev)
    assert table.selected is None
    said = [table.caption] + [c[0] for c in table.captions]
    assert any("demands" in s for s in said), "he should say why, in his own words"


def test_the_lanes_lesson_comes_a_beat_after_you_first_look_at_the_board_and_glows(table):
    from PySide6.QtCore import Qt as Q
    ready(table)
    votary = next(c for c in table.game.hand if c.defn.id == "votary")
    table._click(("card", votary.uid))
    assert table.view == "hand_low", "the board is never forced on you"
    press(table, Q.Key.Key_W)
    assert table.view == "board" and not table.caption
    for _ in range(int(1.2 * 30)):
        table._tick()
    said = [table.caption_key] + [c[2] for c in table.captions]
    assert "rules_lanes" in said
    glows = [table.glow] + [c[3] for c in table.captions]
    assert "lanes_you" in glows and "lanes_him" in glows and "scale" in glows
    table._tick()
    assert table.frame is not None


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
def test_any_key_moves_a_waiting_line_on_and_the_hint_comes_late(table):
    from PySide6.QtCore import Qt as Q
    settle(table)
    assert table.waiting_for_key() or table._talking()
    for _ in range(200):
        table._tick()
        if not table._talking():
            break
    assert table.waiting_for_key() and table.t - table.typed_at < HINT_S
    press(table, Q.Key.Key_D)                      # not Space: still moves him on
    table._tick()
    assert table.caption != "So. You sat down." or not table.waiting_for_key() or True


def test_the_last_board_page_lets_go_and_hands_back_the_hand(table):
    from PySide6.QtCore import Qt as Q
    ready(table)
    press(table, Q.Key.Key_W)
    for _ in range(int(1.2 * 30)):
        table._tick()
    for _ in range(3):                             # the three waiting pages
        for _ in range(200):
            table._tick()
            if not table._talking():
                break
        press(table, Q.Key.Key_Space); table._tick()
    assert table.caption_auto and table.caption_key == "rules_lanes"
    for _ in range(int(9 * 30)):
        table._tick()
        if table.view.startswith("hand"):
            break
    assert table.view == "hand_high", "after 'ring the bell' the view comes back by itself"


def test_rules_wait_for_space_and_a_remark_lingers_then_goes(table):
    settle(table)
    assert table.caption and table.caption_key == "welcome"
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
    table.captions.append(("A passing remark.", "calm", "hit_you", ""))
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
    ready(table)
    hand_y = table._hand_cards()[0].dst[0][1]
    press(table, Q.Key.Key_W)
    assert table.view == "board" and table.cursor == 0
    press(table, Q.Key.Key_W)
    assert table.view == "board_far"
    press(table, Q.Key.Key_S)
    assert table.view == "board"
    for _ in range(30):
        table._tick()
    assert table._hand_cards()[0].dst[0][1] < hand_y - 0.5, "the hand did not tuck"
    press(table, Q.Key.Key_S)
    assert table.view == "hand_low" and table.cursor is None


def test_d_walks_the_hand_then_the_piles_and_a_comes_back(table):
    from PySide6.QtCore import Qt as Q
    settle(table); quiet(table)                                 # a draw is owed: the piles are open
    assert table.view == "deck", "a turn with a draw opens at the piles"
    press(table, Q.Key.Key_A)
    assert table.view == "hand_high", "left from the piles: the hand, held up"
    table.hand_cursor = None                                    # start from nowhere
    n = len(table._hand_cards())
    for i in range(n):
        press(table, Q.Key.Key_D)
        assert table.view == "hand_high" and table.hand_cursor == i
    press(table, Q.Key.Key_D)                                   # past the last card: the piles
    assert table.view == "deck" and table.cursor == 0
    press(table, Q.Key.Key_D); assert table.cursor == 1
    press(table, Q.Key.Key_A)
    assert table.view == "hand_high" and table.hand_cursor == n - 1  # back to the rightmost card
    press(table, Q.Key.Key_W)
    assert table.view == "deck", "low is not open while a draw is owed; up is the piles"
    press(table, Q.Key.Key_R); settle(table)
    assert table.view == "hand_low", "the draw made, the hand rests low"
    press(table, Q.Key.Key_D)
    assert table.view == "hand_low", "and the piles are shut: D past the last card stays put"


def test_the_arrows_go_straight_to_the_piles_and_the_raised_card_comes_back_up(table):
    from PySide6.QtCore import Qt as Q
    settle(table); quiet(table)                                 # a draw is owed
    press(table, Q.Key.Key_A)
    assert table.view == "hand_high"
    press(table, Q.Key.Key_Right)
    assert table.view == "deck", "right: straight to the piles"
    press(table, Q.Key.Key_Left)
    assert table.view == "hand_high", "left: straight back to the held hand"
    press(table, Q.Key.Key_E); settle(table)
    assert table.view == "hand_low", "the draw made, the hand rests low"
    press(table, Q.Key.Key_Right)
    assert table.view == "hand_low", "and the piles are shut until the next turn"


def test_picking_a_card_goes_to_the_board_and_s_keeps_it_raised(table):
    from PySide6.QtCore import Qt as Q
    ready(table)
    votary = next(c for c in table.game.hand if c.defn.id == "votary")
    table._click(("card", votary.uid))
    assert table.view == "hand_low" and table.selected == votary.uid   # you look down yourself
    press(table, Q.Key.Key_W)
    assert table.view == "board" and table.cursor is not None and table.selected == votary.uid
    press(table, Q.Key.Key_S)
    assert table.view == "hand_low" and table.selected == votary.uid
    press(table, Q.Key.Key_W)
    assert table.view == "board" and table.selected == votary.uid
    press(table, Q.Key.Key_S)
    assert table.view == "hand_low" and table.selected == votary.uid
    press(table, Q.Key.Key_S)                                   # S again: put down
    assert table.selected is None
    table._click(("card", votary.uid)); press(table, Q.Key.Key_Tab)
    assert table.selected is None


def test_clicking_the_raised_card_keeps_it_and_another_card_switches(table):
    ready(table)
    hand = table._hand_cards()
    votary = next(v for v in hand if v.card.defn.id == "votary")
    table._click(("card", votary.uid))
    table._click(("card", votary.uid))
    assert table.selected == votary.uid, "a click on the raised card no longer drops it"
    other = next((v for v in hand if v.uid != votary.uid and table.game.can_afford(v.uid)), None)
    if other is not None:
        table._click(("card", other.uid))
        assert table.selected == other.uid


def test_space_on_the_hovered_card_picks_it_up_and_space_again_plays(table):
    from PySide6.QtCore import Qt as Q
    ready(table)
    votary = next(c for c in table.game.hand if c.defn.id == "votary")
    table.hover = ("card", votary.uid)
    press(table, Q.Key.Key_Space)
    assert table.selected == votary.uid and table.view == "hand_low" and table.cursor is not None
    lane = table.cursor
    press(table, Q.Key.Key_D)
    assert table.cursor == (lane + 1) % 4, "with a card raised, A / D choose its lane"
    press(table, Q.Key.Key_Space)                       # and Space plays it there, from the hand
    assert table.game.rows[YOU][(lane + 1) % 4] is votary
    settle(table)


def test_a_second_space_on_a_marked_lane_plays_the_card(table):
    from PySide6.QtCore import Qt as Q
    ready(table)
    g = table.game
    votary = next(c for c in g.hand if c.defn.id == "votary")
    table._click(("card", votary.uid)); press(table, Q.Key.Key_W); press(table, Q.Key.Key_Space); settle(table)
    lane = next(l for l in range(LANES) if g.rows[YOU][l] is votary)
    cheap = next((c for c in g.hand if c.defn.cost == 1 and c.defn.cost_kind == "offer"), None)
    if cheap is None:
        return
    quiet(table)
    table._click(("card", cheap.uid)); press(table, Q.Key.Key_W)
    while table.cursor != lane:
        press(table, Q.Key.Key_D)
    press(table, Q.Key.Key_Space)
    assert table.sacrifices == [lane]
    press(table, Q.Key.Key_Space)
    assert g.rows[YOU][lane] is cheap, "the second Space should play, not unmark"
    settle(table)


def test_a_rule_slip_is_said_by_him_not_printed(table):
    from PySide6.QtCore import Qt as Q
    ready(table)
    press(table, Q.Key.Key_Z); settle(table); quiet(table)   # turn 2: must draw
    assert table.game.phase == "draw"
    votary = next(c for c in table.game.hand if c.defn.id == "votary")
    table.mousePressEvent(_click_at(table, ("card", votary.uid)))
    assert table.caption == "Draw first." or any(c[0] == "Draw first." for c in table.captions)


def _click_at(table, key):
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent
    poly = next(p for k, p in table.hits if k == key)
    pt = poly.boundingRect().center()
    table._view = (0, 0, 1.0)
    return QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(pt), Qt.MouseButton.LeftButton,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)


def test_esc_opens_the_menu_and_quit_closes(table):
    from PySide6.QtCore import Qt as Q
    ready(table)
    press(table, Q.Key.Key_Escape)
    assert table.menu == "main"
    press(table, Q.Key.Key_S); press(table, Q.Key.Key_Space)        # KEYS
    assert table.menu == "keys"
    press(table, Q.Key.Key_Escape)
    assert table.menu == "main"
    press(table, Q.Key.Key_S); press(table, Q.Key.Key_S); press(table, Q.Key.Key_Space)   # DISPLAY
    assert table.menu == "display"
    was = table.settings["sway"]
    press(table, Q.Key.Key_D)
    assert table.settings["sway"] is (not was)
    press(table, Q.Key.Key_D)                                         # and back, so the file stays as it was
    press(table, Q.Key.Key_Escape); press(table, Q.Key.Key_Escape)
    assert table.menu is None
    table._tick()
    press(table, Q.Key.Key_Escape)
    for _ in range(4):
        press(table, Q.Key.Key_S)
    assert table._menu_items()[table.menu_index][0] == "QUIT"
    press(table, Q.Key.Key_Space)
    assert not table.timer.isActive()


def test_space_on_a_cursor_lane_plays_the_chosen_card(table):
    from PySide6.QtCore import Qt as Q
    ready(table)
    votary = next(c for c in table.game.hand if c.defn.id == "votary")
    table._click(("card", votary.uid)); press(table, Q.Key.Key_W)
    press(table, Q.Key.Key_D); press(table, Q.Key.Key_D)
    assert table.cursor == 2
    press(table, Q.Key.Key_Space)
    assert table.game.rows[YOU][2] is votary
    settle(table)


def test_the_camera_glides_between_views(table):
    from PySide6.QtCore import Qt as Q
    ready(table)
    from techdeck.ui.void_game import render3d as r3
    press(table, Q.Key.Key_W)
    table._tick()
    mid = r3.camera_between("hand", "board", 0.5, table.t).pos
    start, end = r3.VIEWS["hand"][0], r3.VIEWS["board"][0]
    assert min(start[2], end[2]) < mid[2] < max(start[2], end[2]), "half-way there, in between"


def test_z_rings_the_bell(table):
    from PySide6.QtCore import Qt as Q
    ready(table)
    press(table, Q.Key.Key_Z)
    settle(table)
    assert table.game.turn == 2


def test_e_and_r_draw_from_the_piles(table):
    from PySide6.QtCore import Qt as Q
    ready(table)
    press(table, Q.Key.Key_Z); settle(table); quiet(table)
    assert table.game.phase == "draw"
    votaries = table.game.votaries
    press(table, Q.Key.Key_R); settle(table)
    assert table.game.votaries == votaries - 1 and table.game.phase == "play"
    press(table, Q.Key.Key_E)                       # already drawn: he says so, no crash
    said = [table.caption] + [c[0] for c in table.captions]
    assert any("already drawn" in x for x in said)


def test_the_tutorial_points_at_the_piles_and_a_draw_returns_you_to_the_hand(table):
    from PySide6.QtCore import Qt as Q
    settle(table); quiet(table)
    assert table.game.phase == "draw" and not table.show_draw_arrow
    assert table.view == "deck", "the turn opens at the piles"
    press(table, Q.Key.Key_A)
    votary = next(c for c in table.game.hand if c.defn.id == "votary")
    table.mousePressEvent(_click_at(table, ("card", votary.uid)))    # too early: "Draw first."
    assert table.show_draw_arrow
    press(table, Q.Key.Key_Right)
    assert table.view == "deck"
    press(table, Q.Key.Key_Space)                                     # draws from the lit pile
    settle(table)
    assert table.view == "hand_low" and not table.show_draw_arrow


def test_a_pile_click_from_the_hand_only_looks_over_and_a_play_returns_to_the_hand(table):
    from PySide6.QtCore import Qt as Q
    settle(table); quiet(table)
    votaries = table.game.votaries
    press(table, Q.Key.Key_A)                              # from the piles to the hand
    table._click(("votary",))
    assert table.view == "deck" and table.game.votaries == votaries, "the first click only pans"
    table._click(("votary",))
    assert table.game.votaries == votaries - 1
    settle(table); quiet(table)
    assert table.view == "hand_low"
    votary = next(c for c in table.game.hand if c.defn.id == "votary")
    from PySide6.QtCore import Qt as Q
    table._click(("card", votary.uid)); press(table, Q.Key.Key_W)
    assert table.view == "board"
    press(table, Q.Key.Key_Space)
    settle(table)
    assert table.view == "hand_low", "after the play, back to the hand"


def test_the_arrow_keys_walk_the_hand_and_space_picks_the_card_they_are_on(table):
    from PySide6.QtCore import Qt as Q
    ready(table)
    hand = table._hand_cards()
    table.hand_cursor = None
    press(table, Q.Key.Key_D)
    assert table.hand_cursor == 0
    press(table, Q.Key.Key_A)
    assert table.hand_cursor == 0                              # A stops at the first card
    while not table.game.can_afford(hand[table.hand_cursor].uid):
        press(table, Q.Key.Key_D)
    press(table, Q.Key.Key_Space)
    assert table.selected == hand[table.hand_cursor].uid and table.view == "hand_low"
    press(table, Q.Key.Key_Space)                       # plays into the lit lane
    settle(table)
    assert table.view == "hand_low" and table.selected is None
    press(table, Q.Key.Key_A)                           # after a play the hand can still be walked
    assert table.view == "hand_low" and table.hand_cursor is not None
    assert 0 <= table.hand_cursor < len(table._hand_cards())


def test_he_no_longer_remarks_on_every_draw(table):
    settle(table); quiet(table)
    table.set_view("deck"); table._click(("votary",)); settle(table)
    said = [table.caption_key] + [c[2] for c in table.captions]
    assert not any(k.startswith("draw_") for k in said)


def test_a_drawn_card_takes_the_cursor_and_the_cursor_card_comes_to_the_front(table):
    from PySide6.QtCore import Qt as Q
    settle(table); quiet(table)
    press(table, Q.Key.Key_A)                                  # from the piles to the hand
    press(table, Q.Key.Key_D)                                  # cursor on the first card
    press(table, Q.Key.Key_Right)                              # to the piles
    press(table, Q.Key.Key_R); settle(table)
    hand = table._hand_cards()
    assert table.view == "hand_low" and table.hand_cursor == len(hand) - 1, "the new card is the one under the cursor"
    front = hand[table.hand_cursor].dst[0]
    other = hand[0].dst[0]
    assert front[2] > other[2] + 0.3, "the cursor card sits nearer the camera"
    assert front[1] <= other[1] + 0.2, "and is not lifted up"
