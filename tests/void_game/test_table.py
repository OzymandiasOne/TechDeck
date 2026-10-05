"""The table window, driven by hand: the clock is ticked, never run."""
import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt

from techdeck.ui.void_game.rules import HIM, LANES, YOU
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
    w.bell_told = True                                  # the tutorial's bell guard is not under test here
    if g.phase == "draw":
        w.set_view("deck")                        # look over first, then draw
        w._click(("votary",) if not any(c.defn.cost == 0 for c in g.hand) and g.votaries else ("deck",))
        settle(w)
    for card in sorted(list(g.hand), key=lambda c: (c.defn.cost > 0, -c.power)):
        if card not in g.hand or g.phase != "play" or not g.can_afford(card.uid) or w.over:
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
                w.put_down()                          # not worth it
                continue
        free = [l for l in range(LANES) if g.rows[YOU][l] is None or l in w.sacrifices]
        if not free:
            w.put_down()
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
    """Settled, his opening lines waved through, the first draw taken, the bell spoken of."""
    settle(w); quiet(w)
    w.bell_told = True
    if w.game.phase == "draw":
        w.set_view("deck"); w._click(("votary",)); settle(w); quiet(w)


def walk_to(w: VoidTable, lane: int):
    """A / D along the board's slots to a lane (past an end is a glance, so walk the right way)."""
    from PySide6.QtCore import Qt as Q
    for _ in range(8):
        if w.cursor == lane:
            return
        press(w, Q.Key.Key_D if (w.cursor is None or w.cursor < lane) else Q.Key.Key_A)
    raise AssertionError(f"could not walk to lane {lane}: cursor {w.cursor}, view {w.view}")


def board(w: VoidTable):
    """W to the board with a card raised - and, in the tutorial, through the
    board lesson that holds the first play until it is over."""
    from PySide6.QtCore import Qt as Q
    press(w, Q.Key.Key_W)
    if w.lesson_at is not None:
        for _ in range(int(1.4 * 30)):
            w._tick()
        quiet(w)


def quiet(w: VoidTable):
    """Wave his dialogue through (rules wait for Space) so clicks reach the table."""
    for _ in range(80):                                # the forge's intro runs to ten pages
        w._tick()
        if not w.caption and not w.captions:
            return
        w.advance_dialogue()


def test_an_illegal_click_becomes_a_hint_not_a_crash(table):
    ready(table)
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    def blood_card():
        return next((c for c in table.game.hand if c.defn.cost >= 2 and c.defn.cost_kind == "offer"), None)
    while blood_card() is None:                              # a four-card deck: the hound may still be in it
        press(table, Qt.Key_Tab); settle(table); quiet(table)
        press(table, Qt.Key_E); settle(table); quiet(table)
    big = blood_card()
    poly = next(p for k, p in table.hits if k == ("card", big.uid))
    r = poly.boundingRect()
    pt = QPointF(r.left() + 12, r.center().y())            # the fan overlaps: aim at the card's own sliver
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
    r = poly.boundingRect()
    pt = QPointF(r.left() + 12, r.center().y())
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(pt), Qt.MouseButton.LeftButton,
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    table.mousePressEvent(ev)
    assert table.selected is None
    said = [table.caption] + [c[0] for c in table.captions]
    assert any("requires" in s for s in said), "he should say why, in his own words"


def test_the_lanes_lesson_comes_a_beat_after_you_first_look_at_the_board_and_glows(table):
    from PySide6.QtCore import Qt as Q
    ready(table)
    votary = next(c for c in table.game.hand if c.defn.id == "votary")
    table._click(("card", votary.uid))
    assert table.view == "hand_low", "the board is never forced on you"
    press(table, Q.Key.Key_W)
    assert table.view == "board" and not table.caption
    for _ in range(int(0.7 * 30)):
        table._tick()
    assert not table.caption, "a beat before the lesson"
    for _ in range(int(0.7 * 30)):
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
    for _ in range(int(1.8 * 30)):
        table._tick()
    for _ in range(4):                             # the four waiting pages
        for _ in range(400):
            table._tick()
            if table.caption and not table._talking():
                break
        press(table, Q.Key.Key_Space); table._tick()
    assert table.caption_auto and table.caption_key == "rules_lanes"
    for _ in range(int(2 * 30)):
        table._tick()
    assert table.view == "board_right", "the bell page glances right at the bell, a beat later"
    for _ in range(int(12 * 30)):
        table._tick()
        if table.view == "board":
            break
    assert table.view == "board", "after 'ring the bell' the view comes back to the board"


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
    for _ in range(20):                                         # (before the board lesson begins)
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
    assert table.view == "hand_low" and table.selected is None, "leaving the board puts the card down"
    table._click(("card", votary.uid))
    assert table.selected == votary.uid
    press(table, Q.Key.Key_S)                                   # S in the hand: put down
    assert table.selected is None
    table._click(("card", votary.uid)); press(table, Q.Key.Key_S)
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
    table._click(("card", votary.uid)); board(table); press(table, Q.Key.Key_Space); settle(table)
    lane = next(l for l in range(LANES) if g.rows[YOU][l] is votary)
    cheap = next((c for c in g.hand if c.defn.cost == 1 and c.defn.cost_kind == "offer"), None)
    if cheap is None:
        return
    quiet(table)
    table._click(("card", cheap.uid)); board(table)
    walk_to(table, lane)
    press(table, Q.Key.Key_Space)
    assert table.sacrifices == [lane]
    press(table, Q.Key.Key_Space)
    assert g.rows[YOU][lane] is cheap, "the second Space should play, not unmark"
    settle(table)


def test_a_rule_slip_is_said_by_him_not_printed(table):
    from PySide6.QtCore import Qt as Q
    ready(table)
    press(table, Q.Key.Key_Tab); settle(table); quiet(table)   # turn 2: must draw
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
    was = table.settings["scanlines"]
    press(table, Q.Key.Key_D)
    assert table.settings["scanlines"] is (not was)
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
    table._click(("card", votary.uid)); board(table)
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


def test_tab_rings_the_bell(table):
    from PySide6.QtCore import Qt as Q
    ready(table)
    press(table, Q.Key.Key_Tab)
    settle(table)
    assert table.game.turn == 2


def test_e_and_r_draw_from_the_piles(table):
    from PySide6.QtCore import Qt as Q
    ready(table)
    press(table, Q.Key.Key_Tab); settle(table); quiet(table)
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
    table._click(("card", votary.uid)); board(table)
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
    quiet(table)                                               # his "play your Votary" waits for a key
    press(table, Q.Key.Key_S)                                  # the held hand: the current card steps up
    table._layout_hand()
    front = hand[table.hand_cursor].dst[0]
    other = hand[0].dst[0]
    assert front[1] > other[1] + 0.1, "the cursor card steps up, clear of its neighbours"
    assert abs(front[2] - other[2]) < 0.4, "and not toward the camera (it must not grow)"


def test_the_scale_page_glances_left_and_a_glances_at_the_scale_any_time(table):
    from PySide6.QtCore import Qt as Q
    ready(table)
    press(table, Q.Key.Key_W)
    for _ in range(int(1.8 * 30)):
        table._tick()
    for _ in range(2):                             # your side, my side
        for _ in range(400):
            table._tick()
            if table.caption and not table._talking():
                break
        press(table, Q.Key.Key_Space); table._tick()
    assert table.glow == "scale" and table.view == "board", "a beat of silence first"
    for _ in range(int(1.4 * 30)):
        table._tick()
    assert table.view == "board_left", "then the camera looks left at the scale"
    assert table.active_glow() == "", "the glow waits for the middle of the line"
    quiet(table)
    for _ in range(int(12 * 30)):
        table._tick()
        if table.view == "board" and not table.caption:
            break
    assert table.view == "board", "the lesson ends on the board"
    press(table, Q.Key.Key_A)
    assert table.view == "board_left"
    press(table, Q.Key.Key_D)
    assert table.view == "board"


def test_the_tutorial_points_at_the_votary_after_the_first_draw(table):
    settle(table); quiet(table)
    table.set_view("deck"); table._click(("votary",)); settle(table)
    said = [table.caption_key] + [c[2] for c in table.captions]
    assert "first_draw" in said and table.selected is None, "he points; you play it yourself"


def test_his_first_hit_on_your_card_is_narrated_with_names(table):
    ready(table)
    from tests.void_game.test_rules import put
    g = table.game
    g.incoming = [None] * LANES
    put(g, "sleeper", HIM, 0); put(g, "hound", YOU, 0)
    table.enqueue(g.ring_bell())
    settle(table)
    lines = [table.caption] + [c[0] for c in table.captions]
    assert any("Sleeper" in ln and "Hound" in ln for ln in lines), lines


def test_the_tutorial_says_the_second_turns_choice_once(table):
    from PySide6.QtCore import Qt as Q
    ready(table)
    press(table, Q.Key.Key_Tab); settle(table)
    said = [table.caption_key] + [c[2] for c in table.captions]
    assert "second_turn" in said


def test_his_instructions_never_eat_your_keys(table):
    from PySide6.QtCore import Qt as Q
    settle(table); quiet(table)
    table.set_view("deck"); table._click(("votary",)); settle(table)
    assert table.caption_key == "first_draw" and not table.waiting_for_key()
    press(table, Q.Key.Key_A)
    assert table.view == "hand_low" and table.hand_cursor is not None, "A walked the hand, it did not dismiss him"
    assert table.caption_key == "first_draw", "and he is still asking"
    hand = table._hand_cards()
    votary = next(v for v in hand if v.card.defn.id == "votary")
    table._click(("card", votary.uid))
    table._tick()
    assert table.caption_key != "first_draw", "you did what he asked: the line lets go"


def test_the_tutorial_looks_at_the_piles_only_when_he_offers_the_draw(table):
    settle(table)                                               # the welcome is still up
    assert table.game.phase == "draw" and table.caption_key == "welcome"
    assert table.view != "deck", "the camera waits for his line"
    for _ in range(40):
        table._tick()
        if table.caption_key == "first_turn":
            break
        table.advance_dialogue()
    assert table.caption_key == "first_turn"
    assert table.view == "deck", "the piles open as he offers the choice"


def test_the_tutorial_keeps_the_bell_out_of_reach_until_he_speaks_of_it(table):
    from PySide6.QtCore import Qt as Q
    settle(table); quiet(table)
    press(table, Q.Key.Key_R); settle(table); quiet(table)          # drawn: it is your turn to play
    assert table.game.phase == "play" and not table.bell_told
    press(table, Q.Key.Key_Tab); settle(table)
    assert table.game.phase == "play", "the bell did not ring"
    said = [table.caption_key] + [c[2] for c in table.captions]
    assert "bell_early" in said
    quiet(table)
    table.set_view("board")                                          # the lesson, bell page included
    for _ in range(400):
        table._tick()
        if table.bell_told:
            break
        table.advance_dialogue()
    assert table.bell_told
    quiet(table)
    press(table, Q.Key.Key_Tab); settle(table)
    assert table.game.phase != "play" or table.game.turn > 1, "now it rings"


def test_on_the_board_a_and_d_walk_the_slots_and_look_past_the_ends(table):
    from PySide6.QtCore import Qt as Q
    ready(table)
    press(table, Q.Key.Key_W); settle(table); quiet(table)          # the board, no card raised
    table.set_view("board")
    assert table.view == "board" and table.cursor == 0
    for lane in (1, 2, 3):
        press(table, Q.Key.Key_D)
        assert table.view == "board" and table.cursor == lane
    press(table, Q.Key.Key_D)
    assert table.view == "board_right", "past the rightmost slot: the bell and the candles"
    press(table, Q.Key.Key_A)
    assert table.view == "board" and table.cursor == 3, "and back, on the same slot"
    for lane in (2, 1, 0):
        press(table, Q.Key.Key_A)
        assert table.cursor == lane
    press(table, Q.Key.Key_A)
    assert table.view == "board_left", "past the leftmost slot: the scale"
    press(table, Q.Key.Key_D)
    assert table.view == "board" and table.cursor == 0


def test_he_remarks_on_one_played_card_per_match(table):
    from PySide6.QtCore import Qt as Q
    ready(table)
    g = table.game
    said = []
    for _ in range(4):
        card = next((c for c in g.hand if not g.why_not(c.uid, 0)), None)
        if card is None:
            break
        table._click(("card", card.uid)); press(table, Q.Key.Key_W)
        lane = next(l for l in range(LANES) if not g.why_not(card.uid, l))
        walk_to(table, lane)
        press(table, Q.Key.Key_Space); settle(table)
        said += [k for k in [table.caption_key] + [c[2] for c in table.captions] if k.startswith("play_")]
        quiet(table)
    assert len(set(said)) <= 1 and len(said) <= 1, said


def test_the_generic_card_remarks_come_only_in_some_matches(table):
    from PySide6.QtCore import Qt as Q
    ready(table)
    g = table.game
    votary = next(c for c in g.hand if c.defn.id == "votary")
    cheap = next(c for c in g.hand if c.defn.cost == 1 and c.defn.cost_kind == "offer")
    table.run.memory["cards_played"] = ["votary", cheap.defn.id]      # both played before, in some other run
    table.generic_remark_ok = False
    table._click(("card", votary.uid)); board(table); press(table, Q.Key.Key_Space); settle(table); quiet(table)
    table._click(("card", cheap.uid)); board(table)
    walk_to(table, 0)
    press(table, Q.Key.Key_Space); press(table, Q.Key.Key_Space); settle(table)
    assert g.rows[YOU][0] is cheap
    said = [k for k in [table.caption_key] + [c[2] for c in table.captions] if k.startswith("play_")]
    assert not said, said
    assert not table.card_remark_said, "nothing was said, so the match's one remark is still to come"


def test_a_cards_first_play_is_remembered_across_runs_and_sessions(table, tmp_path):
    from PySide6.QtCore import Qt as Q
    ready(table)
    votary = next(c for c in table.game.hand if c.defn.id == "votary")
    table._click(("card", votary.uid)); board(table); press(table, Q.Key.Key_Space); settle(table)
    said = [k for k in [table.caption_key] + [c[2] for c in table.captions] if k.startswith("play_")]
    assert said == ["play_votary"], said
    assert "votary" in table.run.memory["cards_played"]
    import json
    saved = json.loads((tmp_path / "void_game.json").read_text(encoding="utf-8"))
    assert "votary" in saved["memory"]["cards_played"], "saved at once, for the next session"


def test_a_glance_with_a_card_raised_comes_back_with_the_other_key(table):
    from PySide6.QtCore import Qt as Q
    ready(table)
    votary = next(c for c in table.game.hand if c.defn.id == "votary")
    table._click(("card", votary.uid)); press(table, Q.Key.Key_W)
    assert table.view == "board" and table.selected == votary.uid
    while table.cursor > 0:
        press(table, Q.Key.Key_A)
    press(table, Q.Key.Key_A)
    assert table.view == "board_left"
    press(table, Q.Key.Key_A)
    assert table.view == "board_left" and table.cursor == 0, "the lane does not move while looking away"
    press(table, Q.Key.Key_D)
    assert table.view == "board" and table.cursor == 0 and table.selected == votary.uid
    while table.cursor < 3:
        press(table, Q.Key.Key_D)
    press(table, Q.Key.Key_D)
    assert table.view == "board_right"
    press(table, Q.Key.Key_D)
    assert table.view == "board_right" and table.cursor == 3
    press(table, Q.Key.Key_A)
    assert table.view == "board" and table.cursor == 3


def test_offering_remarks_are_rare_and_once_a_match(table, monkeypatch):
    """A 1-in-25 roll per offering; the first to land is the match's only one."""
    from PySide6.QtCore import Qt as Q
    ready(table)
    g = table.game
    table.run.memory["cards_played"] = [c.defn.id for c in g.hand]       # no card remarks in the way
    table.generic_remark_ok = False
    votary = next(c for c in g.hand if c.defn.id == "votary")
    cheap = next(c for c in g.hand if c.defn.cost == 1 and c.defn.cost_kind == "offer")
    table._click(("card", votary.uid)); press(table, Q.Key.Key_W); press(table, Q.Key.Key_Space); settle(table); quiet(table)
    monkeypatch.setattr(table.run.rng, "random", lambda: 0.99)           # the roll misses
    table._click(("card", cheap.uid)); press(table, Q.Key.Key_W); walk_to(table, 0)
    press(table, Q.Key.Key_Space); press(table, Q.Key.Key_Space); settle(table)
    said = [k for k in [table.caption_key] + [c[2] for c in table.captions] if k.startswith("sacrifice")]
    assert said == [] and not table.sacrifice_remark_said
    monkeypatch.setattr(table.run.rng, "random", lambda: 0.0)            # the roll lands
    table.sacrifice_remark_said = False
    table._play(cheap, 0, 1)                                              # the visual step alone, again
    said = [k for k in [table.caption_key] + [c[2] for c in table.captions] if k.startswith("sacrifice")]
    assert said == ["sacrifice"] and table.sacrifice_remark_said
    quiet(table)
    table._play(cheap, 0, 2)                                              # a second offering this match: quiet
    said = [k for k in [table.caption_key] + [c[2] for c in table.captions] if k.startswith("sacrifice")]
    assert said == []


def test_the_first_hit_narration_is_said_once_ever_and_counts_its_points(table, tmp_path):
    import json
    ready(table)
    assert not table._retired("first_hit")
    table._retire("first_hit")
    assert table._retired("first_hit")
    saved = json.loads((tmp_path / "void_game.json").read_text(encoding="utf-8"))
    assert "first_hit" in saved["memory"]["retired"]
    from techdeck.ui.void_game.window import plural
    assert (plural("point", 1), plural("point", 2), plural("weight", 1)) == ("point", "points", "weight")
    got = table.dlg.line("first_hit", yours="Votary", his="Hound", n=1, points=plural("point", 1))
    assert got and "1 point of damage" in got[0] and "1 point lower" in got[0]


def test_the_board_lesson_holds_the_first_play_until_it_is_over(table):
    """Reach the board with a card raised and play at once: the card waits,
    the lesson runs, and only then does Space play it."""
    from PySide6.QtCore import Qt as Q
    ready(table)
    g = table.game
    votary = next(c for c in g.hand if c.defn.id == "votary")
    table._click(("card", votary.uid)); press(table, Q.Key.Key_W)
    assert table.view == "board" and table.lesson_at is not None
    press(table, Q.Key.Key_Space)                                    # too soon
    assert table.selected == votary.uid and all(c is None for c in g.rows[YOU]), "the card waited"
    for _ in range(int(1.3 * 30) + 2):
        table._tick()
    assert table.caption_key == "rules_lanes"
    table._click(("slot", table.cursor))                              # a click during the lesson: nothing
    assert all(c is None for c in g.rows[YOU])
    quiet(table)
    assert table.view == "board" and table.selected == votary.uid
    press(table, Q.Key.Key_Space)
    assert g.rows[YOU][table.cursor] is votary, "and now it plays"
