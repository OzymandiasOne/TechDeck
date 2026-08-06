"""The Cheshire Cat — character-grid face art + compositor for the console.

The cat is rendered as colored monospace text INSIDE the console's QTextEdit
(never a widget overlay). FACE_ART was recovered from the reference ASCII cat
(reference/cheshire_cat_1088p_frames) by luminance-sampling the frames on
their detected 7x13px character grid and mapping cell brightness back through
the density ramp — the inverse of the technique that generated the original.
The resting face IS the reference, whisker-mouth and all; the striped
Cheshire grin appears only when the cat SPEAKS (and its smile row is what a
dissolve erases last).

Regenerate / recalibrate with the sampler in the session notes, or edit
FACE_ART directly — it's a plain glyph grid (house style, like MOTH_FRAMES):

  glyphs  ' ·~ox=+%@' dark→bright (space = empty, '·' halo dot, '%' field,
          '@' peak) — brightness comes from CHAR_TIER, not the glyph itself
  PUPIL   the gaze stamp: a dotted-rim, black-centered HOLE in the glow
          (the reference's pupil is a void, never a bright cluster)
  MOUTH_FRAMES  full replacement rows for the mouth band: frame 0 (rest) is
          the reference's own whisker rows; 1/2 are the speaking grin, teeth
          as '|'. Strings are centered via _center() — no column counting.

Blink is DERIVED, not drawn: every eye glyph collapses to a lid line '—' of
the same span, the pupil staying faintly visible — the reference's exact
behaviour. Preview with `python tools/preview_console_cat.py`.
"""

from __future__ import annotations

FACE_WIDTH = 55

# Rows 0-8: eyes. Rows 8-10: nose. Rows 11-13: the mouth band (whiskers at
# rest — see MOUTH_FRAMES[0]).
FACE_ART = [
    "    ~~~~%%~~~~~                       ~~~~~%~~~~~      ",
    "  ~+%+%@@@%%%++~~~                 ~~=%+%%%@%%%%+~~    ",
    "~++@@@@@@@@@@@@%+o~               ~o=@@@@@@@@@@@@%+~   ",
    "o%@@@@@@@@@@%@@@@+o~             ~o=%@@@@@@@@%%@@@@+~  ",
    "o%@@@@@@@@@%@@@@@@+o             o=%@@@@@@@@%@@@%@@+o  ",
    "~+%@@@@@@%@@@@@@@@+o             o%@@@@@%%@@@@@@@@=o·  ",
    " ·o+@@%@@@@@@@@@@=o~             ·=%@@@@@@@@@@@@@=o~   ",
    "  ~~%+=+@@@@%+=%%~·               ~o++++%@@@@==++··    ",
    "    ~~~~=+++~·~·~       o===o      ·~~~·~=%%%~~~       ",
    "                       ~+%@@%o                         ",
    "                       o+@@@@x                         ",
    "                ~=%++===+@@@+====%=~                   ",
    "                ·=@@@%%%@%+@@@%%%@%~                   ",
    "                  ~=%+=++o x%%++=x~                    ",
    "                                                       ",
]

MOUTH_TOP = 11          # first row of the mouth band
GRIN_ROW = 12           # the smile arc — what a dissolve erases last

# Eye bounding boxes (row0, col0, row1, col1) inclusive, in FACE_ART coords.
EYE_BOXES = ((0, 0, 8, 20), (0, 33, 8, 54))

# The gaze stamp — the '+' IRIS ring travelling with its black pupil core:
# a hole in the glow ringed by mid-brightness, as in the reference.
PUPIL = [
    "·++++·",
    "+    +",
    "+    +",
    "·++++·",
]

# 5 x 3 gaze positions (ix 0..4 left→right, iy 0..2 up→down); (2, 1) centers.
IRIS_COLS = 5
IRIS_ROWS = 3
# Pupil-origin travel within each eye, in eye-local coords.
_PUPIL_ROWS = (1, 3)
_PUPIL_COLS = (3, 12)


def _center(s: str) -> str:
    pad = (FACE_WIDTH - len(s)) // 2
    return " " * pad + s + " " * (FACE_WIDTH - pad - len(s))


# Full replacement rows for the mouth band (4 rows — the last is FACE_ART's
# reserved empty bottom row, so a speaking jaw can actually DROP). Frame 0 =
# at rest = the reference's own whisker-mouth, verbatim, jaw shut. Frames
# 1/2 = the Cheshire grin: upper lip arc, '|' teeth, a dark mouth cavity,
# and a chin bow whose brightness peaks at center (the lowest point).
MOUTH_FRAMES = [
    FACE_ART[MOUTH_TOP:MOUTH_TOP + 4],
    [
        _center("~=%+=+%@@@@@@@@@%+=+%=~"),
        _center("~=@@%|%@%|%@@%|%@%|@@=~"),
        _center("~=%+·        ·+%=~"),
        _center("~==+%@@@@%+==~"),
    ],
    [
        _center("~=%@@@@@@@@@@@@@@@@@%=~"),
        _center("=@@%|%@@%|%@@%|%@@%|@@="),
        _center("~=%+·          ·+%=~"),
        _center("~==++%@@@@@@%++==~"),
    ],
]

# Phosphor tier palette — classic green CRT. Theme hook comes later; keep
# every color here so a swap is one dict.
PHOSPHOR = {
    "dim": "#1E5A2A",
    "mid": "#2FA84F",
    "bright": "#4FD468",
    "peak": "#7CFF96",
}

CHAR_TIER = {
    "·": "dim", "~": "dim",
    "o": "mid", "x": "mid", "=": "mid", "+": "mid", "—": "mid",
    "%": "bright",
    "@": "peak", "|": "peak",
}
# Cells the pupil may stamp over / the blink collapses to lid lines.
_FIELD_CHARS = set("%@+=xo")
_BLINK_CHAR = "—"

_PUPIL_H = len(PUPIL)
_PUPIL_W = len(PUPIL[0])


def _pupil_origin(ix: int, iy: int):
    r0, r1 = _PUPIL_ROWS
    c0, c1 = _PUPIL_COLS
    return (r0 + round((r1 - r0) * iy / (IRIS_ROWS - 1)),
            c0 + round((c1 - c0) * ix / (IRIS_COLS - 1)))


def compose_face(iris=(2, 1), mouth: int = 0, blink: bool = False):
    """Compose one face frame.

    Returns a rectangular grid (list of rows) of (char, tier) cells where
    tier is a PHOSPHOR key, or (" ", None) for empty cells.

    iris:  (ix, iy) in the 5x3 gaze grid; both eyes move together.
    mouth: index into MOUTH_FRAMES (0 = the reference's resting whiskers).
    blink: eyes collapse to lid lines of the same span, the pupil hole
           staying faintly visible (the reference's blink).
    """
    ix, iy = iris
    if not (0 <= ix < IRIS_COLS and 0 <= iy < IRIS_ROWS):
        raise ValueError(f"iris out of range: {iris!r}")
    p_row, p_col = _pupil_origin(ix, iy)
    frame = MOUTH_FRAMES[mouth]

    out = []
    for r in range(len(FACE_ART)):
        if MOUTH_TOP <= r < MOUTH_TOP + len(frame):
            art_row = frame[r - MOUTH_TOP]
        else:
            art_row = FACE_ART[r]
        out_row = []
        for c, ch in enumerate(art_row):
            if ch == " ":
                out_row.append((" ", None))
                continue
            # Inside an eye?
            eye_local = None
            for er0, ec0, er1, ec1 in EYE_BOXES:
                if er0 <= r <= er1 and ec0 <= c <= ec1:
                    eye_local = (r - er0, c - ec0)
                    break
            if eye_local is not None and ch in _FIELD_CHARS:
                lr, lc = eye_local
                if (p_row <= lr < p_row + _PUPIL_H
                        and p_col <= lc < p_col + _PUPIL_W):
                    p_ch = PUPIL[lr - p_row][lc - p_col]
                    if p_ch == " ":
                        out_row.append((" ", None))
                    else:
                        out_row.append((p_ch, CHAR_TIER[p_ch]))
                    continue
            if eye_local is not None and blink:
                out_row.append((_BLINK_CHAR, "mid"))
                continue
            out_row.append((ch, CHAR_TIER[ch]))
        out.append(out_row)
    return out


def _cell_hash(r: int, c: int, seed: int, salt: int = 0) -> int:
    h = (r * 73856093) ^ (c * 19349663) ^ (seed * 83492791) ^ (salt * 2654435761)
    h = (h ^ (h >> 13)) * 1274126177
    return (h ^ (h >> 16)) & 0x7FFFFFFF


# ── the summon: the face comes FORWARD out of the dark ────────────────────
# Choreography (progress 0..1): two straight slit lines GLOW IN from the
# darkness (phosphor warming up — the closed eyes), hold a beat → the eyes
# SNAP open like a cat's, the pupil already on you → they hold, staring →
# the nose tip and mouth corners seed, and the lower face GRADUALLY flowers
# outward from them. Materialized cells rise toward full tier as progress
# advances, so the whole face brightens toward the viewer; open-eye cells
# come in at mid brightness so the snap reads crisp, while the slits and the
# lower face warm up out of the dark.

_LID_IN = (0.03, 0.10)      # slits glow in, center-out
_LID_RISE = 0.05            # the phosphor warm-up on each slit cell
_EYES_OPEN = (0.24, 0.30)   # the snap — full open in a blink's time
_SEEDS_AT = 0.46            # after a held stare
_FLOWER = (0.50, 0.90)
_RISE = 0.11            # per-tier-step delay after a cell materializes
_TIER_RANK = {"dim": 0, "mid": 1, "bright": 2, "peak": 3}
_TIER_BY_RANK = ("dim", "mid", "bright", "peak")

_EYE_MID = (EYE_BOXES[0][0] + EYE_BOXES[0][2]) // 2


def _feature_of(r: int, c: int):
    for er0, ec0, er1, ec1 in EYE_BOXES:
        if er0 <= r <= er1 and ec0 <= c <= ec1:
            return "eye"
    return "mouth" if r >= MOUTH_TOP else "nose"


def _dist(a, b) -> float:
    # Character cells are ~2x taller than wide — weight rows double so the
    # flowering spreads in visually round rings.
    return ((a[1] - b[1]) ** 2 + (2 * (a[0] - b[0])) ** 2) ** 0.5


def _summon_schedule(final_cells, seed: int):
    """Per-cell materialization time (progress units) for one summon."""
    filled = [(r, c) for r, row in enumerate(final_cells)
              for c, (ch, _) in enumerate(row) if ch != " "]
    nose_cells = [p for p in filled if _feature_of(*p) == "nose"]
    mouth_cells = [p for p in filled if _feature_of(*p) == "mouth"]
    nose_seed = max(nose_cells, key=lambda p: (p[0], -abs(p[1] - FACE_WIDTH // 2)))
    grin_cols = [c for r, c in mouth_cells if r == GRIN_ROW]
    mouth_seeds = ((GRIN_ROW, min(grin_cols)), (GRIN_ROW, max(grin_cols)))

    def flower_t(p, seeds):
        d = min(_dist(p, s) for s in seeds)
        return d

    nose_max = max(flower_t(p, [nose_seed]) for p in nose_cells) or 1.0
    mouth_max = max(flower_t(p, mouth_seeds) for p in mouth_cells) or 1.0

    schedule = {}
    for p in filled:
        r, c = p
        u = _cell_hash(r, c, seed) / 0x7FFFFFFF
        kind = _feature_of(r, c)
        if kind == "eye":
            if r == _EYE_MID:
                # The lid line draws center-out from each eye's middle.
                box = next(b for b in EYE_BOXES if b[1] <= c <= b[3])
                center_c = (box[1] + box[3]) / 2
                frac = abs(c - center_c) / max(1.0, (box[3] - box[1]) / 2)
                schedule[p] = (_LID_IN[0] + (_LID_IN[1] - _LID_IN[0])
                               * (0.75 * frac + 0.25 * u))
            else:
                span = _EYES_OPEN[1] - _EYES_OPEN[0]
                frac = abs(r - _EYE_MID) / max(1, EYE_BOXES[0][2] - _EYE_MID)
                schedule[p] = (_EYES_OPEN[0] + span * frac
                               + 0.01 * (u - 0.5))
        else:
            seeds = [nose_seed] if kind == "nose" else mouth_seeds
            if p in ((nose_seed,) if kind == "nose" else mouth_seeds):
                schedule[p] = _SEEDS_AT
            else:
                span = _FLOWER[1] - _FLOWER[0]
                frac = flower_t(p, seeds) / (nose_max if kind == "nose"
                                             else mouth_max)
                schedule[p] = _FLOWER[0] + span * frac + 0.02 * (u - 0.5)

    # The slits must be STRAIGHT lines: schedule the mid-row cells the final
    # face leaves blank (the pupil hole) too — they render as lid until the
    # eyes snap open, then the lid splits and they return to darkness.
    for er0, ec0, er1, ec1 in EYE_BOXES:
        center_c = (ec0 + ec1) / 2
        for c in range(ec0, ec1 + 1):
            p = (_EYE_MID, c)
            if p not in schedule and FACE_ART[_EYE_MID][c] != " ":
                u = _cell_hash(_EYE_MID, c, seed) / 0x7FFFFFFF
                frac = abs(c - center_c) / max(1.0, (ec1 - ec0) / 2)
                schedule[p] = (_LID_IN[0] + (_LID_IN[1] - _LID_IN[0])
                               * (0.75 * frac + 0.25 * u))
    return schedule


def summon_frame(final_cells, progress: float, seed: int = 0):
    """One frame of the summon (see choreography above).

    Deterministic for a given seed. progress 0.0 → darkness; 1.0 → exactly
    final_cells. Cell presence is monotonic — nothing materializes and then
    vanishes; the face only ever gains ground on the dark.
    """
    if progress >= 1.0:
        return [list(row) for row in final_cells]
    schedule = _summon_schedule(final_cells, seed)
    lids_only = progress < _EYES_OPEN[0]
    out = []
    for r, row in enumerate(final_cells):
        out_row = []
        for c, (ch, tier) in enumerate(row):
            t_mat = schedule.get((r, c))
            in_eye = _feature_of(r, c) == "eye"
            if (lids_only and r == _EYE_MID and in_eye
                    and t_mat is not None):
                # The closed slits — unbroken lines (they span the pupil
                # hole) glowing in dim → mid as the phosphor warms up.
                if progress < t_mat:
                    out_row.append((" ", None))
                else:
                    rank = min(1, int((progress - t_mat) / _LID_RISE))
                    out_row.append((_BLINK_CHAR, _TIER_BY_RANK[rank]))
                continue
            if ch == " " or t_mat is None or progress < t_mat:
                out_row.append((" ", None))
                continue
            # Late-materializing cells rise faster so everything reaches its
            # full tier just before progress hits 1.0 — no end-of-summon pop.
            rise = min(_RISE, max(0.02, (0.99 - t_mat) / 3))
            # Eyes materialize at mid so the snap reads crisp; the lower
            # face starts dim and grows out of the dark.
            floor = 1 if in_eye else 0
            rank = min(_TIER_RANK[tier],
                       floor + int((progress - t_mat) / rise))
            out_row.append((ch, _TIER_BY_RANK[rank]))
        out.append(out_row)
    return out


def face_html(cells, palette=None) -> str:
    """Render composed cells to HTML (consecutive same-tier runs merged into
    one span) for insertion into the console document. Rows joined with \\n —
    the caller wraps them in a white-space:pre block."""
    palette = palette or PHOSPHOR
    lines = []
    for row in cells:
        parts = []
        run_chars: list[str] = []
        run_tier = "sentinel"
        for ch, tier in row + [("", "sentinel")]:   # sentinel flushes the last run
            if tier != run_tier:
                if run_chars:
                    text = "".join(run_chars)
                    if run_tier is None:
                        parts.append(text)
                    else:
                        parts.append(f'<span style="color: '
                                     f'{palette[run_tier]};">{text}</span>')
                run_chars = []
                run_tier = tier
            run_chars.append(ch)
        lines.append("".join(parts))
    return "\n".join(lines)
