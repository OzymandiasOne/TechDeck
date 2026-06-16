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
    W, H = 40, 44
    pal = {
        "k": "#2a2a2e", "g": "#b9bcc4", "d": "#7e828c", "l": "#e8e2d0",
        "h": "#d8402e", "b": "#2f6bd0", "s": "#aeb4be", "w": "#ffffff",
        "t": "#1a1a1e", "y": "#f4c430",
    }
    g = blank(W, H)
    # body
    fill_rect(g, 5, 4, 34, 40, "g")
    fill_rect(g, 5, 4, 34, 4, "d")          # top edge
    fill_rect(g, 33, 4, 34, 40, "d")        # right shade
    fill_rect(g, 5, 39, 34, 40, "d")        # bottom shade
    # top ridges (cart grip)
    for x in range(8, 32, 3):
        fill_rect(g, x, 5, x, 8, "d")
    # outline
    for x in range(5, 35):
        put(g, x, 3, "k"); put(g, x, 41, "k")
    for y in range(3, 42):
        put(g, 4, y, "k"); put(g, 35, y, "k")
    # label
    fill_rect(g, 9, 12, 30, 36, "l")
    for x in range(9, 31):
        put(g, x, 11, "k"); put(g, x, 37, "k")
    for y in range(11, 38):
        put(g, 8, y, "k"); put(g, 31, y, "k")
    fill_rect(g, 9, 12, 30, 16, "h")        # red header
    # title art: steel tube on blue
    fill_rect(g, 10, 18, 29, 31, "b")
    fill_ellipse(g, 20, 24, 9, 3, "s")      # tube body
    fill_ellipse(g, 20, 24, 9, 3, "s")
    fill_rect(g, 11, 24, 29, 26, "s")
    fill_ellipse(g, 12, 25, 2.4, 3, "d")    # tube end (hole)
    fill_ellipse(g, 12, 25, 1.4, 2, "k")
    put(g, 16, 22, "w"); put(g, 22, 22, "w")  # highlight glints
    # footer text bar
    fill_rect(g, 10, 33, 29, 35, "t")
    for x in range(12, 28, 2):
        put(g, x, 34, "y")
    return to_tdart(g, pal)


# ── Woogy (UFO50) salesman — fixed palette ───────────────────────────────────
def woogy():
    W, H = 44, 58
    pal = {
        "k": "#0c160c", "g": "#3f7a3a", "G": "#2c5a2a", "l": "#5fae50",
        "w": "#f4f4ec", "p": "#14140e", "m": "#6b4a2c", "M": "#4a3220",
        "r": "#d23a3a", "i": "#ffffff", "y": "#f4c430",
    }
    g = blank(W, H)
    cx = 22
    # silhouette (black) then green inset = clean 1px outline
    fill_poly(g, [(22, 2), (12, 22), (32, 22)], "k")     # pointed crown
    fill_ellipse(g, cx, 34, 17, 22, "k")
    fill_poly(g, [(22, 4), (14, 22), (30, 22)], "g")
    fill_ellipse(g, cx, 34, 16, 21, "g")
    # shading
    for y in range(H):
        for x in range(W):
            if g[y][x] == "g" and (x - cx) - (34 - y) > 9:
                g[y][x] = "G"
            elif g[y][x] == "g" and (cx - x) - (34 - y) > 11:
                g[y][x] = "l"
    # eyes
    fill_circle(g, 14, 24, 5, "k")
    fill_circle(g, 30, 24, 5, "k")
    fill_circle(g, 14, 24, 4.2, "w")
    fill_circle(g, 30, 24, 4.2, "w")
    fill_circle(g, 15, 22, 1.8, "p")     # pupils up/out
    fill_circle(g, 31, 22, 1.8, "p")
    # mouth (brown lens with white oval)
    fill_ellipse(g, cx, 40, 12, 4.5, "M")
    fill_ellipse(g, cx, 39, 11, 3.5, "m")
    fill_ellipse(g, cx, 39, 4.5, 2.2, "i")
    # candy-stripe base
    base_y0, base_y1 = 48, 53
    for x in range(10, 35):
        if g[base_y0][x] in ("g", "G", "l", "k") or g[base_y1][x] in ("g", "G", "l", "k"):
            col = "r" if ((x - 10) // 2) % 2 == 0 else "w"
            for y in range(base_y0, base_y1 + 1):
                if g[y][x] != ".":
                    g[y][x] = col
    # gold flecks
    for fx, fy in [(9, 16), (34, 18), (11, 42), (33, 40), (22, 10)]:
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
