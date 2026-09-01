"""ConsoleWidget.show_report - the worker-thread -> GUI-thread hop.

A plugin's run() is on a worker thread, and Qt widgets may only be touched on the
GUI thread, so show_report marshals across with a BlockingQueuedConnection the
same way show_warning and request_directory do. If that hop is wrong the report
either never appears or takes the app down, and neither shows up in a unit test
of the dialog on its own - so it is tested here, from a real thread.

The difference from show_warning: this one must NOT keep blocking once the window
is up. The run is finished by the time a report is shown, and holding the worker
would leave the app looking busy for as long as somebody reads.
"""

import threading

from techdeck.ui.widgets.console import ConsoleWidget


def _pump(qapp, predicate, tries=200):
    """Run the GUI event loop until predicate() or we give up."""
    for _ in range(tries):
        if predicate():
            return True
        qapp.processEvents()
    return predicate()


def test_show_report_from_a_worker_thread_opens_the_dialog(qapp, tmp_path):
    console = ConsoleWidget()
    done = threading.Event()
    error = []

    def worker():
        try:
            console.show_report("A Report", "what it is", "BODY\nLINE 2",
                                str(tmp_path / "report.txt"))
        except Exception as exc:            # would otherwise vanish into the thread
            error.append(exc)
        finally:
            done.set()

    t = threading.Thread(target=worker)
    t.start()
    _pump(qapp, done.is_set)
    t.join(timeout=5)

    assert not error, f"show_report raised on the worker thread: {error}"
    assert done.is_set(), "show_report never returned - it is still blocking"

    dlg = console._open_report
    assert dlg is not None, "no report window was opened"
    assert dlg.isVisible()
    dlg.close()


def test_the_console_holds_the_dialog_and_lets_go_on_close(qapp, tmp_path):
    """Qt collects a dialog whose last Python reference drops (Hard Rule 4)."""
    console = ConsoleWidget()
    console.show_report("A Report", "sub", "BODY", str(tmp_path / "r.txt"))

    dlg = console._open_report
    assert dlg is not None

    dlg.accept()
    qapp.processEvents()
    assert console._open_report is None, "the console still pins a closed report"


def test_calling_on_the_gui_thread_works_too(qapp, tmp_path):
    """Straight call, no marshalling - a headless/test caller must not deadlock."""
    console = ConsoleWidget()
    console.show_report("A Report", "sub", "BODY", str(tmp_path / "r.txt"))
    assert console._open_report is not None
    console._open_report.close()
