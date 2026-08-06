"""Tests for the Cheshire Cat face art + compositor (console_cat.py)."""

import pytest

from techdeck.ui.widgets.console_cat import (
    FACE_ART, FACE_WIDTH, EYE_BOXES, PUPIL, MOUTH_FRAMES, MOUTH_TOP,
    GRIN_ROW, IRIS_COLS, IRIS_ROWS, PHOSPHOR, CHAR_TIER,
    compose_face, face_html, summon_frame,
)

LEGAL_CHARS = set(" ·~ox=+%@")
EYE_H = EYE_BOXES[0][2] - EYE_BOXES[0][0] + 1


def test_face_art_is_rectangular_and_legal():
    for r, row in enumerate(FACE_ART):
        assert len(row) == FACE_WIDTH, f"row {r} is {len(row)} wide"
        assert set(row) <= LEGAL_CHARS, f"row {r} has illegal chars"


def test_every_glyph_has_a_tier():
    for row in FACE_ART:
        for ch in row:
            if ch != " ":
                assert ch in CHAR_TIER, f"no tier for {ch!r}"
    for frame in MOUTH_FRAMES:
        for row in frame:
            for ch in row:
                if ch != " ":
                    assert ch in CHAR_TIER, f"no tier for {ch!r}"


def test_mouth_frames_are_full_width_bands():
    for i, frame in enumerate(MOUTH_FRAMES):
        assert len(frame) == 4, f"frame {i} row count"
        for j, row in enumerate(frame):
            assert len(row) == FACE_WIDTH, f"frame {i} row {j} width"
    # The resting frame IS the reference's own mouth rows (jaw shut — its
    # last row is the reserved empty bottom row the speaking jaw drops into).
    assert MOUTH_FRAMES[0] == FACE_ART[MOUTH_TOP:MOUTH_TOP + 4]
    assert set(MOUTH_FRAMES[0][3]) == {" "}
    for frame in MOUTH_FRAMES[1:]:
        assert frame[3].strip(), "speaking jaw must drop into the bottom row"
    assert MOUTH_TOP <= GRIN_ROW < MOUTH_TOP + 4


def test_compose_matches_art_dimensions():
    cells = compose_face()
    assert len(cells) == len(FACE_ART)
    assert all(len(row) == FACE_WIDTH for row in cells)


def test_compose_is_deterministic():
    assert compose_face(iris=(1, 2), mouth=1) == compose_face(iris=(1, 2), mouth=1)


def _hole_cells(cells):
    """Pupil = cells inside the eye boxes that compose to the hole (dim dots
    or blanks where the art has field glyphs)."""
    holes = set()
    for er0, ec0, er1, ec1 in EYE_BOXES:
        for r in range(er0, er1 + 1):
            for c in range(ec0, ec1 + 1):
                art = FACE_ART[r][c]
                ch, tier = cells[r][c]
                if art in "%@+=" and (tier in (None, "dim")):
                    holes.add((r, c))
    return holes


def test_pupil_is_a_hole_inside_both_eyes():
    for ix in range(IRIS_COLS):
        for iy in range(IRIS_ROWS):
            holes = _hole_cells(compose_face(iris=(ix, iy)))
            assert holes, f"no pupil hole at gaze {(ix, iy)}"
            in_left = any(c <= EYE_BOXES[0][3] for _, c in holes)
            in_right = any(c >= EYE_BOXES[1][1] for _, c in holes)
            assert in_left and in_right


def test_pupil_moves_with_gaze():
    center = _hole_cells(compose_face(iris=(2, 1)))
    left = _hole_cells(compose_face(iris=(0, 1)))
    right = _hole_cells(compose_face(iris=(4, 1)))
    assert min(c for _, c in left) < min(c for _, c in center)
    assert max(c for _, c in right) > max(c for _, c in center)


def test_blink_collapses_eyes_but_keeps_the_hole():
    cells = compose_face(blink=True)
    eye_rows = range(EYE_H)
    eye_chars = {ch for r in eye_rows for ch, _ in cells[r] if ch != " "}
    assert "—" in eye_chars          # lid lines
    assert "@" not in eye_chars      # the glow field is gone
    assert _hole_cells(cells)        # the pupil hole stays visible
    # The nose and mouth are untouched by a blink.
    assert cells[MOUTH_TOP] == compose_face(blink=False)[MOUTH_TOP]


def test_iris_out_of_range_raises():
    with pytest.raises(ValueError):
        compose_face(iris=(5, 0))


def test_rest_is_reference_and_speech_grins():
    rest = compose_face(mouth=0)
    open_ = compose_face(mouth=2)
    assert rest != open_
    flat_rest = "".join(ch for row in rest for ch, _ in row)
    flat_open = "".join(ch for row in open_ for ch, _ in row)
    assert "|" not in flat_rest      # at rest the cat IS the reference
    assert "|" in flat_open          # teeth only when it speaks


def _present(frame):
    return {(r, c) for r, row in enumerate(frame)
            for c, (ch, _) in enumerate(row) if ch != " "}


def _in_eye(r, c):
    return any(er0 <= r <= er1 and ec0 <= c <= ec1
               for er0, ec0, er1, ec1 in EYE_BOXES)


def test_summon_ends_exactly_on_the_face():
    final = compose_face()
    assert summon_frame(final, 1.0, seed=3) == final


def test_summon_starts_dark():
    final = compose_face()
    frame = summon_frame(final, 0.0, seed=3)
    assert all(ch == " " for row in frame for ch, _ in row)


def test_summon_is_deterministic_per_seed():
    final = compose_face()
    assert summon_frame(final, 0.7, seed=3) == summon_frame(final, 0.7, seed=3)
    # Mid-flower, the materialization order's jitter differs by seed.
    assert summon_frame(final, 0.7, seed=3) != summon_frame(final, 0.7, seed=4)


def test_summon_opens_with_closed_lids():
    final = compose_face()
    frame = summon_frame(final, 0.12, seed=3)
    present = _present(frame)
    assert present, "the lids should have faded in by 12%"
    mid = (EYE_BOXES[0][0] + EYE_BOXES[0][2]) // 2
    for r, c in present:
        assert r == mid and _in_eye(r, c)
        assert frame[r][c][0] == "—"


def test_summon_eyes_open_before_the_lower_face():
    final = compose_face()
    frame = summon_frame(final, 0.36, seed=3)  # mid-stare, post-snap
    present = _present(frame)
    assert sum(1 for p in present if _in_eye(*p)) > 40  # eyes well open
    assert all(_in_eye(*p) for p in present)            # nothing else yet


def test_summon_stare_plays_on_fully_lit_eyes():
    # By the stare beat the eyes must be COMPLETE — every eye cell at its
    # final glyph and tier — so the lower face enters against a settled face.
    final = compose_face()
    frame = summon_frame(final, 0.40, seed=3)
    for er0, ec0, er1, ec1 in EYE_BOXES:
        for r in range(er0, er1 + 1):
            for c in range(ec0, ec1 + 1):
                assert frame[r][c] == final[r][c], (r, c)


def _lower_by_region(frame):
    from techdeck.ui.widgets.console_cat import MOUTH_TOP
    lower = [p for p in _present(frame) if not _in_eye(*p)]
    nose = [p for p in lower if p[0] < MOUTH_TOP]
    mouth = [p for p in lower if p[0] >= MOUTH_TOP]
    return nose, mouth


def test_summon_nose_breaches_first():
    final = compose_face()
    # The nose tip is the lone lower-face point right after the stare…
    nose, mouth = _lower_by_region(summon_frame(final, 0.46, seed=3))
    assert len(nose) == 1
    assert mouth == []
    # …and is well into its bloom before the mouth corners even seed.
    nose, mouth = _lower_by_region(summon_frame(final, 0.53, seed=3))
    assert len(nose) > 3
    assert mouth == []
    nose, mouth = _lower_by_region(summon_frame(final, 0.56, seed=3))
    assert len(mouth) == 2  # the two corner seeds arrive while the nose finishes


def test_summon_presence_is_monotonic_after_the_snap():
    # The one sanctioned disappearance is the lid splitting open (its cells
    # over the pupil hole return to darkness) — from the snap onward the
    # face only ever gains ground on the dark.
    final = compose_face()
    prev = set()
    for p in (0.3, 0.4, 0.55, 0.7, 0.85, 1.0):
        now = _present(summon_frame(final, p, seed=3))
        assert prev <= now, f"cells vanished between steps at {p}"
        prev = now


def test_summon_slits_are_straight_lines():
    # During the hold, each eye's slit is one unbroken run of lid chars —
    # it spans the pupil hole rather than breaking around it.
    final = compose_face()
    frame = summon_frame(final, 0.15, seed=3)
    mid = (EYE_BOXES[0][0] + EYE_BOXES[0][2]) // 2
    for er0, ec0, er1, ec1 in EYE_BOXES:
        cols = [c for c in range(ec0, ec1 + 1) if frame[mid][c][0] != " "]
        assert cols, "slit missing"
        assert cols == list(range(min(cols), max(cols) + 1)), "slit is broken"
        assert all(frame[mid][c][0] == "—" for c in cols)


def test_face_html_emits_tier_colors_and_rows():
    cells = compose_face()
    html = face_html(cells)
    assert html.count("\n") == len(FACE_ART) - 1
    for color in (PHOSPHOR["dim"], PHOSPHOR["bright"], PHOSPHOR["peak"]):
        assert color in html
