"""The Cheshire Cat — character-grid face art + compositor for the console.

The cat is rendered as colored monospace text INSIDE the console's QTextEdit
(never a widget overlay). The eyes, nose, and blink are TRANSCRIBED from the
reference ASCII cat (reference/cheshire_cat_1088p_frames — the moshi cat),
glyph for glyph; the striped Cheshire grin is ours (the reference cat has no
mouth to speak of, and the grin is the point of this character).

Editing the art (house style — hand-editable grids like MOTH_FRAMES):

  EYE_LEFT / EYE_RIGHT   18x8 glyph grids, '.' = empty. Drawn WITHOUT a
                         pupil — the pupil is stamped at compose time.
  PUPIL                  the 5x3-position gaze stamp: a DIM squiggle patch —
                         a hole in the glow, exactly as in the reference
                         (never a bright cluster).
  NOSE                   the small squiggle cluster between the eyes.
  MOUTH_FRAMES           closed / half / open grin, tier-coded 1/2/3 plus
                         '|' tooth separators. The resting frame already
                         wears the full striped grin.

Brightness comes from a per-character tier map (CHAR_TIER): '·' halo dots are
dim, 'ox=+0' structure chars are mid, '%' field is bright. Blink is DERIVED,
not drawn: every eye glyph collapses to a lid line '—' of the same span, the
pupil squiggle staying faintly visible — the reference's exact behaviour.

Preview any change with `python tools/preview_console_cat.py`.
"""

from __future__ import annotations

# ── components (transcribed) ──────────────────────────────────────────────

EYE_LEFT = [
    ".....··oo··.......",
    "...·ox=%%%%%%xx·..",
    "..·o=%%%%%%%%==%x·",
    "..=%%%%%%%%%+%%=x·",
    ".·o%%%%%%%%%%o%%o·",
    "..x%%%%%%%%%%o%=·.",
    "..·ox=%%%%+%%oo·..",
    "....·oooo··.......",
]

EYE_RIGHT = [
    "......·o··........",
    "...·ox=%%%%%%xx·..",
    "..·=%%%%%%%%=+%%x·",
    "..=%%%%%%%%+%%%%x·",
    ".x%%%%%%%%%%o%=·..",
    ".o%%%%%%%=%%+=·...",
    "..xx=%%%%o%%o·....",
    ".....·oooo···.....",
]

# The gaze stamp — dim squiggles, mid-tier blend chars at the edges. Stamped
# only over field cells so it never escapes the eye.
PUPIL = [
    "+~~~=",
    "~~~~o",
    "+~~oo",
]

NOSE = [
    "~~~~",
    "=%%%%x",
    "=%%~",
]

# closed / half / open — cycled while the cat speaks. The RESTING frame
# already wears the full striped grin (the signature); speaking widens and
# brightens it rather than revealing it.
MOUTH_FRAMES = [
    [
        "33" + "." * 22 + "33",
        ".33" + "22|22|22|22|22|22|22" + "33.",
        "..1" + "1" * 20 + "1..",
    ],
    [
        "333" + "." * 20 + "333",
        ".33" + "33|33|33|33|33|33|33" + "33.",
        "..3" + "3" * 20 + "3..",
    ],
    [
        "333" + "." * 20 + "333",
        "3333|33|33|33|33|33|33|333",
        ".33" + "3" * 20 + "33.",
    ],
]

# ── assembly ──────────────────────────────────────────────────────────────

FACE_WIDTH = 45
EYE_TOP = 0
EYE_LEFT_COL = 2
EYE_RIGHT_COL = 25

_EYE_W = len(EYE_LEFT[0])
_EYE_H = len(EYE_LEFT)


def _assemble_face():
    """Build the full glyph grid from the components. Mouth rows are region
    markers ('M') resolved against MOUTH_FRAMES at compose time."""
    rows = []
    for r in range(_EYE_H):
        row = ["."] * FACE_WIDTH
        for c, ch in enumerate(EYE_LEFT[r]):
            row[EYE_LEFT_COL + c] = ch
        for c, ch in enumerate(EYE_RIGHT[r]):
            row[EYE_RIGHT_COL + c] = ch
        rows.append("".join(row))
    for nose_row in NOSE:
        start = (FACE_WIDTH - len(nose_row)) // 2
        rows.append("." * start + nose_row
                    + "." * (FACE_WIDTH - start - len(nose_row)))
    m_w = len(MOUTH_FRAMES[0][0])
    m_start = (FACE_WIDTH - m_w) // 2
    for _ in MOUTH_FRAMES[0]:
        rows.append("." * m_start + "M" * m_w
                    + "." * (FACE_WIDTH - m_start - m_w))
    return rows


FACE_GRID = _assemble_face()

# The grin's tooth band — what the dissolve erases last.
GRIN_ROW = _EYE_H + len(NOSE) + 1

# 5 x 3 gaze positions (ix 0..4 left→right, iy 0..2 up→down); (2, 1) centers.
IRIS_COLS = 5
IRIS_ROWS = 3

# Phosphor tier palette — classic green CRT. Theme hook comes later; keep
# every color here so a swap is one dict.
PHOSPHOR = {
    "dim": "#1E5A2A",
    "mid": "#2FA84F",
    "bright": "#5CE87A",
}

# Field cells the pupil may stamp over / the blink collapses to lid lines.
_FIELD_CHARS = set("%=x+o0")
CHAR_TIER = {
    "·": "dim", "~": "dim",
    "o": "mid", "x": "mid", "=": "mid", "+": "mid", "0": "mid", "—": "mid",
    "%": "bright", "|": "bright", "@": "bright",
}
# Nose squiggles read clearly in the reference — mid, not pupil-dim.
_NOSE_TIER = {"~": "mid"}

_TIER_CHARS = {"1": ("·",), "2": ("=", "%", "=", "~"), "3": ("%", "@", "%", "%")}
_TIER_OF = {"1": "dim", "2": "mid", "3": "bright"}
_BLINK_CHAR = "—"

# Pupil travel: interior of each eye (inset from the rim) minus stamp size.
_PUPIL_H = len(PUPIL)
_PUPIL_W = len(PUPIL[0])
_PUPIL_ROW_MIN = 1
_PUPIL_ROW_MAX = _EYE_H - 2 - _PUPIL_H   # bottom rim row excluded
_PUPIL_COL_MIN = 3
_PUPIL_COL_MAX = _EYE_W - 3 - _PUPIL_W


def _pick(seq, r: int, c: int) -> str:
    return seq[(c * 7 + r * 13) % len(seq)]


def _pupil_origin(ix: int, iy: int):
    """Stamp origin (within one eye's local grid) for gaze (ix, iy)."""
    row = _PUPIL_ROW_MIN + round(
        (_PUPIL_ROW_MAX - _PUPIL_ROW_MIN) * iy / (IRIS_ROWS - 1))
    col = _PUPIL_COL_MIN + round(
        (_PUPIL_COL_MAX - _PUPIL_COL_MIN) * ix / (IRIS_COLS - 1))
    return row, col


def compose_face(iris=(2, 1), mouth: int = 0, blink: bool = False):
    """Compose one face frame.

    Returns a rectangular grid (list of rows) of (char, tier) cells where
    tier is a PHOSPHOR key, or (" ", None) for empty cells.

    iris:  (ix, iy) in the 5x3 gaze grid; both eyes move together.
    mouth: index into MOUTH_FRAMES.
    blink: eyes collapse to lid lines of the same span, the pupil squiggle
           staying faintly visible (the reference's blink).
    """
    ix, iy = iris
    if not (0 <= ix < IRIS_COLS and 0 <= iy < IRIS_ROWS):
        raise ValueError(f"iris out of range: {iris!r}")
    frame = MOUTH_FRAMES[mouth]
    p_row, p_col = _pupil_origin(ix, iy)

    out = []
    for r, row in enumerate(FACE_GRID):
        out_row = []
        for c, ch in enumerate(row):
            if ch == ".":
                out_row.append((" ", None))
                continue
            if ch == "M":
                m_start = row.index("M")
                m_ch = frame[r - GRIN_ROW + 1][c - m_start]
                if m_ch == ".":
                    out_row.append((" ", None))
                elif m_ch == "|":
                    out_row.append(("|", "bright"))
                else:
                    out_row.append((_pick(_TIER_CHARS[m_ch], r, c),
                                    _TIER_OF[m_ch]))
                continue
            # Eye cells: pupil stamp, then blink collapse, then the glyph.
            in_eye = r < _EYE_H
            if in_eye:
                local_col = None
                if EYE_LEFT_COL <= c < EYE_LEFT_COL + _EYE_W:
                    local_col = c - EYE_LEFT_COL
                elif EYE_RIGHT_COL <= c < EYE_RIGHT_COL + _EYE_W:
                    local_col = c - EYE_RIGHT_COL
                if (local_col is not None
                        and p_row <= r - EYE_TOP < p_row + _PUPIL_H
                        and p_col <= local_col < p_col + _PUPIL_W
                        and ch in _FIELD_CHARS):
                    p_ch = PUPIL[r - EYE_TOP - p_row][local_col - p_col]
                    out_row.append((p_ch, CHAR_TIER[p_ch]))
                    continue
                if blink:
                    out_row.append((_BLINK_CHAR, "mid"))
                    continue
                out_row.append((ch, CHAR_TIER[ch]))
                continue
            # Nose rows.
            tier = _NOSE_TIER.get(ch, CHAR_TIER[ch])
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
