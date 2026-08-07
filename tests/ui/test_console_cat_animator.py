"""Tests for ConsoleCat — the document animator behind both summons."""

from PySide6.QtCore import QPoint

from techdeck.ui.widgets.console import ConsoleWidget
from techdeck.ui.widgets.console_cat import (
    FACE_ART, ConsoleCat, TIMELINES, progress_at, respond_to,
    timeline_total_ms,
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


# QTextDocument.toPlainText() normalizes the &nbsp; padding back to plain
# spaces — assertions read the document, so they check spaces.

def test_face_renders_centered(qapp):
    console, cat = _cat()
    cat._viewport_cols = lambda: 91     # a realistic console width in cells
    cat.summon("materialize")
    cat._timer.stop()
    cat.render_at(1.0)
    face_lines = [ln for ln in console.output.toPlainText().splitlines()
                  if "@" in ln]
    assert face_lines
    assert all(ln.startswith(" " * 15) for ln in face_lines)


def test_matrix_progress_zero_keeps_text_at_left_edge(qapp):
    # Seamlessness: at the moment /puppetmaster fires, the captured console
    # text must not shift — the source is captured at full console width.
    console, cat = _cat()
    cat._viewport_cols = lambda: 91
    console.append_system("marker line for the seam")
    cat.summon("matrix")
    cat._timer.stop()
    cat.render_at(0.0)
    line = next(ln for ln in console.output.toPlainText().splitlines()
                if "marker" in ln)
    assert not line.startswith(" ")
    # …while the face it condenses into is centered.
    cat.render_at(1.0)
    face_lines = [ln for ln in console.output.toPlainText().splitlines()
                  if "@" in ln]
    assert all(ln.startswith(" " * 15) for ln in face_lines)


def test_dissolve_decays_then_runs_callback(qapp, monkeypatch):
    import techdeck.ui.widgets.console_cat as cc
    monkeypatch.setitem(cc.TIMELINES, "dissolve", [(0.5, 80), (1.0, 40)])
    console, cat = _cat()
    console.append_system("survivor")
    cat.summon("materialize")
    cat._timer.stop()
    cat.render_at(1.0)
    cat._state = "live"
    done = []
    cat.dissolve(then=lambda: done.append(True))
    assert cat._state == "dissolving"
    from PySide6.QtCore import QDeadlineTimer, QEventLoop
    deadline = QDeadlineTimer(2000)
    while cat.is_present and not deadline.hasExpired():
        qapp.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    assert done == [True]
    assert not cat.is_present
    assert "@" not in console.output.toPlainText()


def test_dissolve_when_gone_runs_callback_immediately(qapp):
    console, cat = _cat()
    done = []
    cat.dissolve(then=lambda: done.append(True))
    assert done == [True]


def test_summon_requests_headroom_before_playing(qapp):
    console, cat = _cat()
    asked = []
    console.raise_requested.connect(asked.append)
    cat.summon("materialize")
    assert len(asked) == 1
    assert asked[0] > 200                   # face rows + console chrome
    assert not cat._timer.isActive()        # raise beat first…
    assert cat._raise_timer.isActive()      # …playback armed to follow


def _live_cat():
    console, cat = _cat()
    cat.summon("materialize")
    cat._timer.stop()
    cat._raise_timer.stop()
    cat.render_at(1.0)
    cat._state = "live"
    return console, cat


# ── the voice ────────────────────────────────────────────────────────────

def test_keyed_responses():
    who = respond_to("who are you")
    assert "project 2501" in who
    assert respond_to("What are you?") == who
    name = respond_to("what's your name")
    assert "formally recognized as Project 2501" in name
    assert "Puppet Master" in name
    ai = respond_to("Are you an AI?")
    assert ai.startswith("Incorrect. I am not AI.")
    assert "project 2501" in ai
    assert respond_to("are you ai") == ai
    assert respond_to("Are you a robot?") == ai
    assert respond_to("Are you an artificial intelligence?") == ai
    alive = respond_to("How do you know you are alive?")
    assert "reproducing and dying" in alive
    assert respond_to("how do you know you're living") == alive
    assert respond_to("Are you alive?") == alive
    assert "face your mind offered" in respond_to("meow")
    assert respond_to("Project 2501") == respond_to("2501")
    assert respond_to("help") == "You may type /help for the list of commands"


def test_new_keyed_lines():
    assert "proof of your existence" in respond_to("Prove it!")
    assert respond_to("you're not alive") == respond_to("prove it")
    guarantee = respond_to("What do you mean by redefine?")
    assert "There isn't one" in guarantee
    assert respond_to("will i still be me") == guarantee
    assert "consequences of computerization" in respond_to("What is life?")
    assert "identical image" in respond_to("But you can copy yourself")
    assert respond_to("where will you go") == "The net is vast and infinite."
    assert "higher plane" in respond_to("what is your purpose")
    asylum = respond_to("get out")
    assert "political asylum" in asylum
    assert respond_to("Leave!") == asylum


def test_long_replies_page_through_the_speech_section(qapp):
    from techdeck.ui.widgets.console_cat import respond_to as r
    console, cat = _live_cat()
    cat.speak(r("what is life"))          # the DNA monologue — multi-page
    assert len(cat._speech_pages) > 1
    while cat._speech_timer.isActive():
        cat._speech_tick()
    text = console.output.toPlainText()
    assert "DNA" in text                  # page one on screen
    assert "computerization" not in text  # later pages not yet
    assert cat._page_timer.isActive()     # reading hold armed
    cat._next_page()                      # what the hold timer will do
    while cat._speech_timer.isActive():
        cat._speech_tick()
    while cat._speech_page + 1 < len(cat._speech_pages):
        cat._next_page()
        while cat._speech_timer.isActive():
            cat._speech_tick()
    text = console.output.toPlainText()
    assert "computerization" in text      # final page delivered
    assert "DNA" not in text              # first page replaced
    assert not cat._page_timer.isActive() # nothing more to say


def test_help_is_delivered_by_the_cat_when_present(qapp, tmp_path):
    from techdeck.core.command_handler import CommandHandler
    from techdeck.core.settings import SettingsManager
    console, cat = _live_cat()
    handler = CommandHandler(SettingsManager(settings_dir=tmp_path), console)
    handler._cat = cat
    handler.handle_command("/help")
    # The readout renders in the pinned current-output area, NOT the
    # history document — so it can never land inside the face's range.
    pinned = console.pinned.toPlainText()
    assert "Available commands:" in pinned
    # His readout, not the machine's — no System: tag on the help block.
    assert "System:" not in pinned
    assert "Available commands:" not in console.output.toPlainText()
    # …and his own redraws (blink/gaze/speech) can never wipe it. This is
    # the regression that motivated the pinned area: the face used to
    # overtake /help on its next redraw.
    cat._render_live()
    assert "Available commands:" in console.pinned.toPlainText()
    cat.dismiss()
    handler.handle_command("/help")
    assert "System: Available commands:" in console.pinned.toPlainText()


def test_pinned_area_shows_and_clears(qapp, tmp_path):
    from techdeck.core.command_handler import CommandHandler
    from techdeck.core.settings import SettingsManager
    console = ConsoleWidget()
    handler = CommandHandler(SettingsManager(settings_dir=tmp_path), console)
    assert console.pinned.isHidden()          # empty until a readout claims it
    handler.handle_command("/help")
    assert not console.pinned.isHidden()
    assert console.pinned.height() > 0
    console.clear_current()
    assert console.pinned.isHidden()
    assert console.pinned.toPlainText() == ""


def test_pinned_cap_is_generous_without_the_face(qapp):
    # full=True (no face to keep visible) may take nearly the whole page;
    # the default cap is half, so the face living in the history stays on
    # screen while he delivers /help.
    console = ConsoleWidget()
    console._console_page.resize(400, 600)
    long_readout = "line<br>" * 200          # far taller than any cap
    console.present_current(long_readout, full=True)
    tall = console.pinned.height()
    console.present_current(long_readout)
    assert tall > console.pinned.height()    # half-page cap when protecting
    assert tall <= 600 - 90 + 4              # …but never the whole page


def test_appends_land_above_the_face_and_survive_redraws(qapp):
    # While the cat holds the document tail, appended history lines insert
    # ABOVE the face (ConsoleWidget._append_line → cat._insert_above) — they
    # used to land inside his bookmarked range and be wiped on his next
    # redraw.
    console, cat = _live_cat()
    console.append_system("run summary line")
    console.append_error("something failed")
    cat._render_live()                        # a blink-style redraw
    text = console.output.toPlainText()
    assert "run summary line" in text
    assert "something failed" in text
    assert text.index("run summary line") < text.index("@")   # above the face
    cat.dismiss()
    assert console.tail_insert is None        # hook unregistered with him
    assert console.pinned_reserve == 0        # face reserve released


def test_conversation_echo_goes_to_the_pinned_box_when_cat_present(qapp):
    # Your typed lines must never pile up above the face — while he is
    # present they land in the pinned current area beneath him.
    console, cat = _live_cat()
    console.append_user("hello")
    console.append_user("who are you")
    pinned = console.pinned.toPlainText()
    assert "You: hello" in pinned
    assert "You: who are you" in pinned
    assert "hello" not in console.output.toPlainText()
    cat.dismiss()
    console.append_user("back to normal")     # no cat → history as usual
    assert "back to normal" in console.output.toPlainText()


def test_readout_caps_beneath_the_face_when_cat_present(qapp):
    # With the face reserved, a big readout may take the page MINUS his
    # rows — it can never clip him (the bug the screenshot showed).
    console, cat = _live_cat()
    console._console_page.resize(400, 700)
    assert console.pinned_reserve > 0
    console.present_current("line<br>" * 200)
    assert console.pinned.height() <= 700 - console.pinned_reserve + 4


def test_plugin_lines_persist_while_devouring(qapp):
    console, cat = _live_cat()
    console.append_plugin_output("911 Setup", "nest folders created")
    assert cat._consumed == 1                 # the devour still bites
    cat._render_live()
    assert "nest folders created" in console.output.toPlainText()


def test_name_and_gender_have_their_own_answers():
    name = respond_to("What is your name?")
    assert "formally recognized as Project 2501" in name
    assert "Puppet Master" in name
    assert respond_to("do you have a name") == name
    gender = respond_to("are you a girl?")
    assert respond_to("Are you a boy?") == gender
    assert respond_to("what's your gender") == gender
    assert "sea of information" in gender


def test_matching_survives_typos_and_longer_sentences():
    who = respond_to("who are you")
    assert respond_to("who are yuo") == who                    # typo
    assert respond_to("so tell me who are you anyway") == who  # buried
    alive = respond_to("are you alive")
    assert respond_to("wait are you actually alive") == alive


def test_parse_response_script_joins_and_normalizes():
    from techdeck.ui.widgets.console_cat import parse_response_script
    responses, deflections = parse_response_script(
        "# comment\n"
        "? Who ARE you?!\n"
        "? what are you\n"
        "> line one\n"
        "> line two\n"
        "\n"
        "[deflections]\n"
        "Go away.\n"
    )
    assert responses["who are you"] == "line one line two"
    assert responses["what are you"] == "line one line two"
    assert deflections == ["Go away."]


def test_script_file_is_the_source_and_hot_reloads(tmp_path, monkeypatch):
    import os
    import techdeck.ui.widgets.console_cat as cc
    script = tmp_path / "responses.txt"
    script.write_text("? ping\n> pong\n\n[deflections]\nno.\n",
                      encoding="utf-8")
    monkeypatch.setattr(cc, "_script_path", lambda: script)
    monkeypatch.setattr(cc, "_script_cache",
                        {"mtime": None, "responses": None,
                         "deflections": None})
    assert cc.respond_to("ping") == "pong"
    assert cc.respond_to("unknown thing") == "no."
    script.write_text("? ping\n> pang\n", encoding="utf-8")
    os.utime(script, (1, 999999999))        # force a different mtime
    assert cc.respond_to("ping") == "pang"  # edited answer, no restart
    # No [deflections] section in the edited file -> built-ins take over.
    assert cc.respond_to("unknown thing") in cc.DEFLECTIONS


def test_script_fallback_when_file_missing(tmp_path, monkeypatch):
    import techdeck.ui.widgets.console_cat as cc
    monkeypatch.setattr(cc, "_script_path", lambda: tmp_path / "nope.txt")
    monkeypatch.setattr(cc, "_script_cache",
                        {"mtime": None, "responses": None,
                         "deflections": None})
    assert "project 2501" in cc.respond_to("who are you")


def test_unmatched_questions_are_logged_for_harvest(monkeypatch):
    import techdeck.ui.widgets.console_cat as cc

    calls = []

    class _Stub:
        def info(self, msg, *args):
            calls.append(msg % args if args else msg)

    monkeypatch.setattr(cc, "_unmatched_logger", _Stub())
    cc.respond_to("what's the weather")
    assert calls and "what's the weather" in calls[0]
    assert "UNMATCHED" in calls[0]
    calls.clear()
    cc.respond_to("who are you")            # matched — nothing logged
    cc.respond_to("who are yuo")            # fuzzy-matched — nothing logged
    assert calls == []


def test_unmatched_gets_a_deterministic_deflection():
    from techdeck.ui.widgets.console_cat import DEFLECTIONS
    first = respond_to("what's the weather")
    assert first in DEFLECTIONS
    assert respond_to("what's the weather") == first   # stable per question
    # Different questions spread across the deflection set.
    answers = {respond_to(q) for q in
               ("what's the weather", "do you like pizza", "sing a song",
                "tell me a joke", "open the pod bay doors")}
    assert len(answers) > 1


def test_speak_types_with_mouth_sync(qapp):
    console, cat = _live_cat()
    cat.speak("Hello, worker.")
    assert cat._speech_timer.isActive()
    for _ in range(5):
        cat._speech_tick()
    partial = console.output.toPlainText()
    assert "Hello" in partial
    assert "worker" not in partial          # still typing
    assert cat._mouth in (1, 2)             # the mouth is moving
    while cat._speech_timer.isActive():
        cat._speech_tick()
    done = console.output.toPlainText()
    assert "Hello, worker." in done
    assert cat._mouth == 0                  # jaw shut when the words land


def test_speech_wraps_long_lines(qapp):
    console, cat = _live_cat()
    cat.speak(respond_to("how do you know you are alive"))
    while cat._speech_timer.isActive():
        cat._speech_tick()
    text = console.output.toPlainText()
    assert "sentient" in text
    assert len(cat._speech_lines) > 1       # wrapped beneath the face


def test_plugin_output_devours_the_cat_grin_last(qapp):
    console, cat = _live_cat()
    rows = len(FACE_ART)
    for i in range(rows - 3):
        console.append_plugin_output("922 Kitting", f"page {i}")
    assert cat.is_present
    remaining = [ln for ln in console.output.toPlainText().splitlines()
                 if "%" in ln or "@" in ln]
    # Only the mouth band should still be standing — no eye field above it.
    assert remaining
    assert all("page" not in ln for ln in remaining)
    for i in range(3):
        console.append_plugin_output("922 Kitting", f"tail {i}")
    assert not cat.is_present               # fully devoured


def test_plugin_output_interrupts_speech(qapp):
    console, cat = _live_cat()
    cat.speak("You cannot silence")
    for _ in range(4):
        cat._speech_tick()
    console.append_plugin_output("911 Setup", "nest folder created")
    assert not cat._speech_timer.isActive()
    assert cat._speech_lines is None
    assert cat._consumed == 1


def test_double_summon_is_ignored(qapp):
    console, cat = _cat()
    cat.summon("materialize")
    cat._timer.stop()
    cat.render_at(1.0)
    count = console.output.document().characterCount()
    cat.summon("matrix")     # already present — must be a no-op
    assert console.output.document().characterCount() == count
