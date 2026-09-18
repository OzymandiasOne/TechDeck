"""Gate: the publish scrub must never turn a Python file into a syntax error.

`publish_mirror.py` rewrites every blob with the literal rules in
`.claude/publish/replacements.txt` (git-filter-repo --replace-text). A scrub
key that appears inside a Python IDENTIFIER - a function named after the
person who requested the feature was the live case - becomes its replacement
(e.g. initials with dots) in the published copy, which no longer parses. Local
tests stay green; the break exists only on the public repo's CI, and it is a
collection error, so it takes the whole suite down with it.

Found 2026-09-04 on the v0.8.7.4 push: a test named after the requester
compiled to `def test_..._is_A.T.s(...)` in the mirror - SyntaxError at
collection, red public main, discovered after the tag was cut (again).

This gate applies the same literal replacements to every tracked .py that
publishing keeps, and compiles the result - so the class dies locally, in
build.ps1's pytest run, before anything is pushed.

On the public repo this file skips: the replacements map lives under .claude,
which publishing strips, and there the scrub has already happened.
"""

import ast
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REPLACEMENTS = ROOT / ".claude" / "publish" / "replacements.txt"


def _private_paths() -> list:
    """PRIVATE_PATHS parsed out of publish_mirror.py, never duplicated (same
    pattern as test_private_doc_reads.py, same reason: a copy drifts)."""
    src = (ROOT / "tools" / "publish_mirror.py").read_text(encoding="utf-8")
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "PRIVATE_PATHS"
                for t in node.targets):
            return [ast.literal_eval(e) for e in node.value.elts]
    raise AssertionError(
        "tools/publish_mirror.py no longer defines PRIVATE_PATHS - this gate "
        "needs updating alongside it.")


def _rules() -> list:
    """The literal old==>new rules, in file order (filter-repo applies them
    as successive literal replaces; the file has no comment syntax)."""
    rules = []
    for line in REPLACEMENTS.read_text(encoding="utf-8").splitlines():
        if "==>" in line:
            old, new = line.split("==>", 1)
            if old:
                rules.append((old, new))
    return rules


def test_every_published_py_file_still_compiles_after_the_scrub():
    if not REPLACEMENTS.is_file():
        pytest.skip("no replacements map here - published tree, scrub already applied")

    rules = _rules()
    assert rules, "replacements.txt parsed to zero rules - format change?"
    stripped = tuple(p.rstrip("/") for p in _private_paths())

    tracked = subprocess.run(
        ["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True,
        text=True, check=True).stdout.splitlines()

    broken = []
    for rel in tracked:
        if rel.startswith(stripped):
            continue                      # never published, cannot break CI
        text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        scrubbed = text
        for old, new in rules:
            scrubbed = scrubbed.replace(old, new)
        if scrubbed == text:
            continue
        try:
            compile(scrubbed, rel, "exec")
        except SyntaxError as e:
            broken.append(f"{rel}:{e.lineno}: {e.msg}")

    assert not broken, (
        "The publish scrub turns these files into syntax errors on the PUBLIC "
        "repo (they are fine locally - that is the trap): "
        + "; ".join(broken)
        + ". A scrub-map key is inside an identifier or other load-bearing "
          "code. Rename the identifier to something neutral; never name code "
          "after a person."
    )
