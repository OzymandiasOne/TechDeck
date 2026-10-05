"""The /seance ritual — the hand-off illusion and the phase machine.

The load-bearing property is the SEAM: the console veil and the free
apparition each paint half the creature, and their union must be pixel-
identical to the whole. If that ever breaks the effect stops reading as
"something climbing out" and starts reading as "something being erased".
"""

from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QImage, QPainter

from techdeck.ui.widgets.console import ConsoleWidget
from techdeck.ui.widgets.seance import (
    GRID_H, GRID_W, SIZE_H, SIZE_W, Apparition, ConsoleVeil, SeanceRitual,
    paint_ghost,
)


def _render(spans):
    img = QImage(SIZE_W, SIZE_H, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    painter = QPainter(img)
    for lo, hi in spans:
        paint_ghost(painter, lo, hi)
    painter.end()
    return img


def test_seam_is_invisible_at_every_split(qapp):
    """Rows [0,k) + rows [k,H) == the whole ghost, for every k."""
    whole = _render([(0, GRID_H)])
    for k in range(GRID_H + 1):
        assert _render([(0, k), (k, GRID_H)]) == whole, f"seam visible at {k}"


def test_the_real_sprite_loads_not_the_fallback(qapp):
    """The art is an editable asset now — a missing/corrupt file falls back
    to a featureless blob, so assert we are actually rendering the ghost."""
    from techdeck.ui.widgets.seance import (
        GHOST_ROWS, GHOST_SPRITE, _FALLBACK, _sprite_path,
    )
    assert _sprite_path().exists(), "assets/sprites/ghost.tdart is missing"
    assert GHOST_ROWS != _FALLBACK["rows"], "fell back to the blank shape"
    assert GRID_W > 0 and GRID_H > 0
    for r, row in enumerate(GHOST_ROWS):
        assert len(row) == GRID_W, f"row {r} is ragged"
    # the palette is the FILE's, so recolouring in Pixel Studio just works
    assert GHOST_SPRITE["palette"], "the sprite should carry its own palette"


def test_sprite_edits_reach_the_render(qapp, tmp_path, monkeypatch):
    """Editing ghost.tdart in Pixel Studio must actually change him."""
    import json
    import techdeck.ui.widgets.seance as seance
    edited = tmp_path / "ghost.tdart"
    edited.write_text(json.dumps({
        "format": "tdart", "version": 1,
        "palette": {"B": "#FF0000"},
        "rows": ["BBBB", "BBBB"],
    }), encoding="utf-8")
    monkeypatch.setattr(seance, "_sprite_path", lambda: edited)
    loaded = seance._load_sprite()
    assert loaded["rows"] == ["BBBB", "BBBB"]
    assert loaded["palette"]["B"] == "#FF0000"


def _ritual(qapp, tmp_console=None):
    console = tmp_console or ConsoleWidget()
    console.resize(700, 320)
    ritual = SeanceRitual(console)          # no host: no shudder, no wash
    return console, ritual


def _pump(ritual, cap=400):
    """Tick until the beat changes (or the ritual ends) — never past it, so
    a boundary is observed exactly where it happens."""
    start = ritual._phase
    for _ in range(cap):
        if ritual._phase != start or not ritual._timer.isActive():
            return
        ritual._tick()
    raise AssertionError(f"stuck in {start!r}")


def test_ritual_walks_every_beat_and_cleans_up(qapp):
    console, ritual = _ritual(qapp)
    # compress the whole ceremony so the test is instant
    ritual.DISTURB_MS = ritual.MANIFEST_MS = 60
    ritual.EMERGE_MS = 60
    ritual.LINGER_MS = ritual.FADE_MS = 60

    ritual.start()
    assert ritual.is_running
    assert ritual._phase == "disturb"

    _pump(ritual)
    assert ritual._phase == "manifest"
    _pump(ritual)
    assert ritual._phase == "emerge"
    assert ritual._app is not None, "the free half must exist by now"

    _pump(ritual)
    assert ritual._phase == "linger"
    assert ritual._veil is None, "the console half is spent once it is out"
    assert ritual._app.rows_to == GRID_H, "the free half owns every row"

    ritual.banish()                       # he leaves when shooed, not on a clock
    assert ritual._phase == "fade"
    _pump(ritual)
    assert not ritual.is_running
    assert ritual._app is None and ritual._veil is None


def _into_emerge(qapp, emerge_ms=900):
    console, ritual = _ritual(qapp)
    ritual.DISTURB_MS = ritual.MANIFEST_MS = 60
    ritual.EMERGE_MS = emerge_ms
    ritual.start()
    _pump(ritual)
    _pump(ritual)                       # disturb -> manifest -> emerge
    assert ritual._phase == "emerge"
    return console, ritual


def test_halves_are_complementary_and_aligned_mid_emerge(qapp):
    console, ritual = _into_emerge(qapp)
    veil, app = ritual._veil, ritual._app
    assert veil is not None and app is not None
    # every row belongs to exactly one half…
    assert app.rows_to == veil.rows_from
    # …and both draw at the same screen point, at the same scale.
    assert app.art_global_pos() == veil.ghost_global_pos()
    ritual.dismiss()


def test_split_tracks_the_surface_line(qapp):
    """THE invariant of the redesign: the row that changes hands is the one
    crossing the console's top edge — not an abstract counter. That is what
    makes the hand-off read as rising THROUGH a surface."""
    import math
    from techdeck.ui.widgets.seance import CELL
    console, ritual = _into_emerge(qapp, emerge_ms=900)
    seen = set()
    for _ in range(60):
        if ritual._phase != "emerge":
            break
        veil, app = ritual._veil, ritual._app
        surface = veil.surface_global_y()
        art_y = app.art_global_pos().y()
        expected = max(0, min(GRID_H, int(math.ceil((surface - art_y) / CELL))))
        assert app.rows_to == expected, "split drifted off the surface line"
        assert veil.rows_from == expected
        seen.add(expected)
        ritual._tick()
    # it really travelled: it began submerged and ended up out
    assert min(seen) == 0 and max(seen) == GRID_H, sorted(seen)
    ritual.dismiss()


def test_the_tear_only_burns_while_it_is_crossing(qapp):
    """No tear before it breaks the surface, none once it is clear."""
    console, ritual = _into_emerge(qapp, emerge_ms=900)
    strengths = []
    for _ in range(60):
        if ritual._phase != "emerge":
            break
        strengths.append((ritual._app.rows_to, ritual.tear_strength))
        ritual._tick()
    for rows, strength in strengths:
        if rows in (0, GRID_H):
            assert strength == 0.0, "the tear must be shut when not crossing"
        else:
            assert strength > 0.0, "it should glow while breaking through"
    ritual.dismiss()


def test_dismiss_is_idempotent(qapp):
    console, ritual = _ritual(qapp)
    ritual.start()
    ritual.dismiss()
    ritual.dismiss()                          # must not raise
    assert not ritual.is_running


def test_veil_never_touches_the_console_document(qapp):
    """The ritual is paint-only: the console's text is not its business."""
    console, ritual = _ritual(qapp)
    console.append_system("a line that must survive the haunting")
    before = console.output.toPlainText()
    ritual.DISTURB_MS = ritual.MANIFEST_MS = 60
    ritual.start()
    _pump(ritual)
    assert console.output.toPlainText() == before
    ritual.dismiss()
    assert console.output.toPlainText() == before


def test_veil_is_click_through_but_he_is_not(qapp):
    """The veil sits over the console and must never eat the user's typing.
    He, on the other hand, has to be grabbable."""
    from PySide6.QtCore import Qt
    console = ConsoleWidget()
    veil = ConsoleVeil(console)
    assert veil.testAttribute(
        Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    apparition = Apparition()
    assert not apparition.testAttribute(
        Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert apparition.testAttribute(
        Qt.WidgetAttribute.WA_TranslucentBackground)


# ── the command ──────────────────────────────────────────────────────────

def _handler(console, tmp_path):
    from techdeck.core.command_handler import CommandHandler
    from techdeck.core.settings import SettingsManager
    return CommandHandler(SettingsManager(settings_dir=tmp_path), console)


def test_seance_needs_the_season(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "0")
    console = ConsoleWidget()
    handler = _handler(console, tmp_path)
    handler.handle_command("/seance")
    # Out of season it is indistinguishable from a typo.
    assert "Unknown command: /seance" in console.output.toPlainText()
    assert handler._seance is None


def test_seance_runs_in_season_without_the_puppet_master(qapp, tmp_path,
                                                         monkeypatch):
    """The ghost is not the cat — his flag must not gate this."""
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "1")
    monkeypatch.setenv("TECHDECK_PUPPET_MASTER", "0")
    console = ConsoleWidget()
    handler = _handler(console, tmp_path)
    handler.handle_command("/seance")
    assert "Unknown command" not in console.output.toPlainText()
    assert handler._seance is not None and handler._seance.is_running
    handler.stop_session_effects()            # what /clear does
    assert handler._seance is None


def test_second_seance_does_not_stack(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "1")
    console = ConsoleWidget()
    handler = _handler(console, tmp_path)
    handler.handle_command("/seance")
    first = handler._seance
    handler.handle_command("/seance")
    assert handler._seance is first, "a second call must not summon a rival"
    handler.stop_session_effects()


def test_he_says_hello_once_he_settles(qapp):
    """The greeting arrives after the climb, rides along while he bobs, and
    never outlives him."""
    console, ritual = _ritual(qapp)
    ritual.DISTURB_MS = ritual.MANIFEST_MS = ritual.EMERGE_MS = 60
    ritual.GREET_AFTER_MS = 60
    ritual.LINGER_MS = 100000            # stay put so we can watch him
    ritual.start()
    _pump(ritual); _pump(ritual); _pump(ritual)
    assert ritual._phase == "linger"
    assert ritual._bubble is None, "not before he has settled"

    for _ in range(6):
        ritual._tick()
    assert ritual._bubble is not None, "he should have said something"
    assert ritual._app.companion is ritual._bubble, (
        "the bubble must travel with him through minimise/restore")

    # it stays glued to him as he bobs
    before = ritual._bubble.pos()
    for _ in range(30):
        ritual._tick()
    assert ritual._bubble.pos() != before

    ritual.dismiss()
    assert ritual._bubble is None


def test_the_greeting_is_dropped_before_he_fades(qapp):
    console, ritual = _ritual(qapp)
    ritual.DISTURB_MS = ritual.MANIFEST_MS = ritual.EMERGE_MS = 60
    ritual.GREET_AFTER_MS = 0
    ritual.FADE_MS = 60
    ritual.start()
    _pump(ritual); _pump(ritual); _pump(ritual)   # into linger
    ritual._tick()
    assert ritual._bubble is not None
    ritual.banish()
    assert ritual._phase == "fade"
    ritual._tick()
    assert ritual._bubble is None, "he stops talking before he stops being"
    ritual.dismiss()


# ── he is a resident, not a cutscene ─────────────────────────────────────

def _to_linger(qapp):
    console, ritual = _ritual(qapp)
    ritual.DISTURB_MS = ritual.MANIFEST_MS = ritual.EMERGE_MS = 60
    ritual.GREET_AFTER_MS = 100000        # keep the bubble out of the way
    ritual.start()
    _pump(ritual); _pump(ritual); _pump(ritual)
    assert ritual._phase == "linger"
    return console, ritual


def test_he_stays_until_shooed(qapp):
    """No timer takes him away — you can keep him as long as you like."""
    console, ritual = _to_linger(qapp)
    for _ in range(400):                  # far past any old linger timeout
        ritual._tick()
    assert ritual._phase == "linger"
    assert ritual._app is not None
    ritual.banish()
    assert ritual._phase == "fade"
    ritual.dismiss()


def test_he_floats_gently_in_place(qapp):
    """Movement is a drift, not a bob: small, and it comes back."""
    console, ritual = _to_linger(qapp)
    anchor = ritual._anchor
    seen = []
    for _ in range(240):
        ritual._tick()
        seen.append(ritual._app.art_global_pos())
    xs = [p.x() - anchor.x() for p in seen]
    ys = [p.y() - anchor.y() for p in seen]
    assert len(set(xs)) > 3 and len(set(ys)) > 3, "he should be moving"
    assert max(abs(v) for v in xs) <= 10, "drift, not a bob"
    assert max(abs(v) for v in ys) <= 9
    assert min(xs) < 0 < max(xs), "he should wander both ways, not sail off"
    ritual.dismiss()


def test_dragging_re_anchors_him_where_he_is_dropped(qapp):
    """Let go and he floats about the NEW spot, not where he was summoned."""
    console, ritual = _to_linger(qapp)
    start_anchor = QPoint(ritual._anchor)
    app = ritual._app

    app.dragging = True                   # as the mouse handlers would
    app.move_art_to(QPoint(start_anchor.x() + 260, start_anchor.y() - 120))
    ritual._tick()
    app.dragging = False
    dropped = QPoint(ritual._anchor)
    assert dropped != start_anchor, "the anchor must follow him"

    for _ in range(60):
        ritual._tick()
    drift = ritual._app.art_global_pos() - dropped
    assert abs(drift.x()) <= 10 and abs(drift.y()) <= 9, (
        "he should be floating about where he was dropped")
    ritual.dismiss()


def test_double_click_shoos_him(qapp):
    console, ritual = _to_linger(qapp)
    assert ritual._app.on_shoo is not None, "the gesture must be wired up"
    ritual._app.on_shoo()
    assert ritual._phase == "fade"
    ritual.dismiss()


def test_the_greeting_stops_being_said(qapp):
    """He says his piece and the bubble goes — it does not hang around for
    as long as he does."""
    console, ritual = _ritual(qapp)
    ritual.DISTURB_MS = ritual.MANIFEST_MS = ritual.EMERGE_MS = 60
    ritual.GREET_AFTER_MS = 0
    ritual.GREET_READ_MS = 120
    ritual.start()
    _pump(ritual); _pump(ritual); _pump(ritual)
    assert ritual._phase == "linger"
    ritual._tick()
    assert ritual._bubble is not None, "he should have greeted us"

    for _ in range(200):                  # past typing + the read window
        ritual._tick()
    assert ritual._bubble is None, "the greeting should have expired"
    assert ritual._phase == "linger", "…but he is still here"
    assert ritual._app is not None
    ritual.dismiss()


def test_he_only_greets_once(qapp):
    """Once said, it stays said — no loop of hellos while he floats."""
    console, ritual = _ritual(qapp)
    ritual.DISTURB_MS = ritual.MANIFEST_MS = ritual.EMERGE_MS = 60
    ritual.GREET_AFTER_MS = 0
    ritual.GREET_READ_MS = 60
    ritual.start()
    _pump(ritual); _pump(ritual); _pump(ritual)
    for _ in range(300):
        ritual._tick()
    assert ritual._bubble is None
    for _ in range(300):
        ritual._tick()
    assert ritual._bubble is None, "he should not start talking again"
    ritual.dismiss()
