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


def test_add_color_reuses_existing(qapp):
    from tools.pixel_editor import Canvas
    c = Canvas(2, 2)
    existing_hex = c.palette["k"]
    ch = c.add_color(existing_hex)
    assert ch == "k"                       # same color -> same char, no new entry
    before = len(c.palette)
    new = c.add_color("#abcdef")
    assert new not in ("k",) and len(c.palette) == before + 1
