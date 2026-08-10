"""A missing comma in a list of strings silently GLUES two entries together.

Python concatenates adjacent string literals, so this:

    "PDF bothered and quit their jobs in"      # <- comma forgotten
    "Hullaballooed for",

is not a syntax error — it is one entry reading
"PDF bothered and quit their jobs inHullaballooed for", and the list is one
shorter than it looks. Nothing crashes; a user just sees a garbled line every
30-odd runs and assumes the app clobbered its own output. Reported that way
2026-08-10 ("the flavor text is getting clobbered").

Grepping for it is hopeless — the AST has already folded the two literals into
one string by the time anything can look. The tell is POSITIONAL: a string
element of a list/tuple/set whose source span covers more than one line, with
no explicit ``+``. A deliberately wrapped long string is the same shape, so
this checks the flavor/personality lists — short, one-per-line, user-facing
lines where a multi-line element is always the bug — rather than every literal
in the app.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# (file, list-literal names to check) — the user-facing one-liner pools.
TARGETS = [
    ("techdeck/ui/shell.py", {"_DONE_TEXTS"}),
    ("techdeck/core/flavor.py", None),   # None = every list in the module
]


def _glued_entries(path: Path, names):
    """[(list_name, joined_text)] for every multi-line string element."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        target = node.targets[0]
        name = getattr(target, "id", None) or getattr(target, "attr", None)
        if name is None or not isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
            continue
        if names is not None and name not in names:
            continue
        for element in node.value.elts:
            if (isinstance(element, ast.Constant)
                    and isinstance(element.value, str)
                    and element.end_lineno is not None
                    and element.end_lineno > element.lineno):
                found.append((name, element.value))
    return found


@pytest.mark.parametrize("rel,names", TARGETS, ids=[t[0] for t in TARGETS])
def test_no_flavor_lines_were_glued_together_by_a_missing_comma(rel, names):
    glued = _glued_entries(ROOT / rel, names)
    assert not glued, (
        "a missing comma joined these into one entry:\n  "
        + "\n  ".join(f"{n}: {v!r}" for n, v in glued))


def test_the_detector_actually_catches_the_original_bug(tmp_path):
    """A test that can't fail is worse than no test. Feed it the exact shape
    that shipped and confirm it trips."""
    sample = tmp_path / "sample.py"
    sample.write_text(
        '_DONE_TEXTS = [\n'
        '    "Rustled that paperwork in",\n'
        '    "PDF bothered and quit their jobs in"\n'
        '    "Hullaballooed for",\n'
        ']\n', encoding="utf-8")
    glued = _glued_entries(sample, {"_DONE_TEXTS"})
    assert [v for _n, v in glued] == [
        "PDF bothered and quit their jobs inHullaballooed for"]


def test_every_done_line_is_a_sane_one_liner():
    """The pool is rendered as '<line> 12s.' in the run banner, so an entry
    that swallowed its neighbour is both garbled AND too long for the bar."""
    import re
    src = (ROOT / "techdeck/ui/shell.py").read_text(encoding="utf-8")
    block = re.search(r"_DONE_TEXTS = \[(.*?)\n    \]", src, re.S).group(1)
    lines = ast.literal_eval("[" + block + "]")
    assert len(lines) >= 25
    for line in lines:
        assert line == line.strip(), f"stray whitespace: {line!r}"
        assert len(line) <= 45, f"too long for the run banner: {line!r}"
