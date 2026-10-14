"""An action item POPS UP — and almost nothing is an action item.

Batch 499, 2026-10-07. 922 FormingFinder could not match the formed bar
`H6512163-H17-2` to any PO row, so it wrote the Bent Plates row with no PPN and
no SOURCE MATERIAL. It said so, correctly, in the console — and that line scrolled
past under the run summary. 922 Kitting then matched its kit pages against that
row, stamped FORMED on nothing, and the kitting paperwork shipped a formed part
with no FORMED tag. The detection worked; the DELIVERY did not.

The first fix over-reached: 158 console `WARNING` lines became 145 popup items
across 21 plugins, and about 130 of those were "ran fine, but one thing was not
found". That is the wrong class. 922 LST Organizer naming a tube it could not
find is the app working CORRECTLY — the user reads it and goes and cuts the tube.
Popping everything teaches him to dismiss the dialog without reading it, which
costs more than it buys. That attempt was reverted (`1a90993a`); the old head is
on branch `action-items-attempt`.

The rule, in the user's words: **the run failed, the run is waiting on you, or
the output will make the NEXT app do the wrong thing.** A run that is waiting
already pops — that is the `request_*` prompt itself. So `sdk.flag_action` covers
only the other two, and this file pins exactly where it is used, because the
pressure is always to add one more.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"

# Every sdk.flag_action call in the codebase, and WHY it earns a dialog. Adding
# or removing one fails this test until the list is updated — which is the point:
# it forces whoever adds the next one to say which half of the rule it meets.
EXPECTED_ITEMS = {
    # "the output will make the NEXT app do the wrong thing"
    "922_formingfinder": 1,     # Bent Plates row with no SOURCE MATERIAL — 922
                                # Kitting stamps FORMED off that column
    "922_kitting": 3,           # no Bent Plates sheet / no DYPN column (NOT ONE
                                # part tagged), and a tag that could not be written
    # "a whole stage produced nothing usable"
    "902_dxf_prep": 2,          # no pricing workbook, and no PO rows — either way
                                # the QTY workbook was never built
    "922_runtime_genie": 1,     # no .lst files, so the estimate came out at zero
    "922_batch_repeater": 1,    # 922 MPL.xlsx open in Excel — nothing saved
    "911_po_pdf_extractor": 1,  # nothing extracted, so nothing written
}

# Plugins that raised their OWN ending popup before any of this, and still do.
# Left exactly as they were by the user's call: undo the 130 that were added,
# leave what he already relies on. A new one here needs his say-so, not ours.
LEGACY_POPUP_PLUGINS = {
    "902_batch_validator",
    "911_lst_organizer",
    "911_remove_ticket",
    "911_setup",
    "911_teams_cards",
    "922_batch_repeater",
    "922_difficulty_stamper",
    "922_lst_organizer",
    "922_pallet_stamper",
    "922_setup",
}

PLUGIN_IDS = sorted(d.name for d in PLUGINS.iterdir() if (d / "run.py").is_file())


def _count_calls(plugin_id: str, attr: str) -> int:
    total = 0
    for path in sorted((PLUGINS / plugin_id).rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as exc:                      # pragma: no cover
            pytest.fail(f"{path.relative_to(ROOT)} does not parse: {exc}")
        total += sum(1 for n in ast.walk(tree)
                     if isinstance(n, ast.Call)
                     and getattr(n.func, "attr", None) == attr)
    return total


def test_the_action_item_roster_is_exactly_what_we_signed_off():
    """A console line is the right home for nearly every finding. If this fails
    because you added an item, say which half of the rule it meets - the run
    failed / a stage produced nothing, or the NEXT app will act on it wrongly -
    and only then add it to EXPECTED_ITEMS."""
    found = {pid: n for pid in PLUGIN_IDS
             if (n := _count_calls(pid, "flag_action"))}
    assert found == EXPECTED_ITEMS, (
        "the action-item roster moved.\n"
        f"  expected: {EXPECTED_ITEMS}\n"
        f"  found:    {found}"
    )


def test_no_plugin_hand_rolls_a_new_ending_popup():
    """Raising the dialog is the executor's job. The listed plugins kept the
    popups they already had; nothing else may grow one."""
    offenders = sorted(pid for pid in PLUGIN_IDS
                       if _count_calls(pid, "show_warning")
                       and pid not in LEGACY_POPUP_PLUGINS)
    assert not offenders, (
        f"{offenders} hand-roll their own warning popup. Record the item with "
        "sdk.flag_action(params, ...) instead - the executor raises ONE dialog "
        "listing them all as the run ends."
    )


def test_the_mechanism_is_wired_end_to_end():
    from techdeck.core import plugin_sdk as sdk
    from techdeck.core.plugin_executor import PluginExecutor

    assert callable(sdk.flag_action) and callable(sdk.action_items)
    assert hasattr(PluginExecutor, "_show_action_items"), (
        "the executor no longer raises the ending dialog, so every plugin's "
        "flag_action items would go unseen"
    )


def test_flag_action_records_logs_and_formats():
    from techdeck.core import plugin_sdk as sdk

    lines = []
    params = {"log": lines.append}
    assert sdk.action_items(params) == []

    sdk.flag_action(params, "Fill SOURCE MATERIAL on Bent Plates row 6",
                    "H6512163-H17-2 (order FK411600)")
    sdk.flag_action(params, "Second thing")
    sdk.flag_action(params, "   ")            # nothing to say -> nothing recorded

    items = sdk.action_items(params)
    assert len(items) == 2
    assert items[0] == {"item": "Fill SOURCE MATERIAL on Bent Plates row 6",
                        "detail": "H6512163-H17-2 (order FK411600)"}
    # It still reaches the console, so the run log keeps the whole story.
    assert any("Fill SOURCE MATERIAL" in line for line in lines)

    title, body = sdk.format_action_items(items, "922 FormingFinder")
    assert title == "922 FormingFinder - 2 things need your attention"
    assert body.splitlines()[0] == "1. Fill SOURCE MATERIAL on Bent Plates row 6"
    assert "H6512163-H17-2" in body.splitlines()[1]

    one_title, _ = sdk.format_action_items(items[:1], "922 Kitting")
    assert one_title == "922 Kitting - 1 thing needs your attention"


def test_an_action_item_makes_the_run_report_a_warning():
    """A run that needs the user to go and fix something never reports a clean
    success - that is the whole point of surfacing it."""
    from techdeck.core import plugin_sdk as sdk
    from techdeck.core.plugin_executor import PluginExecutor

    assert PluginExecutor._run_outcome_from({}) == (None, "")

    params = {"log": lambda *_: None}
    sdk.flag_action(params, "Go and fill in the Bent Plates row")
    assert PluginExecutor._run_outcome_from(params) == (
        sdk.RUN_OUTCOME_WARNING, "1 thing needs your attention")

    # An explicit outcome still wins: the plugin knows more than the count does.
    sdk.set_run_outcome(params, sdk.RUN_OUTCOME_PARTIAL, "two of three orders")
    assert PluginExecutor._run_outcome_from(params) == ("partial",
                                                        "two of three orders")


def test_the_dialog_stays_a_size_a_screen_can_hold():
    """A QMessageBox does not scroll, so a body taller than the screen is clipped
    - and the clipped part is silently lost, which is the failure this whole
    feature exists to stop. The console keeps every line."""
    from techdeck.core import plugin_sdk as sdk

    params = {"log": lambda *_: None}
    sdk.flag_action(params, "20 rows have no SOURCE MATERIAL",
                    "\n".join(f"PART-{n}" for n in range(20)))
    _title, body = sdk.format_action_items(sdk.action_items(params), "922 X")
    lines = body.splitlines()
    assert len(lines) == 1 + sdk.DIALOG_LINES_PER_ITEM + 1
    assert lines[-1].strip() == "...(the console lists them all)"


def test_the_executor_shows_the_dialog_through_the_console():
    """The seam that matters: ONE formatted dialog, nothing when there is nothing
    to say, and a console that blows up does not lose the text."""
    from techdeck.core import plugin_sdk as sdk
    from techdeck.core.plugin_executor import PluginExecutor

    shown = []

    class FakeConsole:
        def show_warning(self, title, text):
            shown.append((title, text))

    logs = []
    params = {"log": logs.append, "console": FakeConsole()}
    sdk.flag_action(params, "Fill SOURCE MATERIAL on Bent Plates row 6")
    PluginExecutor._show_action_items(params, "922 FormingFinder", logs.append)
    assert len(shown) == 1
    assert shown[0][0] == "922 FormingFinder - 1 thing needs your attention"
    assert "Bent Plates row 6" in shown[0][1]

    shown.clear()
    PluginExecutor._show_action_items({"log": logs.append, "console": FakeConsole()},
                                      "922 Kitting", logs.append)
    assert shown == [], "nothing to say -> no dialog"

    class BrokenConsole:
        def show_warning(self, title, text):
            raise RuntimeError("no GUI here")

    fallback = []
    broken = {"log": fallback.append, "console": BrokenConsole()}
    sdk.flag_action(broken, "Something to do")
    PluginExecutor._show_action_items(broken, "922 Setup", fallback.append)
    assert any("Something to do" in line and "922 Setup" in line
               for line in fallback), fallback


def test_the_dialog_comes_up_after_the_run_reads_as_finished():
    """Ordering: progress 100 and the run-log line land BEFORE the modal, so the
    run does not look stuck behind it - and the dialog still comes before
    completion_callback, which is what starts the next queued plugin."""
    import inspect

    from techdeck.core.plugin_executor import PluginExecutor

    src = inspect.getsource(PluginExecutor._run_plugin_body)
    assert (src.index("safe_progress(100)")
            < src.index("self._show_action_items(")
            < src.index("completion_callback(")), (
        "the dialog must sit between progress 100 and the completion callback")


def test_a_gui_plugin_does_not_lose_its_popup_to_the_thread_guard():
    """console.show_warning used to RAISE on the GUI thread, so a
    requires_main_thread plugin silently lost its dialog. It shows the box
    directly there now."""
    import inspect

    from techdeck.ui.widgets import console as console_mod

    src = inspect.getsource(console_mod.ConsoleWidget.show_warning)
    assert "self._warning_gui()" in src
    assert "cannot be called from main GUI thread" not in src
