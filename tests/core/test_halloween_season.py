"""The Halloween season gate — the one switch every seasonal feature checks.

Mirrors test_puppet_master_gate.py's philosophy: pin BOTH states. The window
must open on Oct 1 and close after Nov 2, the env override must force either
state in any month, and the professional theme must suppress the FEATURES
(never the seasonal theme itself - reversed 2026-10-16, see effective_theme).
"""

import datetime

from techdeck.core.constants import (
    HALLOWEEN_SEASON, halloween_active, is_halloween_season,
)


def _d(month, day):
    return datetime.date(2026, month, day)


def test_window_boundaries():
    assert not is_halloween_season(_d(9, 30))     # night before
    assert is_halloween_season(_d(10, 1))         # opening day
    assert is_halloween_season(_d(10, 31))        # the day itself
    assert is_halloween_season(_d(11, 2))         # last day
    assert not is_halloween_season(_d(11, 3))     # over


def test_ordinary_months_are_off():
    for month in (1, 2, 3, 4, 5, 6, 7, 8, 9, 12):
        assert not is_halloween_season(_d(month, 15)), month


def test_env_override_forces_either_state(monkeypatch):
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "1")
    assert is_halloween_season()                  # August, forced on
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "0")
    assert not is_halloween_season()              # forced off, any month


def test_explicit_date_ignores_the_override(monkeypatch):
    # Tests and callers passing a date want pure calendar logic.
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "1")
    assert not is_halloween_season(_d(8, 10))
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "0")
    assert is_halloween_season(_d(10, 31))


class _Settings:
    def __init__(self, professional):
        self._professional = professional

    def is_professional(self):
        return self._professional


def test_halloween_active_needs_season_and_not_professional(monkeypatch):
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "1")
    assert halloween_active(settings=_Settings(professional=False))
    # The professional theme suppresses the whole update.
    assert not halloween_active(settings=_Settings(professional=True))
    # Out of season nothing shows, whatever the theme.
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "0")
    assert not halloween_active(settings=_Settings(professional=False))


def test_window_constant_shape():
    (m0, d0), (m1, d1) = HALLOWEEN_SEASON
    assert (m0, d0) == (10, 1)
    assert (m1, d1) == (11, 2)


# ── the seasonal default theme ────────────────────────────────────────────

def _mgr(tmp_path):
    from techdeck.core.settings import SettingsManager
    return SettingsManager(settings_dir=tmp_path)


def test_halloween_is_the_default_theme_in_season(tmp_path, monkeypatch):
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "1")
    s = _mgr(tmp_path)
    assert s.get_theme() == "halloween"          # overrides the dark default
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "0")
    assert s.get_theme() == "dark"               # out of season: untouched


def test_professional_users_DO_get_the_seasonal_look(tmp_path, monkeypatch):
    """Reversed on 2026-10-16 (his call) after a user on professional silently
    missed the entire Halloween update. A seasonal theme we decide the app
    should open in is a product decision, not a personality feature — so it
    applies to professional too, while professional keeps its sober FEATURE
    set (no crawlies, no stock, no games). Set the stored pick directly: going
    through set_theme IN season is an explicit choice and records an opt-out,
    which is the next test."""
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "1")
    s = _mgr(tmp_path)
    s.data.setdefault("settings", {})["theme"] = "professional"
    assert s.get_stored_theme() == "professional"   # what they picked
    assert s.get_theme() == "halloween"             # what they wear
    assert s.is_professional()                      # features stay sober
    assert not halloween_active(settings=s)         # so: no crawlies


def test_professional_picked_in_season_is_still_an_opt_out(tmp_path, monkeypatch):
    # Explicitly choosing professional DURING the season means "no thanks".
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "1")
    s = _mgr(tmp_path)
    s.set_theme("professional")
    assert s.get_theme() == "professional"
    assert s.is_professional()


def test_picking_another_theme_in_season_sticks(tmp_path, monkeypatch):
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "1")
    s = _mgr(tmp_path)
    assert s.get_theme() == "halloween"
    s.set_theme("cyberpunk")                     # explicit opt-out
    assert s.get_theme() == "cyberpunk"
    s.set_theme("halloween")                     # opting back in works
    assert s.get_theme() == "halloween"


def test_opt_out_expires_with_the_year(tmp_path, monkeypatch):
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "1")
    s = _mgr(tmp_path)
    s.set_theme("cyberpunk")
    # Fake last year's opt-out: next October the magic returns.
    s.data["settings"]["halloween_opt_out_year"] = 2025
    assert s.get_theme() == "halloween"
