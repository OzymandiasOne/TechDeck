"""The Cheshire Cat — character-grid face art + compositor for the console.

The cat is rendered as colored monospace text INSIDE the console's QTextEdit
(never a widget overlay), in the phosphor-terminal style of the reference set:
character density carries brightness. This module owns the ART and the pure
COMPOSITOR; the animator that writes frames into the console document lives
with the console wiring (phase 3).

Editing the art (house style — hand-editable grids like the moth's
MOTH_FRAMES and the fidget's SPINNER_ART):

FACE_GRID legend (every row exactly the same length):
  .  empty
  1  dim glow        (sparse halo char)
  2  mid glow
  3  bright glow
  L  left eye socket  (textured field computed at render time; iris stamps here)
  R  right eye socket
  M  mouth region     (rows replaced by the active MOUTH_FRAMES frame)

MOUTH_FRAMES: three frames (closed / half / open), each exactly the size of
the M region. Same 1/2/3 tiers, plus '|' — a tooth separator, drawn verbatim
at bright tier (the striped Cheshire grin).

The socket texture, rim detection, and iris clipping are computed at render
time from the shapes (precedent: the fidget auto-traces its outline). Preview
any change with `python tools/preview_console_cat.py`.
"""

from __future__ import annotations

FACE_GRID = [
    "......1............................1......",
    ".....131..........................131.....",
    "....13331........................13331....",
    "...133333331..................133333331...",
    "......LLLLLLLLL............RRRRRRRRR......",
    ".....LLLLLLLLLLL..........RRRRRRRRRRR.....",
    "....LLLLLLLLLLLLL........RRRRRRRRRRRRR....",
    "....LLLLLLLLLLLLL........RRRRRRRRRRRRR....",
    ".....LLLLLLLLLLL..........RRRRRRRRRRR.....",
    "......LLLLLLLLL............RRRRRRRRR......",
    "...................1221...................",
    "........MMMMMMMMMMMMMMMMMMMMMMMMMM........",
    "........MMMMMMMMMMMMMMMMMMMMMMMMMM........",
    "........MMMMMMMMMMMMMMMMMMMMMMMMMM........",
]

# closed / half / open — cycled while the cat speaks. The RESTING frame
# already wears the full striped grin (the signature — the cat grins at
# rest); speaking widens and brightens it rather than revealing it.
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

# The grin alone — what remains mid-dissolve (phase 4) and the last thing
# plugin output erases.
GRIN_ROW = 12   # FACE_GRID row where the grin's tooth band sits

# 5 x 3 iris positions (ix 0..4 left→right, iy 0..2 up→down), matching the
# reference recipe's pre-generated frame grid. (2, 1) is dead center.
IRIS_COLS = 5
IRIS_ROWS = 3
IRIS_W = 4
IRIS_H = 2

# Phosphor tier palette — classic green CRT. Theme hook comes later; keep
# every color here so a swap is one dict.
PHOSPHOR = {
    "dim": "#1E5A2A",
    "mid": "#2FA84F",
    "bright": "#5CE87A",
    "iris": "#B6FFC6",
}

# Deterministic per-cell character choice (stable across frames — the face
# must not shimmer while idle). Indexed by (x * 7 + y * 13) % len.
_TIER_CHARS = {
    "1": ("·",),                    # ·
    "2": ("=", "%", "=", "~"),
    "3": ("%", "@", "%", "%"),
}
_SOCKET_INTERIOR = ("%", "=", "%", "~", "=", "%")
_SOCKET_RIM = ("·", "·", "·", "o")
_BLINK_CHAR = "—"                   # — (lid line)
_IRIS_CHAR = "@"

_TIER_OF = {"1": "dim", "2": "mid", "3": "bright"}


def _grid_dims():
    return len(FACE_GRID), len(FACE_GRID[0])


def _socket_cells(marker: str):
    """All (row, col) of one eye socket, plus its bounding box."""
    cells = set()
    for r, row in enumerate(FACE_GRID):
        for c, ch in enumerate(row):
            if ch == marker:
                cells.add((r, c))
    rows = [r for r, _ in cells]
    cols = [c for _, c in cells]
    bbox = (min(rows), min(cols), max(rows), max(cols))
    return cells, bbox


def _iris_origin(bbox, ix: int, iy: int):
    """Top-left cell of the iris stamp for grid position (ix, iy)."""
    r0, c0, r1, c1 = bbox
    span_w = (c1 - c0 + 1) - IRIS_W
    span_h = (r1 - r0 + 1) - IRIS_H
    col = c0 + round(span_w * ix / (IRIS_COLS - 1))
    row = r0 + round(span_h * iy / (IRIS_ROWS - 1))
    return row, col


def _pick(seq, r: int, c: int) -> str:
    return seq[(c * 7 + r * 13) % len(seq)]


def compose_face(iris=(2, 1), mouth: int = 0, blink: bool = False):
    """Compose one face frame.

    Returns a rectangular grid (list of rows) of (char, tier) cells where
    tier is a PHOSPHOR key, or (" ", None) for empty cells.

    iris:  (ix, iy) in the 5x3 gaze grid; both eyes move together.
    mouth: index into MOUTH_FRAMES.
    blink: closed lids — irises hidden, sockets collapse to lid lines.
    """
    ix, iy = iris
    if not (0 <= ix < IRIS_COLS and 0 <= iy < IRIS_ROWS):
        raise ValueError(f"iris out of range: {iris!r}")
    frame = MOUTH_FRAMES[mouth]

    left_cells, left_bbox = _socket_cells("L")
    right_cells, right_bbox = _socket_cells("R")
    sockets = left_cells | right_cells
    iris_cells = set()
    if not blink:
        for cells, bbox in ((left_cells, left_bbox), (right_cells, right_bbox)):
            r0, c0 = _iris_origin(bbox, ix, iy)
            for dr in range(IRIS_H):
                for dc in range(IRIS_W):
                    if (r0 + dr, c0 + dc) in cells:   # clip to the shape
                        iris_cells.add((r0 + dr, c0 + dc))

    # Lid line rows: the middle of each socket's bbox when blinking.
    lid_rows = set()
    if blink:
        for r0, _, r1, _ in (left_bbox, right_bbox):
            mid = (r0 + r1) // 2
            lid_rows.update((mid, mid + 1))

    mouth_rows = [r for r, row in enumerate(FACE_GRID) if "M" in row]
    mouth_start_col = FACE_GRID[mouth_rows[0]].index("M")

    out = []
    for r, row in enumerate(FACE_GRID):
        out_row = []
        for c, ch in enumerate(row):
            if ch == ".":
                out_row.append((" ", None))
            elif ch in _TIER_OF:
                out_row.append((_pick(_TIER_CHARS[ch], r, c), _TIER_OF[ch]))
            elif ch in ("L", "R"):
                if blink:
                    if r in lid_rows:
                        out_row.append((_BLINK_CHAR, "mid"))
                    else:
                        out_row.append((" ", None))
                elif (r, c) in iris_cells:
                    out_row.append((_IRIS_CHAR, "iris"))
                else:
                    # Rim cells (any 4-neighbour outside the socket) render
                    # sparse; the interior renders as the dense field.
                    neighbours = ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1))
                    rim = any(n not in sockets for n in neighbours)
                    seq = _SOCKET_RIM if rim else _SOCKET_INTERIOR
                    tier = "dim" if rim else "mid"
                    out_row.append((_pick(seq, r, c), tier))
            elif ch == "M":
                m_row = frame[r - mouth_rows[0]]
                m_ch = m_row[c - mouth_start_col]
                if m_ch == ".":
                    out_row.append((" ", None))
                elif m_ch == "|":
                    out_row.append(("|", "bright"))
                else:
                    out_row.append((_pick(_TIER_CHARS[m_ch], r, c),
                                    _TIER_OF[m_ch]))
            else:
                raise ValueError(f"unknown grid char {ch!r} at {(r, c)}")
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
