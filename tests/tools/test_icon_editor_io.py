"""Tests for icon_editor's generator-script IO (parse / format / save)."""

import shutil


def test_format_and_parse_roundtrip():
    from tools.icon_editor import format_block, parse_icon
    rows = ["ab", "ba", ".."]
    tones = {"a": "#112233", "b": "#445566"}
    block = format_block("test_key", rows, tones)
    parsed_rows, parsed_tones = parse_icon(block, "test_key")
    assert parsed_rows == rows
    assert parsed_tones == tones


def test_list_icons_finds_known_themed_icon():
    from tools.icon_editor import list_icons
    icons = list_icons()
    assert icons.get("badge") == "themed"
    # A static "TechDeck pack pixel" symbol should be classified static.
    assert any(mode == "static" for mode in icons.values())


def test_save_new_themed_icon_into_temp_copy(tmp_path, monkeypatch):
    """save_icon_to_script inserts a new themed icon's block, draw fn and ICONS
    entry. Exercised against a COPY so the real generator is never touched."""
    import tools.icon_editor as ie
    tmp = tmp_path / "gen.py"
    shutil.copy(ie.THEMED_SCRIPT, tmp)
    monkeypatch.setattr(ie, "THEMED_SCRIPT", tmp)

    rows = ["a" * 32 for _ in range(32)]
    tones = {"a": "#123456"}
    ie.save_icon_to_script("zzz_test_icon", False, rows, tones)

    text = tmp.read_text(encoding="utf-8")
    parsed_rows, parsed_tones = ie.parse_icon(text, "zzz_test_icon")
    assert parsed_rows == rows
    assert parsed_tones == tones
    assert '"zzz_test_icon": zzz_test_icon,' in text   # registered in ICONS


def test_resave_replaces_block_in_place(tmp_path, monkeypatch):
    import tools.icon_editor as ie
    tmp = tmp_path / "gen.py"
    shutil.copy(ie.THEMED_SCRIPT, tmp)
    monkeypatch.setattr(ie, "THEMED_SCRIPT", tmp)

    rows1 = ["a" * 32 for _ in range(32)]
    ie.save_icon_to_script("zzz_test_icon", False, rows1, {"a": "#111111"})
    before = tmp.read_text(encoding="utf-8").count("def zzz_test_icon(")

    rows2 = ["b" * 32 for _ in range(32)]
    ie.save_icon_to_script("zzz_test_icon", False, rows2, {"b": "#222222"})
    text = tmp.read_text(encoding="utf-8")

    parsed_rows, parsed_tones = ie.parse_icon(text, "zzz_test_icon")
    assert parsed_rows == rows2
    assert parsed_tones == {"b": "#222222"}
    # Re-save must not duplicate the draw fn / registration.
    assert text.count("def zzz_test_icon(") == before == 1
