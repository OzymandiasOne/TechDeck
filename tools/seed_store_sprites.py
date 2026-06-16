"""
Seed initial Woogy's Prizes sprites as .tdart files.
=====================================================

A one-time authoring helper (NOT shipped) that draws the first-pass store
sprites with real geometry and writes them to assets/sprites/*.tdart. Open any
of them in the editor (`python tools/pixel_editor.py assets/sprites/<f>.tdart`)
to repaint and save — these are just starting points.

Run:  python tools/seed_store_sprites.py
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from techdeck.ui import pixel_art

OUT = Path(__file__).resolve().parents[1] / "assets" / "sprites"


# ── tiny pixel toolkit ───────────────────────────────────────────────────────
def blank(w, h):
    return [["." for _ in range(w)] for _ in range(h)]


def put(g, x, y, c):
    if 0 <= y < len(g) and 0 <= x < len(g[0]):
        g[y][x] = c


def fill_ellipse(g, cx, cy, rx, ry, c):
    for y in range(len(g)):
        for x in range(len(g[0])):
            if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0:
                g[y][x] = c


def fill_circle(g, cx, cy, r, c):
    fill_ellipse(g, cx, cy, r, r, c)


def fill_rect(g, x0, y0, x1, y1, c):
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            put(g, x, y, c)


def _in_poly(x, y, pts):
    inside = False
    n = len(pts)
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if ((yi > y) != (yj > y)) and \
                (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def fill_poly(g, pts, c):
    for y in range(len(g)):
        for x in range(len(g[0])):
            if _in_poly(x + 0.5, y + 0.5, pts):
                g[y][x] = c


def star_pts(cx, cy, outer, inner, points=4, rot=-math.pi / 2):
    pts = []
    for i in range(points * 2):
        r = outer if i % 2 == 0 else inner
        a = rot + i * math.pi / points
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def to_tdart(g, palette):
    return {"palette": palette, "rows": ["".join(row) for row in g]}


def outline(g, fill_chars, oc):
    """Trace `oc` into every transparent cell 4-adjacent to a `fill_chars` cell."""
    H, W = len(g), len(g[0])
    adds = []
    for y in range(H):
        for x in range(W):
            if g[y][x] != ".":
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < W and 0 <= ny < H and g[ny][nx] in fill_chars:
                    adds.append((x, y))
                    break
    for x, y in adds:
        g[y][x] = oc


# ── Beyblade (Dragoon) — 4-blade metallic spinner, fixed palette ─────────────
def beyblade():
    N = 43
    c = N // 2
    pal = {
        "k": "#14141c", "b": "#2a5cd8", "B": "#1d3f9c", "r": "#d83030",
        "R": "#9c2020", "s": "#c8ccd4", "d": "#868c98", "g": "#f4c430",
        "o": "#b8860b", "w": "#ffffff",
    }
    g = blank(N, N)
    R = 20
    for y in range(N):
        for x in range(N):
            dx, dy = x - c, y - c
            r = math.hypot(dx, dy)
            if r > R:
                continue
            if r > R - 1.5:
                g[y][x] = "k"            # outer dark rim
                continue
            ang = math.atan2(dy, dx) + 0.10 * r   # swirl
            sect = (ang / (math.pi / 2)) % 1.0     # 4 blades
            if sect < 0.10 or sect > 0.90:
                g[y][x] = "s"            # bright metal blade edge
            elif sect < 0.5:
                g[y][x] = "b" if sect < 0.32 else "B"
            else:
                g[y][x] = "r" if sect < 0.72 else "R"
    # hub
    fill_circle(g, c, c, 8, "k")
    fill_circle(g, c, c, 7, "d")
    fill_circle(g, c, c, 6, "s")
    fill_circle(g, c, c, 4, "o")
    fill_circle(g, c, c, 3, "g")
    put(g, c, c, "k")
    put(g, c - 1, c - 1, "w")
    return to_tdart(g, pal)


# ── Naruto shuriken — 4-point matte-black throwing star, fixed palette ───────
def shuriken():
    N = 43
    c = N // 2
    pal = {
        "k": "#16161c", "d": "#2c2e36", "s": "#9aa0ac", "w": "#d6dae2",
        "o": "#08080c",
    }
    g = blank(N, N)
    fill_poly(g, star_pts(c, c, 20, 6.5), "o")     # outline
    fill_poly(g, star_pts(c, c, 19, 6.0), "s")     # steel edge
    fill_poly(g, star_pts(c, c, 17, 5.0), "k")     # black body
    # subtle facet shading: a darker half
    for y in range(N):
        for x in range(N):
            if g[y][x] == "k" and (x - c) + (y - c) > 2:
                g[y][x] = "d"
    # center hole
    fill_circle(g, c, c, 4.2, "o")
    fill_circle(g, c, c, 3.3, ".")
    # tip highlights
    put(g, c, c - 18, "w")
    put(g, c + 18, c, "w")
    return to_tdart(g, pal)


# ── NES cartridge — STEEL TUBE OP, fixed palette ─────────────────────────────
def cartridge():
    # Authentic NES cartridge: beveled top, chamfered bottom corners, a ridged
    # grip band down the left, and a clean label panel on the right. The label
    # carries a generic NES layout (red header / sky / footer) as a canvas to
    # repaint in the editor.
    W, H = 42, 48
    pal = {
        "k": "#3a3a40",   # outline
        "g": "#bcbfc6",   # body grey (front face)
        "d": "#9aa0a8",   # ridges / mid shade
        "e": "#82868e",   # deepest shade
        "l": "#f2efe6",   # label off-white
        "h": "#d8402e",   # label red header
        "b": "#7fc7e8",   # label sky (placeholder art)
        "t": "#3a3a40",   # label footer text
        "w": "#ffffff",
    }
    g = blank(W, H)
    # outer silhouette: beveled top corners + chamfered bottom corners
    fill_poly(g, [(7, 2), (35, 2), (39, 6), (39, 38), (34, 45),
                  (8, 45), (3, 38), (3, 6)], "k")          # outline
    fill_poly(g, [(7, 3), (35, 3), (38, 7), (38, 38), (33, 44),
                  (9, 44), (4, 38), (4, 7)], "g")          # grey face
    # top lid seam
    fill_rect(g, 5, 9, 37, 9, "d")
    # right-edge shading
    for y in range(8, 38):
        put(g, 37, y, "d")
    # left ridged grip band
    for x in range(7, 18, 2):
        for y in range(12, 40):
            if g[y][x] != ".":
                g[y][x] = "d"
    fill_rect(g, 18, 12, 18, 39, "e")        # band divider
    # label panel (right side)
    lx0, ly0, lx1, ly1 = 20, 7, 36, 35
    fill_rect(g, lx0 - 1, ly0 - 1, lx1 + 1, ly1 + 1, "k")  # border
    fill_rect(g, lx0, ly0, lx1, ly1, "l")
    for rx, ry in [(lx0, ly0), (lx1, ly0), (lx0, ly1), (lx1, ly1)]:
        g[ry][rx] = "g"                       # round the label corners
    fill_rect(g, lx0, ly0, lx1, ly0 + 4, "h")        # red header
    fill_rect(g, lx0, ly0 + 5, lx1, ly1 - 5, "b")    # sky middle (canvas)
    fill_rect(g, lx0, ly1 - 4, lx1, ly1, "l")        # footer
    fill_rect(g, lx0 + 1, ly1 - 2, lx1 - 1, ly1 - 2, "t")  # footer text line
    # bottom-center thumb-notch detail
    fill_poly(g, [(19, 44), (23, 44), (21, 46)], "e")
    return to_tdart(g, pal)


# ── Woogy (UFO50) salesman — fixed palette ───────────────────────────────────
def woogy():
    # Garlic-bulb body (lumpy lobed top + curled sprout), vertical streak
    # texture, wide outlined eyes, brown almond mouth, candy-stripe legs, gold
    # sparkles — matching the WOOGY card. Refine the rest in the editor.
    W, H = 44, 58
    cx = 22
    pal = {
        "k": "#0c160c", "g": "#4a8a3f", "G": "#2f5e2a", "l": "#6fbf5c",
        "w": "#f4f4ec", "p": "#14140e", "m": "#7a5230", "M": "#4a3220",
        "r": "#d23a3a", "i": "#ffffff", "y": "#f4c430",
    }
    g = blank(W, H)

    # ── body: overlapping lobes form a lumpy garlic bulb ──
    fill_ellipse(g, cx, 36, 16, 19, "g")          # main mass
    fill_ellipse(g, cx, 20, 9, 9, "g")            # center top bump
    fill_ellipse(g, cx - 9, 24, 6.5, 8, "g")      # left bump
    fill_ellipse(g, cx + 9, 24, 6.5, 8, "g")      # right bump
    # curled sprout
    for (sx, sy) in [(22, 4), (22, 6), (23, 8), (24, 10), (23, 12),
                     (21, 13), (20, 11), (21, 9)]:
        fill_circle(g, sx, sy, 1.4, "g")

    # ── texture: vertical crevices (dark) + left highlight ──
    for y in range(H):
        for x in range(W):
            if g[y][x] != "g":
                continue
            # crevices between lobes
            if x in (cx - 4, cx + 4) and 12 < y < 30:
                g[y][x] = "G"
            elif (x - cx) % 6 == 0 and y > 30:
                g[y][x] = "G"
            elif (cx - x) > 6 and (y - 30) > (cx - x):
                g[y][x] = "l"           # lower-left sheen

    outline(g, ("g", "G", "l"), "k")    # clean silhouette outline

    # ── eyes (wide, outlined, looking up/out) ──
    for ex, pdx in ((cx - 8, 1), (cx + 8, 1)):
        fill_circle(g, ex, 26, 5.4, "k")
        fill_circle(g, ex, 26, 4.4, "w")
        fill_circle(g, ex + pdx, 24, 2.0, "p")
        put(g, ex + pdx - 1, 23, "i")   # catchlight

    # ── brown almond mouth with white blob ──
    fill_ellipse(g, cx, 42, 12, 4.6, "k")
    fill_ellipse(g, cx, 42, 11, 3.7, "M")
    fill_ellipse(g, cx, 41, 10, 2.8, "m")
    fill_ellipse(g, cx, 41, 4.2, 2.0, "i")

    # ── two candy-stripe legs ──
    for lx0 in (cx - 8, cx + 2):
        for x in range(lx0, lx0 + 6):
            col = "r" if (x - lx0) % 2 == 0 else "w"
            for y in range(50, 56):
                if (x - (lx0 + 2.5)) ** 2 / 9 + (y - 52) ** 2 / 16 <= 1.2:
                    g[y][x] = col
    outline(g, ("r", "w"), "k")

    # ── gold sparkles ──
    for fx, fy in [(8, 18), (35, 20), (10, 44), (34, 42), (cx, 8), (37, 33)]:
        put(g, fx, fy, "y")
    return to_tdart(g, pal)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sprites = {
        "spinner_beyblade.tdart": beyblade(),
        "spinner_shuriken.tdart": shuriken(),
        "cartridge_steeltube.tdart": cartridge(),
        "woogy.tdart": woogy(),
    }
    for name, data in sprites.items():
        pixel_art.save(OUT / name, data)
        w, h = pixel_art.dimensions(data)
        print(f"wrote {name}  ({w}x{h}, {len(data['palette'])} colors)")


if __name__ == "__main__":
    main()
