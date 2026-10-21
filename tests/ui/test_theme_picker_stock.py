"""The theme picker's seasonal stock — and the one-way door it used to be.

A user on the professional theme silently missed the entire Halloween look
(0.8.7.8/0.8.7.9, reported 2026-10-16), and could not even FIND halloween in
the picker to opt in: the list filtered on halloween_active(), which folds in
the professional check. Worse, the list is built once at page construction, so
switching away from professional did nothing until TechDeck was restarted.

Pin all of it: the stock rule is the SEASON alone, and the list is rebuilt
whenever the answer could have changed.
"""

import datetime

import pytest

from techdeck.core.constants import effective_theme

def _choices(current, season):
    """SettingsPage._theme_choices, exercised without building the page.

    It touches nothing on ``self``, so an unbound call is the honest unit —
    and it is the REAL function, not a reimplementation of it.
    """
    from techdeck.ui.pages.settings_page import SettingsPage
    import techdeck.core.constants as consts
    real = consts.is_halloween_season
    consts.is_halloween_season = lambda today=None: season
    try:
        return SettingsPage._theme_choices(None, current)
    finally:
        consts.is_halloween_season = real

# ── the picker's stock ─────────────────────────────────────────────────────

def test_halloween_is_offered_in_season():
    assert "halloween" in _choices("dark", season=True)

def test_halloween_is_offered_to_professional_users_in_season():
    # THE REGRESSION. Professional suppresses the seasonal FEATURES, never
    # the user's ability to find the theme and choose it.
    assert "halloween" in _choices("professional", season=True)

def test_halloween_is_hidden_out_of_season():
    assert "halloween" not in _choices("dark", season=False)

def test_halloween_stays_listed_out_of_season_while_worn():
    # A session open across Nov 2 must still be able to switch AWAY from it.
    assert "halloween" in _choices("halloween", season=False)

def test_every_other_theme_is_always_offered():
    for season in (True, False):
        offered = _choices("dark", season=season)
        for name in ("dark", "light", "professional", "cyberpunk", "matrix",
                     "cherry_blossom"):
            assert name in offered, (name, season)

# ── the list cannot go stale ───────────────────────────────────────────────

def test_applying_a_theme_rebuilds_the_list():
    """_apply_theme must refresh the combo.

    The bug: the list was filled once at construction, so a user who started
    the app on professional had to RESTART TechDeck before halloween appeared.
    """
    import inspect
    from techdeck.ui.pages.settings_page import SettingsPage
    body = inspect.getsource(SettingsPage._apply_theme)
    assert "_refresh_theme_combo()" in body, (
        "_apply_theme must rebuild the picker: the applied theme can change "
        "which themes belong in it")

def test_opening_the_tab_rebuilds_the_list():
    import inspect
    from techdeck.ui.pages.settings_page import SettingsPage
    body = inspect.getsource(SettingsPage._load_personalization_settings)
    assert "_refresh_theme_combo()" in body, (
        "showing the tab must rebuild the picker, not just re-select: the "
        "season can turn over while the app is open")

def test_both_combos_share_one_stock_rule():
    """Centralized, per the Fix Protocol: one filter, not two copies."""
    import inspect
    from techdeck.ui.pages.settings_page import SettingsPage
    for fn in (SettingsPage._refresh_theme_combo,
               SettingsPage._refresh_assistant_theme_combo):
        body = inspect.getsource(fn)
        assert "_theme_choices(" in body, fn.__name__
        assert "halloween_active" not in body, (
            f"{fn.__name__} must not gate its STOCK on halloween_active - "
            "that folds in the professional check and locks the user out")

# ── the seasonal default itself ────────────────────────────────────────────

OCT = datetime.date(2026, 10, 16)
JUNE = datetime.date(2026, 6, 16)

def test_seasonal_theme_overrides_professional():
    # His call 2026-10-16: a theme we decide the app should open in applies to
    # everyone, professional included.
    assert effective_theme("professional", None, today=OCT) == "halloween"

def test_seasonal_theme_overrides_every_stored_pick():
    for stored in ("dark", "light", "professional", "matrix", "my_custom"):
        assert effective_theme(stored, None, today=OCT) == "halloween", stored

def test_an_explicit_opt_out_still_wins():
    assert effective_theme("professional", 2026, today=OCT) == "professional"
    assert effective_theme("light", 2026, today=OCT) == "light"

def test_the_opt_out_expires_with_the_year():
    assert effective_theme("light", 2025, today=OCT) == "halloween"

def test_out_of_season_the_stored_pick_rules():
    for opt_out in (None, 2025, 2026):
        assert effective_theme("professional", opt_out, today=JUNE) == "professional"
        assert effective_theme("light", opt_out, today=JUNE) == "light"

# ── professional keeps its sober FEATURES while wearing the look ───────────

def test_professional_user_wears_halloween_but_keeps_sober_features(tmp_path,
                                                                    monkeypatch):
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "1")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from techdeck.core.constants import halloween_active
    from techdeck.core.settings import SettingsManager
    s = SettingsManager()
    s.data.setdefault("settings", {})["theme"] = "professional"

    assert s.get_stored_theme() == "professional"   # what they picked
    assert s.get_theme() == "halloween"             # what they wear
    assert s.is_professional()                      # still sober...
    assert not halloween_active(settings=s)         # ...so no crawlies/stock

def test_ordinary_user_gets_the_features_too(tmp_path, monkeypatch):
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "1")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from techdeck.core.constants import halloween_active
    from techdeck.core.settings import SettingsManager
    s = SettingsManager()
    s.data.setdefault("settings", {})["theme"] = "dark"
    assert s.get_theme() == "halloween"
    assert not s.is_professional()
    assert halloween_active(settings=s)

# ── the splash cannot drift from the app ───────────────────────────────────

def test_splash_uses_the_one_shared_rule():
    """The rule was written twice; the copies could drift."""
    import inspect
    import techdeck.__main__ as m
    body = inspect.getsource(m._current_theme_name)
    assert "effective_theme" in body
    assert "professional" not in body, (
        "the splash must not carry its own copy of the seasonal rule")
