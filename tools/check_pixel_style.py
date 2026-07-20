"""
Pixel-art style linter — mechanical checks for the TechDeck icon/sprite style.

Derived from analysis of the two Icons8 reference packs (July 2026): all 44
reference icons have ZERO orphan pixels, ZERO diagonal-only connections, no
partial alpha, tiny flat palettes, and chunky 2x2-block structure. This tool
turns those measured properties (plus standard pixel-art theory: jaggies,
clusters, doubles) into pass/warn/fail checks so generated art can be iterated
until it matches the reference quality. The authoring rules live in the
`pixel-icon-style` skill; this is the enforcement half.

Targets (mix freely):
    python tools/check_pixel_style.py assets/icons/... .png|.tdart|dir
    python tools/check_pixel_style.py key:SCISSORS            # generator grid
    python tools/check_pixel_style.py --profile character dir

Profiles: logo (default -- flat object/logo tile icons), character (busier,
1px face detail allowed), sprite (.tdart freeform art; diagonal strokes are
legal). Exit code 1 if any FAIL.

Options:
    --profile logo|character|sprite   check thresholds (default logo; .tdart
                                      targets default to sprite)
    --expect-symmetric                FAIL if the silhouette is not perfectly
                                      left-right mirror symmetric (lists the
                                      mismatched cells)
    --script PATH                     generator script for key: targets
                                      (default: tools/generate_tile_icons_32.py,
                                      falls back to tools/generate_pack_icons.py)
"""

import argparse
import ast
import json
import math
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Near-duplicate colors closer than this (RGB distance) are one "clustered"
# color -- absorbs the compression noise found in the reference PNGs.
COLOR_CLUSTER_DIST = 24

PROFILES = {
    #             palette      margin  chunk   iso-color  diag-only
    #             warn / fail  (px@32) warn<   warn>      severity
    "logo":      dict(pal_warn=5, pal_fail=8,  margin=2, chunk=0.60, iso=4,  diag="FAIL"),
    "character": dict(pal_warn=8, pal_fail=10, margin=1, chunk=0.40, iso=10, diag="FAIL"),
    "sprite":    dict(pal_warn=10, pal_fail=14, margin=0, chunk=None, iso=14, diag="WARN"),
}


# -- target loading ----------------------------------------------------------

def load_png(path):
    from PIL import Image
    img = Image.open(path).convert("RGBA")
    w, h = img.size
    px = img.load()
    # downsample to native grid: largest scale where every s x s block is uniform
    for s in range(min(w, h), 0, -1):
        if w % s or h % s:
            continue
        if all(px[bx + dx, by + dy] == px[bx, by]
               for by in range(0, h, s) for bx in range(0, w, s)
               for dy in range(s) for dx in range(s)):
            img = img.resize((w // s, h // s), Image.NEAREST)
            break
    px = img.load()
    gw, gh = img.size
    return [[px[x, y] if px[x, y][3] > 0 else None for x in range(gw)] for y in range(gh)]


def load_tdart(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    pal = {k: _hex(v) for k, v in data["palette"].items()}
    rows = data["rows"]
    gw = max(len(r) for r in rows)
    grid = []
    for r in rows:
        r = r.ljust(gw)
        grid.append([pal.get(ch) and (*pal[ch], 255) for ch in r])
    return grid


def load_generator_key(key, script_paths):
    key = key.upper()
    for sp in script_paths:
        text = Path(sp).read_text(encoding="utf-8")
        gm = re.search(rf"_{key}_GRID\s*=\s*(\[.*?\])", text, re.S)
        tm = re.search(rf"_{key}_TONES\s*=\s*(\{{.*?\}})", text, re.S)
        if gm and tm:
            rows = ast.literal_eval(gm.group(1))
            tones = {k: _hex(v) for k, v in ast.literal_eval(tm.group(1)).items()}
            gw = max(len(r) for r in rows)
            return [[tones.get(ch) and (*tones[ch], 255) for ch in r.ljust(gw)]
                    for r in rows]
    raise FileNotFoundError(f"no _{key}_GRID/_TONES block in: " + ", ".join(map(str, script_paths)))


def _hex(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# -- analysis ----------------------------------------------------------------

def cluster_colors(counts):
    """Greedy-merge near-duplicate colors; returns list of (rep_rgb, count)."""
    merged = []
    for c, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        for m in merged:
            if math.dist(c[:3], m[0][:3]) < COLOR_CLUSTER_DIST:
                m[1] += n
                break
        else:
            merged.append([c, n])
    return merged


def analyze(grid):
    gh = len(grid)
    gw = len(grid[0]) if gh else 0

    def at(x, y):
        if 0 <= x < gw and 0 <= y < gh:
            return grid[y][x]
        return None

    counts = {}
    partial_alpha = []
    minx, miny, maxx, maxy = gw, gh, -1, -1
    for y in range(gh):
        for x in range(gw):
            c = at(x, y)
            if c is None:
                continue
            if len(c) > 3 and c[3] not in (255,):
                partial_alpha.append((x, y))
            counts[c[:3]] = counts.get(c[:3], 0) + 1
            minx, maxx = min(minx, x), max(maxx, x)
            miny, maxy = min(miny, y), max(maxy, y)
    if maxx < 0:
        raise ValueError("empty image")

    # cluster reps absorb PNG compression noise for the color-identity checks
    reps = cluster_colors(counts)

    def rep(c):
        if c is None:
            return None
        for m in reps:
            if math.dist(c[:3], m[0][:3]) < COLOR_CLUSTER_DIST:
                return tuple(m[0][:3])
        return c[:3]

    N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
    N8 = N4 + ((1, 1), (1, -1), (-1, 1), (-1, -1))
    orphans, diag_only, stubs, iso_color = [], [], [], []
    notches = []
    for y in range(gh):
        for x in range(gw):
            c = at(x, y)
            if c is None:
                # 1px dent: transparent cell with 3+ opaque orthogonal neighbors
                if sum(1 for dx, dy in N4 if at(x + dx, y + dy)) >= 3:
                    notches.append((x, y))
                continue
            n4 = sum(1 for dx, dy in N4 if at(x + dx, y + dy))
            n8 = sum(1 for dx, dy in N8 if at(x + dx, y + dy))
            if n8 == 0:
                orphans.append((x, y))
            elif n4 == 0:
                diag_only.append((x, y))
            elif n4 == 1:
                stubs.append((x, y))
            ns = [rep(at(x + dx, y + dy)) for dx, dy in N4]
            ns = [n for n in ns if n]
            if ns and all(n != rep(c) for n in ns):
                iso_color.append((x, y))

    # 2x2 chunkiness on 32-wide grids (clustered colors absorb PNG noise)
    chunk = None
    if gw == gh == 32:
        uni = tot = 0
        for by in range(0, 32, 2):
            for bx in range(0, 32, 2):
                block = {rep(at(bx + dx, by + dy)) for dy in (0, 1) for dx in (0, 1)}
                tot += 1
                uni += len(block) == 1
        chunk = uni / tot

    # silhouette horizontal symmetry over the content bbox
    sym_bad = []
    for y in range(miny, maxy + 1):
        for x in range(minx, (minx + maxx) // 2 + 1):
            mx = maxx - (x - minx)
            if (at(x, y) is None) != (at(mx, y) is None):
                sym_bad.append((x, y))
    area = (maxx - minx + 1) * (maxy - miny + 1)
    hsym = 1.0 - 2 * len(sym_bad) / area if area else 1.0

    # deliberate-looking dither: 2x2 blocks with two colors on the diagonals
    dither = 0
    for y in range(gh - 1):
        for x in range(gw - 1):
            b = [at(x, y), at(x + 1, y), at(x, y + 1), at(x + 1, y + 1)]
            if all(b) and b[0] == b[3] and b[1] == b[2] and b[0] != b[1]:
                dither += 1

    margins = (minx, miny, gw - 1 - maxx, gh - 1 - maxy)
    return dict(grid=(gw, gh), bbox=(maxx - minx + 1, maxy - miny + 1),
                margins=margins, colors=len(cluster_colors(counts)),
                raw_colors=len(counts), partial_alpha=partial_alpha,
                orphans=orphans, diag_only=diag_only, stubs=stubs,
                notches=notches, iso_color=iso_color, chunk=chunk,
                hsym=hsym, sym_bad=sym_bad, dither=dither)


# -- reporting ---------------------------------------------------------------

def _fmt_px(pts, limit=8):
    s = ", ".join(f"({x},{y})" for x, y in pts[:limit])
    return s + (f" +{len(pts) - limit} more" if len(pts) > limit else "")


def lint(name, grid, profile, expect_symmetric=False):
    p = PROFILES[profile]
    a = analyze(grid)
    scale = a["grid"][0] / 32  # thresholds are stated at 32-scale
    issues = []  # (level, message)

    def add(level, msg):
        issues.append((level, msg))

    if a["partial_alpha"]:
        add("FAIL", f"partial alpha at {_fmt_px(a['partial_alpha'])} -- alpha must be 0 or 255, no AA")
    if a["orphans"]:
        add("FAIL", f"orphan pixels (no neighbors) at {_fmt_px(a['orphans'])}")
    if a["diag_only"]:
        add(p["diag"], f"diagonal-only pixels (weak connections) at {_fmt_px(a['diag_only'])}")
    if a["colors"] > p["pal_fail"]:
        add("FAIL", f"{a['colors']} clustered colors (max {p['pal_fail']} for {profile})")
    elif a["colors"] > p["pal_warn"]:
        add("WARN", f"{a['colors']} clustered colors (target <= {p['pal_warn']} for {profile})")
    min_margin = max(1, round(p["margin"] * scale)) if p["margin"] else 0
    if min_margin and min(a["margins"]) < min_margin:
        add("WARN", f"margins {a['margins']} (L,T,R,B) -- want >= {min_margin}px empty per side")
    if p["chunk"] is not None and a["chunk"] is not None and a["chunk"] < p["chunk"]:
        add("WARN", f"2x2 chunkiness {a['chunk']:.2f} < {p['chunk']:.2f} -- too much 1px detail; "
                    "author at 16x16 logical (2x2 blocks on the 32 grid)")
    if a["stubs"]:
        add("WARN", f"1px stubs (jaggy candidates, single orthogonal neighbor) at {_fmt_px(a['stubs'])}")
    if a["notches"]:
        add("WARN", f"1px notches (dents) at {_fmt_px(a['notches'])}")
    if len(a["iso_color"]) > p["iso"]:
        add("WARN", f"{len(a['iso_color'])} isolated-color pixels (> {p['iso']} for {profile}) "
                    f"at {_fmt_px(a['iso_color'])} -- reads as noise; merge into 2x2+ clusters")
    if expect_symmetric and a["sym_bad"]:
        add("FAIL", f"silhouette not mirror-symmetric; mismatched cells at {_fmt_px(a['sym_bad'])}")

    level = "FAIL" if any(l == "FAIL" for l, _ in issues) else \
            "WARN" if any(l == "WARN" for l, _ in issues) else "PASS"
    print(f"[{level}] {name}  ({a['grid'][0]}x{a['grid'][1]}, {a['colors']} colors, "
          f"bbox {a['bbox'][0]}x{a['bbox'][1]}, hsym {a['hsym']:.2f}"
          + (f", chunk {a['chunk']:.2f}" if a["chunk"] is not None else "")
          + (f", dither {a['dither']}" if a["dither"] else "") + ")")
    for l, msg in issues:
        print(f"    {l}: {msg}")
    return level


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("targets", nargs="+", help="PNG/.tdart/dir or key:NAME")
    ap.add_argument("--profile", choices=sorted(PROFILES), default=None)
    ap.add_argument("--expect-symmetric", action="store_true")
    ap.add_argument("--script", default=None, help="generator script for key: targets")
    args = ap.parse_args(argv)

    scripts = [args.script] if args.script else [
        ROOT / "tools" / "generate_tile_icons_32.py",
        ROOT / "tools" / "generate_pack_icons.py",
    ]

    jobs = []
    for t in args.targets:
        if t.startswith("key:"):
            jobs.append((t, "key"))
        elif os.path.isdir(t):
            for f in sorted(os.listdir(t)):
                if f.lower().endswith((".png", ".tdart")):
                    jobs.append((os.path.join(t, f), "file"))
        else:
            jobs.append((t, "file"))

    worst = "PASS"
    order = {"PASS": 0, "WARN": 1, "FAIL": 2}
    for target, kind in jobs:
        if kind == "key":
            grid = load_generator_key(target[4:], scripts)
            profile = args.profile or "logo"
        elif target.lower().endswith(".tdart"):
            grid = load_tdart(target)
            profile = args.profile or "sprite"
        else:
            grid = load_png(target)
            profile = args.profile or "logo"
        level = lint(os.path.basename(target), grid, profile, args.expect_symmetric)
        if order[level] > order[worst]:
            worst = level

    print(f"\nresult: {worst}")
    return 1 if worst == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
