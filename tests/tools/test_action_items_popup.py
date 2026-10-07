"""An action item POPS UP. It is never only a console line.

Reported 2026-10-07, off Batch 499. 922 FormingFinder could not match the formed
bar `H6512163-H17-2` to any PO row -- the drawings number that order's parts
`-2 / -3A / -3B` while the PO numbers them `-1 / -2A / -2B` -- so it wrote the
Bent Plates row with no PPN and no SOURCE MATERIAL. It said so, correctly, in
the console:

    WARNING: H6512163-H17-2 (order FK411600) has no PO match - its Bent Plates
    PPN and SOURCE MATERIAL will be blank ...

and that line scrolled past under the run summary. Nothing popped. 922 Kitting
then matched its kit pages against a Bent Plates row that did not line up with
them and stamped FORMED on nothing, so Batch 499's kitting paperwork shipped a
formed part with no FORMED tag. The detection worked; the DELIVERY did not.

Thirteen apps already raised an ending `sdk.show_warning`, eight did not, and
each one that did had hand-rolled its own -- so whether a problem reached the
user depended on which app found it. `sdk.flag_action` is now the single home:
the plugin records items, the EXECUTOR raises the one blocking dialog as the run
ends, and the run reports WARNING instead of a blank check mark. A plugin cannot
forget the popup because showing it is no longer a plugin's job.

This test is the gate, in two narrow rules. Successful runs still go to the
console -- that is `log()`, and nothing here touches it.
"""

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"

# The log-ish callables a plugin writes its console lines through. `log` is the
# SDK contract name; the rest are the local aliases in use.
_LOG_CALLS = {"log", "safe_log", "_log", "print"}

# Rule 1. The shout words. A console line that SHOUTS is a line the author
# already knew the user must see -- which is exactly what flag_action is for.
# Matching the literal text catches it wherever it is passed.
_SHOUT_RE = re.compile(r"\b(WARNING|ACTION REQUIRED|ACTION NEEDED)\b")

# Rule 2. The ending popup is the executor's job now. A plugin calling
# show_warning is hand-rolling the thing flag_action centralizes; the one
# legitimate shape left is a problem raised BEFORE the work starts, which
# `request_*` prompts already cover, so no plugin needs it.
_HAND_ROLLED_POPUP = "show_warning"

PLUGIN_IDS = sorted(d.name for d in PLUGINS.iterdir() if (d / "run.py").is_file())


def _py_files(plugin_id: str):
    return sorted((PLUGINS / plugin_id).rglob("*.py"))


def _shouting_log_calls(path: Path):
    """[(lineno, source)] for every log-ish call whose literal text shouts."""
    src = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:                      # pragma: no cover
        pytest.fail(f"{path.relative_to(ROOT)} does not parse: {exc}")
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name not in _LOG_CALLS:
            continue
        # Only the literal text matters: a variable holding a line built
        # elsewhere is caught at the site that built it.
        text = " ".join(
            sub.value for sub in ast.walk(node)
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str)
        )
        if _SHOUT_RE.search(text):
            out.append((node.lineno, (ast.get_source_segment(src, node) or "")
                        .splitlines()[0].strip()))
    return out


@pytest.mark.parametrize("plugin_id", PLUGIN_IDS)
def test_no_shouting_console_lines(plugin_id):
    """A problem the user must act on goes through sdk.flag_action, not a
    hand-written WARNING line that scrolls past."""
    offences = []
    for path in _py_files(plugin_id):
        for lineno, snippet in _shouting_log_calls(path):
            offences.append(f"  {path.relative_to(ROOT)}:{lineno}  {snippet}")
    assert not offences, (
        f"{plugin_id}: {len(offences)} console line(s) SHOUT at the user instead "
        f"of raising an action item.\n" + "\n".join(offences) + "\n\n"
        "Use sdk.flag_action(params, '<what is wrong and what to do about it>') "
        "- TechDeck pops every item once as the run ends. If the line is not "
        "something the user must act on, it is ordinary log() output: drop the "
        "WARNING word."
    )


@pytest.mark.parametrize("plugin_id", PLUGIN_IDS)
def test_no_hand_rolled_ending_popup(plugin_id):
    """Raising the dialog is the executor's job - a plugin only records items."""
    offences = []
    for path in _py_files(plugin_id):
        src = path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(src.splitlines(), 1):
            if _HAND_ROLLED_POPUP in line and not line.lstrip().startswith("#"):
                offences.append(f"  {path.relative_to(ROOT)}:{i}  {line.strip()}")
    assert not offences, (
        f"{plugin_id}: hand-rolls its own warning popup.\n" + "\n".join(offences)
        + "\n\nRecord each item with sdk.flag_action(params, ...) instead; the "
        "executor raises ONE dialog listing them all as the run ends."
    )


def test_flag_action_is_the_documented_home():
    """The SDK helper and the executor hook both exist and are wired together."""
    from techdeck.core import plugin_sdk as sdk
    from techdeck.core.plugin_executor import PluginExecutor

    assert callable(sdk.flag_action)
    assert callable(sdk.action_items)
    assert hasattr(PluginExecutor, "_show_action_items"), (
        "the executor no longer raises the ending action-item dialog, so every "
        "plugin's flag_action items would go unseen"
    )


def test_flag_action_records_logs_and_formats():
    from techdeck.core import plugin_sdk as sdk

    lines = []
    params = {"log": lines.append}
    assert sdk.action_items(params) == []

    sdk.flag_action(params, "Fill PPN on Bent Plates row 6", "order FK411600")
    sdk.flag_action(params, "Second thing")
    sdk.flag_action(params, "   ")            # nothing to say -> nothing recorded

    items = sdk.action_items(params)
    assert len(items) == 2
    assert items[0] == {"item": "Fill PPN on Bent Plates row 6",
                        "detail": "order FK411600"}
    # It still reaches the console, so the run log keeps the whole story.
    assert any("Fill PPN" in line for line in lines)

    title, body = sdk.format_action_items(items, "922 FormingFinder")
    assert title == "922 FormingFinder - 2 things need your attention"
    assert body.splitlines()[0] == "1. Fill PPN on Bent Plates row 6"
    assert "order FK411600" in body.splitlines()[1]

    one_title, _ = sdk.format_action_items(items[:1], "922 Kitting")
    assert one_title == "922 Kitting - 1 thing needs your attention"


def test_action_item_makes_the_run_report_a_warning():
    """A run that needs the user to go and fix something never reports a clean
    success - that is the whole point of surfacing it."""
    from techdeck.core import plugin_sdk as sdk
    from techdeck.core.plugin_executor import PluginExecutor

    assert PluginExecutor._run_outcome_from({}) == (None, "")

    params = {"log": lambda *_: None}
    sdk.flag_action(params, "Go and fix the Bent Plates row")
    status, message = PluginExecutor._run_outcome_from(params)
    assert status == sdk.RUN_OUTCOME_WARNING
    assert message == "1 thing needs your attention"

    # An explicit outcome still wins: the plugin knows more than the count does.
    sdk.set_run_outcome(params, sdk.RUN_OUTCOME_PARTIAL, "two of three orders")
    assert PluginExecutor._run_outcome_from(params) == ("partial",
                                                        "two of three orders")
