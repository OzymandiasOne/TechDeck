"""What actually ships in this release - read from git, not from memory.

Release notes used to be assembled from docs/FEEDBACK_TRACKER.md (the tickets
that ride the release). That list only knows about work somebody ASKED for.
v0.8.7.6 shipped a whole new app, MieTrak Tools, that had no ticket - so it
appeared in no pop-up, no Teams post, no GitHub Release and no README
"What's New", while its six commits sat in plain view in the log.

This tool is the other half of the list: every plugin that is NEW or whose
version CHANGED between the previous release tag and this one, with the commit
subjects that touched it, and whether the release text names it.

    python tools\\release_inventory.py                  # check README What's New
    python tools\\release_inventory.py --check "<file>"  # also check a Teams post / pop-up text

Exit 1 when a NEW app is named nowhere in a checked text. CHANGED apps that go
unmentioned are listed as a prompt, not a failure - some bumps are internal.
The same check runs in pytest (tests/tools/test_release_inventory.py), so
build.ps1 refuses to build a release whose README skips a new app.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAMILY_PREFIX_RE = re.compile(r"^(?:902|911|922|QA)\s+", re.IGNORECASE)


class GitUnavailable(RuntimeError):
    """No git, not a repo, or no release tags (a shallow CI checkout)."""


def _git(*args: str) -> str:
    try:
        out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                             text=True, encoding="utf-8", errors="replace")
    except OSError as exc:
        raise GitUnavailable(str(exc)) from exc
    if out.returncode != 0:
        raise GitUnavailable(out.stderr.strip())
    return out.stdout


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", version))


def app_version() -> str:
    src = (ROOT / "techdeck" / "core" / "constants.py").read_text(encoding="utf-8")
    match = re.search(r'APP_VERSION = "([^"]+)"', src)
    if not match:
        raise RuntimeError("constants.py no longer has an APP_VERSION line")
    return match.group(1)


def release_tags() -> list[str]:
    tags = [t for t in _git("tag", "--list", "v*").split() if re.fullmatch(r"v\d[\d.]*", t)]
    return sorted(tags, key=version_key)


def release_range(version: str) -> tuple[str, str]:
    """(base, end): the last tag BELOW `version`, and tag v<version> if it is
    already cut, else HEAD. Once the tag exists the range is frozen, so work on
    the next release branch never reads as part of the shipped one."""
    tags = release_tags()
    older = [t for t in tags if version_key(t) < version_key(version)]
    if not older:
        raise GitUnavailable(f"no release tag older than v{version}")
    end = f"v{version}" if f"v{version}" in tags else "HEAD"
    return older[-1], end


def _manifests(ref: str) -> dict[str, dict]:
    """plugin id -> plugin.json contents, as committed at `ref`."""
    found = {}
    for path in _git("ls-tree", "-r", "--name-only", ref, "plugins/").splitlines():
        parts = path.split("/")
        if len(parts) != 3 or parts[2] != "plugin.json":
            continue
        try:
            found[parts[1]] = json.loads(_git("show", f"{ref}:{path}"))
        except (json.JSONDecodeError, GitUnavailable):
            continue
    return found


@dataclass
class AppChange:
    plugin_id: str
    name: str
    kind: str                       # "NEW" or "CHANGED"
    old_version: str | None
    new_version: str
    commits: list[str] = field(default_factory=list)


def inventory(base: str, end: str) -> list[AppChange]:
    before, after = _manifests(base), _manifests(end)
    names_before = {m.get("name") for m in before.values()}
    changes = []
    for pid, manifest in sorted(after.items()):
        name = str(manifest.get("name") or pid)
        new_version = str(manifest.get("version", "?"))
        if pid not in before:
            # A renamed folder is not a new app: same display name, new id.
            kind, old_version = ("CHANGED", None) if name in names_before else ("NEW", None)
        elif str(before[pid].get("version", "?")) != new_version:
            kind, old_version = "CHANGED", str(before[pid].get("version", "?"))
        else:
            continue
        commits = _git("log", "--format=%s", f"{base}..{end}", "--", f"plugins/{pid}").splitlines()
        changes.append(AppChange(pid, name, kind, old_version, new_version, commits))
    return changes


def whats_new_section(readme_text: str, version: str) -> str | None:
    # (?!\.?\d): "v0.8.7.2" must not match the "v0.8.7.2.1" heading.
    match = re.search(rf"^## What's New in v{re.escape(version)}(?!\.?\d).*?(?=^## |\Z)",
                      readme_text, re.MULTILINE | re.DOTALL)
    return match.group(0) if match else None


def is_mentioned(name: str, text: str) -> bool:
    """The app's display name appears, with or without its family prefix
    ("911 Setup" is usually written "911 Setup", sometimes just "Remove Ticket")."""
    flat = re.sub(r"\s+", " ", text).lower()
    candidates = {name.lower(), FAMILY_PREFIX_RE.sub("", name).lower()}
    return any(c and c in flat for c in candidates)


def unmentioned(changes: list[AppChange], text: str, kind: str) -> list[AppChange]:
    return [c for c in changes if c.kind == kind and not is_mentioned(c.name, text)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--version", help="release to inventory (default: APP_VERSION)")
    parser.add_argument("--check", action="append", default=[], metavar="FILE",
                        help="a release text (Teams post, pop-up...) that must name every new app")
    args = parser.parse_args(argv)

    version = args.version or app_version()
    try:
        base, end = release_range(version)
        changes = inventory(base, end)
    except GitUnavailable as exc:
        print(f"cannot read git history: {exc}")
        return 2

    print(f"Release v{version}: {base}..{end}\n")
    for kind in ("NEW", "CHANGED"):
        for c in (c for c in changes if c.kind == kind):
            was = f" (was {c.old_version})" if c.old_version else ""
            print(f"{kind:8}{c.name}  v{c.new_version}{was}   [{c.plugin_id}]")
            for subject in c.commits:
                print(f"          - {subject}")
    if not changes:
        print("No plugin is new or changed version in this range.")

    texts = {}
    section = whats_new_section((ROOT / "README.md").read_text(encoding="utf-8"), version)
    texts[f"README What's New in v{version}"] = section
    for file in args.check:
        texts[file] = Path(file).read_text(encoding="utf-8")

    failed = False
    for label, text in texts.items():
        print(f"\n== {label}")
        if text is None:
            print("   not written yet")
            continue
        missing_new = unmentioned(changes, text, "NEW")
        missing_changed = unmentioned(changes, text, "CHANGED")
        for c in missing_new:
            print(f"   MISSING NEW APP: {c.name}")
        for c in missing_changed:
            print(f"   not mentioned (changed): {c.name} - fine only if the bump is internal")
        if not missing_new and not missing_changed:
            print("   names every new and changed app")
        failed = failed or bool(missing_new)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
