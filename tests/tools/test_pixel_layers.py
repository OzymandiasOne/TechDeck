"""Tests for the pixel_editor layer stack — multi-part sprites edited
overlapping on one canvas while each part stays its own file.

Canvas is a QWidget, so these need the qapp fixture. Model ops only, no
painting."""


def _c(w=4, h=4):
    from tools.pixel_editor import Canvas
    return Canvas(w, h)


def test_starts_with_one_layer(qapp):
    c = _c()
    assert len(c.layers) == 1
    assert c.active == 0
    assert c.rows is c.layer.rows


def test_rows_and_palette_follow_the_active_layer(qapp):
    c = _c()
    c.rows[0][0] = "k"
    c.add_layer("second")
    assert c.active == 1
    assert c.rows[0][0] == "."          # the new layer is empty
    c.rows[0][1] = "w"
    c.set_active(0)
    assert c.rows[0][0] == "k" and c.rows[0][1] == "."


def test_undo_history_is_per_layer(qapp):
    c = _c()
    c.rows[0][0] = "k"
    c.push_undo()
    c.rows[0][0] = "w"
    c.add_layer("second")
    assert c._undo == []                # fresh layer, fresh history
    c.set_active(0)
    assert len(c._undo) == 1
    c.undo()
    assert c.rows[0][0] == "k"


def test_composite_draws_bottom_to_top(qapp):
    c = _c()
    c.rows[0][0] = "k"
    c.rows[0][1] = "k"
    c.add_layer("top")
    c.rows[0][0] = "w"                  # covers the lower cell
    comp = c.composite_rows()
    assert comp[0][0] == "w"            # upper layer wins
    assert comp[0][1] == "k"            # lower shows where upper is clear


def test_hidden_layers_are_excluded(qapp):
    c = _c()
    c.rows[0][0] = "k"
    c.add_layer("top")
    c.rows[0][0] = "w"
    c.layers[1].visible = False
    assert c.composite_rows()[0][0] == "k"


def test_opacity_never_changes_saved_data(qapp):
    c = _c()
    c.rows[0][0] = "k"
    before = c.layer.data()
    c.layer.opacity = 0.25
    assert c.layer.data() == before


def test_export_remaps_colliding_chars(qapp):
    """Two layers may use the same char for DIFFERENT colours. Flattening must
    remap rather than silently recolour."""
    c = _c()
    c.palette["k"] = "#111111"
    c.rows[0][0] = "k"
    c.add_layer("top", palette={"k": "#ff0000"})
    c.rows[1][1] = "k"
    data = c.export()
    hexes = {data["palette"][data["rows"][0][0]],
             data["palette"][data["rows"][1][1]]}
    assert hexes == {"#111111", "#ff0000"}


def test_export_folds_identical_hexes_onto_one_char(qapp):
    c = _c()
    c.palette["k"] = "#123456"
    c.rows[0][0] = "k"
    c.add_layer("top", palette={"q": "#123456"})
    c.rows[1][1] = "q"
    data = c.export()
    assert len(data["palette"]) == 1
    assert data["rows"][0][0] == data["rows"][1][1]


def test_load_as_layer_pads_never_rescales(qapp):
    c = _c(4, 4)
    c.rows[0][0] = "k"
    c.load_as_layer({"palette": {"w": "#ffffff"},
                     "rows": ["w" * 6] * 6}, "big")
    assert c.grid_size() == (6, 6)
    assert c.layers[0].rows[0][0] == "k"     # original art unmoved
    assert len(c.layers[0].rows) == 6        # padded, not scaled


def test_resize_keeps_layers_aligned(qapp):
    c = _c(4, 4)
    c.rows[1][1] = "k"
    c.add_layer("top")
    c.rows[1][1] = "w"
    c.pad_grid(2, 0, 2, 0)
    assert c.grid_size() == (6, 6)
    assert all(len(lay.rows) == 6 and len(lay.rows[0]) == 6 for lay in c.layers)
    assert c.layers[0].rows[3][3] == "k"
    assert c.layers[1].rows[3][3] == "w"


def test_move_layer_reorders_and_tracks_active(qapp):
    c = _c()
    c.add_layer("second")
    c.add_layer("third")
    assert [lay.name for lay in c.layers] == ["Layer 1", "second", "third"]
    assert c.active == 2
    c.move_layer(2, -1)
    assert [lay.name for lay in c.layers] == ["Layer 1", "third", "second"]
    assert c.layers[c.active].name == "third"


def test_last_layer_cannot_be_removed(qapp):
    c = _c()
    assert c.remove_layer(0) is False
    assert len(c.layers) == 1


def test_load_replaces_the_whole_stack(qapp):
    c = _c()
    c.add_layer("second")
    c.load({"palette": {"k": "#000000"}, "rows": ["k."]}, name="only")
    assert len(c.layers) == 1
    assert c.layer.name == "only"
