"""
Generate the reworked Woogy's Emporium arcade cabinet sprite.
=============================================================

Builds a higher-fidelity upright arcade cabinet (gold side rails, blue marquee
with "ARCADE", a gold-framed screen, an angled control deck with two ball-top
joysticks + two buttons, and a silver coin door) drawn entirely in the store's
EMP palette. The screen interior is left dark and is animated by EmporiumPage at
runtime.

Writes assets/sprites/arcade_cabinet.tdart and (with --preview) a scaled PNG so
the geometry can be eyeballed.

Run:  python tools/generate_arcade_cabinet.py [--preview]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from techdeck.ui import pixel_art
from tools.seed_store_sprites import (
    blank, put, fill_rect, fill_circle, fill_poly, outline, to_tdart,
)

OUT = Path(__file__).resolve().parents[1] / "assets" / "sprites"

W, H = 48, 76

# Cabinet metrics (cells). Kept in sync with EmporiumPage._draw_cabinet.
BODY_L, BODY_R = 6, 41            # outer body edge cols (outline lives here)
INT_L, INT_R = 10, 37            # red interior cols
SCREEN_L, SCREEN_R = 13, 34      # animated screen interior cols
SCREEN_T, SCREEN_B = 21, 40      # animated screen interior rows
MARQUEE_L, MARQUEE_R = 4, 43     # marquee box cols
MARQUEE_BULB_ROW = 3             # row the page paints chase bulbs on

PAL = {
    "k": "#120f2a",   # outline / black
    "r": "#c42a34",   # body red (EMP buy)
    "d": "#7a1a22",   # body red, deep shade
    "o": "#e8841f",   # orange trim / ARCADE text (EMP buy_edge family)
    "y": "#f4c430",   # gold rail (EMP ticket)
    "Y": "#b8911f",   # gold, dark
    "b": "#243bb0",   # marquee blue
    "B": "#3f56e0",   # marquee blue, light
    "c": "#37c9da",   # cyan accent (EMP frame_a)
    "m": "#cf3597",   # magenta accent (EMP frame_b)
    "p": "#5a4f80",   # control deck, purple-grey
    "P": "#39335c",   # control deck, dark face
    "g": "#c8c8d8",   # silver (coin door)
    "G": "#8a8aa0",   # silver, dark
    "s": "#0a0a18",   # screen (animated overlay paints here)
    "w": "#f0f0ff",   # white highlight
}

# 3x5 micro-font for the marquee word.
FONT = {
    "A": ["###", "#.#", "###", "#.#", "#.#"],
    "R": ["###", "#.#", "##.", "#.#", "#.#"],
    "C": ["###", "#..", "#..", "#..", "###"],
    "D": ["##.", "#.#", "#.#", "#.#", "##."],
    "E": ["###", "#..", "##.", "#..", "###"],
}


def text(g, x0, y0, word, c):
    """Blit `word` in the 3x5 micro-font, 1px letter spacing."""
    cx = x0
    for ch in word:
        glyph = FONT[ch]
        for dy, row in enumerate(glyph):
            for dx, cell in enumerate(row):
                if cell == "#":
                    put(g, cx + dx, y0 + dy, c)
        cx += 4


def build():
    g = blank(W, H)

    # ── body shell (full height, gold rails down both sides) ──────────────────
    fill_rect(g, BODY_L, 15, BODY_R, 74, "r")          # red body field
    fill_rect(g, 7, 15, 8, 74, "y")                    # left gold rail
    fill_rect(g, 39, 15, 40, 74, "y")                  # right gold rail
    fill_rect(g, 9, 15, 9, 74, "Y")                    # rail inner shade L
    fill_rect(g, 38, 15, 38, 74, "Y")                  # rail inner shade R
    # deep-shade band down the right interior for volume
    fill_rect(g, 34, 16, 37, 73, "d")

    # ── marquee (overhangs the body; page paints chase bulbs on top) ──────────
    fill_rect(g, MARQUEE_L, 2, MARQUEE_R, 13, "y")     # gold marquee frame
    fill_rect(g, MARQUEE_L + 1, 3, MARQUEE_R - 1, 12, "Y")
    fill_rect(g, MARQUEE_L + 2, 4, MARQUEE_R - 2, 11, "b")   # blue field
    fill_rect(g, MARQUEE_L + 2, 4, MARQUEE_R - 2, 4, "B")    # top sheen
    text(g, 13, 6, "ARCADE", "o")                      # 6 letters, centered

    # ── screen: gold bezel with a magenta/cyan inner line, dark animated face ─
    fill_rect(g, INT_L, 19, INT_R, 42, "y")            # gold bezel
    fill_rect(g, INT_L + 1, 20, INT_R - 1, 41, "Y")    # bezel shade
    fill_rect(g, SCREEN_L - 1, SCREEN_T - 1, SCREEN_R + 1, SCREEN_B + 1, "k")
    fill_rect(g, SCREEN_L, SCREEN_T, SCREEN_R, SCREEN_B, "s")   # animated area
    # thin red gap line just under the screen bezel
    fill_rect(g, INT_L, 43, INT_R, 45, "r")
    fill_rect(g, INT_L, 18, INT_R, 18, "c")            # cyan accent over screen

    # ── control deck (slight overhang, two joysticks + two buttons) ───────────
    fill_poly(g, [(8, 46), (39, 46), (40, 56), (7, 56)], "p")
    fill_rect(g, 8, 46, 39, 46, "y")                   # gold lip
    fill_rect(g, 7, 53, 40, 56, "P")                   # dark angled face
    # joysticks (outer): black base ring, shaft, red ball
    for jx in (14, 33):
        fill_circle(g, jx, 51, 2.4, "k")               # base
        fill_rect(g, jx, 48, jx, 51, "k")              # shaft
        fill_circle(g, jx, 48, 1.8, "r")               # ball
        put(g, jx - 1, 47, "w")                        # ball highlight
    # buttons (inner): black socket, red top, white glint
    for bx in (20, 28):
        fill_circle(g, bx, 50, 2.6, "k")
        fill_circle(g, bx, 50, 1.9, "r")
        put(g, bx - 1, 49, "w")

    # ── lower body: silver coin door (left-of-centre) on the red front ────────
    fill_rect(g, 13, 61, 25, 70, "k")                  # door outline
    fill_rect(g, 14, 62, 24, 69, "g")                  # silver face
    fill_rect(g, 14, 67, 24, 69, "G")                  # lower shade
    fill_rect(g, 16, 64, 19, 65, "G")                  # coin slot
    fill_circle(g, 22, 65, 1.4, "r")                   # red coin-return button
    # a couple of sparse highlight scuffs on the red (top-left lit)
    for sx, sy in [(12, 50), (30, 58), (16, 72), (33, 67)]:
        put(g, sx, sy, "d")

    # ── base / feet ───────────────────────────────────────────────────────────
    fill_rect(g, BODY_L, 73, BODY_R, 74, "Y")          # gold kick plate
    fill_rect(g, BODY_L, 75, BODY_R, 75, "k")

    # crisp black silhouette + internal-edge outline
    outline(g, ("r", "d", "y", "Y", "b", "B", "c", "m", "p", "P",
                "g", "G", "s", "o", "w"), "k")
    return to_tdart(g, PAL)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data = build()
    dest = OUT / "arcade_cabinet.tdart"
    pixel_art.save(dest, data)
    w, h = pixel_art.dimensions(data)
    print(f"wrote {dest.name}  ({w}x{h}, {len(data['palette'])} colors)")

    if "--preview" in sys.argv:
        from PySide6.QtGui import QGuiApplication
        _ = QGuiApplication.instance() or QGuiApplication(sys.argv)
        pix = pixel_art.render(data, scale=8)
        png = OUT.parent / "arcade_cabinet_preview.png"
        pix.save(str(png))
        print(f"preview -> {png}")


if __name__ == "__main__":
    main()
