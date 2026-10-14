r"""No tracked text file may contain control characters.

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

Widened 2026-10-05 after two more of the same class got PAST this gate, both in
`docs/FEEDBACK_TRACKER.md`, both written by a non-raw Python string:

- `C:\Dev\_repo_backups\telemetry\...` held a real TAB where `\t` belonged, so the
  one path telling you where a shared-workbook backup went read
  `_repo_backups<TAB>elemetry`. A tab is legal in source, so it was in ALLOWED -
  but a tab in a MARKDOWN file is never wanted and is virtually always this bug.
- `\2026-09-21` became `\x82` + `6-09-21`: `\202` is a valid OCTAL escape. It is
  above 32, so the ord() < 32 test never saw it. Nothing in the 0x7f-0x9f C1 range
  belongs in text, in any file type.

So: tabs are an offence in `.md` only, and the C1 range is an offence everywhere.
"""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TEXT = (".md", ".py", ".iss", ".spec", ".json", ".txt", ".ps1", ".yml", ".yaml", ".cfg")
ALLOWED = {"\n", "\t"}
# A tab carries meaning in source and config; in prose it never does, and every
# one found so far was a mangled "\t" inside a Windows path.
ALLOWED_MD = {"\n"}


def _offends(ch: str, suffix: str) -> bool:
    allowed = ALLOWED_MD if suffix == ".md" else ALLOWED
    return (ord(ch) < 32 and ch not in allowed) or 0x7f <= ord(ch) < 0xa0


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
        suffix = path.suffix.lower()
        for i, ch in enumerate(text):
            if _offends(ch, suffix):
                line = text.count("\n", 0, i) + 1
                offenders.append(
                    f"{path.relative_to(ROOT)}:{line} contains {ch!r} "
                    f"-> {text[max(0, i-40):i+12]!r}")
                break
    assert not offenders, (
        "control characters in tracked text files:\n  "
        + "\n  ".join(offenders)
        + "\nAlmost always a Python non-raw string that wrote the file: "
          "'\b' is a backspace, '\1' is SOH, '\t' is a tab and '\202' is an "
          "octal escape - Python warns for none of them. "
          "Use a raw string or chr(92).")
