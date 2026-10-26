"""Put a dialog in FRONT of whatever the user is actually looking at.

A run prompts while the user is in Excel or Teams. TechDeck is then a background
process, and Windows does not let a background process take the foreground - so
`raise_()` and `activateWindow()` can both be refused and the dialog opens
BEHIND the other app, with nothing but a taskbar flash to say so. A run sits
waiting and the user never knows.

`WindowStaysOnTopHint` is what actually works: a topmost window renders above
every non-topmost window of every other app, and it needs no focus to do it. The
pattern is already proven here - `widgets/chopper_picker.py` has used it since
the Sentry Drone kill-cam shipped.

Two rules this file exists to enforce:

  * The flag goes on BEFORE the first show. Changing window flags on a visible
    widget hides it in Qt, and the re-show flickers (or, with a modal already
    exec()ing, never comes back).
  * The native file dialogs are the exception and cannot use this. See
    `front_parent_for_native_dialog`.
  * A popup TechDeck opens ON ITS OWN waits for the screen to be clear. See
    `when_no_modal`.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QWidget

logger = logging.getLogger(__name__)


def bring_to_front(widget: QWidget) -> QWidget:
    """Make `widget` topmost, raise it, and flash the taskbar. Returns it, so it
    can wrap a constructor inline: ``bring_to_front(MyDialog(parent)).exec()``.

    Call it BEFORE the first show. Never raises - a dialog that cannot be lifted
    must still open, because the thing it has to say matters more than where it
    sits.
    """
    try:
        widget.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    except Exception as exc:                                  # pragma: no cover
        logger.warning("could not set WindowStaysOnTopHint: %s", exc)
    try:
        widget.raise_()
        widget.activateWindow()
        # A topmost window is already visible; alert() is for the taskbar, so the
        # user notices TechDeck wants them even when the dialog is on a screen
        # they are not looking at.
        alert = getattr(QApplication.instance(), "alert", None)
        if callable(alert):
            alert(widget)
    except Exception as exc:                                  # pragma: no cover
        logger.warning("could not raise the dialog: %s", exc)
    return widget


def message_box(parent, icon, title: str, text: str,
                buttons=QMessageBox.StandardButton.Ok,
                default=None) -> int:
    """A QMessageBox that comes up in front, and the answer the user gave.

    The static helpers (`QMessageBox.warning(...)` and friends) build and show in
    one call, so there is no moment to set a window flag - which is why every one
    of them becomes an instance. Same arguments, same return value.
    """
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(str(title))
    box.setText(str(text))
    box.setStandardButtons(buttons)
    if default is not None:
        box.setDefaultButton(default)
    bring_to_front(box)
    return box.exec()


def exec_in_front(dialog: QDialog) -> int:
    """`dialog.exec()`, in front. For a dialog built elsewhere."""
    bring_to_front(dialog)
    return dialog.exec()


def front_parent_for_native_dialog(parent: QWidget | None) -> None:
    """Lift `parent` just before a NATIVE file dialog opens.

    `QFileDialog.getExistingDirectory` / `getOpenFileName` hand the job to the
    Windows picker, which is not a Qt window and cannot be given Qt window flags.
    What it does honour is its owner: a picker opens in front of the window that
    owns it, so lifting that window first is the best available handle on it.

    The alternative is `DontUseNativeDialog`, which makes the picker a Qt widget
    this module can lift properly - the Sentry Drone path already does that. It
    is NOT the default here because it trades the familiar Windows picker, with
    its Quick Access and OneDrive shortcuts, for Qt's own.
    """
    if parent is None:
        return
    try:
        parent.raise_()
        parent.activateWindow()
        alert = getattr(QApplication.instance(), "alert", None)
        if callable(alert):
            alert(parent)
    except Exception as exc:                                  # pragma: no cover
        logger.warning("could not lift the native dialog's owner: %s", exc)


def when_no_modal(callback, owner: QWidget | None = None,
                  retry_ms: int = 750) -> None:
    """Run `callback` once nothing modal is on screen.

    Anything TechDeck pops up ON ITS OWN - the update offer, the crash-report
    offer - must go through here. Two of them can come due in the same second
    (the update check answers on a 3s timer, the crash-report offer fires on a
    4s one). Both parent to the main window, so the newcomer is app-modal but
    Windows stacks it BEHIND the dialog already showing: invisible, and eating
    every click meant for the dialog the user CAN see. The app looks frozen and
    is not - Esc is the only way out, and only if you know it is there.

    Cost: 2026-10-26, an "exe is completely frozen" report that was two popups
    deep. `bring_to_front` cannot help: both dialogs are topmost, so the one
    that got there first still wins the stack.

    NOT for a dialog the user just asked for by clicking something. That one is
    a reply and belongs on top immediately.
    """
    from PySide6.QtCore import QTimer

    def _attempt() -> None:
        app = QApplication.instance()
        if app is None:               # shutting down - drop it
            return
        if owner is not None:
            try:
                if not owner.isVisible():
                    return            # window gone/hidden: nothing to open over
            except RuntimeError:
                return                # underlying C++ object already deleted
        if app.activeModalWidget() is not None:
            QTimer.singleShot(retry_ms, _attempt)
            return
        callback()

    _attempt()
