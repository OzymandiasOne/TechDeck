"""Take a full, unfiltered snapshot of the repo before anything risky touches it.

WHY (2026-09-01). A publish step ran git-filter-repo in the WORKING repo instead
of a throwaway mirror. It rewrote all 1282 commits in place, deleted CLAUDE.md,
LESSONS_LEARNED.md, docs/ and .claude/ from history AND from disk, scrubbed names
out of every blob, dropped the origin remote, and garbage-collected the originals.
Everything came back -- but only because an earlier step had happened to leave an
unfiltered `--mirror` clone in TEMP. Recovery was luck. This makes it policy.

A `--mirror` clone is the right shape for this: it carries EVERY ref (all branches,
all tags, all remote-tracking refs) and every object, so a restore is complete
rather than "whatever was checked out".

Two rules this file exists to enforce:

  * The backup lives OUTSIDE the repo. A snapshot inside the working tree is
    destroyed by the same `filter-repo`/`gc` that destroys the thing it is backing
    up, and by a stray `git clean -xfd`.
  * The backup is taken BEFORE the risky step, never after. `publish_mirror.py`
    calls this as its step 0.

Usage:
    python tools/backup_repo.py             # snapshot now, prune old ones
    python tools/backup_repo.py --list      # what snapshots exist
    python tools/backup_repo.py --verify    # integrity-check the newest one
"""

from __future__ import annotations

import argparse
import datetime
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# Sibling of the repo, never inside it - see the module docstring.
BACKUP_ROOT = REPO.parent / "_repo_backups" / REPO.name
KEEP = 5


def rmtree(path: Path) -> None:
    """Delete a git dir on Windows, where pack files are marked read-only."""
    def on_error(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    shutil.rmtree(path, onexc=on_error)


def git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(["git", *args], cwd=str(cwd), text=True,
                            capture_output=True)
    if result.returncode != 0:
        sys.exit(f"FAILED: git {' '.join(args)}\n{result.stderr}")
    return result.stdout


def snapshots() -> list[Path]:
    if not BACKUP_ROOT.is_dir():
        return []
    return sorted((p for p in BACKUP_ROOT.iterdir() if p.is_dir()),
                  key=lambda p: p.name)


def census(repo: Path) -> tuple[int, int, int]:
    """(commits, branches, tags) - what a restore has to bring back."""
    commits = int(git(["rev-list", "--all", "--count"], repo).strip() or 0)
    branches = len([l for l in git(["for-each-ref", "--format=%(refname)",
                                    "refs/heads"], repo).splitlines() if l])
    tags = len([l for l in git(["for-each-ref", "--format=%(refname)",
                                "refs/tags"], repo).splitlines() if l])
    return commits, branches, tags


def verify(path: Path) -> bool:
    """A backup nobody checked is a rumour, not a backup."""
    if git(["rev-parse", "--is-bare-repository"], path).strip() != "true":
        print(f"  [FAIL] {path.name} is not a bare mirror")
        return False
    src, dst = census(REPO), census(path)
    ok = dst[0] >= src[0] and dst[1] >= src[1] and dst[2] >= src[2]
    print(f"  {'[ok]  ' if ok else '[FAIL]'} {path.name}  "
          f"commits {dst[0]} (repo {src[0]}), branches {dst[1]} (repo {src[1]}), "
          f"tags {dst[2]} (repo {src[2]})")
    return ok


def take() -> Path:
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_ROOT / f"{stamp}.git"
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    print(f"Backing up {REPO}\n        -> {dest}")
    subprocess.run(["git", "clone", "--quiet", "--mirror", str(REPO), str(dest)],
                   check=True)
    if not verify(dest):
        sys.exit("The snapshot did not verify - do NOT run the risky step.")

    for old in snapshots()[:-KEEP]:
        print(f"  pruning {old.name}")
        rmtree(old)
    return dest


def restore_help(path: Path) -> None:
    print(f"""
To restore from this snapshot (run from the repo root):

  git remote add recovery "{path}"
  git fetch recovery --force "+refs/heads/*:refs/remotes/recovery/*" "+refs/tags/*:refs/tags/*"
  git reset --hard recovery/<your-branch>
  git branch -f <each-other-branch> recovery/<same>
  git remote remove recovery

Then re-check: `git remote -v` (filter-repo drops `origin`) and
`git config --get-regexp '^branch\\..*\\.remote'` (fetching leaves branches
tracking `recovery`, which points at a path that is about to be pruned).""")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="list existing snapshots")
    ap.add_argument("--verify", action="store_true", help="verify the newest snapshot")
    args = ap.parse_args()

    if args.list:
        found = snapshots()
        print(f"{len(found)} snapshot(s) in {BACKUP_ROOT}")
        for p in found:
            print(f"  {p.name}")
        return 0

    if args.verify:
        found = snapshots()
        if not found:
            sys.exit(f"No snapshots in {BACKUP_ROOT} - run without --verify first.")
        return 0 if verify(found[-1]) else 1

    dest = take()
    restore_help(dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
