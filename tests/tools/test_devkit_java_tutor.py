"""The Java Tutor is personal tooling that must never reach a colleague's
install. It used to live in `plugins/` and was held back by two `Excludes:`
patterns in TechDeck-Setup.iss - string matching, so a folder rename or a
reworded pattern would have shipped it silently, and nothing would have failed.

It now lives under `tools/devkit/`, which TechDeck.spec excludes wholesale from
every frozen build. These tests pin the three things that guarantee stays true.
"""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TUTOR = ROOT / "tools" / "devkit" / "java_tutor"


def test_tutor_is_not_a_shipped_plugin():
    """plugins/ is what the installer copies; the tutor must not be in it."""
    assert not (ROOT / "plugins" / "java_tutor").exists(), (
        "plugins/java_tutor is back. Anything under plugins/ is bundled into "
        "the installer. Dev-only tooling belongs in tools/devkit/.")


def test_spec_excludes_the_whole_tools_package():
    """The single guarantee everything else here leans on."""
    spec = (ROOT / "TechDeck.spec").read_text(encoding="utf-8")
    tree = ast.parse(spec)
    excludes = [
        elt.value
        for node in ast.walk(tree)
        if isinstance(node, ast.keyword) and node.arg == "excludes"
        for elt in getattr(node.value, "elts", [])
        if isinstance(elt, ast.Constant)
    ]
    assert "tools" in excludes, (
        "TechDeck.spec no longer excludes the 'tools' package. That exclusion "
        "is the ONLY thing keeping tools/devkit/java_tutor (and the rest of "
        "the DevKit) out of the frozen build.")


def test_installer_has_no_stale_java_tutor_exclusion():
    """A dead Excludes: pattern reads as protection that isn't there."""
    iss = (ROOT / "TechDeck-Setup.iss").read_text(encoding="utf-8-sig")
    for line in iss.splitlines():
        if line.strip().startswith(";"):
            continue                      # comments explain the history
        assert "java_tutor" not in line, (
            f"stale java_tutor rule in TechDeck-Setup.iss: {line.strip()!r}. "
            f"The tutor is not under plugins/ any more, so this matches "
            f"nothing and only implies a protection that no longer applies.")


def test_repo_root_fallback_depth_is_right():
    """Each module has a `sys.path.insert(... parents[N])` fallback used when
    techdeck isn't importable. N is a hardcoded depth, so MOVING these files
    breaks it silently - which is exactly what the DevKit move did (they said
    parents[2], correct only under plugins/). Resolve it and check."""
    checked = 0
    for py in sorted(TUTOR.glob("*.py")):
        src = py.read_text(encoding="utf-8")
        for depth in map(int, re.findall(r"resolve\(\)\.parents\[(\d+)\]", src)):
            assert py.resolve().parents[depth] == ROOT, (
                f"{py.relative_to(ROOT)} uses parents[{depth}] as the repo "
                f"root, but that resolves to "
                f"{py.resolve().parents[depth]} (repo root is {ROOT}).")
            checked += 1
    assert checked, "no parents[N] fallback found - did the idiom change?"


def test_devkit_registry_offers_the_tutor():
    from tools.devkit.registry import DEV_TOOLS
    keys = {t.key for t in DEV_TOOLS}
    assert "java_tutor" in keys, (
        f"Java Tutor missing from the DevKit picker; have {sorted(keys)}")
