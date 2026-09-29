"""The road between fights, and what survives a run."""
import pytest

from techdeck.ui.void_game import cards as C
from techdeck.ui.void_game.rules import HIM, LANES, YOU
from techdeck.ui.void_game.run import CANDLES, ROAD_LENGTH, DeckCard, Run, empty_memory
from tests.void_game.test_rules import greedy_turn


def finish(run: Run, make_you_win: bool | None = None):
    """Play the current fight out with the greedy bot; optionally rig the end."""
    g = run.game
    if g.phase == "new":
        g.start()                              # the window does this when the table appears
    if make_you_win is not None:
        g.phase = "over"
        g.winner = YOU if make_you_win else HIM
        g.scale = 6 if make_you_win else -5
    while g.phase != "over":
        greedy_turn(g)
    return run.settle_fight()


def test_the_road_opens_with_a_fight_then_three_doors():
    run = Run(seed=1)
    assert [s.kind for s in run.offer()] == ["fight"]
    run.choose(0)
    assert run.game is not None and run.step == 1
    finish(run, make_you_win=True)
    doors = run.offer()
    assert len(doors) == 3 and len({d.kind for d in doors}) == 3
    assert all(d.kind in ("fight", "choice", "fire", "altar", "rare") for d in doors)


def test_the_first_fight_is_his_scripted_one():
    run = Run(seed=2)
    run.offer(); run.choose(0)
    assert run.game.plan[0] == [("votary", 1)]


def test_him_at_the_end_of_the_road():
    run = Run(seed=3)
    run.step = ROAD_LENGTH
    assert [s.kind for s in run.offer()] == ["boss"]
    run.choose(0)
    assert run.game.boss


def test_losing_costs_a_candle_and_the_second_loss_kills():
    run = Run(seed=4)
    run.offer(); run.choose(0)
    assert finish(run, make_you_win=False) == "lost"
    assert run.candles == CANDLES - 1 and not run.over
    run.offer(); run.choose(next(i for i, s in enumerate(run.offers) if s.kind == "fight") if any(s.kind == "fight" for s in run.offers) else 0)
    if run.game is None:                       # picked a non-fight door: take a fight next
        run.offer(); run.offers = [run._stop("fight")]; run.choose(0)
    assert finish(run, make_you_win=False) == "dead"
    assert run.dead and run.over and run.memory["deaths"] == 1


def test_a_card_taken_at_a_choice_is_in_the_next_fight():
    run = Run(seed=5)
    run.offer(); run.choose(0); finish(run, make_you_win=True)
    run.offers = [run._stop("choice")]; run.choose(0)
    picked = run.take_card(1)
    assert picked in run.deck
    run.offers = [run._stop("fight")]; run.choose(0)
    ids = [e["id"] if isinstance(e, dict) else e for e in run.game.deck] + [c.defn.id for c in run.game.hand]
    assert picked.id in ids


def test_the_fire_buffs_first_and_may_eat_later():
    run = Run(seed=6)
    run.offer(); run.choose(0); finish(run, make_you_win=True)
    run.offers = [run._stop("fire")]; run.choose(0)
    card = run.deck[0]
    assert run.rest(0) == "buffed"
    assert (card.power, card.health) in ((1, 0), (0, 2))
    outcomes = {run.rest(0) for _ in range(3)}
    assert outcomes <= {"buffed", "eaten"}


def test_the_fire_buff_reaches_the_table():
    run = Run(seed=7)
    run.offer(); run.choose(0); finish(run, make_you_win=True)
    run.offers = [run._stop("fire")]; run.choose(0)
    run.stop.fire = "power"
    run.rest(0)
    boosted = run.deck[0]
    g = run.new_game()
    card = g._make_entry(boosted.as_entry())
    assert card.power == boosted.defn.power + 1


def test_the_altar_moves_sigils_and_takes_the_giver():
    run = Run(seed=8)
    run.offer(); run.choose(0); finish(run, make_you_win=True)
    run.offers = [run._stop("altar")]; run.choose(0)
    giver = next(i for i, c in enumerate(run.deck) if c.id == "huginn")
    taker = next(i for i, c in enumerate(run.deck) if c.id == "hound")
    n = len(run.deck)
    got = run.altar(giver, taker)
    assert C.WINGED in got.sigils and len(run.deck) == n - 1
    g = run.new_game()
    card = g._make_entry(got.as_entry())
    assert card.has(C.WINGED)


def test_a_dead_player_forges_a_deathcard_that_later_runs_remember():
    run = Run(seed=9)
    run.candles = 1
    run.offer(); run.choose(0)
    assert finish(run, make_you_win=False) == "dead"
    cost_i = next(i for i, c in enumerate(run.deck) if c.id == "hound")      # 2 offerings
    stats_i = next(i for i, c in enumerate(run.deck) if c.id == "scarab")    # 1/2
    sig_i = next(i for i, c in enumerate(run.deck) if c.id == "huginn")      # winged
    d = run.forge_deathcard("Anthony", cost_i, stats_i, sig_i)
    assert d.deathcard and d.name == "ANTHONY" and (d.power, d.health, d.cost) == (1, 2, 2)
    assert C.WINGED in d.sigils and d.id in C.CARDS
    mem = run.memory
    assert len(mem["deathcards"]) == 1
    later = Run(seed=10, memory=mem)
    assert later.memory["runs"] == 2
    # rarely in his plans, sometimes in your deck: over many seeds both happen
    his, yours = 0, 0
    for seed in range(60):
        r = Run(seed=seed, memory=mem)
        yours += any(c.id == d.id for c in r.deck)
        r.step = 4
        plan, _ = r._plan(False)
        his += any(cid == d.id for row in plan for cid, _ in row)
    assert yours > 0 and his > 0


def test_the_boss_has_a_second_phase():
    run = Run(seed=11)
    run.step = ROAD_LENGTH
    run.offer(); run.choose(0)
    g = run.game
    g.start()
    if g.phase == "draw":
        g.draw("votary")
    g.incoming = [None] * LANES
    g.rows[HIM] = [None] * LANES
    from tests.void_game.test_rules import put
    put(g, "sleeper", YOU, 0); put(g, "hound", YOU, 1)
    events = g.ring_bell()
    assert any(e.kind == "boss_phase" for e in events)
    assert g.phase != "over" and g.scale == 0 and g.boss_phase == 2
    unmade = [e for e in events if e.kind == "unmade"]
    assert len(unmade) == 2 and all(e["card"].defn.id == "votary" for e in unmade), "he unmakes your board"
    assert any(c is not None for c in g.incoming), "and plays what he kept back"


def test_an_ouroboros_remembers_dying_across_fights_and_runs():
    run = Run(seed=12)
    run.offer(); run.choose(0)
    g = run.game
    g.undying_bonus["ouroboros"] = 2
    finish(run, make_you_win=True)
    assert run.memory["undying_bonus"]["ouroboros"] == 2
    again = Run(seed=13, memory=run.memory)
    again.offer(); again.choose(0)
    assert again.game._make("ouroboros", YOU).power == 3


@pytest.mark.parametrize("seed", range(6))
def test_a_whole_run_ends_one_way_or_the_other(seed):
    run = Run(seed=seed)
    guard = 0
    while not run.over and guard < 60:
        guard += 1
        doors = run.offer()
        pick = next((i for i, d in enumerate(doors) if d.kind in ("fight", "boss")), 0)
        stop = run.choose(pick)
        if stop.kind in ("fight", "boss"):
            finish(run)
        elif stop.kind in ("choice", "rare"):
            run.take_card(0)
        elif stop.kind == "fire":
            run.rest(0)
        elif stop.kind == "altar" and len(run.deck) > 2:
            run.altar(0, 1)
    assert run.over and (run.won or run.dead)
