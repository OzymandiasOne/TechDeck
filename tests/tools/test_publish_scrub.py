"""Tests for the publish-scrub gate (tools/check_publish_scrub.py).

The gate is what stands between a filtered mirror and a public force-push, so
the cases that matter are: it CATCHES a personal path/email anywhere in
history, it does NOT fire on the placeholders and false positives that live in
the tree normally, and the allowlist actually suppresses.
"""

import subprocess

import pytest

from tools.check_publish_scrub import (
    ADVISORY, BLOCKING, load_allowlist, main, scan,
)


def _find(label_prefix, text):
    """All matches for the pattern whose label starts with label_prefix."""
    for label, rx in {**BLOCKING, **ADVISORY}.items():
        if label.startswith(label_prefix):
            return rx.findall(text)
    raise AssertionError(f"no pattern labelled {label_prefix}")


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    (r"#   C:\Users\<user>\American Steel & Alum", [r"C:\Users\<user>"]),
    (r"C:\Users\ASiebenmorgen\OneDrive", [r"C:\Users\ASiebenmorgen"]),
    (r"D:\Users\someone.else\x", [r"D:\Users\someone.else"]),
])
def test_user_dir_detected(text, expected):
    assert _find("E1", text) == expected


@pytest.mark.parametrize("text", [
    # The placeholder the scrub map rewrites real paths INTO. If this ever
    # matched, every successful scrub would fail its own gate.
    r"#   ~\<user>\American Steel & Alum",
    r"C:\Users\<user>\Documents",
    r"%LOCALAPPDATA%\TechDeck\usage",
])
def test_user_dir_placeholders_ignored(text):
    assert _find("E1", text) == []


def test_email_detected():
    assert _find("E2", "contact bob.smith@example.com now") == \
        ["bob.smith@example.com"]


@pytest.mark.parametrize("text", [
    # Regression: the first version of the email pattern let the local part be
    # a bare diff marker, so every parametrised test in the repo matched.
    "-@pytest.mark.parametrize",
    "+@pytest.fixture",
    "@staticmethod",
    "decorated @property here",
])
def test_email_false_positives_ignored(text):
    assert _find("E2", text) == []


def test_org_path_is_advisory_not_blocking():
    assert any(k.startswith("W1") for k in ADVISORY)
    assert not any(k.startswith("W") for k in BLOCKING)


# ---------------------------------------------------------------------------
# Allowlist
# ---------------------------------------------------------------------------

def test_allowlist_skips_comments_and_blanks(tmp_path):
    f = tmp_path / "allow.txt"
    f.write_text(
        "# a comment\n\n  real@example.com  \n#another\nC:\\Users\\Me\n",
        encoding="utf-8",
    )
    assert load_allowlist(f) == {"real@example.com", "C:\\Users\\Me"}


def test_missing_allowlist_is_not_fatal(tmp_path):
    assert load_allowlist(tmp_path / "nope.txt") == set()


# ---------------------------------------------------------------------------
# End to end, against a throwaway repo
# ---------------------------------------------------------------------------

def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo)] + list(args),
                   check=True, capture_output=True)


@pytest.fixture
def dirty_repo(tmp_path):
    """A repo whose only offending content was ADDED then DELETED - the case
    a working-tree check (ship-readiness W1) passes and a history scan must
    not, because a mirror publishes every commit."""
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev")

    src = repo / "note.py"
    src.write_text(r"# example: C:\Users\RealPerson\Docs" + "\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add note")

    src.write_text(r"# example: C:\Users\<user>\Docs" + "\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "use a placeholder")
    return repo


def test_scan_finds_value_removed_at_tip(dirty_repo):
    hits = scan(dirty_repo)
    found = hits["E1 windows-user-dir"]
    assert r"C:\Users\RealPerson" in found
    # ...and the clean tip did not reintroduce a hit
    assert r"C:\Users\<user>" not in found


def test_main_fails_on_unscrubbed_history(dirty_repo, tmp_path, capsys):
    empty = tmp_path / "allow.txt"
    empty.write_text("", encoding="utf-8")
    rc = main_with_args(str(dirty_repo), empty)
    assert rc == 1
    assert "RealPerson" in capsys.readouterr().out


def test_main_passes_when_value_is_allowlisted(dirty_repo, tmp_path, capsys):
    allow = tmp_path / "allow.txt"
    # dev@example.com is the fixture's own commit identity - a genuine hit
    # from the identity pass, which is exactly what we want the gate to see.
    allow.write_text("C:\\Users\\RealPerson\ndev@example.com\n", encoding="utf-8")
    rc = main_with_args(str(dirty_repo), allow)
    assert rc == 0
    assert "RESULT: PASS" in capsys.readouterr().out


def test_main_errors_on_missing_repo(tmp_path):
    assert main_with_args(str(tmp_path / "absent"), tmp_path / "a.txt") == 2


def main_with_args(repo, allowlist):
    import sys
    argv = sys.argv
    sys.argv = ["check_publish_scrub.py", repo, "--allowlist", str(allowlist)]
    try:
        return main()
    finally:
        sys.argv = argv
