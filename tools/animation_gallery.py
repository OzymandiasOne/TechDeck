"""
Garden animation gallery — a standalone dev tool to review every animated sprite.

Run:  python tools/animation_gallery.py

Scans assets/garden/ for sprite sequences (any sPet_*_<n>.png with 2+ frames),
groups them into animation clips, and plays them all at once in a labelled,
scrollable grid. Use it to see how each animation looks and decide which should
loop on a timer, fire randomly, or be triggered by the pet. Not shipped.
"""

import glob
import re
import sys
from collections import defaultdict
from pathlib import Path

from PySide6.QtWidgets import (QApplication, QWidget, QScrollArea, QGridLayout,
                               QVBoxLayout, QLabel)
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont
from PySide6.QtCore import Qt, QTimer

ROOT = Path(__file__).resolve().parents[1]
GARDEN = ROOT / "assets" / "garden"


def find_clips():
    groups = defaultdict(list)
    for f in glob.glob(str(GARDEN / "sPet_*.png")):
        m = re.match(r"(.+)_(\d+)$", Path(f).stem)
        if m:
            groups[m.group(1)].append((int(m.group(2)), f))
    clips = {}
    for base, frames in groups.items():
        short = base.replace("sPet_", "")
        if "Icons" in short or len(frames) < 2:   # skip UI icon sheets
            continue
        frames.sort()
        clips[short] = [f for _, f in frames]
    return dict(sorted(clips.items()))


class AnimCell(QWidget):
    def __init__(self, short, files):
        super().__init__()
        self.short = short
        self.frames = [QPixmap(f) for f in files]
        w = max(p.width() for p in self.frames)
        h = max(p.height() for p in self.frames)
        self.scale = max(1, min(5, 88 // max(w, h, 1)))
        self.idx = 0
        self.setFixedSize(max(w * self.scale + 12, 132),
                          h * self.scale + 30)

    def advance(self):
        self.idx = (self.idx + 1) % len(self.frames)
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#1d1d26"))
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        pm = self.frames[self.idx]
        sp = pm.scaled(pm.width() * self.scale, pm.height() * self.scale,
                       Qt.AspectRatioMode.IgnoreAspectRatio,
                       Qt.TransformationMode.FastTransformation)
        p.drawPixmap((self.width() - sp.width()) // 2, 4, sp)
        p.setPen(QColor("#cfcfe0"))
        p.setFont(QFont("Consolas", 8))
        p.drawText(3, self.height() - 7, f"{self.short} ({len(self.frames)}f)")
        p.end()


class Gallery(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Garden animation gallery")
        self.resize(1180, 820)
        root = QVBoxLayout(self)
        clips = find_clips()
        root.addWidget(QLabel(f"  {len(clips)} animation clips  —  "
                              "name (frame count) under each", self))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background:#12121a;")
        host = QWidget()
        grid = QGridLayout(host)
        grid.setSpacing(8)
        self.cells = []
        cols = 8
        for i, (short, files) in enumerate(clips.items()):
            cell = AnimCell(short, files)
            self.cells.append(cell)
            grid.addWidget(cell, i // cols, i % cols, Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(host)
        root.addWidget(scroll)
        self.timer = QTimer(self)
        self.timer.setInterval(360)   # 3x slower than the original 120ms
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    def _tick(self):
        for c in self.cells:
            c.advance()


def main():
    app = QApplication(sys.argv)
    g = Gallery()
    g.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
