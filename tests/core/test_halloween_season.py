"""The Halloween season gate — the one switch every seasonal feature checks.

Mirrors test_puppet_master_gate.py's philosophy: pin BOTH states. The window
must open on Oct 1 and close after Nov 2, the env override must force either
state in any month, and the professional theme must suppress everything.
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
