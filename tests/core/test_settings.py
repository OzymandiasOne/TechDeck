"""Tests for SettingsManager persistence + migrations.

Every test passes settings_dir=tmp_path — settings.py:__new__ returns a fresh
independent instance for an explicit dir (never the process singleton), so the
real %LOCALAPPDATA% store is never touched.
"""

import json

from techdeck.core.settings import SettingsManager, DEFAULT_PROFILE_NAME


def test_defaults_on_empty_dir(tmp_path):
    s = SettingsManager(settings_dir=tmp_path)
    assert s.get_current_profile_name() == DEFAULT_PROFILE_NAME
    assert DEFAULT_PROFILE_NAME in s.get_profile_names()
    assert (tmp_path / "settings.json").exists()


def test_save_reload_roundtrip(tmp_path):
    s = SettingsManager(settings_dir=tmp_path)
    s.set_theme("matrix")
    s.add_tickets(10)
    reloaded = SettingsManager(settings_dir=tmp_path)   # fresh instance, same dir
    assert reloaded.get_theme() == "matrix"
    assert reloaded.get_tickets() == s.get_tickets()


def test_recovers_from_backup_when_live_file_corrupt(tmp_path):
    s = SettingsManager(settings_dir=tmp_path)
    s.set_theme("blue")                                  # writes settings.json + .bak
    bak = tmp_path / "settings.bak"                       # settings.json -> settings.bak
    assert bak.exists()
    (tmp_path / "settings.json").write_text("{ not valid json", encoding="utf-8")
    recovered = SettingsManager(settings_dir=tmp_path)
    assert recovered.get_theme() == "blue"


def test_plugin_id_migration_remaps_dedupes_and_drops_retired(tmp_path):
    doc = {
        "version": 1,
        "current_profile": DEFAULT_PROFILE_NAME,
        "profiles": {DEFAULT_PROFILE_NAME: {"tiles": [
            "lst_organizer",          # -> 922_lst_organizer
            "922_lst_organizer",      # dedupe with the remapped one
            "911_linear_inch_cuttime",  # retired -> dropped
            "qa_rework",              # -> qa_gemba_analyzer
        ]}},
        "settings": {"theme": "dark",
                     "unlocked_items": ["steeltube_game", "steeltube_game"]},
        "plugin_settings": {"qa_rework": {"x": 1}},
        "plugin_stats": {"911_linear_inch_cuttime": {"runs": 3}},
    }
    (tmp_path / "settings.json").write_text(json.dumps(doc), encoding="utf-8")
    s = SettingsManager(settings_dir=tmp_path)

    assert s.data["profiles"][DEFAULT_PROFILE_NAME]["tiles"] == [
        "922_lst_organizer", "qa_gemba_analyzer"]
    assert "qa_gemba_analyzer" in s.data["plugin_settings"]
    assert "qa_rework" not in s.data["plugin_settings"]
    assert "911_linear_inch_cuttime" not in s.data["plugin_stats"]
    assert s.data["settings"]["unlocked_items"] == ["game_asa_the_video_game"]

    # Idempotent: reloading the migrated file changes nothing.
    again = SettingsManager(settings_dir=tmp_path)
    assert again.data["profiles"][DEFAULT_PROFILE_NAME]["tiles"] == [
        "922_lst_organizer", "qa_gemba_analyzer"]


def test_total_runs_backfilled_from_family_tallies(tmp_path):
    """The pre-singleton settings race froze total_runs while the shell-written
    family_runs kept climbing (A.T.'s 'first four achievements never
    progress'). Migration raises total_runs to the family-tally floor, shifts
    the tree planting stamp by the same delta (growth unchanged), and is
    idempotent."""
    doc = {
        "version": 1,
        "current_profile": DEFAULT_PROFILE_NAME,
        "profiles": {DEFAULT_PROFILE_NAME: {"tiles": []}},
        "settings": {
            "theme": "dark",
            "total_runs": 2,                       # frozen by the race
            "family_runs": {"911": 40, "922": 55, "General": 5},
            "tree_planted_runs": 1,
        },
        "plugin_settings": {},
        "plugin_stats": {},
    }
    (tmp_path / "settings.json").write_text(json.dumps(doc), encoding="utf-8")
    s = SettingsManager(settings_dir=tmp_path)

    assert s.get_total_runs() == 100                # raised to the floor
    assert s.data["settings"]["tree_planted_runs"] == 99  # shifted by delta=98

    # Idempotent + monotonic: reload changes nothing, and a healthy file
    # (total >= family sum) is left alone.
    again = SettingsManager(settings_dir=tmp_path)
    assert again.get_total_runs() == 100
    again.increment_plugin_runs("911_setup")
    third = SettingsManager(settings_dir=tmp_path)
    assert third.get_total_runs() == 101


def test_ticket_economy_clamps(tmp_path):
    s = SettingsManager(settings_dir=tmp_path)
    s.add_tickets(-10_000)
    assert s.get_tickets() == 0                      # never negative
    s.add_tickets(50)
    assert s.spend_tickets(20) is True
    assert s.get_tickets() == 30
    assert s.spend_tickets(999) is False             # refuse unaffordable
    assert s.get_tickets() == 30
    assert s.spend_tickets(-5) is False              # refuse negative
