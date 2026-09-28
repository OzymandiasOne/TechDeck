"""His lines file: parsing, pools, holes, hot reload."""
import os
import time

from techdeck.ui.void_game.dialogue import MOODS, Dialogue, lines_path, parse_lines


def test_the_shipped_file_parses_and_covers_the_moments_that_matter():
    lines = parse_lines(lines_path().read_text(encoding="utf-8"))
    for key in ("welcome", "rules", "first_turn", "hit_him", "hit_you", "kill_his",
                "kill_yours", "undying", "grow", "win", "lose", "idle"):
        assert lines.get(key), f"no line for {key}"
    for pool in lines.values():
        for emotion, text in pool:
            assert emotion in MOODS
            assert "—" not in text, "his voice rules: no em-dashes"


def test_bad_lines_are_skipped_not_fatal():
    got = parse_lines("# comment\n\nwelcome | amused | Hi.\nbroken line\nx | y\nrules | nonsense | Text.\n")
    assert got["welcome"] == [("amused", "Hi.")]
    assert got["rules"] == [("calm", "Text.")]          # unknown emotion falls back to calm
    assert len(got) == 2


def test_a_pool_never_repeats_itself_twice_running(tmp_path):
    f = tmp_path / "l.txt"
    f.write_text("k | calm | one\nk | calm | two\nk | calm | three\n", encoding="utf-8")
    d = Dialogue(f, seed=4)
    said = [d.line("k")[0] for _ in range(30)]
    assert all(a != b for a, b in zip(said, said[1:]))
    assert set(said) == {"one", "two", "three"}


def test_holes_are_filled_and_missing_holes_are_forgiven(tmp_path):
    f = tmp_path / "l.txt"
    f.write_text("k | calm | You played {name}.\nj | calm | Bad {hole}.\n", encoding="utf-8")
    d = Dialogue(f)
    assert d.line("k", name="HOUND") == ("You played HOUND.", "calm")
    assert d.line("j") == ("Bad {hole}.", "calm")
    assert d.line("missing") is None


def test_the_file_hot_reloads(tmp_path):
    f = tmp_path / "l.txt"
    f.write_text("k | calm | before\n", encoding="utf-8")
    d = Dialogue(f)
    assert d.line("k")[0] == "before"
    f.write_text("k | grave | after\n", encoding="utf-8")
    later = time.time() + 5
    os.utime(f, (later, later))
    assert d.line("k") == ("after", "grave")
