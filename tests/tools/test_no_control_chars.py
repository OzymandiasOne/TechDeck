"""No tracked text file may contain control characters.

Found 2026-09-02, three instances, two of them long-standing:

- `CLAUDE.md` and `.claude/skills/techdeck-release/SKILL.md` both told you to run
  `python tools\backup_repo.py` - except the file held a literal BACKSPACE where
  the `\b` had been. It rendered as `toolsackup_repo.py`, a file that does not
  exist, in the one instruction whose whole job is taking a backup before a
  history rewrite.
- `tools/devkit/java_tutor/render.py` had a real SOH byte where a regex
  backreference `\1` belonged, so the markdown horizontal-rule pattern silently
  matched nothing and `---` never rendered.

All three came from the same mistake: writing a file with a Python script using a
NON-raw string, where `\b` is a backspace and `\1` is SOH. Python does not warn
for those - they are valid escapes - so the corruption is silent, survives review
(the char is invisible), and only shows up when someone copies a broken command.

Use raw strings, or chr(92), when a written string contains backslashes.
"""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TEXT = (".md", ".py", ".iss", ".spec", ".json", ".txt", ".ps1", ".yml", ".yaml", ".cfg")
ALLOWED = {"\n", "\t"}


def _tracked_text_files():
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        pytest.skip("not a git repo")
    return [ROOT / f for f in out.stdout.split()
            if f.lower().endswith(TEXT)]


def test_no_control_characters_in_tracked_text():
    offenders = []
    for path in _tracked_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for i, ch in enumerate(text):
            if ord(ch) < 32 and ch not in ALLOWED:
                line = text.count("\n", 0, i) + 1
                offenders.append(
                    f"{path.relative_to(ROOT)}:{line} contains {ch!r} "
                    f"-> {text[max(0, i-40):i+12]!r}")
                break
    assert not offenders, (
        "control characters in tracked text files:\n  "
        + "\n  ".join(offenders)
        + "\nAlmost always a Python non-raw string that wrote the file: "
          "'\b' is a backspace and '\1' is SOH, and Python does not warn. "
          "Use a raw string or chr(92).")
