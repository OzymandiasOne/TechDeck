"""Tests for the Cheshire Cat face art + compositor (console_cat.py)."""

import pytest

from techdeck.ui.widgets.console_cat import (
    FACE_ART, FACE_WIDTH, EYE_BOXES, PUPIL, MOUTH_FRAMES, MOUTH_TOP,
    GRIN_ROW, IRIS_COLS, IRIS_ROWS, PHOSPHOR, CHAR_TIER,
    compose_face, face_html,
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
        assert len(frame) == 3, f"frame {i} row count"
        for j, row in enumerate(frame):
            assert len(row) == FACE_WIDTH, f"frame {i} row {j} width"
    # The resting frame IS the reference's own mouth rows.
    assert MOUTH_FRAMES[0] == FACE_ART[MOUTH_TOP:MOUTH_TOP + 3]
    assert MOUTH_TOP <= GRIN_ROW < MOUTH_TOP + 3


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


def test_face_html_emits_tier_colors_and_rows():
    cells = compose_face()
    html = face_html(cells)
    assert html.count("\n") == len(FACE_ART) - 1
    for color in (PHOSPHOR["dim"], PHOSPHOR["bright"], PHOSPHOR["peak"]):
        assert color in html
