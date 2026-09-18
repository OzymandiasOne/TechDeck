"""A test that reads a publish-stripped path must go through `private_doc`.

The working repo and the PUBLISHED repo are two different trees.
`tools/publish_mirror.py` deletes `PRIVATE_PATHS` - CLAUDE.md,
LESSONS_LEARNED.md, docs/, .claude/ and the rest - out of every commit of the
mirror. So a test that opens one of them by a fixed path is green on every
developer machine and red only on the public repo's CI, which is the one place
the filtered tree runs. There is no local signal whatsoever.

Found 2026-09-02, at the worst possible moment: both CLAUDE.md budget gates
read `ROOT / "CLAUDE.md"` directly, and public main went red on the v0.8.7.3
push - after the tag was cut and the GitHub Release was published, with the
go-live manifest push still pending.

This is the same shape as the scrub-map-fixture trap already recorded in the
release skill (a fixture keyed on a scrubbed name passes locally and fails only
on the mirror). Both are instances of one class: *the published tree is not the
tree you tested*. That class now has a gate.

The rule: resolve such a path with the `private_doc` fixture (tests/conftest.py),
which skips when the file is absent. A gate about CLAUDE.md has nothing to say
about a mirror that deliberately carries no CLAUDE.md.
"""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Build artifacts are gitignored, so they are never in a test's path anyway;
# listing them would only invite false positives on the word "build".
NOT_DOCS = {"dist", "build", "installer_output"}

# The fixture itself, and this gate, name these paths on purpose.
EXEMPT = {"tests/conftest.py", "tests/tools/test_private_doc_reads.py"}

# `ROOT / "docs"`, `ROOT / "CLAUDE.md"` - the idiom every test here uses to
# build a repo-relative path.
ROOT_JOIN = re.compile(r"""ROOT\s*/\s*['"]([^'"]+)['"]""")


def _private_paths():
    """Read PRIVATE_PATHS out of publish_mirror.py without importing it.

    Parsed rather than duplicated, so the day someone adds a path to the strip
    list this gate covers it too - a copied list would silently fall behind.
    """
    src = (ROOT / "tools" / "publish_mirror.py").read_text(encoding="utf-8")
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "PRIVATE_PATHS"
                for t in node.targets):
            return [ast.literal_eval(e) for e in node.value.elts]
    raise AssertionError(
        "tools/publish_mirror.py no longer defines PRIVATE_PATHS - this gate "
        "reads it to know which paths publishing strips")


def test_private_paths_are_read_through_the_fixture():
    stripped = {p for p in _private_paths() if p not in NOT_DOCS}
    offenders = []

    for path in sorted(ROOT.joinpath("tests").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel in EXEMPT:
            continue
        text = path.read_text(encoding="utf-8")
        if "private_doc" in text:
            continue
        for literal in ROOT_JOIN.findall(text):
            head = literal.replace("\\", "/").split("/")[0]
            if literal in stripped or head in stripped:
                offenders.append(f"{rel}: ROOT / {literal!r}")

    assert not offenders, (
        "these tests read a path that publishing STRIPS from the public "
        "mirror, so they pass here and fail only on the public repo's CI:\n  "
        + "\n  ".join(offenders)
        + "\nResolve it with the `private_doc` fixture instead "
          "(tests/conftest.py) - it skips when the file is absent, which is "
          "the correct behaviour on a tree that deliberately has no such file.")
