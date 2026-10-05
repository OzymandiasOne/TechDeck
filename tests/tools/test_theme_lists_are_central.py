"""Gate: which built-in themes are dark lives in ONE place.

The list ("dark", "blue", "cyberpunk", "matrix") was copy-pasted into nine
files; retiring Blue meant finding every copy. Call
techdeck.ui.theme.icon_folder_for_theme / DARK_BUILTIN_THEMES instead.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
# a literal list/tuple of theme names that includes both "dark" and "matrix"
_THEME_LIST = re.compile(r"""[\[\(\{]\s*["']dark["'][^\]\)\}]*["']matrix["']""")


def test_no_hardcoded_dark_theme_lists():
    offenders = []
    for path in (ROOT / "techdeck").rglob("*.py"):
        if path.name == "theme.py" and path.parent.name == "ui":
            continue
        text = path.read_text(encoding="utf-8")
        for m in _THEME_LIST.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            offenders.append(f"{path.relative_to(ROOT)}:{line}")
    assert not offenders, (
        "Hardcoded theme-name list - use techdeck.ui.theme.icon_folder_for_theme "
        "or DARK_BUILTIN_THEMES: " + ", ".join(offenders))
