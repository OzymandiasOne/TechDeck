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


_RAIN_CHARS = "·~ox=+%@01"


def _cell_hash(r: int, c: int, seed: int, salt: int = 0) -> int:
    h = (r * 73856093) ^ (c * 19349663) ^ (seed * 83492791) ^ (salt * 2654435761)
    h = (h ^ (h >> 13)) * 1274126177
    return (h ^ (h >> 16)) & 0x7FFFFFFF


def compile_frame(final_cells, progress: float, seed: int = 0):
    """One frame of the summon compile: matrix rain condensing into the face.

    Deterministic for a given seed. progress 0.0 → all blank (nothing has
    rained in yet); 1.0 → exactly final_cells. In between, each cell rains
    dim noise from the top down, then LOCKS to its final glyph — flashing
    peak-bright for an instant before settling. Cells empty in the final
    face flicker as noise early and burn out to black.
    """
    rows = len(final_cells)
    tick = int(progress * 24)          # noise re-rolls as progress advances
    out = []
    for r, row in enumerate(final_cells):
        out_row = []
        for c, (ch, tier) in enumerate(row):
            u = _cell_hash(r, c, seed) / 0x7FFFFFFF
            appear = 0.05 + 0.30 * (r / max(1, rows - 1)) * (0.5 + 0.5 * u)
            lock = 0.30 + 0.60 * (0.65 * u + 0.35 * (r / max(1, rows - 1)))
            if progress >= 1.0:
                out_row.append((ch, tier))
            elif ch == " ":
                # Never part of the face: noise that dies out early.
                fade = appear + 0.45 * (lock - appear)
                if appear <= progress < fade:
                    n = _cell_hash(r, c, seed, tick)
                    out_row.append((_RAIN_CHARS[n % len(_RAIN_CHARS)], "dim"))
                else:
                    out_row.append((" ", None))
            elif progress < appear:
                out_row.append((" ", None))
            elif progress < lock:
                n = _cell_hash(r, c, seed, tick)
                noise_tier = "dim" if n & 1 else "mid"
                out_row.append((_RAIN_CHARS[n % len(_RAIN_CHARS)], noise_tier))
            elif progress < lock + 0.05:
                out_row.append((ch, "peak"))   # the lock-in flash
            else:
                out_row.append((ch, tier))
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
