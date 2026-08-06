"""Tests for ConsoleCat — the document animator behind both summons."""

from PySide6.QtCore import QPoint

from techdeck.ui.widgets.console import ConsoleWidget
from techdeck.ui.widgets.console_cat import (
    ConsoleCat, TIMELINES, progress_at, timeline_total_ms,
)


def _cat():
    console = ConsoleWidget()
    return console, ConsoleCat(console)


def test_progress_at_endpoints_and_monotonic():
    for tl in TIMELINES.values():
        assert progress_at(tl, 0) == 0.0
        assert progress_at(tl, timeline_total_ms(tl)) == 1.0
        assert progress_at(tl, timeline_total_ms(tl) + 999) == 1.0
        samples = [progress_at(tl, ms)
                   for ms in range(0, timeline_total_ms(tl), 100)]
        assert samples == sorted(samples)


def test_materialize_summon_inserts_block(qapp):
    console, cat = _cat()
    console.append_system("hello")
    before = console.output.document().blockCount()
    cat.summon("materialize")
    cat._timer.stop()          # drive manually instead of wall-clock
    cat.render_at(1.0)
    text = console.output.toPlainText()
    assert "@" in text         # the face field landed in the document
    assert "hello" in text     # existing text untouched
    assert cat.is_present
    assert console.output.document().blockCount() > before


def test_render_is_stable_not_growing(qapp):
    console, cat = _cat()
    cat.summon("materialize")
    cat._timer.stop()
    cat.render_at(1.0)
    count1 = console.output.document().characterCount()
    cat.render_at(0.5)
    cat.render_at(1.0)
    assert console.output.document().characterCount() == count1


def test_matrix_summon_captures_tail_and_face_replaces_it(qapp):
    console, cat = _cat()
    for i in range(20):
        console.append_system(f"line {i}")
    cat.summon("matrix")
    cat._timer.stop()
    # The captured source holds the console's text (progress 0 renders it)…
    flat = "".join(ch for row in cat._source_cells for ch, _ in row)
    assert "line" in flat
    assert "line 19" in console.output.toPlainText()
    # …and by the end the face has fully consumed those lines.
    cat.render_at(1.0)
    assert "line 19" not in console.output.toPlainText()
    assert "@" in console.output.toPlainText()


def test_dismiss_removes_the_cat_and_keeps_the_rest(qapp):
    console, cat = _cat()
    console.append_system("keep me")
    cat.summon("materialize")
    cat._timer.stop()
    cat.render_at(1.0)
    cat.dismiss()
    assert not cat.is_present
    text = console.output.toPlainText()
    assert "@" not in text
    assert "keep me" in text


def test_stop_resets_without_touching_the_document(qapp):
    console, cat = _cat()
    cat.summon("materialize")
    cat._timer.stop()
    cat.stop()
    assert not cat.is_present
    assert not cat._timer.isActive()


def test_blink_renders_lids_and_recovers(qapp):
    console, cat = _cat()
    cat.summon("materialize")
    cat._timer.stop()
    cat.render_at(1.0)
    cat._state = "live"
    cat._blink = True
    cat._render_live()
    assert "—" in console.output.toPlainText()
    cat._blink = False
    cat._render_live()
    assert "—" not in console.output.toPlainText()


def test_gaze_mapping_buckets(qapp):
    console, cat = _cat()
    out = console.output
    top_left = cat._gaze_from_global(out.mapToGlobal(QPoint(1, 1)))
    bottom_right = cat._gaze_from_global(out.mapToGlobal(
        QPoint(out.width() - 2, out.height() - 2)))
    assert top_left == (0, 0)
    assert bottom_right == (4, 2)


def test_set_mouth_rerenders_when_live(qapp):
    console, cat = _cat()
    cat.summon("materialize")
    cat._timer.stop()
    cat.render_at(1.0)
    cat._state = "live"
    cat.set_mouth(2)
    assert "|" in console.output.toPlainText()   # the grin's teeth
    cat.set_mouth(0)
    assert "|" not in console.output.toPlainText()


def test_timer_path_reaches_live(qapp, monkeypatch):
    """End-to-end on the real QTimer machinery, with a compressed timeline."""
    import techdeck.ui.widgets.console_cat as cc
    monkeypatch.setitem(cc.TIMELINES, "materialize", [(1.0, 120)])
    console, cat = _cat()
    cat.summon("materialize")
    from PySide6.QtCore import QDeadlineTimer, QEventLoop
    deadline = QDeadlineTimer(2000)
    while cat._state != "live" and not deadline.hasExpired():
        qapp.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    assert cat._state == "live"
    assert "@" in console.output.toPlainText()
    assert cat._blink_timer.isActive()      # the blink loop is armed
    cat.dismiss()
    assert not cat._filter_installed


def test_double_summon_is_ignored(qapp):
    console, cat = _cat()
    cat.summon("materialize")
    cat._timer.stop()
    cat.render_at(1.0)
    count = console.output.document().characterCount()
    cat.summon("matrix")     # already present — must be a no-op
    assert console.output.document().characterCount() == count
