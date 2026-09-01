"""Build the filtered public mirror of TechDeck, safely.

The working repo's history is PRIVATE (internal docs, coworker names in old
commits, legacy blobs), so publishing goes through a throwaway mirror that
git-filter-repo strips before anything is pushed. That used to be a wall of
copy-pasted shell.

WHY THIS SCRIPT EXISTS (2026-09-01). The pipeline was pasted as a chained
one-liner: `cd $TEMP; rm -rf mirror; git clone --mirror . mirror; cd mirror;
python -m git_filter_repo ...`. It was written in PowerShell syntax and run in
bash, so every `cd` failed - and because the chain used `;` rather than `&&`,
filter-repo ran anyway, in the working repo. It rewrote all 1282 commits in
place, deleted CLAUDE.md / LESSONS_LEARNED.md / docs / .claude from history and
from disk, scrubbed names out of every blob, dropped the origin remote, and
garbage-collected the originals. The repo was only recovered because an earlier
step happened to have left an unfiltered mirror in TEMP.

Three things here make that impossible:
  1. It is Python, so there is no shell-dialect mismatch to get wrong.
  2. Each step is checked; nothing continues after a failure.
  3. filter-repo is only ever invoked after asserting the CWD is a BARE
     repository that is not the working repo - the one check that would have
     stopped the accident cold.

Usage (from the repo root):
    python tools/publish_mirror.py                  # build + verify the mirror
    python tools/publish_mirror.py --branch main    # which branch to publish

It stops before pushing and prints the push commands. Pushing stays a human
action on purpose: that is the irreversible step.
"""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MIRROR = Path(tempfile.gettempdir()) / "td-public-mirror"
PUBLIC_URL = "https://github.com/OzymandiasOne/TechDeck"

# Paths that must never reach the public repo, in any commit.
PRIVATE_PATHS = [
    "CLAUDE.md", "LESSONS_LEARNED.md", "docs", ".claude",
    "one_off_apps", "dist", "build", "installer_output",
    "tools/pixel_playground",
]


def rmtree(path: Path) -> None:
    """Delete a git directory on Windows.

    git marks pack files and the commit-graph read-only, and shutil.rmtree hands
    those straight back as PermissionError [WinError 5] - so a plain rmtree cannot
    clear a previous mirror. Clear the read-only bit and retry.
    """
    def on_error(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    shutil.rmtree(path, onexc=on_error)


def run(cmd: list[str], cwd: Path, capture: bool = False) -> str:
    """Run a command, aborting the whole script on a non-zero exit."""
    printable = " ".join(cmd)
    print(f"  $ {printable}")
    result = subprocess.run(cmd, cwd=str(cwd), text=True,
                            capture_output=capture)
    if result.returncode != 0:
        if capture:
            sys.stderr.write(result.stdout or "")
            sys.stderr.write(result.stderr or "")
        sys.exit(f"\nFAILED ({result.returncode}): {printable}\n"
                 f"Nothing was pushed. Fix the above and re-run.")
    return (result.stdout or "") if capture else ""


def assert_safe_to_filter(path: Path) -> None:
    """The guard that would have prevented the 2026-09-01 accident.

    filter-repo rewrites whatever repo it is standing in, irreversibly. Refuse
    unless this is a BARE repo that is definitively not the working tree.
    """
    if not path.is_dir():
        sys.exit(f"REFUSING: {path} is not a directory - the mirror never got built.")
    bare = run(["git", "rev-parse", "--is-bare-repository"], path, capture=True).strip()
    if bare != "true":
        sys.exit(f"REFUSING to rewrite history: {path} is not a bare mirror "
                 f"(is-bare-repository = {bare!r}).")
    top = Path(run(["git", "rev-parse", "--absolute-git-dir"], path, capture=True).strip())
    if top.resolve() == (REPO / ".git").resolve() or top.resolve() == REPO.resolve():
        sys.exit(f"REFUSING to rewrite history: {path} resolves to the WORKING repo.")
    print(f"  [guard] {path} is a bare mirror, not the working repo - safe to filter.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--branch", default="", help="branch to publish as public main "
                                                 "(default: the current branch)")
    args = ap.parse_args()

    branch = args.branch or run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                REPO, capture=True).strip()
    replacements = REPO / ".claude" / "publish" / "replacements.txt"
    if not replacements.is_file():
        sys.exit(f"Missing the scrub map: {replacements}")

    print(f"Publishing branch : {branch}")
    print(f"Working repo      : {REPO}")
    print(f"Mirror            : {MIRROR}\n")

    # Step 0 is the backup, and it is not optional. The mirror this script builds
    # gets REWRITTEN in step 3, so it is not a backup of anything - a separate
    # untouched snapshot has to exist before filter-repo is anywhere near the disk.
    print("[0/5] Unfiltered backup snapshot (before anything risky)")
    backup = run([sys.executable, str(REPO / "tools" / "backup_repo.py")],
                 REPO, capture=True)
    for line in backup.strip().splitlines()[:3]:
        print("  " + line)

    print("[1/5] Fresh mirror clone")
    if MIRROR.exists():
        rmtree(MIRROR)
    run(["git", "clone", "--quiet", "--mirror", str(REPO), str(MIRROR)], REPO)

    print("\n[2/5] Guard")
    assert_safe_to_filter(MIRROR)

    print("\n[3/5] Strip private paths and scrub names from every commit")
    cmd = [sys.executable, "-m", "git_filter_repo", "--force", "--invert-paths"]
    for p in PRIVATE_PATHS:
        cmd += ["--path", p]
    cmd += ["--replace-text", str(replacements),
            "--replace-message", str(replacements)]
    run(cmd, MIRROR)

    print("\n[4/5] Verify (this is the gate, not a formality)")
    leftovers = run(["git", "log", "--all", "--oneline", "--"] + PRIVATE_PATHS,
                    MIRROR, capture=True).strip()
    if leftovers:
        sys.exit("REFUSING: private paths still present in history:\n" + leftovers)
    print("  [ok] no private paths remain in any commit")
    run([sys.executable, str(REPO / "tools" / "check_publish_scrub.py"), str(MIRROR)], REPO)

    print()
    print("[5/5] Ready")
    tags = run(["git", "tag", "--merged", "refs/heads/" + branch],
               MIRROR, capture=True).split()
    print("\n" + "=" * 70)
    print("MIRROR READY - nothing has been pushed.")
    print("=" * 70)
    print("\nRun these two to publish (the push is deliberately yours):\n")
    # FULLY QUALIFIED on the left. A release branch and its tag share a name here
    # (v0.8.7.2.1), and git resolves a bare name as refs/tags BEFORE refs/heads -
    # so "v0.8.7.2.1:refs/heads/main" silently publishes whatever the TAG points
    # at. They usually agree; the one time they do not is the one that matters.
    print(f'  git -C "{MIRROR}" push --force {PUBLIC_URL} '
          f'"refs/heads/{branch}:refs/heads/main"')
    if tags:
        print(f'  git -C "{MIRROR}" push --force {PUBLIC_URL} {" ".join(tags)}')
    else:
        print("  (no tags are merged into this branch - nothing to push)")
    print("\nNever push refs/tags/* - most tags here point outside the published "
          "branch and\nthe wildcard would drag unpublished history into the public repo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
