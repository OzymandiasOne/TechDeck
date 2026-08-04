"""Tests for the beyblade parts system — three swappable layers the player
mixes. The whole customisation feature rests on these staying SEPARATE, so
these tests mostly guard against something flattening them."""

import json


def test_every_design_ships_all_three_parts(qapp):
    from techdeck.ui import beyblade as BB
    missing = [f"{d}_{k}" for d in BB.DESIGNS for k in BB.KINDS
               if not BB.has_part(d, k)]
    assert missing == [], f"missing part files: {missing}"


def test_parts_declare_two_fold_symmetry(qapp):
    """The spinner engine force-4-folds equipped sprites, which shreds a 180
    degree design. Every part must carry the marker that opts out."""
    from techdeck.ui import beyblade as BB
    for d in BB.DESIGNS:
        for k in BB.KINDS:
            raw = json.loads(BB.part_path(d, k).read_text(encoding="utf-8"))
            assert raw.get("symmetry") == 2, f"{d}_{k} lost its symmetry marker"


def test_symmetry_survives_load_and_save(tmp_path, qapp):
    from techdeck.ui import pixel_art
    src = {"palette": {"k": "#000000"}, "rows": ["k.", ".k"], "symmetry": 2}
    fn = tmp_path / "s.tdart"
    pixel_art.save(fn, src)
    assert pixel_art.load(fn).get("symmetry") == 2


def test_compose_produces_one_sprite(qapp):
    from techdeck.ui import beyblade as BB
    data = BB.compose({"top": "tidewing", "bottom": "tidewing",
                       "center": "tidewing"})
    assert data is not None
    assert len(data["rows"]) == 62
    assert all(len(r) == 62 for r in data["rows"])
    assert data["symmetry"] == 2


def test_mixing_parts_actually_changes_the_result(qapp):
    """The point of the feature: a different part must produce different art."""
    from techdeck.ui import beyblade as BB
    stock = BB.compose({"top": "tidewing", "bottom": "tidewing",
                        "center": "tidewing"})
    mixed = BB.compose({"top": "tidewing", "bottom": "forgeheart",
                        "center": "nightspur"})
    assert stock["rows"] != mixed["rows"]
    # ...and the top is still tidewing's, so only the swapped layers moved
    same = sum(1 for a, b in zip(stock["rows"], mixed["rows"])
               for c, d in zip(a, b) if c == d)
    assert same > 62 * 62 * 0.4


def test_compose_keeps_layer_colours_apart(qapp):
    """Designs reuse the same tone CHARS for different colours — e.g. '4' is a
    warm grey on one bottom and a cold blue-grey on another's top. Merging by
    char alone would repaint one layer with another layer's palette."""
    from techdeck.ui import beyblade as BB
    bottom = BB.load_part("silver_fang", "bottom")
    top = BB.load_part("tidewing", "top")
    clashing = {c for c in set(bottom["palette"]) & set(top["palette"])
                if bottom["palette"][c] != top["palette"][c]}
    assert clashing, "expected these two parts to disagree on a char"

    data = BB.compose({"bottom": "silver_fang", "top": "tidewing",
                       "center": "tidewing"})
    hexes = set(data["palette"].values())
    for ch in clashing:
        assert bottom["palette"][ch] in hexes, "bottom's colour was overwritten"
        assert top["palette"][ch] in hexes, "top's colour was overwritten"


def test_variant_id_round_trips(qapp):
    from techdeck.ui import beyblade as BB
    choice = {"top": "ironclad", "bottom": "verdanox", "center": "nightspur"}
    vid = BB.variant_id(choice)
    assert vid.startswith("beyblade:")
    assert BB.parse_variant(vid) == choice


def test_parse_variant_ignores_non_beyblades(qapp):
    from techdeck.ui import beyblade as BB
    assert BB.parse_variant("spinner_shuriken") is None
    assert BB.parse_variant(None) is None


def test_unknown_design_falls_back_instead_of_blanking(qapp):
    from techdeck.ui import beyblade as BB
    choice = BB.normalize_choice({"top": "does_not_exist", "bottom": "ironclad"})
    assert choice["top"] in BB.DESIGNS
    assert choice["bottom"] == "ironclad"
    assert BB.compose(choice) is not None


def test_spinner_renders_a_beyblade_variant(qapp):
    from techdeck.ui import beyblade as BB
    from techdeck.ui.widgets.fidget_spinner import _render_variant_pixmap
    vid = BB.variant_id({"top": "tidewing", "bottom": "ironclad",
                         "center": "forgeheart"})
    pm = _render_variant_pixmap(vid)
    assert pm is not None and not pm.isNull()


def test_two_fold_art_is_not_force_four_folded(qapp):
    """Regression: enforce_4fold stamps the top arm into all four quadrants.
    Running it on a 180 degree design destroys it."""
    from techdeck.ui import beyblade as BB, pixel_art
    data = BB.compose({"top": "nightspur", "bottom": "nightspur",
                       "center": "nightspur"})
    folded = pixel_art.enforce_4fold_data(data)
    assert folded["rows"] != data["rows"], "these designs are NOT 4-fold"
    # and the shipped parts opt out, so the spinner path leaves them alone
    for d in BB.DESIGNS:
        raw = json.loads(BB.part_path(d, "top").read_text(encoding="utf-8"))
        assert int(raw.get("symmetry", 4)) != 4


def test_catalog_lists_every_design(qapp):
    """Every design is buyable, and every beyblade catalog id resolves to a
    real design — including the original item, which kept its id through the
    rebuild so existing purchases survive."""
    from techdeck.ui import beyblade as BB
    from techdeck.ui.emporium_catalog import CATALOG
    # Layered items are identified by their sprite path, not a separate kind
    # (they are ordinary spinners so the existing UI handles them).
    ids = {i["id"] for i in CATALOG
           if str(i.get("sprite", "")).startswith("beyblade/")}
    assert ids == set(BB.ITEM_DESIGN)
    assert {BB.ITEM_DESIGN[i] for i in ids} == set(BB.DESIGNS)
    assert BB.ITEM_DESIGN["spinner_beyblade"] == "classic"


def test_old_item_ids_still_resolve(qapp):
    """A save from before the rebuild points at "spinner_beyblade"; it must
    still render rather than silently falling back to the default spinner."""
    from techdeck.ui import beyblade as BB
    choice = BB.parse_variant("spinner_beyblade")
    assert choice == {k: "classic" for k in BB.KINDS}
    assert BB.compose(choice) is not None


def test_all_spinner_sprites_are_the_same_size(qapp):
    """Uniform in the shop: a 43px sprite next to a 62px one renders at a
    different tile scale and looks wrong."""
    import json
    from pathlib import Path as _P
    from techdeck.ui import beyblade as BB
    sizes = set()
    for d in BB.DESIGNS:
        for k in BB.KINDS:
            rows = json.loads(BB.part_path(d, k).read_text(encoding="utf-8"))["rows"]
            sizes.add((max(len(r) for r in rows), len(rows)))
    shuriken = _P("assets/sprites/spinner_shuriken.tdart")
    rows = json.loads(shuriken.read_text(encoding="utf-8"))["rows"]
    sizes.add((max(len(r) for r in rows), len(rows)))
    assert sizes == {(62, 62)}, f"mixed sprite sizes: {sizes}"


def test_tile_scale_never_overflows(qapp):
    """Regression: the tile scale rounded UP, so a 62px sprite rendered at
    124px against a 72px budget and burst out of its tile."""
    from techdeck.ui.arcade_chrome import _tile_scale
    for size in (16, 32, 43, 62, 72, 96):
        assert size * _tile_scale(size, size, 72) <= 72 or _tile_scale(size, size, 72) == 1


def test_store_tile_can_render_a_beyblade(qapp):
    """The catalog points at "beyblade/<design>", which is NOT a file — the
    preview has to be composed from the three parts."""
    from techdeck.ui.arcade_chrome import _load_pixmap
    from techdeck.ui.emporium_catalog import CATALOG
    for item in CATALOG:
        if not str(item.get("sprite", "")).startswith("beyblade/"):
            continue
        pm = _load_pixmap(item["sprite"], 72)
        assert pm is not None and not pm.isNull(), f"{item['id']} has no preview"


def test_beyblades_are_spinner_kind(qapp):
    """A beyblade IS a fidget spinner. Giving it its own `kind` meant every
    call site that filters on kind == "spinner" skipped it — so a purchased
    beyblade never showed up in My Stuff."""
    from techdeck.ui.emporium_catalog import CATALOG
    kinds = {i["kind"] for i in CATALOG if str(i.get("sprite", "")).startswith("beyblade/")}
    assert kinds == {"spinner"}


def test_owned_beyblades_reach_my_stuff(qapp):
    """The My Stuff list is built from catalog spinners the player owns."""
    from techdeck.ui.emporium_catalog import CATALOG
    owned = {"bey_tidewing", "spinner_beyblade"}
    listed = [c["id"] for c in CATALOG
              if c["kind"] == "spinner" and c["id"] in owned]
    assert sorted(listed) == sorted(owned)


def test_default_spinner_matches_the_others(qapp):
    """The built-in spinner is theme-coloured, so it is authored in semantic
    slots rather than greys — but it still has to be the same 62x62 size and
    exactly 4-fold, or it spins with a flicker."""
    from techdeck.ui.widgets.fidget_spinner import SPINNER_ART, _ART
    assert len(SPINNER_ART) == 62 and max(len(r) for r in SPINNER_ART) == 62
    n = len(_ART)
    for y in range(n):
        for x in range(n):
            assert _ART[y][x] == _ART[n - 1 - x][y], "default spinner is not 4-fold"
    assert set("".join(_ART)) <= set(".BWRHo"), "unknown slot in SPINNER_ART"


def _edge_hits(win, deg):
    """Opaque pixels landing on the window border once the art is rotated —
    i.e. art the window would cut off."""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtCore import QPointF
    size = win.WINDOW_SIZE
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
    p.translate(size / 2.0, size / 2.0)
    p.rotate(deg)
    p.drawPixmap(QPointF(-win._pixmap.width() / 2.0,
                         -win._pixmap.height() / 2.0), win._pixmap)
    p.end()
    return sum(1 for i in range(size)
               for (x, y) in ((i, 0), (i, size - 1), (0, i), (size - 1, i))
               if img.pixelColor(x, y).alpha() > 0)


def test_spinner_never_clips_while_rotating(qapp):
    """Regression: the window was sized to the art's BOUNDING BOX, but several
    designs paint past the inscribed circle (silver_fang reaches r=34 on a
    62-cell grid whose inscribed radius is 30.5), so those corners swung
    outside the window and were sliced off mid-spin."""
    from techdeck.ui import beyblade as BB
    from techdeck.ui.widgets.fidget_spinner import FidgetSpinnerWindow
    variants = [None, "spinner_shuriken", "spinner_beyblade"] + \
               [f"bey_{d}" for d in BB.DESIGNS if d != "classic"]
    for v in variants:
        win = FidgetSpinnerWindow(variant=v)
        for angle in (0, 22.5, 45, 60):
            assert _edge_hits(win, angle) == 0, f"{v} clips at {angle} deg"


def test_spinner_window_fits_its_art(qapp):
    from techdeck.ui.widgets.fidget_spinner import FidgetSpinnerWindow
    win = FidgetSpinnerWindow(variant="bey_silver_fang")
    assert win.width() == win.height() == win.WINDOW_SIZE
    # sized from the art's reach, so it exceeds the pixmap for a design that
    # paints into the bounding-box corners
    assert win.WINDOW_SIZE > win._pixmap.width()


def test_top_speed_follows_the_art_symmetry(qapp):
    """A sprite with n-fold symmetry looks identical every 360/n degrees, so a
    frame that turns it more than HALF that period reads as going backward.
    The cap must therefore come from the ART: 2-fold designs can safely spin
    twice as fast as the 4-fold built-in one."""
    import math
    from techdeck.ui.widgets.fidget_spinner import (
        FidgetSpinnerWindow, _variant_symmetry)
    for variant in (None, "spinner_shuriken", "spinner_beyblade",
                    "bey_tidewing", "bey_nightspur"):
        win = FidgetSpinnerWindow(variant=variant)
        fold = _variant_symmetry(variant) if variant else 4
        per_frame = math.degrees(win.MAX_VELOCITY * win.FRAME)
        assert per_frame < 180.0 / fold, (
            f"{variant} would strobe: {per_frame:.1f} deg/frame at {fold}-fold")
    # and the 2-fold art really is allowed to go faster
    slow = FidgetSpinnerWindow(variant="spinner_shuriken").MAX_VELOCITY
    fast = FidgetSpinnerWindow(variant="bey_tidewing").MAX_VELOCITY
    assert fast > slow * 1.9


def test_a_few_clicks_reach_top_speed(qapp):
    """A fixed impulse needed ~30 clicks once the cap doubled."""
    from techdeck.ui.widgets.fidget_spinner import FidgetSpinnerWindow
    for variant in (None, "bey_ironclad"):
        win = FidgetSpinnerWindow(variant=variant)
        assert 4 <= win.MAX_VELOCITY / win.CLICK_IMPULSE <= 8
