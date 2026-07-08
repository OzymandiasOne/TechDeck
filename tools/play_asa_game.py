"""
Dev launcher for ASA: The Video Game — boot straight into any chapter.

The plugin normally starts you at five tons of scrap. This opens the real game
window pre-seeded to a chosen stage so you can test the late game without
grinding the whole arc first. It drives the game's own unlock methods
(_complete_project, _buy_*) so the seeded state matches real progression, then
tops up money/ops/steel so the stage is playable from the moment it opens.

Usage (from the repo root, dev environment):
    python tools/play_asa_game.py                 # interactive menu
    python tools/play_asa_game.py space           # boot into ASA Space Division
    python tools/play_asa_game.py --list          # list stage names

Stages (each is cumulative — everything before it is already unlocked):
    yard        fresh start (identical to the shipped plugin)
    tech        Tech Team + a fully-kitted yard, reputation to spend
    aframes     A-Frame division open, fabs running, steel stocked
    market      Trading Desk section revealed on the Tech Team tab, cash to trade
    drones      Drone Fleet, a few drones deployed
    space       ASA Space Division, orbital hardware in place
    probes      Probe Program: the UI has TRANSFORMED to the 2-tab probe interface;
                probes launched, trust allocated, replicating
    drift       Probes mid-drift — the drifter swarm + the Combat button live
    converting  Universe 100% explored, the matter-conversion finale running
    ending      Straight to the end screen (rest / new universe)

This is a dev tool: it imports the widget directly and never touches the
Emporium unlock gate, so you don't need to buy the game first.
"""
from __future__ import annotations

import os
import sys

# Repo root on path (this file lives in <root>/tools/)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from PySide6.QtWidgets import QApplication  # noqa: E402

from techdeck.ui.widgets.steelbeams_game import SteelBeamsGame, PROJECTS  # noqa: E402


STAGES = [
    "yard", "tech", "aframes", "market", "drones",
    "space", "probes", "drift", "converting", "ending",
]

# Comfortable "play from here" bankroll per stage.
_MONEY = {
    "tech": 100_000, "aframes": 250_000, "market": 500_000,
    "drones": 2_000_000, "space": 25_000_000, "probes": 100_000_000,
    "drift": 100_000_000, "converting": 100_000_000, "ending": 0,
}


def _grant(g: SteelBeamsGame, pid: str) -> None:
    """Complete a project the honest way: cheat in just enough currency, then
    call the game's own handler so every unlock/tab/effect fires normally."""
    proj = next((p for p in PROJECTS if p["id"] == pid), None)
    if proj is None or pid in g.completed_projects:
        return
    if proj.get("cur", "ops") == "ops":
        g.ops = max(g.ops, proj["cost"])
    else:
        g.inno_unlocked = True
        g.inno = max(g.inno, proj["cost"])
    g._complete_project(pid)


def _kit_yard(g: SteelBeamsGame) -> None:
    """Give the Yard a full, running loadout without minding the cost curve."""
    keep = g.money
    g.money = 1e15
    g.steel = 1_000_000
    for _ in range(10):
        g._buy_auto_fab()
    g._buy_faster()
    g._buy_bulk()
    g._buy_precision()
    for _ in range(4):
        g._buy_marketing()
    g.money = keep


def _staff_tech(g: SteelBeamsGame) -> None:
    """Reputation + a team so ops actually flow on arrival."""
    g.rep_total += 16
    g.developers = 8
    g.servers = 8
    g.ops = g._ops_cap * 0.5


def apply_stage(g: SteelBeamsGame, stage: str) -> None:
    if stage not in STAGES:
        raise SystemExit(f"Unknown stage '{stage}'. Options: {', '.join(STAGES)}")
    target = STAGES.index(stage)
    if target == 0:
        return  # pristine yard

    def reached(s: str) -> bool:
        return target >= STAGES.index(s)

    # --- Tech Team + kitted yard (baseline for everything past 'yard') ---
    g.total_money = max(g.total_money, 6_000)
    g._check_milestones()          # unlocks the Tech Team tab via the milestone
    _staff_tech(g)
    _kit_yard(g)
    _grant(g, "form_tech_team")
    _grant(g, "mega_fab")
    g.money = 1e15
    for _ in range(4):
        g._buy_mega_fab()

    if reached("aframes"):
        _grant(g, "aframe_proto")
        _grant(g, "solar_v1")
        g.money = 1e15
        g.steel = 1_000_000
        for _ in range(6):
            g._buy_af_fab()

    if reached("market"):
        _grant(g, "algo_trading")

    if reached("drones"):
        _grant(g, "drone_fleet")
        g.money = 1e15
        for _ in range(6):
            g._buy_mfg_drone()
            g._buy_del_drone()

    if reached("space"):
        _grant(g, "space_div")
        g.money = 1e15
        for _ in range(3):
            g._buy_solar_col()
            g._buy_space_fab()
        g._buy_harvester()

    if reached("probes"):
        _grant(g, "quantum")
        _grant(g, "probe_program")     # this TRANSFORMS the UI to the probe tabs
        g.servers = 40                 # big ops cap so probe launches don't starve
        g.probe_trust = 14
        g.money = 1e15
        g.ops = g._ops_cap
        for _ in range(6):
            g._launch_probe()
        # A sensible starter allocation (Speed/Exploration live on the Fleet tab,
        # the rest on the Replication tab, but the pool is shared)
        for _ in range(5): g._alloc_change("replicate", +1)
        for _ in range(4): g._alloc_change("explore", +1)
        for _ in range(3): g._alloc_change("speed", +1)
        for _ in range(2): g._alloc_change("shield", +1)

    if reached("drift"):
        # Enough probes + drifters to see the swarm and unlock Combat Subroutines
        g.probes = 5_000_000_000
        g.drifters = 250_000_000
        g._flags.add("drift_seen")
        g.explored = 3.5

    if reached("converting"):
        g.probes = 5e13
        g.drifters = 0.0
        g.combat_done = True
        g.explored = 100.0
        g.converting = True
        g.matter_pct = 30.0
        g._trust_fired = {f"tr{th}" for th in
                          (0.0001, 0.001, 0.01, 0.1, 1.0, 5.0, 10.0, 25.0, 50.0, 75.0, 99.0)}

    if stage == "ending":
        g.total_made = max(g.total_made, 9.9e13)
        g.total_money = max(g.total_money, 5e12)
        g._fire_ending()

    # Comfortable bankroll for the stage, and land on the most relevant tab.
    g.money = float(_MONEY.get(stage, g.money))
    _focus_tab(g, stage)
    g._log(f"[dev] Booted into stage: {stage.upper()}", "cyan")
    g._update_ui()


def _focus_tab(g: SteelBeamsGame, stage: str) -> None:
    # Market is a section on the Tech Team tab now, not a tab. From the probe
    # act on, only the two probe tabs exist.
    tab = {
        "tech": g._tech_tab, "aframes": g._aframe_tab, "market": g._tech_tab,
        "drones": g._drones_tab, "space": g._space_tab,
        "probes": g._probe_fleet_tab, "drift": g._probe_dev_tab,
        "converting": g._probe_fleet_tab, "ending": g._probe_dev_tab,
    }.get(stage)
    if tab is not None:
        # Guard: the tab only exists if its unlock ran (it always should have).
        if g.tabs.indexOf(tab) != -1:
            g.tabs.setCurrentWidget(tab)


def _pick_stage_interactive() -> str:
    print("ASA: The Video Game — dev stage launcher\n")
    for i, s in enumerate(STAGES):
        print(f"  {i}. {s}")
    raw = input("\nStage number or name (default 0=yard): ").strip()
    if not raw:
        return "yard"
    if raw.isdigit() and 0 <= int(raw) < len(STAGES):
        return STAGES[int(raw)]
    if raw in STAGES:
        return raw
    raise SystemExit(f"Unknown stage '{raw}'. Options: {', '.join(STAGES)}")


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if a]
    if args and args[0] in ("--list", "-l"):
        print("\n".join(STAGES))
        return 0
    if args and args[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    if args:
        stage = args[0].lower()
    else:
        stage = _pick_stage_interactive()

    app = QApplication.instance() or QApplication(sys.argv)
    game = SteelBeamsGame()
    apply_stage(game, stage)
    game.setWindowTitle(f"ASA: The Video Game  [DEV — {stage}]")
    game.show()
    game.raise_()
    game.activateWindow()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
