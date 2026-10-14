"""A dialog a RUN can raise opens in front of whatever app the user is in.

Reported 2026-10-08. A run prompts — for a folder, a choice, an action item —
while the user is in Excel or Teams. TechDeck is then a background process, and
Windows does not let a background process take the foreground, so `raise_()` and
`activateWindow()` can both be refused: the dialog opens BEHIND the other app
with nothing but a taskbar flash to say so, and the run sits waiting while the
user has no idea. `WindowStaysOnTopHint` is what actually works, because a
topmost window renders above every non-topmost window of every other app and
needs no focus to do it.

`techdeck/ui/dialog_front.py` is the single home. This gate keeps new dialogs
from skipping it, and keeps the flag going on BEFORE the first show - setting
window flags on a visible widget hides it in Qt.

Scope, deliberately: the dialogs a RUN (or the updater) raises, because those are
the ones that can appear while TechDeck is behind another window. A dialog that
only opens from a click on a TechDeck page is already in front of what the user
is looking at, so the in-app pages are listed as out of scope rather than swept.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# The run-time dialog surfaces: every one must go through dialog_front.
IN_SCOPE = [
    "techdeck/ui/widgets/console.py",            # every console prompt
    "techdeck/ui/dialogs/selection_dialog.py",
    "techdeck/ui/dialogs/grouped_toggle_dialog.py",
    "techdeck/ui/dialogs/report_dialog.py",
    "techdeck/ui/dialogs/update_dialog.py",       # fires at launch
    "techdeck/ui/dialogs/details_dialog.py",
    "techdeck/ui/arcade_chrome.py",               # PixelDialog
    "techdeck/core/plugin_sdk.py",                # pick_file_gui's native picker
    "plugins/911_sspo_invoicing_prep/run.py",     # its boxes end a long run
]

# Out of scope, with the reason. A dialog here only ever opens in response to a
# click on a TechDeck page, so TechDeck already has the foreground.
OUT_OF_SCOPE_REASON = {
    "techdeck/ui/pages": "only reachable by clicking a TechDeck page",
    "techdeck/ui/dialogs/feedback_dialog.py": "opened from the feedback button",
    "techdeck/ui/dialogs/profile_dialog.py": "opened from the account page",
    "techdeck/ui/dialogs/theme_builder_dialog.py": "opened from settings",
    "techdeck/ui/dialogs/schedule_wizard.py": "opened from the Assistant",
    "techdeck/ui/dialogs/sentry_config_dialog.py": "opened from My Stuff",
    "techdeck/ui/widgets/assistant_notes.py": "opened from the Assistant page",
    "techdeck/ui/widgets/assistant_schedule.py": "every box is click-driven",
    "techdeck/ui/widgets/beyblade_builder.py": "opened from My Stuff",
    "techdeck/ui/widgets/library_card.py": "opened from the Library page",
    "techdeck/ui/widgets/plugin_settings_widget.py": "opened from a plugin's settings",
    "techdeck/ui/widgets/rogue_mode_player.py": "opened from the console",
    "techdeck/ui/shell.py": "the shell's own boxes are click-driven",
    "plugins/customer_dxf_analysis/run.py": "its boxes answer a click in its own window",
    "plugins/qr_code_generator/run.py": "its boxes answer a click in its own window",
}


def test_the_helper_exists_and_offers_the_three_shapes():
    from techdeck.ui import dialog_front

    assert callable(dialog_front.bring_to_front)
    assert callable(dialog_front.message_box)
    assert callable(dialog_front.exec_in_front)
    assert callable(dialog_front.front_parent_for_native_dialog)


def test_the_flag_goes_on_before_the_first_show():
    """Setting window flags on a VISIBLE widget hides it in Qt, so the lift has
    to happen before show/exec, never after."""
    import inspect

    from techdeck.ui import dialog_front

    src = inspect.getsource(dialog_front.bring_to_front)
    assert "WindowStaysOnTopHint" in src
    # raise/activate alone is not enough - Windows can refuse both.
    assert "raise_()" in src and "activateWindow()" in src
    assert "alert" in src, "the taskbar flash is the fallback when focus is refused"

    box_src = inspect.getsource(dialog_front.message_box)
    assert box_src.index("bring_to_front(box)") < box_src.index("box.exec()")


@pytest.mark.parametrize("rel", IN_SCOPE)
def test_a_run_time_dialog_surface_uses_the_helper(rel):
    src = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
    assert "dialog_front" in src, (
        f"{rel} raises a dialog during a run but does not go through "
        "techdeck/ui/dialog_front.py, so it can open behind Excel"
    )


@pytest.mark.parametrize("rel", [r for r in IN_SCOPE if r.endswith(".py")])
def test_no_static_message_box_on_a_run_time_surface(rel):
    """The static QMessageBox helpers build AND show in one call, so there is no
    moment to set a window flag. Use dialog_front.message_box instead."""
    src = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
    offenders = [
        f"line {i}: {line.strip()}"
        for i, line in enumerate(src.splitlines(), 1)
        if re.search(r"QMessageBox\.(information|warning|critical|question)\s*\(", line)
    ]
    assert not offenders, f"{rel} still calls a static QMessageBox:\n  " + \
        "\n  ".join(offenders)


def test_the_native_picker_lifts_its_owner_instead():
    """QFileDialog's static helpers open the WINDOWS picker, which is not a Qt
    window and cannot take Qt window flags. Lifting its owner is the handle we
    have; DontUseNativeDialog is the alternative and costs the familiar picker."""
    import inspect

    from techdeck.ui import dialog_front

    src = inspect.getsource(dialog_front.front_parent_for_native_dialog)
    assert "DontUseNativeDialog" in src, "the trade-off has to stay written down"

    console = (ROOT / "techdeck/ui/widgets/console.py").read_text(encoding="utf-8")
    for call in ("getExistingDirectory", "getOpenFileName"):
        i = console.index(call)
        before = console[max(0, i - 400):i]
        assert "front_parent_for_native_dialog" in before, (
            f"the {call} picker does not lift its owner first")


def test_out_of_scope_surfaces_are_listed_with_a_reason():
    """Not a sweep: a dialog only reachable by clicking a TechDeck page is
    already in front of what the user is looking at. The list is the record of
    that judgement, so a future reader can disagree with it knowingly."""
    assert OUT_OF_SCOPE_REASON, "the reasoning must stay written down"
    for rel, reason in OUT_OF_SCOPE_REASON.items():
        assert (ROOT / rel).exists(), f"{rel} is listed but gone - prune the list"
        assert len(reason) > 10, f"{rel} needs a real reason, not '{reason}'"
    assert not set(OUT_OF_SCOPE_REASON) & set(IN_SCOPE), \
        "a surface cannot be both in and out of scope"
