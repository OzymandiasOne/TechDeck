"""A new app must be named in the release notes that ship it.

v0.8.7.6 shipped MieTrak Tools and announced it nowhere - not the pop-up, the
Teams post, the GitHub Release or the README. The notes were assembled from
docs/FEEDBACK_TRACKER.md, and an app nobody filed a ticket for is invisible to
that list. tools/release_inventory.py reads the list from git instead; this
test holds the README "What's New" to it, so build.ps1 (which runs pytest
first) cannot build a release that skips a new app.
"""

import pytest

from tools import release_inventory as inv


def test_version_key_orders_four_part_versions():
    tags = ["v0.8.7.10", "v0.8.7.2", "v0.8.7.2.1", "v0.8.7"]
    assert sorted(tags, key=inv.version_key) == ["v0.8.7", "v0.8.7.2", "v0.8.7.2.1", "v0.8.7.10"]


def test_whats_new_section_stops_at_the_next_release():
    readme = ("# TechDeck v2\n\n## What's New in v2 - B\n\nNew app: Widget\n\n"
              "## What's New in v1 - A\n\nNew app: Gadget\n")
    section = inv.whats_new_section(readme, "2")
    assert section is not None and "Widget" in section and "Gadget" not in section
    assert inv.whats_new_section(readme, "3") is None


def test_whats_new_section_does_not_match_a_longer_version():
    readme = "## What's New in v0.8.7.2.1 - Patch\n\ntext\n"
    assert inv.whats_new_section(readme, "0.8.7.2") is None


def test_is_mentioned_ignores_case_wrapping_and_family_prefix():
    assert inv.is_mentioned("MieTrak Tools", "New app: mietrak\n  tools")
    assert inv.is_mentioned("911 Remove Ticket", "911 Setup and Remove Ticket now find")
    assert not inv.is_mentioned("MieTrak Tools", "right next to where the Mie Trak invoice goes")


def test_readme_whats_new_names_every_new_app():
    version = inv.app_version()
    try:
        base, end = inv.release_range(version)
        changes = inv.inventory(base, end)
    except inv.GitUnavailable as exc:
        pytest.skip(f"no git history to compare against: {exc}")

    new_apps = [c for c in changes if c.kind == "NEW"]
    if not new_apps:
        return
    readme = (inv.ROOT / "README.md").read_text(encoding="utf-8")
    section = inv.whats_new_section(readme, version)
    names = ", ".join(c.name for c in new_apps)
    assert section is not None, (
        f"v{version} adds {names} but README.md has no \"What's New in v{version}\" section")
    missing = [c.name for c in inv.unmentioned(changes, section, "NEW")]
    assert not missing, (
        f"README \"What's New in v{version}\" never names the new app(s): {', '.join(missing)} "
        f"(added between {base} and {end}). Run `python tools\\release_inventory.py` for the "
        f"full list of what ships, and lead the notes with the new app "
        f"(techdeck-release-notes skill).")
