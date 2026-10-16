"""The Halloween opt-out: the 2026 reset, and saying it out loud.

The opt-out itself was never designed — it arrived on 2026-08-19 bundled into
"halloween is the seasonal default", nobody asked for it, and nothing told the
user it existed. It earns its keep (without it, picking Dark in October gets
overridden again at every launch, forever), so it stays — but the flags it
recorded during the 2026 lockout record a BUG, not a preference, and from now
on the settings page says when it is in effect.
"""

import datetime


from techdeck.core.settings import SettingsManager

RESET_KEY = SettingsManager._OPT_OUT_RESET_KEY


def _mgr(tmp_path, **settings):
    """An install that predates the reset, which is who the reset is for.

    A manager built today is born with the marker already set, so the helper
    strips it: an existing user upgrading into this build has a settings.json
    written before the marker existed.
    """
    s = SettingsManager(settings_dir=tmp_path)
    block = s.data.setdefault("settings", {})
    block.pop(RESET_KEY, None)
    block.update(settings)
    return s


# ── the one-time reset ─────────────────────────────────────────────────────

def test_a_2026_opt_out_is_cleared(tmp_path):
    s = _mgr(tmp_path, halloween_opt_out_year=2026)
    s._reset_bugged_halloween_opt_outs()
    assert "halloween_opt_out_year" not in s.data["settings"]


def test_the_reset_runs_only_once(tmp_path):
    """The marker is the whole point: without it nobody could EVER opt out,
    because the next launch would wipe the flag they just set."""
    s = _mgr(tmp_path, halloween_opt_out_year=2026)
    s._reset_bugged_halloween_opt_outs()
    assert s.data["settings"][RESET_KEY] is True

    s.data["settings"]["halloween_opt_out_year"] = 2026   # a REAL opt-out now
    s._reset_bugged_halloween_opt_outs()
    assert s.data["settings"]["halloween_opt_out_year"] == 2026


def test_an_older_opt_out_is_left_alone(tmp_path):
    # Already expired; touching it would mean nothing either way.
    s = _mgr(tmp_path, halloween_opt_out_year=2025)
    s._reset_bugged_halloween_opt_outs()
    assert s.data["settings"]["halloween_opt_out_year"] == 2025


def test_a_user_with_no_opt_out_is_untouched(tmp_path):
    s = _mgr(tmp_path)
    s._reset_bugged_halloween_opt_outs()
    assert "halloween_opt_out_year" not in s.data["settings"]
    assert s.data["settings"][RESET_KEY] is True


def test_the_reset_runs_on_load(tmp_path):
    """It must be wired into the migration chain, not merely exist."""
    import inspect
    body = inspect.getsource(SettingsManager._validate_and_migrate)
    assert "_reset_bugged_halloween_opt_outs()" in body


def test_faith_gets_the_theme_back(tmp_path, monkeypatch):
    """Her report, end to end: stored light, opted out, on the new build."""
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "1")
    s = _mgr(tmp_path, theme="light", halloween_opt_out_year=2026)
    assert s.get_theme() == "light"            # before
    s._reset_bugged_halloween_opt_outs()
    assert s.get_theme() == "halloween"        # after


# ── the opt-out is no longer silent ────────────────────────────────────────

def test_paused_is_true_only_for_this_years_opt_out(tmp_path, monkeypatch):
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "1")
    year = datetime.date.today().year
    assert _mgr(tmp_path, halloween_opt_out_year=year).seasonal_theme_paused()
    assert not _mgr(tmp_path, halloween_opt_out_year=year - 1).seasonal_theme_paused()
    assert not _mgr(tmp_path).seasonal_theme_paused()


def test_nothing_is_paused_out_of_season(tmp_path, monkeypatch):
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "0")
    year = datetime.date.today().year
    assert not _mgr(tmp_path, halloween_opt_out_year=year).seasonal_theme_paused()


def test_the_settings_page_says_so(tmp_path):
    """The notice must exist, be driven by seasonal_theme_paused(), and be
    refreshed at the same two moments the picker is."""
    import inspect
    from techdeck.ui.pages.settings_page import SettingsPage

    note = inspect.getsource(SettingsPage._refresh_seasonal_note)
    assert "seasonal_theme_paused()" in note
    assert "Nov 2" in note          # names the date it comes back
    assert "setVisible(False)" in note   # and hides itself when it does

    for fn in (SettingsPage._apply_theme,
               SettingsPage._load_personalization_settings):
        assert "_refresh_seasonal_note()" in inspect.getsource(fn), fn.__name__


def test_a_genuine_opt_out_survives_the_next_launch(tmp_path, monkeypatch):
    """The hole the marker alone did not close.

    _create_default_settings does NOT run the migration chain, so on a fresh
    install the marker was absent until the SECOND launch — by which time the
    user may have made a real choice, and the one-time reset ate it. They
    picked Matrix in October and got Halloween back anyway.
    """
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "1")
    SettingsManager(settings_dir=tmp_path).set_theme("matrix")
    assert SettingsManager(settings_dir=tmp_path).get_theme() == "matrix"


def test_a_fresh_install_is_born_already_reset(tmp_path):
    s = SettingsManager(settings_dir=tmp_path)
    assert s.data["settings"][RESET_KEY] is True
