"""Tests for the Cheshire Cat face grids + compositor (console_cat.py)."""

import pytest

from techdeck.ui.widgets.console_cat import (
    EYE_LEFT, EYE_RIGHT, PUPIL, NOSE, FACE_GRID, MOUTH_FRAMES,
    IRIS_COLS, IRIS_ROWS, PHOSPHOR, compose_face, face_html,
)

LEGAL_EYE_CHARS = set(".·ox=+%0")
LEGAL_MOUTH_CHARS = set(".123|")
EYE_H = len(EYE_LEFT)


def test_components_are_rectangular_and_legal():
    for eye in (EYE_LEFT, EYE_RIGHT):
        width = len(eye[0])
        for r, row in enumerate(eye):
            assert len(row) == width, f"eye row {r} is {len(row)} wide"
            assert set(row) <= LEGAL_EYE_CHARS, f"eye row {r} has illegal chars"
    assert len(EYE_LEFT) == len(EYE_RIGHT)
    assert len(EYE_LEFT[0]) == len(EYE_RIGHT[0])
    assert len({len(r) for r in PUPIL}) == 1
    for row in NOSE:
        assert len(row) <= len(FACE_GRID[0])


def test_assembled_face_is_rectangular():
    width = len(FACE_GRID[0])
    for r, row in enumerate(FACE_GRID):
        assert len(row) == width, f"face row {r} is {len(row)} wide"


def test_mouth_region_matches_frames():
    mouth_rows = [r for r, row in enumerate(FACE_GRID) if "M" in row]
    assert mouth_rows == list(range(mouth_rows[0], mouth_rows[-1] + 1))
    widths = {row.count("M") for row in FACE_GRID if "M" in row}
    assert len(widths) == 1
    m_w = widths.pop()
    for i, frame in enumerate(MOUTH_FRAMES):
        assert len(frame) == len(mouth_rows), f"frame {i} row count"
        for j, row in enumerate(frame):
            assert len(row) == m_w, f"frame {i} row {j} is {len(row)}, want {m_w}"
            assert set(row) <= LEGAL_MOUTH_CHARS


def test_compose_matches_grid_dimensions():
    cells = compose_face()
    assert len(cells) == len(FACE_GRID)
    assert all(len(row) == len(FACE_GRID[0]) for row in cells)


def test_compose_is_deterministic():
    assert compose_face(iris=(1, 2), mouth=1) == compose_face(iris=(1, 2), mouth=1)


def _pupil_cells(cells):
    """Pupil squiggles live only in the eye rows ('~' below them is the nose)."""
    return {(r, c) for r in range(EYE_H)
            for c, (ch, _) in enumerate(cells[r]) if ch == "~"}


def test_pupil_is_dim_and_inside_the_eyes():
    eye_field = {(r, c) for r in range(EYE_H)
                 for c, ch in enumerate(FACE_GRID[r]) if ch != "."}
    for ix in range(IRIS_COLS):
        for iy in range(IRIS_ROWS):
            cells = compose_face(iris=(ix, iy))
            pupil = _pupil_cells(cells)
            assert pupil, f"no pupil at gaze {(ix, iy)}"
            assert pupil <= eye_field
            for r, c in pupil:
                assert cells[r][c][1] == "dim"


def test_pupil_moves_with_gaze():
    center = _pupil_cells(compose_face(iris=(2, 1)))
    left = _pupil_cells(compose_face(iris=(0, 1)))
    right = _pupil_cells(compose_face(iris=(4, 1)))
    assert min(c for _, c in left) < min(c for _, c in center)
    assert max(c for _, c in right) > max(c for _, c in center)


def test_blink_collapses_to_lids_but_keeps_the_pupil():
    cells = compose_face(blink=True)
    eye_chars = {ch for r in range(EYE_H) for ch, _ in cells[r] if ch != " "}
    assert "—" in eye_chars          # lid lines
    assert "%" not in eye_chars      # the glow field is gone
    assert _pupil_cells(cells)       # the squiggle stays faintly visible


def test_iris_out_of_range_raises():
    with pytest.raises(ValueError):
        compose_face(iris=(5, 0))


def test_mouth_frames_change_the_composed_rows():
    closed = compose_face(mouth=0)
    open_ = compose_face(mouth=2)
    assert closed != open_
    flat_open = "".join(ch for row in open_ for ch, _ in row)
    assert "|" in flat_open  # teeth visible when open


def test_resting_grin_has_teeth():
    flat = "".join(ch for row in compose_face(mouth=0) for ch, _ in row)
    assert "|" in flat  # the signature grin is worn at rest


def test_face_html_emits_tier_colors_and_rows():
    cells = compose_face()
    html = face_html(cells)
    assert html.count("\n") == len(FACE_GRID) - 1
    for color in (PHOSPHOR["dim"], PHOSPHOR["mid"], PHOSPHOR["bright"]):
        assert color in html
