"""Tests for the parts mixer — the screen the three-layer split exists for."""


class FakeSettings:
    def __init__(self, owned=(), equipped=None, build=None):
        self._owned, self._eq, self._build = set(owned), equipped, build

    def is_unlocked(self, item_id):
        return item_id in self._owned

    def get_equipped_spinner(self):
        return self._eq

    def set_equipped_spinner(self, v):
        self._eq = v

    def get_beyblade_build(self):
        return self._build

    def set_beyblade_build(self, v):
        self._build = v


def _builder(owned, equipped=None):
    from techdeck.ui.widgets.beyblade_builder import BeybladeBuilder
    s = FakeSettings(owned, equipped)
    return BeybladeBuilder(None, s), s


def test_only_owned_designs_are_offered(qapp):
    d, _ = _builder({"bey_tidewing", "bey_ironclad"})
    assert sorted(d.owned) == ["ironclad", "tidewing"]


def test_cycling_changes_one_layer_only(qapp):
    d, _ = _builder({"spinner_beyblade", "bey_tidewing", "bey_ironclad"})
    before = dict(d.choice)
    d._cycle("top", 1)
    assert d.choice["top"] != before["top"]
    assert d.choice["bottom"] == before["bottom"]
    assert d.choice["center"] == before["center"]


def test_cycling_wraps_around(qapp):
    d, _ = _builder({"bey_tidewing", "bey_ironclad"})
    start = d.choice["top"]
    for _ in range(len(d.owned)):
        d._cycle("top", 1)
    assert d.choice["top"] == start


def test_equip_writes_a_parseable_variant(qapp):
    from techdeck.ui import beyblade as BB
    d, s = _builder({"spinner_beyblade", "bey_tidewing", "bey_forgeheart"})
    d._cycle("top", 1)
    d._cycle("center", 2)
    d._equip()
    assert s.get_equipped_spinner().startswith("beyblade:")
    assert BB.parse_variant(s.get_equipped_spinner()) == d.choice


def test_preview_recomposes_when_a_part_changes(qapp):
    d, _ = _builder({"spinner_beyblade", "bey_tidewing", "bey_nightspur"})
    first = d.preview.pixmap().toImage()
    d._cycle("bottom", 1)
    second = d.preview.pixmap().toImage()
    assert first != second


def test_equipped_combo_naming_an_unowned_design_snaps_to_owned(qapp):
    """A save can reference a design the player does not have — the arrows must
    never start on a part they cannot use."""
    from techdeck.ui import beyblade as BB
    equipped = BB.variant_id({"top": "verdanox", "bottom": "verdanox",
                              "center": "verdanox"})
    d, _ = _builder({"bey_tidewing"}, equipped)
    assert set(d.choice.values()) == {"tidewing"}


def test_builder_survives_owning_a_single_design(qapp):
    d, s = _builder({"bey_ironclad"})
    assert d.owned == ["ironclad"]
    d._cycle("top", 1)                    # must not divide by zero or crash
    assert d.choice["top"] == "ironclad"
    d._equip()
    assert s.get_equipped_spinner() == "beyblade:ironclad/ironclad/ironclad"


def test_equip_records_the_build_separately_from_the_equipped_slot(qapp):
    """The My Stuff tile shows what they BUILT, so it must survive equipping
    something else afterwards."""
    d, s = _builder({"spinner_beyblade", "bey_tidewing"})
    d._cycle("top", 1)
    d._equip()
    built = s.get_beyblade_build()
    assert built and built.startswith("beyblade:")

    s.set_equipped_spinner("spinner_classic")     # wear a plain spinner instead
    assert s.get_beyblade_build() == built        # the build is still theirs


# ---- the "Build Your Own" tile icon -----------------------------------------

def _icon_source(settings):
    """Which of the two the tile would draw, without needing a live widget."""
    from techdeck.ui import beyblade as BB
    build = settings.get_beyblade_build()
    if not build:
        eq = settings.get_equipped_spinner()
        if eq and eq.startswith(BB.VARIANT_PREFIX):
            build = eq
    return "build" if build else "silhouette"


def test_tile_shows_a_silhouette_until_something_is_built(qapp):
    # Buying a beyblade auto-equips it under its CATALOG id - that is a
    # purchase, not a build, so the tile must still show the placeholder.
    s = FakeSettings({"spinner_beyblade"}, equipped="spinner_beyblade")
    assert _icon_source(s) == "silhouette"


def test_tile_shows_the_build_once_one_exists(qapp):
    s = FakeSettings({"spinner_beyblade", "bey_tidewing"})
    s.set_beyblade_build("beyblade:tidewing/classic/tidewing")
    assert _icon_source(s) == "build"


def test_a_build_made_before_it_was_recorded_still_shows(qapp):
    """Migration: older saves kept the combo only in the equipped slot."""
    s = FakeSettings({"spinner_beyblade"}, equipped="beyblade:classic/classic/classic")
    assert _icon_source(s) == "build"


def test_silhouette_keeps_the_internal_structure(qapp):
    """A flat one-colour cut-out of a top-down beyblade is an anonymous blob -
    every feature that identifies it is internal, so the shape must survive."""
    from techdeck.ui import beyblade as BB
    from techdeck.ui import pixel_art
    composed = BB.compose(BB.DEFAULT)
    sil = BB.silhouette("#6a6488")
    assert sil is not None

    def opaque(d):
        return sum(1 for r in d["rows"] for ch in r
                   if ch not in pixel_art.TRANSPARENT_CHARS)

    assert opaque(sil) == opaque(composed)        # same silhouette
    assert sil["rows"] == composed["rows"]        # same internal structure
    assert len(set(sil["palette"].values())) > 1  # ...and it is not one flat blob
    assert sil["symmetry"] == composed["symmetry"]


def test_build_tile_only_shows_once_parts_are_owned(qapp):
    from techdeck.ui import beyblade as BB
    for owned, expected in (({}, False), ({"bg_starry_night"}, False),
                            ({"spinner_beyblade"}, True), ({"bey_nightspur"}, True)):
        can = any(FakeSettings(owned).is_unlocked(i) for i in BB.ITEM_DESIGN)
        assert can is expected, f"{owned} -> {can}"
