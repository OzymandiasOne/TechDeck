"""Tests for the achievements progress/claim helpers (pure logic over a real
SettingsManager backed by a temp dir)."""

from techdeck.core.settings import SettingsManager
from techdeck.core import achievements as ach


def test_achievement_ids_are_unique():
    assert len(ach.ACHIEVEMENTS_BY_ID) == len(ach.ACHIEVEMENTS)


def test_first_buy_claim_flow(tmp_path):
    s = SettingsManager(settings_dir=tmp_path)
    a = ach.ACHIEVEMENTS_BY_ID["first_buy"]          # target: 1 purchase

    assert ach.is_claimable(a, s) is False           # nothing bought yet
    s.unlock_item("some_item")
    assert ach.is_complete(a, s) is True
    assert ach.is_claimable(a, s) is True

    before = s.get_tickets()
    awarded = ach.claim(a, s)
    assert awarded == a.reward
    assert s.get_tickets() == before + a.reward
    assert ach.is_claimable(a, s) is False           # already claimed
    assert ach.claim(a, s) == 0                       # double-claim awards nothing


def test_claimable_count_tracks_completion(tmp_path):
    s = SettingsManager(settings_dir=tmp_path)
    base = ach.claimable_count(s)
    s.unlock_item("x")                                # completes first_buy
    assert ach.claimable_count(s) == base + 1
