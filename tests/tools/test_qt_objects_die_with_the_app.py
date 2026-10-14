"""No test may flush Qt's delete queue app-wide.

**The trap, and it has bitten twice.** A test that makes a Qt object has to
get rid of it while the ``QApplication`` is still alive, because a widget
destroyed at interpreter shutdown - after the application has gone - aborts
the process. The run then reaches ``[100%]`` with every test passing and dies
with an access violation, no failing test and no summary. Only the exit code
(139) says anything at all.

The obvious fix is the wrong one. ``QCoreApplication.sendPostedEvents(None,
DeferredDelete)`` dispatches the queue for EVERY object in the process, so a
suite calling it also runs deletes that other suites queued and are not
finished with. That crashed the full run at ~96% on 2026-10-05, locally and on
CI, after the release was already published.

Both halves were paid for:

- 2026-10-05: the card-game fixtures flushed app-wide. The fix removed it
  there - and left three more sites in ``tests/ui``, because the reported site
  was treated as the bug rather than as one instance of a class.
- 2026-10-13: ``tests/ui/test_assistant_surface_bleed.py`` showed three
  top-level windows and never closed them. ``tests/ui`` passed alone and
  ``tests/void_game`` passed alone; together they aborted at exit.

So the rule: destroy your own objects on the spot with the ``destroy_qt``
fixture (``shiboken6.delete``), never ``deleteLater`` plus a hope, and never
an app-wide flush. ``tests/conftest.py`` carries the session-end net.
"""

from __future__ import annotations

import pathlib
import re



# A flush aimed at one named object is fine - it cannot reach another suite's
# queue. Only the app-wide form (receiver None) is banned.
APP_WIDE_FLUSH = re.compile(r"sendPostedEvents\(\s*None\b")


def _test_files(root):
    """Every test file but this one: the ban is stated here in prose, and a
    gate that fails on its own description of the rule is no use to anybody."""
    me = pathlib.Path(__file__).resolve()
    return sorted(p for p in (root / "tests").rglob("test_*.py")
                  if p.resolve() != me)


def test_no_test_flushes_the_delete_queue_app_wide():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    offenders = []
    for path in _test_files(root):
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            if APP_WIDE_FLUSH.search(line):
                offenders.append(f"{path.relative_to(root)}:{number}")

    assert not offenders, (
        "These tests dispatch Qt's DeferredDelete queue for EVERY object in "
        "the process, which also runs deletes other suites are not finished "
        "with - the crash of 2026-10-05:\n  " + "\n  ".join(offenders)
        + "\n\nDestroy your own objects with the destroy_qt fixture, or aim "
          "the flush at a named object: sendPostedEvents(obj, ...).")


def test_the_conftest_net_is_still_in_place():
    """The session-end sweep is what makes a missed cleanup survivable. If it
    is ever removed, this says so rather than letting the next full run die
    with no failing test."""
    from pathlib import Path

    conftest = (Path(__file__).resolve().parents[2]
                / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert "_nothing_qt_outlives_the_application" in conftest
    assert "topLevelWidgets" in conftest
    assert "def destroy_qt" in conftest


def test_destroy_qt_really_destroys(qapp, destroy_qt):
    """The fixture has to run the C++ destructor, not queue it - a queued
    delete is exactly the thing that does not happen before exit."""
    import shiboken6
    from PySide6.QtWidgets import QWidget

    widget = QWidget()
    widget.show()
    qapp.processEvents()
    assert shiboken6.isValid(widget)

    destroy_qt(widget)
    assert not shiboken6.isValid(widget), (
        "destroy_qt left the object alive, so it will be destroyed at "
        "interpreter shutdown instead - which is the crash.")


def test_destroy_qt_is_safe_to_call_twice(qapp, destroy_qt):
    """Teardown runs on the failure path too, where an object may already be
    gone. It must not turn a real failure into a confusing crash."""
    from PySide6.QtWidgets import QWidget

    widget = QWidget()
    destroy_qt(widget)
    destroy_qt(widget, None)        # already dead, and a None for good measure
