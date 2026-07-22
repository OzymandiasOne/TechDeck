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
