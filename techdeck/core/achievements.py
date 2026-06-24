"""
TechDeck Achievements — static catalog + progress/claim helpers.

Each achievement measures one trackable stat from SettingsManager and awards
tickets when its target is reached. Progress is computed on demand (no extra
bookkeeping); the only persisted state is which achievements have been claimed
(SettingsManager.claimed_achievements).

To add an achievement: append an Achievement with a `metric` callable that
returns the current value of whatever stat it tracks. Targets/rewards are tuned
here. The UI (AchievementsPage) renders the catalog generically.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from techdeck.core.settings import SettingsManager


@dataclass(frozen=True)
class Achievement:
    id: str
    title: str
    desc: str
    reward: int                              # tickets awarded on claim
    target: int                              # metric value that completes it
    metric: Callable[["SettingsManager"], int]  # current progress value
    difficulty: str = "bronze"               # bronze | silver | gold (trophy tint)


# Order = display order. Grouped milestone -> family -> multitask -> house/shop.
ACHIEVEMENTS: List[Achievement] = [
    # ── Total runs ──────────────────────────────────────────────────────────
    Achievement("first_run", "First Contact",
                "Run your first plugin.",
                10, 1, lambda s: s.get_total_runs(), "bronze"),
    Achievement("runs_25", "Getting the Hang of It",
                "Run 25 plugins total.",
                25, 25, lambda s: s.get_total_runs(), "bronze"),
    Achievement("runs_100", "Centurion",
                "Run 100 plugins total.",
                50, 100, lambda s: s.get_total_runs(), "silver"),
    Achievement("runs_250", "Workhorse",
                "Run 250 plugins total.",
                100, 250, lambda s: s.get_total_runs(), "gold"),
    # ── Family ──────────────────────────────────────────────────────────────
    Achievement("runs_911_10", "911 Operator",
                "Run 10 plugins from the 911 family.",
                30, 10, lambda s: s.get_family_runs("911"), "bronze"),
    Achievement("runs_911_50", "911 Veteran",
                "Run 50 plugins from the 911 family.",
                75, 50, lambda s: s.get_family_runs("911"), "silver"),
    Achievement("runs_922_10", "922 Specialist",
                "Run 10 plugins from the 922 family.",
                30, 10, lambda s: s.get_family_runs("922"), "bronze"),
    Achievement("runs_922_50", "922 Veteran",
                "Run 50 plugins from the 922 family.",
                75, 50, lambda s: s.get_family_runs("922"), "silver"),
    # ── Multitasking ────────────────────────────────────────────────────────
    Achievement("batch_4", "Multitasker",
                "Run 4 or more plugins at once.",
                40, 4, lambda s: s.get_max_run_batch(), "silver"),
    Achievement("batch_8", "Assembly Line",
                "Run 8 or more plugins at once.",
                80, 8, lambda s: s.get_max_run_batch(), "gold"),
    # ── My House / Emporium ─────────────────────────────────────────────────
    Achievement("first_buy", "Big Spender",
                "Buy your first item at Woogy's Emporium.",
                15, 1, lambda s: len(s.get_unlocked_items()), "bronze"),
    Achievement("green_thumb", "Green Thumb",
                "Plant the tree in your yard.",
                15, 1, lambda s: s.get_tree_stage(), "bronze"),
    Achievement("old_growth", "Old Growth",
                "Grow your tree to full size.",
                100, 5, lambda s: s.get_tree_stage(), "gold"),
]

ACHIEVEMENTS_BY_ID = {a.id: a for a in ACHIEVEMENTS}


def progress(a: Achievement, settings: "SettingsManager") -> Tuple[int, int]:
    """(current, target), current clamped to target for display."""
    return min(a.metric(settings), a.target), a.target


def is_complete(a: Achievement, settings: "SettingsManager") -> bool:
    return a.metric(settings) >= a.target


def is_claimable(a: Achievement, settings: "SettingsManager") -> bool:
    return is_complete(a, settings) and not settings.is_achievement_claimed(a.id)


def claimable_count(settings: "SettingsManager") -> int:
    """How many achievements are complete but not yet claimed (badge count)."""
    return sum(1 for a in ACHIEVEMENTS if is_claimable(a, settings))


def claim(a: Achievement, settings: "SettingsManager") -> int:
    """Claim an achievement's reward. Returns tickets awarded (0 if not claimable)."""
    if not is_claimable(a, settings):
        return 0
    settings.claim_achievement(a.id)
    settings.add_tickets(a.reward)
    return a.reward
