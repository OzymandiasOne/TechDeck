"""A popup TechDeck opens ON ITS OWN must wait for the screen to be clear.

2026-10-26: the update offer and the crash-report offer came due in the same
second. Both parent to the main window, so the second one was app-modal but
stacked BEHIND the first: invisible, and swallowing every click meant for the
dialog the user could see. Reported as "the exe is completely frozen" - it was
not, and only Esc got out of it.

Two halves: `when_no_modal` really does queue, and shell.py really does use it.
"""

import re
from pathlib import Path

import pytest

from techdeck.ui.dialog_front import when_no_modal

SHELL = Path(__file__).resolve().parents[2] / "techdeck" / "ui" / "shell.py"


def _pump(qapp, ms=1200):
    from PySide6.QtCore import QDeadlineTimer, QEventLoop
    deadline = QDeadlineTimer(ms)
    while not deadline.hasExpired():
        qapp.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)


def test_runs_immediately_when_screen_is_clear(qapp):
    fired = []
    when_no_modal(lambda: fired.append(1))
    assert fired == [1], "nothing was modal; it should not have waited"


def test_waits_while_a_modal_is_open_then_fires(qapp, destroy_qt):
    from PySide6.QtWidgets import QDialog

    blocker = QDialog()
    blocker.setModal(True)
    blocker.show()
    _pump(qapp, 200)
    assert qapp.activeModalWidget() is not None, "test needs a live modal"

    fired = []
    when_no_modal(lambda: fired.append(1))
    _pump(qapp, 400)
    assert fired == [], "it opened on top of a modal - that is the bug"

    blocker.close()
    _pump(qapp, 1500)
    assert fired == [1], "it never fired after the modal closed"
    destroy_qt(blocker)


def test_drops_the_popup_if_its_owner_is_gone(qapp, destroy_qt):
    """A queued popup must not resurrect itself over a closed window."""
    from PySide6.QtWidgets import QDialog, QWidget

    blocker = QDialog()
    blocker.setModal(True)
    blocker.show()
    _pump(qapp, 200)

    owner = QWidget()
    owner.show()
    _pump(qapp, 100)

    fired = []
    when_no_modal(lambda: fired.append(1), owner=owner)
    owner.hide()
    blocker.close()
    _pump(qapp, 1500)
    assert fired == [], "the owner was gone; the popup should have been dropped"
    destroy_qt(blocker)
    destroy_qt(owner)


# ── the gate: every self-opening popup in the shell goes through the queue ───

SELF_OPENING = {
    # method name in shell.py          -> what the user did to ask for it
    "_show_update_dialog_slot": "nothing - a background update check answered",
    "_maybe_offer_debug_report": "nothing - the last session ended dirty",
}


@pytest.mark.parametrize("method", sorted(SELF_OPENING))
def test_self_opening_popups_are_queued(method):
    src = SHELL.read_text(encoding="utf-8")
    body = re.search(
        rf"\n    def {re.escape(method)}\(.*?(?=\n    def |\nclass |\Z)",
        src, re.S)
    assert body, f"{method} is gone from shell.py - update this gate"
    chunk = body.group(0)
    # Either the method queues itself, or its only caller queues it.
    caller = re.findall(rf"when_no_modal\(\s*self\.{re.escape(method)}\b", src)
    assert "when_no_modal(" in chunk or caller, (
        f"{method} pops up on its own ({SELF_OPENING[method]}) but does not go "
        f"through when_no_modal(). It will stack behind any dialog already "
        f"showing and look like a frozen app. See techdeck/ui/dialog_front.py."
    )
