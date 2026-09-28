"""His lines at the table: text + an emotion -> what his face and the tube do.

Same unit as the game that inspired this: a written line carries an emotion,
and the emotion fires the effects (later, a sound). The lines live in a plain
text file you can edit by hand, exactly like his chat script:

    assets/puppet_master/game_lines.txt

    # key | emotion | text
    welcome | amused | So. You found the table.

Several lines with the same key are a pool: he picks one, never the same one
twice in a row. `{name}`-style holes are filled from the event.
"""
from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from pathlib import Path

EMOTIONS = ("calm", "curious", "amused", "pleased", "displeased", "grave")


@dataclass(frozen=True)
class Mood:
    """What an emotion does to the picture. Numbers are 0..1 strengths."""
    flicker: float = 0.0       # glyphs of his face scrambling
    halo: tuple = (40, 200, 90, 46)   # the light behind his face (r, g, b, a)
    dim: float = 0.0           # the whole tube darkens
    shake: float = 0.0         # the camera trembles
    hold_ms: int = 2600        # how long the caption stays


MOODS = {
    "calm": Mood(),
    "curious": Mood(flicker=0.02, halo=(60, 230, 110, 60), hold_ms=2800),
    "amused": Mood(flicker=0.05, halo=(70, 240, 120, 70), hold_ms=2800),
    "pleased": Mood(flicker=0.03, halo=(110, 255, 150, 95), hold_ms=3000),
    "displeased": Mood(flicker=0.16, halo=(30, 120, 60, 40), dim=0.25, shake=1.0, hold_ms=3000),
    "grave": Mood(flicker=0.01, halo=(120, 70, 40, 60), dim=0.35, hold_ms=3600),
}


def lines_path() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS) / "assets"
    else:
        base = Path(__file__).resolve().parents[3] / "assets"
    return base / "puppet_master" / "game_lines.txt"


def parse_lines(text: str) -> dict[str, list[tuple[str, str]]]:
    """key -> [(emotion, line), ...]. Bad lines are skipped, never fatal."""
    out: dict[str, list[tuple[str, str]]] = {}
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        parts = [x.strip() for x in s.split("|", 2)]
        if len(parts) != 3 or not parts[2]:
            continue
        key, emotion, line = parts
        if emotion not in MOODS:
            emotion = "calm"
        out.setdefault(key, []).append((emotion, line))
    return out


class Dialogue:
    def __init__(self, path: Path | None = None, seed: int | None = None):
        self.path = path or lines_path()
        self.rng = random.Random(seed)
        self._lines: dict[str, list[tuple[str, str]]] = {}
        self._mtime = None
        self._last: dict[str, str] = {}
        self.reload()

    def reload(self):
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            self._lines, self._mtime = {}, None
            return
        if mtime == self._mtime:
            return
        self._mtime = mtime
        try:
            self._lines = parse_lines(self.path.read_text(encoding="utf-8"))
        except OSError:
            self._lines = {}

    def has(self, key: str) -> bool:
        return bool(self._lines.get(key))

    def line(self, key: str, **holes) -> tuple[str, str] | None:
        """(text, emotion) for a key, or None when he has nothing to say.
        The file hot-reloads: save it, play on."""
        self.reload()
        pool = self._lines.get(key)
        if not pool:
            return None
        choices = pool
        if len(pool) > 1 and key in self._last:
            choices = [c for c in pool if c[1] != self._last[key]] or pool
        emotion, text = self.rng.choice(choices)
        self._last[key] = text
        try:
            text = text.format(**holes)
        except (KeyError, IndexError, ValueError):
            pass
        return text, emotion
