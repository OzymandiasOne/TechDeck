"""The game engine, tested without a screen."""
import pytest

from techdeck.ui.void_game import cards as C
from techdeck.ui.void_game.rules import (HIM, LANES, SCALE_TO_WIN, YOU, Card, Game,
                                          IllegalMove)


def kinds(events):
    return [e.kind for e in events]


def fresh(**kw) -> Game:
    g = Game(seed=kw.pop("seed", 1), **kw)
    g.start()
    return g


def put(g: Game, card_id: str, owner: str, lane: int, incoming=False) -> Card:
    card = g._make(card_id, owner)
    if incoming:
        g.incoming[lane] = card
    else:
        g.rows[owner][lane] = card
    return card


def in_hand(g: Game, card_id: str) -> Card:
    card = g._make(card_id, YOU)
    g.hand.append(card)
    return card


# ── the opening ───────────────────────────────────────────────────────────
def test_opening_hand_is_three_from_the_deck_plus_one_votary():
    g = fresh()
    assert len(g.hand) == 4
    assert sum(c.defn.id == "votary" for c in g.hand) == 1
    assert len(g.deck) == len(C.STARTER_DECK) - 3
    assert g.votaries == C.VOTARY_PILE - 1


def test_you_see_his_first_move_before_you_act():
    g = fresh()
    assert any(c is not None for c in g.incoming)
    assert all(c is None for c in g.rows[HIM])


def test_no_draw_on_turn_one():
    g = fresh()
    assert g.phase == "play"
    with pytest.raises(IllegalMove):
        g.draw("deck")


def test_cannot_start_twice():
    g = fresh()
    with pytest.raises(IllegalMove):
        g.start()


# ── paying for cards ──────────────────────────────────────────────────────
def test_a_free_card_needs_an_empty_lane():
    g = fresh()
    votary = next(c for c in g.hand if c.defn.id == "votary")
    events = g.play(votary.uid, 0)
    assert kinds(events) == ["play"]
    assert g.rows[YOU][0] is votary
    assert votary not in g.hand
    with pytest.raises(IllegalMove, match="lane is taken"):
        g.play(in_hand(g, "votary").uid, 0)


def test_offerings_pay_for_a_card():
    g = fresh()
    put(g, "votary", YOU, 0)
    put(g, "votary", YOU, 1)
    hound = in_hand(g, "hound")               # costs 2
    assert "demands 2" in g.why_not(hound.uid, 2)
    assert "demands 2" in g.why_not(hound.uid, 2, [0])
    events = g.play(hound.uid, 2, [0, 1])
    assert kinds(events) == ["sacrifice", "die", "remnants", "sacrifice", "die", "remnants", "play"]
    assert g.rows[YOU][0] is None and g.rows[YOU][1] is None
    assert g.rows[YOU][2] is hound
    assert g.remnants == 2                    # every death of yours leaves a remnant


def test_you_can_play_into_the_lane_you_just_emptied():
    g = fresh()
    put(g, "votary", YOU, 0)
    scarab = in_hand(g, "scarab")
    g.play(scarab.uid, 0, [0])
    assert g.rows[YOU][0] is scarab


def test_the_same_offering_cannot_be_used_twice():
    g = fresh()
    put(g, "votary", YOU, 0)
    hound = in_hand(g, "hound")
    with pytest.raises(IllegalMove, match="same one twice"):
        g.play(hound.uid, 1, [0, 0])


def test_a_worthy_offering_counts_as_three():
    g = fresh()
    worthy = put(g, "votary", YOU, 0)
    worthy.sigils = (C.WORTHY,)
    sleeper = in_hand(g, "sleeper")           # costs 3
    g.play(sleeper.uid, 1, [0])
    assert g.rows[YOU][1] is sleeper


def test_free_cards_refuse_offerings():
    g = fresh()
    put(g, "votary", YOU, 0)
    with pytest.raises(IllegalMove, match="asks for no offering"):
        g.play(in_hand(g, "votary").uid, 1, [0])


def test_remnant_cards_cost_remnants_not_lives():
    g = fresh()
    monolith = in_hand(g, "monolith")         # 3 remnants
    assert "costs 3 remnants" in g.why_not(monolith.uid, 0)
    g.remnants = 3
    events = g.play(monolith.uid, 0)
    assert kinds(events) == ["remnants", "play"]
    assert g.remnants == 0


def test_can_afford_looks_at_the_whole_board():
    g = fresh()
    hound = in_hand(g, "hound")
    assert not g.can_afford(hound.uid)
    put(g, "votary", YOU, 0)
    put(g, "votary", YOU, 3)
    assert g.can_afford(hound.uid)


# ── drawing ───────────────────────────────────────────────────────────────
def test_second_turn_starts_with_one_draw_from_either_pile():
    g = fresh()
    g.ring_bell()
    assert g.phase == "draw"
    with pytest.raises(IllegalMove, match="Draw first"):
        g.ring_bell()
    before = len(g.hand)
    g.draw("votary")
    assert len(g.hand) == before + 1 and g.phase == "play"
    with pytest.raises(IllegalMove, match="already drawn"):
        g.draw("deck")


def test_empty_piles_cannot_be_drawn_from():
    g = fresh()
    g.ring_bell()
    g.deck.clear()
    assert not g.can_draw("deck")
    with pytest.raises(IllegalMove, match="empty"):
        g.draw("deck")
    g.votaries = 0
    g.ring_bell()                             # nothing left to draw: allowed straight through


# ── the bell and combat ───────────────────────────────────────────────────
def test_an_unblocked_strike_lands_as_weight_on_the_scale():
    g = fresh(plan=[[]] * 20)
    g.incoming = [None] * LANES
    put(g, "hound", YOU, 1)
    events = g.ring_bell()
    assert g.scale == 2
    strike = next(e for e in events if e.kind == "strike")
    assert strike["direct"] and strike["power"] == 2


def test_a_blocked_strike_wounds_the_card_in_front():
    g = fresh(plan=[[]] * 20)
    g.incoming = [None] * LANES
    put(g, "hound", YOU, 1)
    his = put(g, "sleeper", HIM, 1)           # 4/6
    g.ring_bell()
    assert his.health == 4
    assert g.rows[YOU][1] is None             # and it hits back on his turn: 4 into a 2/2
    assert g.scale == 0                       # the hound stood in the way, so no weight


def test_a_killing_blow_clears_the_lane():
    g = fresh(plan=[[]] * 20)
    g.incoming = [None] * LANES
    put(g, "hound", YOU, 1)
    put(g, "scarab", HIM, 1)                  # 1/2
    events = g.ring_bell()
    assert "die" in kinds(events)
    assert g.rows[HIM][1] is None
    assert g.remnants == 0                    # his deaths give you nothing


def test_tipping_the_scale_ends_the_game():
    g = fresh(plan=[[]] * 20)
    g.incoming = [None] * LANES
    put(g, "sleeper", YOU, 0)
    put(g, "hound", YOU, 1)
    events = g.ring_bell()
    assert g.winner == YOU and g.phase == "over"
    assert kinds(events)[-1] == "game_over"
    assert g.scale >= SCALE_TO_WIN
    with pytest.raises(IllegalMove):
        g.ring_bell()


def test_he_can_win_too():
    g = fresh(plan=[[]] * 20)
    g.incoming = [None] * LANES
    put(g, "sleeper", HIM, 0)
    put(g, "hound", HIM, 1)
    g.ring_bell()
    assert g.winner == HIM


def test_his_incoming_row_advances_before_he_strikes():
    g = fresh(plan=[[("hound", 2)], []] + [[]] * 20)
    # the opening already committed the first plan entry into lane 2
    coming = g.incoming[2]
    assert coming is not None and coming.defn.id == "hound"
    events = g.ring_bell()
    assert "advance" in kinds(events)
    assert g.rows[HIM][2] is coming
    assert g.scale == -2                      # it moved up AND struck the same turn


def test_incoming_waits_while_a_card_is_still_in_front_of_it():
    g = fresh(plan=[[]] * 20)
    g.incoming = [None] * LANES
    blocker = put(g, "sleeper", HIM, 2)
    waiting = put(g, "scarab", HIM, 2, incoming=True)
    g.ring_bell()
    assert g.rows[HIM][2] is blocker
    assert g.incoming[2] is waiting


def test_he_improvises_after_the_script_runs_out():
    g = fresh(plan=[], pool=["scarab"])
    assert sum(c is not None for c in g.incoming) == 1
    assert next(c for c in g.incoming if c).defn.id == "scarab"


# ── sigils ────────────────────────────────────────────────────────────────
def test_winged_flies_over_a_blocker():
    g = fresh(plan=[[]] * 20)
    g.incoming = [None] * LANES
    put(g, "huginn", YOU, 0)
    wall = put(g, "sleeper", HIM, 0)
    events = g.ring_bell()
    strike = next(e for e in events if e.kind == "strike" and e["card"].defn.id == "huginn")
    assert strike["flew"] and wall.health == 6
    assert g.scale == 1                       # its 1 landed; the wall then ate the raven
    assert g.rows[YOU][0] is None


def test_a_warden_stops_winged_things():
    g = fresh(plan=[[]] * 20)
    g.incoming = [None] * LANES
    put(g, "huginn", YOU, 0)
    wall = put(g, "monolith", HIM, 0)
    g.ring_bell()
    assert wall.health == 4 and g.scale == 0


def test_venom_kills_whatever_it_wounds():
    g = fresh(plan=[[]] * 20)
    g.incoming = [None] * LANES
    put(g, "weigher", YOU, 0)                 # 1 power
    put(g, "sleeper", HIM, 0)                 # 6 health
    events = g.ring_bell()
    die = next(e for e in events if e.kind == "die")
    assert die["cause"] == "venom"
    assert g.rows[HIM][0] is None


def test_three_mouths_bites_three_lanes():
    g = fresh(plan=[[]] * 20)
    g.incoming = [None] * LANES
    put(g, "cerberus", YOU, 1)                # 2 power
    left = put(g, "sleeper", HIM, 0)
    right = put(g, "sleeper", HIM, 2)
    g.ring_bell()
    assert left.health == 4 and right.health == 4
    assert g.scale == 2 - 8                   # middle lane was open: 2 landed; then they hit back


def test_three_mouths_at_the_edge_only_bites_what_exists():
    g = fresh(plan=[[]] * 20)
    g.incoming = [None] * LANES
    put(g, "cerberus", YOU, 0)
    g.ring_bell()
    assert g.scale == 4                       # lanes 0 and 1, nothing at -1


def test_gaze_weakens_the_card_facing_it():
    g = fresh(plan=[[]] * 20)
    g.incoming = [None] * LANES
    gorgon = put(g, "gorgon", YOU, 0)         # 1/2, GAZE
    put(g, "scarab", HIM, 0)                  # 1 power -> 0 against the gorgon
    g.ring_bell()
    assert gorgon.health == 2


def test_undying_returns_to_hand_stronger():
    g = fresh(plan=[[]] * 20)
    g.incoming = [None] * LANES
    snake = put(g, "ouroboros", YOU, 0)       # 1/1
    put(g, "sleeper", HIM, 0)
    events = g.ring_bell()
    back = next(e for e in events if e.kind == "return")["card"]
    assert back in g.hand and back is not snake
    assert (back.power, back.health) == (2, 2)
    assert g.remnants == 1


def test_undying_keeps_its_bonus_when_sacrificed_too():
    g = fresh()
    snake = put(g, "ouroboros", YOU, 0)
    g.play(in_hand(g, "scarab").uid, 1, [0])
    back = next(c for c in g.hand if c.defn.id == "ouroboros")
    assert back is not snake and back.power == 2


def test_a_dead_star_becomes_a_nova_after_a_turn():
    g = fresh(plan=[[]] * 20)
    g.incoming = [None] * LANES
    star = put(g, "dead_star", YOU, 0)
    events = g.ring_bell()                    # it survives his turn...
    grown = next(e for e in events if e.kind == "grow")["card"]
    assert grown.defn.id == "nova" and g.rows[YOU][0] is grown   # ...and wakes on yours
    assert grown is not star


def test_his_dead_star_grows_on_his_turn():
    g = fresh(plan=[[]] * 20)
    g.incoming = [None] * LANES
    put(g, "dead_star", HIM, 3)
    g.ring_bell()                             # his turn passes with it on the board
    assert g.rows[HIM][3].defn.id == "dead_star"
    g.draw("votary")
    g.ring_bell()                             # it wakes at the start of his next turn
    assert g.rows[HIM][3].defn.id == "nova"


# ── the whole game holds together ─────────────────────────────────────────
def greedy_turn(g: Game):
    """Free cards first, then the biggest card you can pay for, then ring."""
    if g.phase == "draw":
        fodder = any(c.defn.cost == 0 for c in g.hand)
        want = "deck" if fodder else "votary"
        g.draw(want if g.can_draw(want) else ("votary" if want == "deck" else "deck"))
    played = True
    while played and g.phase == "play":
        played = False
        for card in sorted(g.hand, key=lambda c: (c.defn.cost > 0, -c.power)):
            if not g.can_afford(card.uid):
                continue
            d = card.defn
            free = [i for i in range(LANES) if g.rows[YOU][i] is None]
            sac = []
            if d.cost_kind == C.OFFER and d.cost:
                worth = 0
                weakest = sorted((i for i, c in enumerate(g.rows[YOU]) if c is not None),
                                 key=lambda i: g.rows[YOU][i].power)
                for i in weakest:
                    if worth < d.cost:
                        sac.append(i)
                        worth += g.offering_worth(g.rows[YOU][i])
                if card.power <= sum(g.rows[YOU][i].power for i in sac):
                    continue                  # never eat more than you gain
            elif not free:
                continue
            g.play(card.uid, (free or sac)[0], sac)
            played = True
            break
    g.ring_bell()


@pytest.mark.parametrize("seed", range(25))
def test_every_game_ends_and_someone_wins(seed):
    g = fresh(seed=seed)
    for _ in range(60):
        if g.phase == "over":
            break
        greedy_turn(g)
    assert g.phase == "over" and g.winner in (YOU, HIM)


def test_the_first_game_is_winnable():
    wins = 0
    for seed in range(40):
        g = fresh(seed=seed)
        while g.phase != "over":
            greedy_turn(g)
        wins += g.winner == YOU
    assert wins >= 8, f"the greedy bot won only {wins} of 40"


def test_every_event_carries_only_plain_data():
    """Events feed the animator. Every card in them is a live Card, every lane an int."""
    g = fresh()
    for _ in range(6):
        if g.phase == "over":
            break
        greedy_turn(g)
    for e in g.ring_bell() if g.phase != "over" else []:
        for k, v in e.data.items():
            if k.endswith("lane"):
                assert isinstance(v, int)
            if k in ("card", "defender", "was"):
                assert isinstance(v, Card)
