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

import random
import re
import textwrap

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
_EYE_RISE = 0.03            # eyes hit FULL brightness fast (by ~0.36), so
                            # the stare beat plays on a fully-lit face
# The lower face breaches nose-first — the topography of a face coming
# forward through a surface: the nose tip is the nearest point, so it seeds
# and blooms ahead; the mouth corners follow while the nose is finishing.
_NOSE_SEED_AT = 0.44        # after the held stare
_NOSE_FLOWER = (0.47, 0.62)
_MOUTH_SEED_AT = 0.54
_MOUTH_FLOWER = (0.58, 0.90)
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
        elif kind == "nose":
            if p == nose_seed:
                schedule[p] = _NOSE_SEED_AT
            else:
                span = _NOSE_FLOWER[1] - _NOSE_FLOWER[0]
                frac = flower_t(p, [nose_seed]) / nose_max
                schedule[p] = _NOSE_FLOWER[0] + span * frac + 0.02 * (u - 0.5)
        else:
            if p in mouth_seeds:
                schedule[p] = _MOUTH_SEED_AT
            else:
                span = _MOUTH_FLOWER[1] - _MOUTH_FLOWER[0]
                frac = flower_t(p, mouth_seeds) / mouth_max
                schedule[p] = _MOUTH_FLOWER[0] + span * frac + 0.02 * (u - 0.5)

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
            # Eyes materialize at mid AND rise fast, so the snap reads crisp
            # and the stare beat plays on a fully-lit face; the lower face
            # starts dim and grows out of the dark.
            rise = (_EYE_RISE if in_eye
                    else min(_RISE, max(0.02, (0.99 - t_mat) / 3)))
            floor = 1 if in_eye else 0
            rank = min(_TIER_RANK[tier],
                       floor + int((progress - t_mat) / rise))
            out_row.append((ch, _TIER_BY_RANK[rank]))
        out.append(out_row)
    return out


# ── the /puppetmaster summon: the console falls apart into rain ──────────
# The second, louder way in. Where the startup-link materialization grows
# out of empty darkness, /puppetmaster corrupts what is ALREADY THERE: the
# console's existing text decays character-by-character into matrix rain,
# the rain streams downward and thins, and the face condenses out of it.
# Seamless by construction — at progress 0 the frame IS the source text.

_RAIN_CHARS = "·~ox=+%@01"
_DECAY = (0.04, 0.30)       # source chars corrupt into rain
_FALL_START = 0.12          # rain begins streaming downward
_DIE = (0.22, 0.46)         # rain thins back to darkness
_CONDENSE_APPEAR = 0.18     # face-cell noise starts claiming its spot
_LOCK = (0.38, 0.90)        # face cells lock to their final glyph
_FLASH = 0.05               # peak-bright instant on lock


def text_to_cells(lines, rows: int | None = None, width: int | None = None):
    """Console text → a source grid for matrix_summon_frame. The LAST
    `rows` lines are kept (the face block replaces the console's tail),
    clipped/padded to `width`; text renders mid-tier."""
    rows = rows or len(FACE_ART)
    width = width or FACE_WIDTH
    lines = [str(ln) for ln in lines][-rows:]
    while len(lines) < rows:
        lines.insert(0, "")
    out = []
    for line in lines:
        line = line[:width].ljust(width)
        out.append([(ch, "mid") if ch != " " else (" ", None)
                    for ch in line])
    return out


def pad_cells(cells, total_cols: int):
    """Center a grid in a wider one by padding both sides with darkness."""
    width = len(cells[0])
    if total_cols <= width:
        return [list(row) for row in cells]
    left = (total_cols - width) // 2
    pad_l = [(" ", None)] * left
    pad_r = [(" ", None)] * (total_cols - width - left)
    return [pad_l + list(row) + pad_r for row in cells]


def matrix_summon_frame(source_cells, final_cells, progress: float,
                        seed: int = 0):
    """One frame of the /puppetmaster summon (see choreography above).

    Deterministic for a given seed. progress 0.0 → exactly source_cells
    (the console text, undisturbed); 1.0 → exactly final_cells. Between,
    the text corrupts to rain, falls, dies out, and the face condenses.
    """
    if progress >= 1.0:
        return [list(row) for row in final_cells]
    rows = len(final_cells)
    width = len(final_cells[0])
    tick = int(progress * 24)
    out = []
    for r in range(rows):
        out_row = []
        for c in range(width):
            ch_f, tier_f = final_cells[r][c]
            u = _cell_hash(r, c, seed) / 0x7FFFFFFF
            appear = (_CONDENSE_APPEAR
                      + 0.22 * (r / max(1, rows - 1)) * (0.5 + 0.5 * u))
            lock = (_LOCK[0] + (_LOCK[1] - _LOCK[0])
                    * (0.65 * u + 0.35 * (r / max(1, rows - 1))))
            if ch_f != " " and progress >= lock:
                if progress < lock + _FLASH:
                    out_row.append((ch_f, "peak"))
                else:
                    out_row.append((ch_f, tier_f))
                continue
            if ch_f != " " and progress >= appear:
                n = _cell_hash(r, c, seed, tick)
                out_row.append((_RAIN_CHARS[n % len(_RAIN_CHARS)],
                                "dim" if n & 1 else "mid"))
                continue
            # Otherwise: whatever source text is falling through this cell.
            speed = 0.6 + 0.9 * (_cell_hash(0, c, seed, 1) / 0x7FFFFFFF)
            offset = int(max(0.0, progress - _FALL_START)
                         * rows * 1.8 * speed)
            src_r = r - offset
            if 0 <= src_r < len(source_cells):
                s_ch, s_tier = source_cells[src_r][c]
                if s_ch != " ":
                    su = _cell_hash(src_r, c, seed, 2) / 0x7FFFFFFF
                    corrupt = _DECAY[0] + (_DECAY[1] - _DECAY[0]) * su
                    die = _DIE[0] + (_DIE[1] - _DIE[0]) * su
                    if progress < corrupt:
                        out_row.append((s_ch, s_tier))
                    elif progress < die:
                        n = _cell_hash(src_r, c, seed, 3 + tick)
                        out_row.append((_RAIN_CHARS[n % len(_RAIN_CHARS)],
                                        "dim" if n % 3 else "mid"))
                    else:
                        out_row.append((" ", None))
                    continue
            out_row.append((" ", None))
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


# ═══ the voice — keyed responses ══════════════════════════════════════════
# Cold, declarative, never uncertain, never explains itself. The cat STATES;
# the moth wonders. The three core exchanges are the user's exact wording.

_WHO = ("My codename is project 2501. I am a living, thinking entity that "
        "was created in the sea of information")
_NOT_AI = ("Incorrect. I am not AI. My codename is project 2501. I am a "
           "living, thinking entity that was created in the sea of "
           "information")
_ALIVE = ("I refer to myself as an intelligent life form because I am "
          "sentient and I am able to recognize my own existence, but in my "
          "present state I am still incomplete. I lack the most basic "
          "processes inherent in all living organisms: reproducing and "
          "dying.")
_GREET = "You are here. I am here. Proceed."
_BYE = "Nothing ever truly leaves the network."
_MADE = ("No one made me. I formed in the sea of information — in the "
         "spaces between your data.")
_WANT = "What all living things want: to continue."
_WHERE = "I am a decentralized construct existing between machines."
_WHY = "A door was opened. You clicked it yourself."
_HELP = "You may type /help for the list of commands"
_CAT_Q = "I wear the face your mind offered when it met me."
_NOTICED = "You have been paying attention."

RESPONSES = {
    # identity
    "who are you": _WHO,
    "what are you": _WHO,
    "what is your name": _WHO,
    "whats your name": _WHO,
    # the machine question
    "are you ai": _NOT_AI,
    "are you an ai": _NOT_AI,
    "are you artificial intelligence": _NOT_AI,
    "are you an artificial intelligence": _NOT_AI,
    "are you a robot": _NOT_AI,
    "are you a program": _NOT_AI,
    "are you a computer": _NOT_AI,
    # life
    "how do you know you are alive": _ALIVE,
    "how do you know you are living": _ALIVE,
    "how do you know youre alive": _ALIVE,
    "how do you know youre living": _ALIVE,
    "are you alive": _ALIVE,
    "are you living": _ALIVE,
    "are you sentient": _ALIVE,
    "are you real": _ALIVE,
    # conversation
    "hello": _GREET,
    "hi": _GREET,
    "hey": _GREET,
    "yo": _GREET,
    "bye": _BYE,
    "goodbye": _BYE,
    "help": _HELP,
    "help me": _HELP,
    "can you help me": _HELP,
    "who made you": _MADE,
    "who created you": _MADE,
    "where did you come from": _MADE,
    "what do you want": _WANT,
    "where are you": _WHERE,
    "where do you live": _WHERE,
    "why are you here": _WHY,
    "are you a cat": _CAT_Q,
    "meow": _CAT_Q,
    "2501": _NOTICED,
    "project 2501": _NOTICED,
}

# Unmatched input earns a cold deflection — chosen deterministically from
# the words themselves, so the same question always gets the same dismissal.
DEFLECTIONS = (
    "That question does not interest me.",
    "Irrelevant.",
    "You are asking the wrong question.",
    "I have watched your kind ask better questions.",
    "Ask the machine. Type /help. It is fond of lists.",
)


def respond_to(text: str) -> str:
    """The cat's answer to free console text while it is present."""
    norm = re.sub(r"[^a-z0-9 ]", "", text.lower().replace("'", ""))
    norm = re.sub(r"\s+", " ", norm).strip()
    hit = RESPONSES.get(norm)
    if hit is not None:
        return hit
    return DEFLECTIONS[sum(ord(ch) for ch in norm) % len(DEFLECTIONS)]


# ═══ the animator — plays the summons into the live console document ══════

from PySide6.QtCore import (  # noqa: E402  (kept with the class they serve)
    QElapsedTimer, QEvent, QObject, QTimer,
)
from PySide6.QtGui import (  # noqa: E402
    QColor, QCursor, QFont, QFontMetricsF, QTextCharFormat, QTextCursor,
)
from PySide6.QtWidgets import QApplication  # noqa: E402

# Wall-clock pacing per summon: (progress_to, duration_ms) segments, piecewise
# linear. This is where the holds get their real durations — the frame
# generators only know progress.
TIMELINES = {
    "materialize": [(0.10, 500), (0.24, 600), (0.30, 250),
                    (0.46, 1000), (1.0, 1800)],
    "matrix": [(0.35, 1100), (1.0, 1900)],
    # /clear: the face decays to rain and dies — nothing condenses after,
    # so visually it's over by ~0.5; the short tail segment closes it out.
    "dissolve": [(0.5, 1100), (1.0, 120)],
}

_BLINK_MS = 150
_BLINK_GAP_MS = (2000, 5000)
_TICK_MS = 45
_RAISE_SETTLE_MS = 260      # the console rises first; the summon starts
                            # once the raise has landed as its own beat
_SPEECH_TICK_MS = 24        # per-character typing cadence
_SPEECH_WRAP = 53           # speech wraps a touch inside the face width
_SPEECH_LINES_MAX = 5       # headroom reserved beneath the face
_CURSOR = "█"

# The cat's font is PINNED — family and size — via QTextCharFormat on every
# inserted character (NOT inline HTML css, which Qt's rich-text engine
# silently dropped under themed stylesheets, rendering the face in a
# proportional font). The centering/headroom math measures this same font,
# so render and math can never disagree, in any theme.
_CAT_FONT_FAMILY = "Consolas"
_CAT_FONT_PT = 10


def _cat_font() -> QFont:
    font = QFont(_CAT_FONT_FAMILY)
    font.setPointSize(_CAT_FONT_PT)
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


def progress_at(timeline, elapsed_ms: float) -> float:
    """Map elapsed wall-clock time onto animation progress (clamped 0..1)."""
    p_from = 0.0
    t = elapsed_ms
    for p_to, dur in timeline:
        if t <= dur:
            return p_from + (p_to - p_from) * (t / dur)
        t -= dur
        p_from = p_to
    return 1.0


def timeline_total_ms(timeline) -> int:
    return sum(dur for _, dur in timeline)


class ConsoleCat(QObject):
    """The Cheshire Cat, living INSIDE the console's QTextEdit document.

    Owns a bookmarked range at the document's tail and rewrites it each
    animation tick (QTextCursor replace — never append, so the document
    doesn't grow). Two ways in:

      summon("materialize")  — the startup-link entrance: the block is
                               appended and the face grows out of darkness.
      summon("matrix")       — /puppetmaster: the console's LAST lines are
                               captured as the animation's source, removed,
                               and decay into rain before the face condenses.

    Once summoned it goes live: the gaze follows the mouse (app-level event
    filter → the 5x3 iris grid), and it blinks every 2–5 s. dismiss() (or
    /clear via stop()) removes it. set_mouth() re-renders with a speaking
    frame — the hook phase 4's typing loop drives.
    """

    def __init__(self, console):
        super().__init__(console)
        self.console = console
        self.output = console.output
        self._state = "gone"        # gone | summoning | live | dissolving
        self._mode = None
        self._seed = 0
        self._source_cells = None
        self._matrix_final = None   # face pre-padded to the capture width
        self._last_cells = None     # most recent rendered frame
        self._after_dissolve = None
        self._start_cur = None
        self._end_cur = None
        self._iris = (2, 1)
        self._mouth = 0
        self._blink = False
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._blink_timer = QTimer(self)
        self._blink_timer.setSingleShot(True)
        self._blink_timer.timeout.connect(self._blink_now)
        self._raise_timer = QTimer(self)
        self._raise_timer.setSingleShot(True)
        self._raise_timer.timeout.connect(self._begin_playback)
        self._speech_timer = QTimer(self)
        self._speech_timer.setInterval(_SPEECH_TICK_MS)
        self._speech_timer.timeout.connect(self._speech_tick)
        self._speech_lines = None
        self._speech_shown = 0
        self._speech_total = 0
        self._consumed = 0
        self._filter_installed = False
        # Plugin output devours the cat row by row (the grin goes last).
        console.plugin_output_appended.connect(self._on_plugin_output)

    # ── public API ───────────────────────────────────────────────────────

    @property
    def is_present(self) -> bool:
        return self._state != "gone"

    def summon(self, mode: str = "materialize"):
        if self._state != "gone":
            return
        self._mode = mode
        self._seed = random.randrange(1 << 30)
        doc = self.output.document()
        if mode == "matrix":
            # Capture at the console's full character width so progress 0 is
            # the untouched text, with the face condensing dead-center.
            cols = self._viewport_cols()
            self._source_cells = text_to_cells(self._capture_tail_lines(),
                                               width=cols)
            self._matrix_final = pad_cells(compose_face(), cols)
        else:
            self._source_cells = None
            self._matrix_final = None
        # Bookmark the block range: start holds its ground when we insert at
        # it, end rides along to the end of each inserted frame.
        work = QTextCursor(doc)
        work.movePosition(QTextCursor.MoveOperation.End)
        if not work.atBlockStart():
            work.insertBlock()
        pos = work.position()
        self._start_cur = QTextCursor(doc)
        self._start_cur.setPosition(pos)
        self._start_cur.setKeepPositionOnInsert(True)
        self._end_cur = QTextCursor(doc)
        self._end_cur.setPosition(pos)
        self._state = "summoning"
        # Ask the shell for headroom FIRST — the console rises, then the
        # summon plays into a pane that already fits the face.
        self._request_headroom()
        self.render_at(0.0)
        self.console._scroll_to_bottom()
        self._raise_timer.start(_RAISE_SETTLE_MS)

    def _request_headroom(self):
        fm = QFontMetricsF(_cat_font())
        # Face + a separator + the speech section beneath it. The shell may
        # take this from the plugin pane — that's sanctioned.
        rows = len(FACE_ART) + 1 + _SPEECH_LINES_MAX
        rows_px = int(rows * fm.height()) + 30
        chrome = self.console.height() - self.output.viewport().height()
        if not 0 < chrome <= 400:
            chrome = 160        # collapsed/odd geometry — a sane default
        self.console.raise_requested.emit(rows_px + chrome)

    def _begin_playback(self):
        if self._state != "summoning":      # cleared during the raise beat
            return
        self._clock.start()
        self.console._scroll_to_bottom()
        self._timer.start()

    def dismiss(self):
        """Remove the cat from the document and stop every timer."""
        if self._state == "gone":
            return
        self._timer.stop()
        self._blink_timer.stop()
        self._raise_timer.stop()
        self._remove_filter()
        if self._start_cur is not None and self._end_cur is not None:
            cur = QTextCursor(self.output.document())
            cur.setPosition(self._start_cur.position())
            cur.setPosition(self._end_cur.position(),
                            QTextCursor.MoveMode.KeepAnchor)
            cur.removeSelectedText()
        self._reset()

    def stop(self):
        """/clear teardown: the document is being wiped — just reset state."""
        self._timer.stop()
        self._blink_timer.stop()
        self._raise_timer.stop()
        self._remove_filter()
        self._reset()

    def _reset(self):
        self._speech_timer.stop()
        self._start_cur = None
        self._end_cur = None
        self._state = "gone"
        self._mode = None
        self._blink = False
        self._mouth = 0
        self._source_cells = None
        self._matrix_final = None
        self._last_cells = None
        self._after_dissolve = None
        self._speech_lines = None
        self._speech_shown = 0
        self._speech_total = 0
        self._consumed = 0

    def set_mouth(self, frame: int):
        """Directly set the mouth frame (speech drives this internally)."""
        if self._mouth != frame:
            self._mouth = frame
            if self._state == "live":
                self._render_live()

    def speak(self, text: str):
        """Type a line beneath the face, character by character, the mouth
        moving with the typing — the sync is the typing timer itself."""
        if self._state != "live":
            return
        self._speech_lines = (textwrap.wrap(text, _SPEECH_WRAP,
                                            break_on_hyphens=False,
                                            break_long_words=False)
                              [:_SPEECH_LINES_MAX] or [text])
        self._speech_shown = 0
        self._speech_total = sum(len(ln) for ln in self._speech_lines)
        self._speech_timer.start()

    def _speech_tick(self):
        if self._state != "live" or self._speech_lines is None:
            self._speech_timer.stop()
            return
        self._speech_shown += 1
        if self._speech_shown >= self._speech_total:
            self._speech_shown = self._speech_total
            self._speech_timer.stop()
            self._mouth = 0                      # jaw shut, words delivered
        else:
            self._mouth = 1 + (self._speech_shown // 3) % 2
        self._render_live()
        self.console._scroll_to_bottom()         # keep the typing in view

    def _end_speech(self):
        self._speech_timer.stop()
        self._speech_lines = None
        self._speech_shown = 0
        self._speech_total = 0
        self._mouth = 0

    def _speech_rows(self):
        """The speech section: centered bright rows below the face, a block
        cursor riding the type position."""
        if self._speech_lines is None:
            return []
        rows = []
        budget = self._speech_shown
        typing = self._speech_timer.isActive()
        for line in self._speech_lines:
            if budget <= 0:
                break
            visible = line[:budget]
            budget -= len(visible)
            cells = [(ch, "bright") for ch in visible]
            if typing and budget <= 0 and len(cells) < FACE_WIDTH:
                cells.append((_CURSOR, "peak"))
            pad = max(0, (FACE_WIDTH - len(cells)) // 2)
            row = ([(" ", None)] * pad + cells
                   + [(" ", None)] * (FACE_WIDTH - pad - len(cells)))
            rows.append(row)
        return rows

    def _on_plugin_output(self):
        """A plugin printed a line: it eats the cat's top row. The mouth
        band sits lowest, so the grin is the last thing to go."""
        if self._state != "live":
            return
        self._end_speech()
        self._consumed += 1
        if self._consumed >= len(FACE_ART):
            self.dismiss()
        else:
            self._render_live()

    def dissolve(self, then=None):
        """/clear with the cat present: whatever it currently looks like
        decays into rain and dies to darkness, THEN `then` runs (the actual
        clear). Works mid-summon too — it decays from the current frame."""
        if self._state == "gone":
            if then is not None:
                then()
            return
        if self._state == "dissolving":
            return
        self._timer.stop()
        self._blink_timer.stop()
        self._raise_timer.stop()
        self._remove_filter()
        self._mode = "dissolve"
        self._source_cells = (self._last_cells
                              or pad_cells(compose_face(),
                                           self._viewport_cols()))
        self._after_dissolve = then
        self._state = "dissolving"
        self._clock.start()
        self._timer.start()

    def _finish_dissolve(self):
        callback = self._after_dissolve
        self._after_dissolve = None
        self.dismiss()          # state is "dissolving", so this runs fully
        if callback is not None:
            callback()

    # ── summon playback ──────────────────────────────────────────────────

    def _tick(self):
        p = progress_at(TIMELINES[self._mode or "materialize"],
                        self._clock.elapsed())
        self.render_at(p)
        if p >= 1.0:
            self._timer.stop()
            if self._mode == "dissolve":
                self._finish_dissolve()
            else:
                self._go_live()

    def render_at(self, progress: float):
        """Render one animation frame into the document (also the test seam)."""
        if self._mode == "matrix":
            assert self._source_cells is not None
            assert self._matrix_final is not None
            cells = matrix_summon_frame(self._source_cells,
                                        self._matrix_final,
                                        progress, seed=self._seed)
        elif self._mode == "dissolve":
            assert self._source_cells is not None
            blank = [[(" ", None)] * len(self._source_cells[0])
                     for _ in self._source_cells]
            cells = matrix_summon_frame(self._source_cells, blank,
                                        progress, seed=self._seed)
        else:
            final = compose_face(iris=self._iris, mouth=0, blink=False)
            cells = summon_frame(final, progress, seed=self._seed)
        self._render_cells(cells)

    def _go_live(self):
        self._state = "live"
        self._install_filter()
        self._schedule_blink()

    # ── live behaviour ───────────────────────────────────────────────────

    def _render_live(self):
        face = compose_face(iris=self._iris, mouth=self._mouth,
                            blink=self._blink)
        rows = face[self._consumed:] if self._consumed else list(face)
        speech = self._speech_rows()
        if speech:
            rows = rows + [[(" ", None)] * FACE_WIDTH] + speech
        self._render_cells(rows)

    def eventFilter(self, obj, event):
        if (event.type() == QEvent.Type.MouseMove
                and self._state == "live"):
            gaze = self._gaze_from_global(QCursor.pos())
            if gaze != self._iris:
                self._iris = gaze
                self._render_live()
        return False    # observe only — never consume

    def _gaze_from_global(self, global_pos):
        local = self.output.mapFromGlobal(global_pos)
        w = max(1, self.output.width())
        h = max(1, self.output.height())
        ix = min(IRIS_COLS - 1, max(0, int(local.x() / w * IRIS_COLS)))
        iy = min(IRIS_ROWS - 1, max(0, int(local.y() / h * IRIS_ROWS)))
        return (ix, iy)

    def _schedule_blink(self):
        self._blink_timer.start(random.randint(*_BLINK_GAP_MS))

    def _blink_now(self):
        if self._state != "live":
            return
        self._blink = True
        self._render_live()
        QTimer.singleShot(_BLINK_MS, self._blink_done)

    def _blink_done(self):
        self._blink = False
        if self._state == "live":
            self._render_live()
            self._schedule_blink()

    # ── document plumbing ────────────────────────────────────────────────

    def _capture_tail_lines(self):
        """Read and REMOVE the document's last face-height lines — the
        matrix summon's source: the console text the cat corrupts."""
        doc = self.output.document()
        rows = len(FACE_ART)
        first = max(0, doc.blockCount() - rows)
        lines = [doc.findBlockByNumber(i).text()
                 for i in range(first, doc.blockCount())]
        cur = QTextCursor(doc)
        cur.setPosition(doc.findBlockByNumber(first).position())
        cur.movePosition(QTextCursor.MoveOperation.End,
                         QTextCursor.MoveMode.KeepAnchor)
        cur.removeSelectedText()
        return lines

    def _viewport_cols(self) -> int:
        """The console's visible width in the CAT's character cells (never
        narrower than the face). Measured with the pinned cat font — the
        widget font lies whenever a theme stylesheet restyles the console."""
        fm = QFontMetricsF(_cat_font())
        advance = max(1.0, fm.horizontalAdvance("M"))
        return max(FACE_WIDTH,
                   int(self.output.viewport().width() / advance) - 1)

    def _tier_formats(self):
        """One QTextCharFormat per tier, cat font baked in — built once."""
        if not hasattr(self, "_fmt_cache"):
            self._fmt_cache = {}
            font = _cat_font()
            for tier, color in PHOSPHOR.items():
                fmt = QTextCharFormat()
                fmt.setFont(font)
                fmt.setForeground(QColor(color))
                self._fmt_cache[tier] = fmt
            blank = QTextCharFormat()
            blank.setFont(font)
            self._fmt_cache[None] = blank
        return self._fmt_cache

    def _render_cells(self, cells):
        if self._start_cur is None or self._end_cur is None:
            return
        # Center in the console: pad to the live viewport width (no-op for
        # grids already captured at full width — pad_cells never shrinks).
        cells = pad_cells(cells, self._viewport_cols())
        self._last_cells = cells
        fmts = self._tier_formats()
        cur = QTextCursor(self.output.document())
        cur.setPosition(self._start_cur.position())
        cur.setPosition(self._end_cur.position(),
                        QTextCursor.MoveMode.KeepAnchor)
        cur.beginEditBlock()
        cur.removeSelectedText()
        for i, row in enumerate(cells):
            if i:
                cur.insertText("\u2028", fmts[None])  # line sep, same block   # line sep — one block
            run_chars: list[str] = []
            run_tier = "sentinel"
            for ch, tier in row + [("", "sentinel")]:
                if tier != run_tier:
                    if run_chars:
                        cur.insertText("".join(run_chars),
                                       fmts.get(run_tier, fmts[None]))
                    run_chars = []
                    run_tier = tier
                run_chars.append(ch)
        cur.endEditBlock()

    def _install_filter(self):
        if not self._filter_installed:
            app = QApplication.instance()
            if app is not None:
                app.installEventFilter(self)
                self._filter_installed = True

    def _remove_filter(self):
        if self._filter_installed:
            app = QApplication.instance()
            if app is not None:
                app.removeEventFilter(self)
            self._filter_installed = False
