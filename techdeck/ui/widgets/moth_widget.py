"""
TechDeck Moth Widget
A small PIXEL-ART moth that flies in from a random screen edge to a random empty
spot (never onto a button), then perches and flutters its wings occasionally.
About 30s after it lands it shows a manufacturing haiku in a themed speech
bubble, and again every ~10 minutes after. Coloured to the active theme.
/moth sends it somewhere new. Double-click to shoo it away entirely.
"""

import math
import random
import sys
from pathlib import Path
from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import Qt, QTimer, QPoint, QRectF, QEvent
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics, QFontDatabase


# ── Haiku font (FOT Bokutoh Pro, bundled in assets/fonts) ───────────────────
# Drop the FOT Bokutoh Pro .otf/.ttf into assets/fonts/ and it's picked up here;
# until then the bubble falls back to a default italic face. Resolved once.
_HAIKU_FAMILY: str | None = None
_HAIKU_FONT_RESOLVED = False


def _assets_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets"
    return Path(__file__).resolve().parents[3] / "assets"


def haiku_font(point_size: int) -> QFont:
    """Return the FOT Bokutoh Pro font if bundled, else a default italic fallback."""
    global _HAIKU_FAMILY, _HAIKU_FONT_RESOLVED
    if not _HAIKU_FONT_RESOLVED:
        _HAIKU_FONT_RESOLVED = True
        fonts_dir = _assets_dir() / "fonts"
        families: list[str] = []
        if fonts_dir.is_dir():
            for f in sorted(fonts_dir.iterdir()):
                if f.suffix.lower() in (".otf", ".ttf", ".ttc"):
                    fid = QFontDatabase.addApplicationFont(str(f))
                    if fid != -1:
                        families += QFontDatabase.applicationFontFamilies(fid)
        _HAIKU_FAMILY = next(
            (fam for fam in families if "bokutoh" in fam.lower()),
            families[0] if families else None)
    if _HAIKU_FAMILY:
        font = QFont(_HAIKU_FAMILY)
    else:
        font = QFont()
        font.setItalic(True)
    font.setPointSize(point_size)
    return font

# ── Moth sound pool ────────────────────────────────────────────────────────────
# Module-level so the pool persists across /moth invocations (new MothWidget
# instances). Exhausts all 11 voices before cycling; never repeats back-to-back.

_MOTH_SOUND_IDS = [f"moth_voice_{i}" for i in range(1, 12)]
_moth_pool: list = []
_moth_last: str | None = None


def _next_moth_sound() -> str:
    global _moth_pool, _moth_last
    if not _moth_pool:
        _moth_pool = [s for s in _MOTH_SOUND_IDS if s != _moth_last]
        if not _moth_pool:           # safety: only 1 sound registered
            _moth_pool = list(_MOTH_SOUND_IDS)
        random.shuffle(_moth_pool)
    sound = _moth_pool.pop()
    _moth_last = sound
    return sound


# ── Pixel-art wing-flutter frames (generated via tools/_scratch_moth.py) ─────
# 19x14 grids; "X" = a filled cell painted in the theme colour. Frame 0 = wings
# spread (rest), 2 = wings raised; cycling them animates a flutter.
MOTH_FRAMES = [
    [
        ".....X.......X.....",
        "......X.....X......",
        "......XX...XX......",
        "........X.X........",
        "....XX..XXX..XX....",
        "..XXXXXXXXXXXXXXX..",
        ".XXXXXXXXXXXXXXXXX.",
        ".XXXXXXXXXXXXXXXXX.",
        "..XXXXXXXXXXXXXXX..",
        "........XXX........",
        "....XXXXXXXXXXX....",
        "....XXXXXXXXXXX....",
        "....XXXX.X.XXXX....",
        ".....XXX.X.XXX.....",
    ],
    [
        ".....X.......X.....",
        "......X.....X......",
        "......XX...XX......",
        "........X.X........",
        "....XXX.XXX.XXX....",
        "...XXXXXXXXXXXXX...",
        "...XXXXXXXXXXXXX...",
        "...XXXXXXXXXXXXX...",
        "....XXXXXXXXXXX....",
        "........XXX........",
        ".....XXXXXXXXX.....",
        ".....XXXXXXXXX.....",
        ".....XXXXXXXXX.....",
        ".....XXX.X.XXX.....",
    ],
    [
        "......X.....X......",
        ".......X...X.......",
        "........X.X........",
        "...................",
        ".....XXXXXXXXX.....",
        "....XXXXXXXXXXX....",
        "....XXXXXXXXXXX....",
        "....XXXXXXXXXXX....",
        ".....XXXXXXXXX.....",
        "........XXX........",
        "......XXXXXXX......",
        "......XXXXXXX......",
        "......XXXXXXX......",
        "......XX.X.XX......",
    ],
]
_GRID_W = len(MOTH_FRAMES[0][0])
_GRID_H = len(MOTH_FRAMES[0])


# ── Editable speech-bubble art (hand-drawn, like MOTH_FRAMES) ───────────────
# Edit these two grids to redesign the bubble. They are stamped/mirrored by the
# renderer, so the bubble still auto-sizes to the text — you draw the CORNER and
# TAIL, the straight edges + middle stretch to fit.
#
# BUBBLE_CORNER: the TOP-LEFT corner shape. 'x' = inside the bubble (gets filled,
#   with its outer edge drawn as the border), '.' = outside (transparent). It is
#   mirrored to the other three corners. Keep it square. The bottom row + right
#   column define the straight edge thickness, so keep those solid 'x'.
BUBBLE_CORNER = [
    "....xxx",
    "..xxxxx",
    ".xxxxxx",
    ".xxxxxx",
    "xxxxxxx",
    "xxxxxxx",
    "xxxxxxx",
]
# BUBBLE_TAIL: the tail for the BOTTOM-LEFT corner (points down-left); mirrored
#   for the other corners. 'x' = tail (drawn in the frame colour), 't' = the tip
#   cell that points at the moth, '.' = transparent. Its corner nearest the box
#   (here the top-right) attaches to the box corner.
BUBBLE_TAIL = [
    "...xx",
    "..xxx",
    ".xxx.",
    "xxxt.",
    "xt...",
]


class SpeechBubble(QWidget):
    """A PIXEL-ART speech bubble (Animal-Crossing-style) that types its text out
    one letter at a time. Its shape is hand-drawn in BUBBLE_CORNER / BUBBLE_TAIL
    (above) and stamped/mirrored here; the straight edges + middle stretch so the
    bubble auto-sizes to the text. Themed: surface fill, accent border + tail,
    distinct text colour.
    """

    CELL = 4                # px per pixel-art cell
    PAD_PX = 11             # interior breathing room around the text
    REVEAL_MS = 55          # per-character typing speed
    FONT_PT = 11
    # Margin reserved around the box for the tail (from the tail grid's size).
    TAIL_MARGIN = max(len(BUBBLE_TAIL), len(BUBBLE_TAIL[0]))
    TAIL_OVERLAP = 2        # cells the tail base overlaps into the box (to connect)

    def __init__(self, text: str, fg: QColor, bg: QColor, frame: QColor,
                 corner: str = "bl", parent=None):
        super().__init__(parent)
        self._fg, self._bg, self._frame = fg, bg, frame
        self._corner = corner                # 'bl'/'br'/'tl'/'tr' = corner the tail leaves from
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._font = haiku_font(self.FONT_PT)
        # Antialias + no aggressive hinting -> uniform glyph sizes (full hinting at
        # small sizes can pixel-snap some letters larger than others).
        self._font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        self._font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        self._fm = QFontMetrics(self._font)
        self._lines = text.split("\n")
        self._lh = self._fm.height()
        # Width via tight ink bounds (handles italic/brush overhang) + padding.
        tw = max((self._fm.boundingRect(ln).width() for ln in self._lines), default=40)
        th = self._lh * len(self._lines)

        S = self.CELL
        self._C = len(BUBBLE_CORNER)                          # corner size (square)
        # Box must be at least two corners wide/tall so the corners don't overlap.
        self._cols = max(math.ceil((tw + self.PAD_PX * 2) / S) + 2, 2 * self._C)
        self._rows = max(math.ceil((th + self.PAD_PX * 2) / S) + 2, 2 * self._C)
        TM = self.TAIL_MARGIN
        self.setFixedSize((self._cols + TM) * S, (self._rows + TM) * S)

        # Typewriter reveal across all lines.
        self._revealed = 0
        self._total = sum(len(ln) for ln in self._lines)
        self._reveal_timer = QTimer(self)
        self._reveal_timer.setInterval(self.REVEAL_MS)
        self._reveal_timer.timeout.connect(self._reveal_step)
        self._reveal_timer.start()

    def set_tail(self, corner: str):
        """Which corner the tail leaves from: bl/br = bubble above the moth,
        tl/tr = below; l/r picks the near side."""
        self._corner = corner
        self.update()

    def _box_off(self, corner=None):
        """(box_x_cells, box_y_cells): where the box sits, leaving tail margin."""
        c = corner or self._corner
        TM = self.TAIL_MARGIN
        return (TM if c in ("bl", "tl") else 0,
                TM if c in ("tl", "tr") else 0)

    def _inside(self, cx, cy) -> bool:
        """Is box cell (cx, cy) inside the bubble? Corners come from BUBBLE_CORNER
        (mirrored); everything between the corners is inside."""
        C, cols, rows = self._C, self._cols, self._rows
        left, right = cx < C, cx >= cols - C
        top, bot = cy < C, cy >= rows - C
        if top and left:
            return BUBBLE_CORNER[cy][cx] == "x"
        if top and right:
            return BUBBLE_CORNER[cy][(C - 1) - (cx - (cols - C))] == "x"
        if bot and left:
            return BUBBLE_CORNER[(C - 1) - (cy - (rows - C))][cx] == "x"
        if bot and right:
            return BUBBLE_CORNER[(C - 1) - (cy - (rows - C))][(C - 1) - (cx - (cols - C))] == "x"
        return True

    def _oriented_tail(self, corner=None):
        """BUBBLE_TAIL placed (mirrored) at `corner`: (filled widget cells, tip)."""
        c = corner or self._corner
        g = BUBBLE_TAIL
        if c in ("br", "tr"):
            g = [row[::-1] for row in g]          # mirror left<->right
        if c in ("tl", "tr"):
            g = g[::-1]                            # mirror up<->down
        ht, wt = len(g), len(g[0])
        box_x, box_y = self._box_off(c)
        cols, rows = self._cols, self._rows
        # Attach the tail's near-corner cell a few cells INTO the solid box
        # (diagonally toward the centre), so its base overlaps the filled corner
        # instead of the rounded-away corner cell -> it always connects.
        ov = self.TAIL_OVERLAP
        if c == "bl":
            bcx, bcy, acx, acy = box_x + ov, box_y + rows - 1 - ov, wt - 1, 0
        elif c == "br":
            bcx, bcy, acx, acy = box_x + cols - 1 - ov, box_y + rows - 1 - ov, 0, 0
        elif c == "tl":
            bcx, bcy, acx, acy = box_x + ov, box_y + ov, wt - 1, ht - 1
        else:  # tr
            bcx, bcy, acx, acy = box_x + cols - 1 - ov, box_y + ov, 0, ht - 1
        cells, tip = [], None
        for r in range(ht):
            for col in range(wt):
                ch = g[r][col]
                if ch == ".":
                    continue
                w = (bcx + (col - acx), bcy + (r - acy))
                cells.append(w)
                if ch == "t":
                    tip = w
        if tip is None:
            tip = cells[-1] if cells else (bcx, bcy)
        return cells, tip

    def tip_offset(self, corner: str):
        """Pixel offset of the tail tip from the widget's top-left, for `corner`."""
        _, tip = self._oriented_tail(corner)
        S = self.CELL
        return (tip[0] * S + S // 2, tip[1] * S + S // 2)

    def _reveal_step(self):
        self._revealed += 1
        if self._revealed >= self._total:
            self._reveal_timer.stop()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        # Pixel cells are integer-aligned rects (AA can't blur them), but text
        # needs antialiasing or letters render unevenly at this size.
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        S = self.CELL
        cols, rows = self._cols, self._rows
        box_x, box_y = self._box_off()

        # Tail (drawn first so the box edge overlaps its base).
        for wx, wy in self._oriented_tail()[0]:
            p.fillRect(wx * S, wy * S, S, S, self._frame)

        # Box: hand-drawn corner shape, surface fill, accent border (an inside
        # cell adjacent to outside / the grid edge).
        for cy in range(rows):
            for cx in range(cols):
                if not self._inside(cx, cy):
                    continue
                border = (cx == 0 or cy == 0 or cx == cols - 1 or cy == rows - 1
                          or not self._inside(cx - 1, cy) or not self._inside(cx + 1, cy)
                          or not self._inside(cx, cy - 1) or not self._inside(cx, cy + 1))
                p.fillRect((box_x + cx) * S, (box_y + cy) * S, S, S,
                           self._frame if border else self._bg)

        # Typewriter text, centered in the interior; prefix drawn left-aligned at
        # the full line's centered start so it types left-to-right.
        p.setPen(self._fg)
        p.setFont(self._font)
        iw = (cols - 2) * S
        interior_h = (rows - 2) * S
        ty = (box_y + 1) * S + (interior_h - self._lh * len(self._lines)) / 2.0
        remaining = self._revealed
        for i, line in enumerate(self._lines):
            take = max(0, min(len(line), remaining))
            remaining -= len(line)
            if take <= 0:
                continue
            lw = self._fm.boundingRect(line).width()
            x0 = (box_x + 1) * S + (iw - lw) / 2.0
            p.drawText(QRectF(x0, ty + i * self._lh, lw + 6, self._lh),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       line[:take])
        p.end()


class MothWidget(QWidget):
    """
    Frameless, translucent pixel-art moth painted in the theme colour. Flies to a
    global point, perches, and flutters occasionally; shows haikus on a delay.
    """

    CELL = 2                                  # px per pixel-art cell
    SIZE_W = _GRID_W * CELL
    SIZE_H = _GRID_H * CELL

    FLY_SEQ = [0, 1, 2, 1]                    # fast flutter while in flight
    MAX_FLY_TICKS = 240                       # ~3.8s fail-safe: always land by then
    # On landing: a couple of flaps that visibly SLOW DOWN (per-frame delay ramps
    # up) so the moth eases to a graceful, still stop. (frame, ms-until-next).
    SETTLE = [(1, 90), (2, 110), (1, 135), (0, 165),
              (1, 205), (2, 255), (1, 320), (0, 400)]
    IDLE_FLAP_MS = 165                        # slow, gentle beat for idle flutters
    IDLE_FLAPS = (1, 3)                        # "just a few" on each random flutter
    IDLE_MIN_MS, IDLE_MAX_MS = 5000, 15000    # long stills between flutters
    HAIKU_FIRST_MIN_MS, HAIKU_FIRST_MAX_MS = 20_000, 50_000  # first haiku within a minute
    SPEAK_EVERY_MS = 200_000                  # then it speaks every ~3.3 min...
    HAIKU_EVERY_SPEAKS = 3                     # ...every 3rd is a haiku (~10 min apart)
    HAIKU_VISIBLE_MS = 13_000                 # how long a bubble lingers

    def __init__(self, color: QColor | None = None, parent=None):
        super().__init__(parent)
        self._color = color if color is not None else QColor(30, 30, 30, 230)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.SIZE_W, self.SIZE_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._frame_idx = 0
        self._fly_tick = 0
        self._flying = False
        self._target_point: QPoint | None = None
        self._landed = False
        self._fx = 0.0           # true float position (window pos is rounded)
        self._fy = 0.0
        self._host = None        # main window we follow / minimize with
        self._host_pos = None
        self._host_hid = False   # we hid because the host minimized/hid

        # Speech state (haiku + Japanese-philosophy musings in between)
        self._haiku_provider = None
        self._musing_provider = None
        self._speak_count = 0
        self._bubble_colors: tuple[QColor, QColor, QColor] | None = None
        self._bubble: SpeechBubble | None = None

        # Movement during flight
        self._move_timer = QTimer(self)
        self._move_timer.setInterval(16)
        self._move_timer.timeout.connect(self._tick)

        # Flutter: a (frame, delay) sequence stepped by a single-shot timer whose
        # delay is re-set per step (so flaps can slow down); scheduled by _idle_timer.
        self._flap_seq: list[tuple[int, int]] = []
        self._flap_timer = QTimer(self)
        self._flap_timer.setSingleShot(True)
        self._flap_timer.timeout.connect(self._flap_step)
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._start_flutter)

        # Speech timers: first utterance soon after landing, then on a cadence.
        self._first_speak = QTimer(self)
        self._first_speak.setSingleShot(True)
        self._first_speak.timeout.connect(self._do_speak)
        self._speak_timer = QTimer(self)
        self._speak_timer.setInterval(self.SPEAK_EVERY_MS)
        self._speak_timer.timeout.connect(self._do_speak)
        self._bubble_hide = QTimer(self)
        self._bubble_hide.setSingleShot(True)
        self._bubble_hide.timeout.connect(self._hide_bubble)

    # ── public API ──────────────────────────────────────────────────────────
    def set_color(self, color: QColor):
        """Re-theme the moth (e.g. on a later /moth after a theme switch)."""
        self._color = color
        self.update()

    def configure_speech(self, haiku_provider, musing_provider,
                         fg: QColor, bg: QColor, frame: QColor):
        """haiku_provider()/musing_provider() -> str; fg/bg/frame colour the bubble."""
        self._haiku_provider = haiku_provider
        self._musing_provider = musing_provider
        self._bubble_colors = (fg, bg, frame)

    def attach_to(self, host):
        """Follow the host window: move with it and hide while it's minimized."""
        if host is None or host is self._host:
            if host is not None:
                self._host_pos = host.frameGeometry().topLeft()
            return
        if self._host is not None:
            try:
                self._host.removeEventFilter(self)
            except RuntimeError:
                pass
        self._host = host
        self._host_pos = host.frameGeometry().topLeft()
        host.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self._host:
            et = event.type()
            if et == QEvent.Type.Move:
                new = self._host.frameGeometry().topLeft()
                delta = new - self._host_pos
                self._host_pos = new
                if not delta.isNull():
                    self._shift_by(delta)
            elif et == QEvent.Type.WindowStateChange:
                (self._hide_for_host if self._host.isMinimized()
                 else self._show_for_host)()
            elif et == QEvent.Type.Hide:
                self._hide_for_host()
            elif et == QEvent.Type.Show:
                self._show_for_host()
        return super().eventFilter(obj, event)

    def _shift_by(self, delta: QPoint):
        """Move the moth (and any bubble + flight state) by the host's move delta."""
        self.move(self.pos() + delta)
        self._fx += delta.x()
        self._fy += delta.y()
        if self._target_point is not None:
            self._target_point += delta
        if self._bubble is not None:
            self._bubble.move(self._bubble.pos() + delta)

    def _hide_for_host(self):
        if self.isVisible():
            self._host_hid = True
            self.hide()
        if self._bubble is not None:
            self._bubble.hide()

    def _show_for_host(self):
        if self._host_hid:
            self._host_hid = False
            self.show()
            self.raise_()
            if self._bubble is not None:
                self._bubble.show()
                self._bubble.raise_()

    def fly_to(self, point: QPoint):
        """Set a new global target point and start flying."""
        self._hide_bubble()
        self._cancel_idle_and_haiku()
        self._target_point = QPoint(point)
        self._flying = True
        self._landed = False
        self._fly_tick = 0
        self._fx, self._fy = float(self.x()), float(self.y())
        self._move_timer.start()
        self.show()
        self.raise_()

    def spawn_from_edge(self, point: QPoint):
        """Pick a random screen edge, start there, then fly to the point."""
        screen = QApplication.primaryScreen().geometry()
        edge = random.choice(["top", "bottom", "left", "right"])
        if edge == "top":
            x, y = random.randint(screen.left(), screen.right()), screen.top() - self.SIZE_H
        elif edge == "bottom":
            x, y = random.randint(screen.left(), screen.right()), screen.bottom() + self.SIZE_H
        elif edge == "left":
            x, y = screen.left() - self.SIZE_W, random.randint(screen.top(), screen.bottom())
        else:
            x, y = screen.right() + self.SIZE_W, random.randint(screen.top(), screen.bottom())
        self.move(x, y)
        self.fly_to(point)

    # ── flight ──────────────────────────────────────────────────────────────
    def _target_top_left(self) -> QPoint | None:
        if self._target_point is None:
            return None
        return self._target_point - QPoint(self.SIZE_W // 2, self.SIZE_H // 2)

    def _tick(self):
        target = self._target_top_left()
        if target is None:
            self._move_timer.stop()
            return

        # flap while flying
        self._fly_tick += 1
        self._frame_idx = self.FLY_SEQ[(self._fly_tick // 3) % len(self.FLY_SEQ)]

        # Track the true position in floats so sub-pixel steering accumulates
        # (rounding the window pos each tick would stall the drift near the target
        # and it would never reach the threshold). Fail-safe lands a stuck flight.
        dx, dy = target.x() - self._fx, target.y() - self._fy
        dist = math.hypot(dx, dy)
        if dist < 3 or self._fly_tick > self.MAX_FLY_TICKS:
            self.move(target)
            self._fx, self._fy = float(target.x()), float(target.y())
            self._move_timer.stop()
            self._flying = False
            self._frame_idx = 0
            if not self._landed:
                self._landed = True
                self._on_landed()
        else:
            speed = min(dist * 0.085, 12.0)
            wander = min(1.0, dist / 26.0)   # calm the wobble as it nears
            self._fx += dx / dist * speed + random.uniform(-1, 1) * wander
            self._fy += dy / dist * speed + random.uniform(-1, 1) * wander
            self.move(round(self._fx), round(self._fy))
        self.update()

    def _on_landed(self):
        # Ease to a stop with a couple of decelerating flaps, then go still; the
        # flutter's completion schedules the next occasional flutter.
        self._settle()
        # Random starting phase so the FIRST message is sometimes a haiku,
        # sometimes a musing (haikus still recur every HAIKU_EVERY_SPEAKS).
        self._speak_count = random.randint(0, self.HAIKU_EVERY_SPEAKS - 1)
        self._first_speak.start(
            random.randint(self.HAIKU_FIRST_MIN_MS, self.HAIKU_FIRST_MAX_MS))

    # ── flutter (slow & graceful, then still) ───────────────────────────────
    def _play_flaps(self, seq):
        """Play a (frame, delay-ms) sequence; _flap_step goes still after."""
        self._flap_seq = list(seq)
        if not self._flap_timer.isActive():
            self._flap_step()

    def _settle(self):
        """The decelerating landing flutter -> graceful, still stop."""
        self._play_flaps(self.SETTLE)

    def _start_flutter(self):
        """An occasional gentle idle flutter: a few slow, even-paced beats."""
        n = random.randint(*self.IDLE_FLAPS)
        self._play_flaps([(f, self.IDLE_FLAP_MS) for _ in range(n) for f in (1, 2, 1, 0)])

    def _flap_step(self):
        if self._flap_seq:
            frame, delay = self._flap_seq.pop(0)
            self._frame_idx = frame
            self.update()
            self._flap_timer.start(delay)
        else:
            self._frame_idx = 0
            self.update()
            self._idle_timer.start(random.randint(self.IDLE_MIN_MS, self.IDLE_MAX_MS))

    # ── speech (haiku + musings) ────────────────────────────────────────────
    def _do_speak(self):
        if self._bubble_colors is None:
            return
        # Every Nth utterance is a haiku; the rest are musings (the "in between").
        is_haiku = (self._speak_count % self.HAIKU_EVERY_SPEAKS == 0)
        provider = self._haiku_provider if is_haiku else self._musing_provider
        self._speak_count += 1
        if provider is None:
            return
        try:
            text = provider()
        except Exception:
            return
        fg, bg, frame = self._bubble_colors
        self._hide_bubble()
        self._bubble = SpeechBubble(text, fg, bg, frame)
        pos, corner = self._bubble_place()
        self._bubble.set_tail(corner)
        self._bubble.show()
        self._bubble.move(pos)
        self._bubble.raise_()
        self._bubble_hide.start(self.HAIKU_VISIBLE_MS)
        if not self._speak_timer.isActive():
            self._speak_timer.start()

    def _bubble_place(self):
        """Position the bubble beside/above the moth (clamped); return (pos, corner).

        The body extends toward whichever side has more room, and the tail leaves
        the near corner diagonally onto the moth. Tail from a BOTTOM corner (bubble
        above the moth) by default; from a TOP corner (below) if there's no room.
        """
        screen = QApplication.primaryScreen().availableGeometry()
        bw, bh = self._bubble.width(), self._bubble.height()
        moth_cx = self.x() + self.SIZE_W // 2
        gap = 8
        left = moth_cx <= (screen.left() + screen.right()) // 2   # moth on left -> tail on left

        # Prefer above: bottom corner, tip a touch above the moth.
        corner = "bl" if left else "br"
        tipx, tipy = self._bubble.tip_offset(corner)
        by = (self.y() - gap) - tipy
        if by < screen.top() + 4:                    # no room above -> go below
            corner = "tl" if left else "tr"
            tipx, tipy = self._bubble.tip_offset(corner)
            by = (self.y() + self.SIZE_H + gap) - tipy
        bx = moth_cx - tipx                          # tip column over the moth centre
        bx = max(screen.left() + 4, min(bx, screen.right() - bw - 4))
        by = max(screen.top() + 4, min(by, screen.bottom() - bh - 4))
        return QPoint(bx, by), corner

    def _hide_bubble(self):
        self._bubble_hide.stop()
        if self._bubble is not None:
            self._bubble.close()
            self._bubble = None

    def _cancel_idle_and_haiku(self):
        for t in (self._idle_timer, self._flap_timer, self._first_speak,
                  self._speak_timer, self._bubble_hide):
            t.stop()
        self._flap_seq = []
        self._speak_count = 0

    # ── interaction / teardown ──────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            from techdeck.core.audio_manager import get_audio_manager
            get_audio_manager().play(_next_moth_sound())
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.dismiss()

    def dismiss(self):
        """Stop everything and remove the moth (and its bubble)."""
        self._move_timer.stop()
        self._cancel_idle_and_haiku()
        self._flying = False
        self._target_point = None
        self._hide_bubble()
        if self._host is not None:
            try:
                self._host.removeEventFilter(self)
            except RuntimeError:
                pass
            self._host = None
        self.close()

    # ── paint ───────────────────────────────────────────────────────────────
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        c = self.CELL
        for y, row in enumerate(MOTH_FRAMES[self._frame_idx]):
            for x, ch in enumerate(row):
                if ch != ".":
                    painter.fillRect(x * c, y * c, c, c, self._color)
        painter.end()
