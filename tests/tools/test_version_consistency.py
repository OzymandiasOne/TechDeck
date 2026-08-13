"""The version number is hand-maintained in three places — constants.py
(the app), TechDeck-Setup.iss (the installer filename + registry stamp), and
the README headline. Nothing cross-checked them: a stale .iss compiled an
old-named installer while the build reported success. build.ps1 now fails
fast on the constants/.iss mismatch; this test makes the same guarantee in
CI (and covers the README, which build.ps1 doesn't read)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _app_version() -> str:
    src = (ROOT / "techdeck" / "core" / "constants.py").read_text(encoding="utf-8")
    match = re.search(r'APP_VERSION = "([^"]+)"', src)
    assert match, "constants.py no longer has an APP_VERSION line"
    return match.group(1)


def test_installer_script_version_matches_constants():
    iss = (ROOT / "TechDeck-Setup.iss").read_text(encoding="utf-8")
    match = re.search(r'#define MyAppVersion "([^"]+)"', iss)
    assert match, "TechDeck-Setup.iss no longer defines MyAppVersion"
    assert match.group(1) == _app_version(), (
        f"TechDeck-Setup.iss says {match.group(1)} but constants.py says "
        f"{_app_version()} - update the '#define MyAppVersion' line "
        f"(the release skill bumps all three version sites together)")


def test_readme_headline_version_matches_constants():
    first_line = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()[0]
    match = re.search(r"\bv(\d[\w.]*)", first_line)
    assert match, f"README.md headline has no version: {first_line!r}"
    assert match.group(1) == _app_version(), (
        f"README.md headline says v{match.group(1)} but constants.py says "
        f"{_app_version()} - update the README title line")
