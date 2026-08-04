"""TechDeck publish-scrub gate.

Scans a FILTERED MIRROR for personal data before it is force-pushed to the
public repo. Run it after git-filter-repo and before any push (the publish
procedure is techdeck-release skill section 4):

    python tools\\check_publish_scrub.py %TEMP%\\td-public-mirror

Exits non-zero if any blocking hit is not on the allowlist, so a publish can
be gated on it the same way build.ps1 is gated on check_ship_readiness.py.

Why this exists: check_ship_readiness W1 flags a hardcoded C:\\Users\\<name>
in plugin source, but it only ever looks at the WORKING TREE. A mirror
publishes every commit, so a personal path that was committed and later
cleaned up is still in the published history even though the tip is spotless.
That is exactly how a coworker's home directory survived into the publish set
(the tip fix was e575c82; the name stayed in 0b6790c) and it was caught by
hand, not by a gate. The scrub map (.claude/publish/replacements.txt) is the
only thing that reaches back through history, so the map is what this
verifies - after the rewrite, not before it.

What gets scanned, across ALL refs and ALL commits:
  - blob contents (every added and removed diff line, so content that only
    ever existed in an intermediate commit is still seen)
  - commit messages (subject + body)
  - author and committer identities

Checks (E = error, fails the publish; W = advisory, reported only):
  E1  Windows user directory - C:\\Users\\<name>, a real person's home dir
  E2  email address
  W1  organisation OneDrive path - OneDrive - <org>

Identity note: --replace-text rewrites blob CONTENT and --replace-message
rewrites MESSAGES, but neither touches author/committer identity. An email in
the E2 list that only ever appears in identity lines cannot be fixed by the
scrub map - that needs --mailmap or --email-callback. The report says which
source each hit came from so the two cases are distinguishable.

The allowlist (.claude/publish/scrub_allowlist.txt, one value per line, '#'
comments allowed) holds values that are intentionally published - the
maintainer's own identity, documentation placeholders. It lives under
.claude/ because it names real people and .claude/ is stripped from the
mirror; this script carries no personal data itself and is safe to publish.

Output is ASCII only.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_ALLOWLIST = REPO / ".claude" / "publish" / "scrub_allowlist.txt"

COMMIT_MARK = "__TDCOMMIT__"

# Blocking patterns. Keep these HIGH PRECISION - a gate that cries wolf is a
# gate someone disables. Generic "looks like a person's name" detection is
# deliberately NOT here; it belongs in a human review pass.
BLOCKING = {
    "E1 windows-user-dir": re.compile(r"[A-Za-z]:\\Users\\[A-Za-z0-9._-]{2,40}"),
    "E2 email": re.compile(
        r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9][A-Za-z0-9._%+-]*"
        r"@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
    ),
}

# Advisory patterns - surfaced for judgement, never fail the run.
ADVISORY = {
    "W1 org-path": re.compile(r"OneDrive - [A-Za-z0-9 &.']{2,40}"),
}


def load_allowlist(path: Path) -> set:
    """Exact values that are intentionally published. Missing file is a
    warning, not a crash - a public clone has no .claude/ directory."""
    if not path.exists():
        print(f"NOTE: no allowlist at {path} - every hit will be reported")
        return set()
    allowed = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            allowed.add(line)
    return allowed


def _git_stream(repo: Path, args: list):
    """Run a git command and yield stdout lines as they arrive. Streamed
    because `log --all -p` over a full history does not fit in memory."""
    proc = subprocess.Popen(
        ["git", "-C", str(repo)] + args,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, encoding="utf-8", errors="replace",
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        yield line.rstrip("\n")
    proc.stdout.close()
    proc.wait()


def scan(repo: Path):
    """Walk every commit's message + diff, then every identity.

    Returns {pattern_label: {value: (source, commit)}} keeping the FIRST
    place each distinct value was seen - one example is enough to act on,
    and the same string usually recurs in hundreds of commits.
    """
    hits = defaultdict(dict)
    patterns = list(BLOCKING.items()) + list(ADVISORY.items())

    def record(text, source, commit):
        for label, rx in patterns:
            for m in rx.finditer(text):
                hits[label].setdefault(m.group(0), (source, commit))

    # One traversal covers messages AND content: the pretty format prints the
    # message, then -p appends that commit's diff. -U0 drops context lines so
    # unchanged neighbours are not rescanned for every commit that touches
    # the file.
    commit = "?"
    for line in _git_stream(repo, [
        "log", "--all", "-p", "-U0", "--no-color",
        f"--pretty=format:{COMMIT_MARK}%H%n%s%n%b",
    ]):
        if line.startswith(COMMIT_MARK):
            commit = line[len(COMMIT_MARK):][:9]
            continue
        # Skip diff headers: they restate paths already covered by content.
        if line.startswith(("index ", "--- ", "+++ ", "@@ ")):
            continue
        record(line, "content/message", commit)

    for line in _git_stream(repo, [
        "log", "--all", "--pretty=format:%an <%ae>%n%cn <%ce>",
    ]):
        record(line, "identity", commit="(identity)")

    return hits


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Scan a filtered mirror for personal data before publishing.")
    ap.add_argument("repo", nargs="?", default=".",
                    help="path to the filtered mirror (default: cwd)")
    ap.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST,
                    help="file of intentionally-published values")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    if not repo.exists():
        print(f"ERROR: no such repo: {repo}")
        return 2

    allowed = load_allowlist(args.allowlist)
    print(f"Scanning {repo}")
    print(f"Allowlist: {len(allowed)} value(s)")
    print()

    hits = scan(repo)

    errors, advisories = [], []
    for label in sorted(hits):
        bucket = errors if label.startswith("E") else advisories
        for value, (source, commit) in sorted(hits[label].items()):
            if value in allowed:
                continue
            bucket.append((label, value, source, commit))

    if advisories:
        print(f"ADVISORY ({len(advisories)}):")
        for label, value, source, commit in advisories:
            print(f"  W  [{label}] {value}  ({source}, {commit})")
        print()

    if errors:
        print(f"ERRORS ({len(errors)}):")
        for label, value, source, commit in errors:
            print(f"  E  [{label}] {value}  ({source}, {commit})")
        print()
        print("Fix by adding a rule to .claude/publish/replacements.txt and")
        print("re-running git-filter-repo, or - if the value is meant to be")
        print("public - by adding it to the allowlist.")
        print()
        print(f"RESULT: FAIL ({len(errors)} error(s), "
              f"{len(advisories)} advisory)")
        return 1

    print(f"RESULT: PASS (0 errors, {len(advisories)} advisory)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
