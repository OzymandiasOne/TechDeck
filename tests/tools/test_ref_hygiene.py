"""A branch and a tag may share a name, and git will not stop you. When they
collide, every bare use of that name ("git log v0.8.7.2.1") prints
"warning: refname is ambiguous" and silently resolves to the TAG. It looks
harmless while both point at the same commit -- which is exactly the state a
fresh release leaves behind, because the release cuts the tag and someone had
also left a branch of the same name. The first commit onto that branch splits
them, and from then on the name means two different commits depending on which
command reads it.

This happened here: a stray `v0.8.7.2.1` branch sat alongside tag `v0.8.7.2.1`
and only surfaced as a warning buried in unrelated git output. The release
skill names release branches `release/v<next>` precisely so they cannot collide
with the `v<version>` tags; this test enforces that naming instead of trusting
it.
"""

import subprocess

import pytest


def _refs(namespace: str) -> set[str]:
    """Short names under refs/<namespace>, read WITHOUT git's own shortening.

    `--format=%(refname:short)` is the obvious choice and the wrong one: it
    returns the shortest UNAMBIGUOUS name, so a colliding branch comes back as
    "heads/v1.2.3" rather than "v1.2.3" -- git hides the very collision we are
    looking for. Strip the prefix ourselves.
    """
    out = subprocess.run(
        ["git", "for-each-ref", "--format=%(refname)", f"refs/{namespace}"],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        pytest.skip(f"git unavailable or not a repo: {out.stderr.strip()}")
    prefix = f"refs/{namespace}/"
    return {line[len(prefix):] for line in out.stdout.splitlines() if line.startswith(prefix)}


def test_no_branch_name_collides_with_a_tag_name():
    collisions = sorted(_refs("heads") & _refs("tags"))
    assert not collisions, (
        f"these names are BOTH a branch and a tag: {', '.join(collisions)}. "
        f"Bare uses of them resolve to the tag and warn 'refname is ambiguous'. "
        f"Delete the branch (the tag preserves the commit): "
        f"git branch -d {collisions[0] if collisions else '<name>'} "
        f"-- and name release branches 'release/v<version>', never 'v<version>'.")


def test_release_branches_use_the_release_prefix():
    """`v<version>` as a BRANCH name is the mistake that creates the collision
    above, whether or not the matching tag exists yet."""
    import re
    stray = sorted(b for b in _refs("heads") if re.fullmatch(r"v\d[\w.]*", b))
    assert not stray, (
        f"branch(es) named like a version tag: {', '.join(stray)}. "
        f"The release skill cuts next-version branches as 'release/v<version>'; "
        f"a bare 'v<version>' branch collides with the release tag of the same name.")
