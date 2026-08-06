"""Tests for the Cheshire Cat face grids + compositor (console_cat.py)."""

import pytest

from techdeck.ui.widgets.console_cat import (
    FACE_GRID, MOUTH_FRAMES, IRIS_COLS, IRIS_ROWS, PHOSPHOR,
    compose_face, face_html,
)

LEGAL_GRID_CHARS = set(".123LRM")
LEGAL_MOUTH_CHARS = set(".123|")


def test_face_grid_is_rectangular_and_legal():
    width = len(FACE_GRID[0])
    for r, row in enumerate(FACE_GRID):
        assert len(row) == width, f"row {r} is {len(row)} wide, expected {width}"
        assert set(row) <= LEGAL_GRID_CHARS, f"row {r} has illegal chars"


def test_mouth_region_is_contiguous_and_frames_match_it():
    mouth_rows = [r for r, row in enumerate(FACE_GRID) if "M" in row]
    assert mouth_rows == list(range(mouth_rows[0], mouth_rows[-1] + 1))
    widths = {row.count("M") for r, row in enumerate(FACE_GRID) if "M" in row}
    assert len(widths) == 1, "M region must be the same width on every row"
    m_w = widths.pop()
    for i, frame in enumerate(MOUTH_FRAMES):
        assert len(frame) == len(mouth_rows), f"frame {i} row count"
        for j, row in enumerate(frame):
            assert len(row) == m_w, f"frame {i} row {j} is {len(row)}, want {m_w}"
            assert set(row) <= LEGAL_MOUTH_CHARS


def test_sockets_are_mirrored_in_size():
    left = sum(row.count("L") for row in FACE_GRID)
    right = sum(row.count("R") for row in FACE_GRID)
    assert left == right > 0


def test_compose_matches_grid_dimensions():
    cells = compose_face()
    assert len(cells) == len(FACE_GRID)
    assert all(len(row) == len(FACE_GRID[0]) for row in cells)


def test_compose_is_deterministic():
    a = compose_face(iris=(1, 2), mouth=1)
    b = compose_face(iris=(1, 2), mouth=1)
    assert a == b


def _tier_positions(cells, tier):
    return {(r, c) for r, row in enumerate(cells)
            for c, (_, t) in enumerate(row) if t == tier}


def test_iris_present_only_inside_sockets():
    socket_positions = {(r, c) for r, row in enumerate(FACE_GRID)
                        for c, ch in enumerate(row) if ch in ("L", "R")}
    for ix in range(IRIS_COLS):
        for iy in range(IRIS_ROWS):
            iris = _tier_positions(compose_face(iris=(ix, iy)), "iris")
            assert iris, f"no iris cells at {(ix, iy)}"
            assert iris <= socket_positions


def test_iris_moves_with_gaze():
    center = _tier_positions(compose_face(iris=(2, 1)), "iris")
    left = _tier_positions(compose_face(iris=(0, 1)), "iris")
    right = _tier_positions(compose_face(iris=(4, 1)), "iris")
    assert min(c for _, c in left) < min(c for _, c in center)
    assert max(c for _, c in right) > max(c for _, c in center)


def test_blink_hides_iris_and_draws_lids():
    cells = compose_face(blink=True)
    assert not _tier_positions(cells, "iris")
    flat = "".join(ch for row in cells for ch, _ in row)
    assert "—" in flat  # the lid line char


def test_iris_out_of_range_raises():
    with pytest.raises(ValueError):
        compose_face(iris=(5, 0))


def test_mouth_frames_change_the_composed_rows():
    closed = compose_face(mouth=0)
    open_ = compose_face(mouth=2)
    assert closed != open_
    flat_open = "".join(ch for row in open_ for ch, _ in row)
    assert "|" in flat_open  # teeth visible when open


def test_face_html_emits_tier_colors_and_rows():
    cells = compose_face()
    html = face_html(cells)
    assert html.count("\n") == len(FACE_GRID) - 1
    for color in (PHOSPHOR["mid"], PHOSPHOR["iris"]):
        assert color in html
