"""Tests for the pixel_editor Canvas model (the shared engine both the
standalone editor and the Pixel Studio reuse). Widget model ops only — no
painting — but Canvas is a QWidget, so these need the qapp fixture."""


def test_export_load_roundtrip(qapp):
    from tools.pixel_editor import Canvas
    c = Canvas(4, 4)
    c.rows[0][0] = "k"
    c.rows[1][2] = "w"
    data = c.export()
    assert data["rows"][0] == "k..."
    c2 = Canvas()
    c2.load(data)
    assert c2.export() == data


def test_pad_and_crop_are_inverse(qapp):
    from tools.pixel_editor import Canvas
    c = Canvas(4, 4)
    c.pad_grid(1, 0, 2, 0)          # +1 row top, +2 cols left
    assert c.grid_size() == (6, 5)
    assert c.crop_grid(1, 0, 2, 0) is True
    assert c.grid_size() == (4, 4)


def test_crop_refuses_to_empty_canvas(qapp):
    from tools.pixel_editor import Canvas
    c = Canvas(4, 4)
    assert c.crop_grid(10, 10, 10, 10) is False
    assert c.grid_size() == (4, 4)


def test_reduce_duplicate_lines_descales(qapp):
    from tools.pixel_editor import Canvas
    c = Canvas(4, 4)
    # Paint a 2x2-block "checker" so every art pixel is a 2x2 run.
    for y in range(4):
        for x in range(4):
            c.rows[y][x] = "k" if (x // 2 + y // 2) % 2 == 0 else "w"
    (ow, oh), (nw, nh) = c.reduce_duplicate_lines()
    assert (ow, oh) == (4, 4)
    assert (nw, nh) == (2, 2)


def test_flood_fill_fills_region(qapp):
    from tools.pixel_editor import Canvas
    c = Canvas(3, 3)
    c.active_char = "k"
    c._flood((1, 1))
    assert all(c.rows[y][x] == "k" for y in range(3) for x in range(3))


def test_undo_redo(qapp):
    from tools.pixel_editor import Canvas
    c = Canvas(2, 2)
    c.push_undo()
    c.rows[0][0] = "k"
    c.undo()
    assert c.rows[0][0] == "."
    c.redo()
    assert c.rows[0][0] == "k"


def test_transform_canvas_flips_and_rotates(qapp):
    from tools.pixel_editor import Canvas
    c = Canvas(3, 2)
    c.rows = [list("kw."), list("...")]
    c.transform("flip_h")
    assert ["".join(r) for r in c.rows] == [".wk", "..."]
    c.undo()
    c.transform("flip_v")
    assert ["".join(r) for r in c.rows] == ["...", "kw."]
    c.undo()
    c.transform("rot_cw")          # 3x2 -> 2x3
    assert ["".join(r) for r in c.rows] == [".k", ".w", ".."]
    c.transform("rot_ccw")         # inverse restores the original
    assert ["".join(r) for r in c.rows] == ["kw.", "..."]


def test_transform_noop_pushes_no_undo(qapp):
    from tools.pixel_editor import Canvas
    c = Canvas(2, 2)
    c.rows = [list("kk"), list("kk")]    # symmetric every way
    c.transform("flip_h")
    c.transform("rot_cw")
    assert c._undo == []


def test_transform_selection_only(qapp):
    from tools.pixel_editor import Canvas
    c = Canvas(4, 4)
    c.rows[0][0] = "k"                   # inside the selection
    c.rows[3][3] = "w"                   # outside — must not move
    c.tool = "select"
    c.selection = {(x, y) for x in range(2) for y in range(2)}
    c.transform("flip_h")
    assert c.rows[0][1] == "k" and c.rows[0][0] == "."
    assert c.rows[3][3] == "w"
    assert c.selection == {(x, y) for x in range(2) for y in range(2)}
    c.transform("rot_cw")                # 2x2 CW: top-right -> bottom-right
    assert c.rows[1][1] == "k"
    c.undo()
    assert c.rows[0][1] == "k"


def test_transform_selection_rotation_reanchors_into_grid(qapp):
    from tools.pixel_editor import Canvas
    c = Canvas(4, 4)
    # A 3-wide x 1-tall strip on the bottom row: rotating CW makes it 1x3,
    # which must shift up to stay on the grid instead of clipping.
    for x in range(3):
        c.rows[3][x] = "k"
    c.tool = "select"
    c.selection = {(x, 3) for x in range(3)}
    c.transform("rot_cw")
    assert c.selection == {(0, 1), (0, 2), (0, 3)}
    assert all(c.rows[y][0] == "k" for y in (1, 2, 3))


def test_line_commit_paints_bresenham(qapp):
    from tools.pixel_editor import Canvas, _line_cells
    c = Canvas(8, 8)
    c.tool = "line"
    c.active_char = "k"
    c._commit_stroke(_line_cells((0, 0), (7, 3)))
    painted = {(x, y) for y in range(8) for x in range(8)
               if c.rows[y][x] == "k"}
    assert painted == set(_line_cells((0, 0), (7, 3)))
    c.undo()
    assert all(ch == "." for r in c.rows for ch in r)


def test_line_respects_brush_size(qapp):
    from tools.pixel_editor import Canvas, _line_cells
    c = Canvas(8, 8)
    c.tool = "line"
    c.active_char = "k"
    c.brush_size = 3
    c._commit_stroke(_line_cells((2, 2), (5, 2)))
    # A 3px brush on a horizontal line covers rows 1-3 across cols 1-6.
    assert all(c.rows[y][x] == "k" for y in (1, 2, 3) for x in range(1, 7))


def test_spline_cells_hits_every_point_gap_free(qapp):
    from tools.pixel_editor import _spline_cells
    pts = [(0, 7), (4, 0), (8, 7), (12, 0)]
    cells = _spline_cells(pts)
    for pt in pts:
        assert pt in cells
    for a, b in zip(cells, cells[1:]):     # 8-connected, no gaps
        assert max(abs(a[0] - b[0]), abs(a[1] - b[1])) <= 1
    assert _spline_cells([(3, 3)]) == [(3, 3)]
    assert set(_spline_cells([(0, 0), (3, 3)])) == {(0, 0), (1, 1), (2, 2), (3, 3)}


def test_spline_commit_and_cancel(qapp):
    from tools.pixel_editor import Canvas
    c = Canvas(8, 8)
    c.tool = "spline"
    c.active_char = "k"
    c._spline_pts = [(0, 4), (3, 1), (7, 4)]
    c.commit_spline()
    assert c._spline_pts is None
    assert c.rows[4][0] == "k" and c.rows[1][3] == "k" and c.rows[4][7] == "k"
    c.undo()
    assert all(ch == "." for r in c.rows for ch in r)
    c._spline_pts = [(0, 0), (5, 5)]
    c._clear_stroke()                       # Esc: no paint, no undo entry
    assert c._spline_pts is None and c._undo == []


def test_leaving_stroke_tool_clears_pending_state(qapp):
    from tools.pixel_editor import Canvas
    c = Canvas(8, 8)
    c.tool = "spline"
    c._spline_pts = [(1, 1), (4, 4)]
    c.tool = "pencil"
    assert c._spline_pts is None


def test_add_color_reuses_existing(qapp):
    from tools.pixel_editor import Canvas
    c = Canvas(2, 2)
    existing_hex = c.palette["k"]
    ch = c.add_color(existing_hex)
    assert ch == "k"                       # same color -> same char, no new entry
    before = len(c.palette)
    new = c.add_color("#abcdef")
    assert new not in ("k",) and len(c.palette) == before + 1
