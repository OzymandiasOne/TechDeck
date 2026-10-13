"""Colours that have to stay readable on whatever theme they land on.

Two traps, both found by looking at real renders on 2026-10-13:

* **A fixed status hue can match the surface it is painted on.** "Critical is
  red" must mean the same thing everywhere, so the hues are deliberately not
  palette entries - but amber on halloween's pumpkin card is the same colour
  twice and the chip disappears.
* **Two palette entries can be the same colour.** halloween's ``accent`` and
  ``border`` are both #4A1F7A, so a bar drawn as an accent fill on a bordered
  track was one solid block and every row on the Time tab read as 100% full
  whatever number sat beside it.
"""

import pytest

from techdeck.ui.theme import (
    MIN_READABLE_CONTRAST, THEMES, contrast_ratio, is_light, readable_on,
    subtle_tint,
)

# The fixed hues the Assistant paints on cards.
STATUS_HUES = {
    "critical": "#EF4444",
    "high": "#F59E0B",
    "medium": "#3B82F6",
    "low": "#6B7280",
    "waiting": "#F59E0B",
    "overdue": "#EF4444",
}


# ── the maths ────────────────────────────────────────────────────────────────

def test_contrast_ratio_endpoints():
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0, abs=0.1)
    assert contrast_ratio("#777777", "#777777") == pytest.approx(1.0, abs=0.01)


def test_contrast_ratio_is_order_independent():
    assert contrast_ratio("#123456", "#EEEEEE") == pytest.approx(
        contrast_ratio("#EEEEEE", "#123456"))


def test_a_garbled_colour_never_raises():
    """These feed a stylesheet, and a hand-edited custom theme must not take
    the page down."""
    assert contrast_ratio("not a colour", "#FFFFFF") > 0
    assert readable_on("", "#FFFFFF", "#000000") == "#000000"
    assert subtle_tint("nonsense").startswith("rgba(")


def test_short_hex_is_understood():
    assert contrast_ratio("#000", "#fff") == pytest.approx(21.0, abs=0.1)


# ── readable_on ──────────────────────────────────────────────────────────────

def test_a_hue_that_reads_is_left_alone():
    dark = THEMES["dark"]
    assert readable_on("#F59E0B", dark.surface, "#000000") == "#F59E0B"


def test_a_hue_that_vanishes_falls_back():
    pumpkin = THEMES["halloween"]
    chosen = readable_on("#F59E0B", pumpkin.surface, pumpkin.on_card_secondary)
    assert chosen == pumpkin.on_card_secondary


@pytest.mark.parametrize("theme_name", sorted(THEMES))
@pytest.mark.parametrize("hue", sorted(STATUS_HUES.values()))
def test_every_status_hue_is_readable_on_every_theme_card(theme_name, hue):
    """The guarantee the chips rely on: after readable_on, whatever comes
    back can actually be read on that theme's card."""
    palette = THEMES[theme_name]
    chosen = readable_on(hue, palette.surface, palette.on_card_secondary)
    assert contrast_ratio(chosen, palette.surface) >= MIN_READABLE_CONTRAST - 0.01, (
        f"{theme_name}: {chosen} is unreadable on {palette.surface}")


# ── card tones ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("theme_name", sorted(THEMES))
def test_card_text_reads_on_the_card(theme_name):
    palette = THEMES[theme_name]
    for colour in (palette.on_card, palette.on_card_secondary):
        assert contrast_ratio(colour, palette.surface) >= MIN_READABLE_CONTRAST, (
            f"{theme_name}: {colour} does not read on {palette.surface}")


def test_card_tones_fall_back_for_a_one_tone_theme():
    """A theme that never sets the card overrides keeps the page's colours,
    so adding the slot changed nothing for the themes that were already fine."""
    dark = THEMES["dark"]
    assert dark.on_card == dark.text
    assert dark.on_card_secondary == dark.text_secondary


def test_a_two_tone_theme_uses_its_own_card_colours():
    pumpkin = THEMES["halloween"]
    assert pumpkin.on_card != pumpkin.text
    assert pumpkin.on_card_secondary != pumpkin.text_secondary


# ── subtle_tint ──────────────────────────────────────────────────────────────

def test_the_tint_follows_the_text_not_the_background_luminance():
    """halloween paints DARK text on a mid-luminance orange. A tint picked by
    background luminance alone would go the other way and disappear."""
    pumpkin = THEMES["halloween"]
    assert not is_light(pumpkin.surface)          # the orange reads as dark...
    assert subtle_tint(pumpkin.on_card).startswith("rgba(0, 0, 0")  # ...but


@pytest.mark.parametrize("theme_name", sorted(THEMES))
def test_a_bar_track_never_matches_its_fill(theme_name):
    """The Time tab's bars. A track equal to the fill is a bar that always
    looks full."""
    palette = THEMES[theme_name]
    track = subtle_tint(palette.on_card)
    assert track != palette.accent
    # And it is a translucent tone, so it cannot collide with any solid hue.
    assert track.startswith("rgba(")


def test_the_strength_is_clamped():
    assert "0.04" in subtle_tint("#000000", strength=-5)
    assert "0.60" in subtle_tint("#000000", strength=99)
