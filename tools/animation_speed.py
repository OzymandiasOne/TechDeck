"""
Animation speed tool — open any of our animations, preview it live, and dial in a
new framerate with a slider plus linked "total run time" and "frames per second"
fields (edit any one, the others follow).

Run:  python tools/animation_speed.py

TechDeck has two kinds of animation, and this tool handles both:

  * GIFs (the theme backgrounds — cat / matrix / cyberpunk / ...). The framerate
    lives in the file as a per-frame delay. **Save** writes a new GIF at the delay
    you chose.

  * Sprite PNG sequences (the garden / game clips — e.g. the Buddy SleepBed snore,
    sPet_BuddySleepBed_0.png / _1.png). Their speed is a CODE constant in
    milliseconds-per-frame (garden_scene.py's BUDDY_ACT_FRAME_MS etc.), NOT stored
    in the frames. There is nothing to save, so the tool REPORTS the ms/frame + fps
    for you to drop into the code (Copy report copies it to the clipboard).

Open a sprite sequence by picking its first frame (the ..._0.png); the rest load
automatically. Not shipped — a dev tool, lives in tools/.
"""

import re
import sys
from pathlib import Path

from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QPushButton,
                               QVBoxLayout, QHBoxLayout, QGridLayout, QSlider,
                               QDoubleSpinBox, QFileDialog, QFrame, QMessageBox)
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QFont, QGuiApplication
from PySide6.QtCore import Qt, QTimer

ROOT = Path(__file__).resolve().parents[1]
GARDEN = ROOT / "assets" / "garden"
GIFS = ROOT / "assets" / "images"

try:
    from PIL import Image
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False


def _pil_to_pixmap(pil_img):
    """Convert a PIL image (any mode) to a QPixmap."""
    rgba = pil_img.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qim = QImage(data, rgba.width, rgba.height, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qim.copy())


def load_animation(path):
    """Load an animation file.

    Returns (frames, kind, orig_fps) where frames is a list[QPixmap],
    kind is 'gif' or 'sprite', and orig_fps is the detected framerate for a GIF
    or None for a sprite sequence (which has no stored framerate).
    """
    path = Path(path)
    if path.suffix.lower() == ".gif":
        if not HAVE_PIL:
            raise RuntimeError("Reading GIFs needs Pillow (pip install pillow).")
        frames, durations = [], []
        with Image.open(path) as im:
            n = getattr(im, "n_frames", 1)
            for i in range(n):
                im.seek(i)
                durations.append(im.info.get("duration", 100) or 100)
                frames.append(_pil_to_pixmap(im))
        avg = sum(durations) / len(durations) if durations else 100
        orig_fps = 1000.0 / avg if avg else 10.0
        return frames, "gif", orig_fps

    # Sprite PNG sequence: strip a trailing _<n> and load _0, _1, _2, ...
    m = re.match(r"(.+)_(\d+)$", path.stem)
    if m:
        base, ext = m.group(1), path.suffix
        files, i = [], 0
        while True:
            f = path.with_name(f"{base}_{i}{ext}")
            if not f.exists():
                break
            files.append(f)
            i += 1
        if not files:
            files = [path]
    else:
        files = [path]
    frames = [QPixmap(str(f)) for f in files]
    frames = [p for p in frames if not p.isNull()]
    if not frames:
        raise RuntimeError(f"No frames loaded from {path.name}")
    return frames, "sprite", None


class Preview(QWidget):
    """Plays the loaded frames at a settable interval. Pixel sprites scale up
    with nearest-neighbor; large GIFs scale down smoothly to fit the box."""

    BOX = 380

    def __init__(self):
        super().__init__()
        self.frames = []
        self.idx = 0
        self.scale = 1
        self.smooth = False
        self.setMinimumSize(self.BOX, self.BOX)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._advance)

    def set_frames(self, frames):
        self.frames = frames
        self.idx = 0
        w = max((p.width() for p in frames), default=1)
        h = max((p.height() for p in frames), default=1)
        fit = self.BOX - 20
        if max(w, h) <= fit:
            self.scale = max(1, fit // max(w, h))     # integer upscale
            self.smooth = False
        else:
            self.scale = fit / max(w, h)              # fractional downscale
            self.smooth = True
        self.update()

    def set_interval_ms(self, ms):
        self.timer.setInterval(max(10, int(round(ms))))
        if self.frames and not self.timer.isActive():
            self.timer.start()

    def _advance(self):
        if self.frames:
            self.idx = (self.idx + 1) % len(self.frames)
            self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#20202b"))
        if not self.frames:
            p.setPen(QColor("#8a8a99"))
            p.setFont(QFont("Segoe UI", 11))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Open a .gif or a sprite _0.png")
            p.end()
            return
        pm = self.frames[self.idx]
        sw, sh = int(pm.width() * self.scale), int(pm.height() * self.scale)
        mode = (Qt.TransformationMode.SmoothTransformation if self.smooth
                else Qt.TransformationMode.FastTransformation)
        sp = pm.scaled(sw, sh, Qt.AspectRatioMode.KeepAspectRatio, mode)
        p.drawPixmap((self.width() - sp.width()) // 2,
                     (self.height() - sp.height()) // 2, sp)
        p.end()


class SpeedTool(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TechDeck — Animation Speed Tool")
        self.resize(520, 720)
        self._path = None
        self._kind = None
        self._n = 0
        self._fps = 10.0
        self._guard = False        # blocks re-entrant control updates

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        # --- open row ---
        top = QHBoxLayout()
        self.open_btn = QPushButton("Open animation…")
        self.open_btn.clicked.connect(self._open)
        top.addWidget(self.open_btn)
        self.file_lbl = QLabel("no file loaded")
        self.file_lbl.setStyleSheet("color:#9a9aac;")
        top.addWidget(self.file_lbl, 1)
        root.addLayout(top)

        # --- preview ---
        self.preview = Preview()
        root.addWidget(self.preview)

        # --- controls ---
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        grid.addWidget(QLabel("Frame rate"), 0, 0)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(1, 60)
        self.slider.valueChanged.connect(self._on_slider)
        grid.addWidget(self.slider, 0, 1)

        grid.addWidget(QLabel("Frames / sec"), 1, 0)
        self.fps_spin = QDoubleSpinBox()
        self.fps_spin.setRange(0.2, 120.0)
        self.fps_spin.setDecimals(2)
        self.fps_spin.setSingleStep(0.5)
        self.fps_spin.valueChanged.connect(self._on_fps)
        grid.addWidget(self.fps_spin, 1, 1)

        grid.addWidget(QLabel("Total run time (s)"), 2, 0)
        self.time_spin = QDoubleSpinBox()
        self.time_spin.setRange(0.02, 600.0)
        self.time_spin.setDecimals(3)
        self.time_spin.setSingleStep(0.1)
        self.time_spin.valueChanged.connect(self._on_time)
        grid.addWidget(self.time_spin, 2, 1)
        root.addLayout(grid)

        # --- report ---
        self.report = QLabel("—")
        self.report.setFrameShape(QFrame.Shape.StyledPanel)
        self.report.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.report.setStyleSheet(
            "QLabel{background:#15151d;color:#d6d6e6;border:1px solid #33333f;"
            "border-radius:6px;padding:10px;}")
        self.report.setFont(QFont("Consolas", 10))
        self.report.setWordWrap(True)
        root.addWidget(self.report)

        # --- actions ---
        actions = QHBoxLayout()
        self.copy_btn = QPushButton("Copy report")
        self.copy_btn.clicked.connect(self._copy)
        self.copy_btn.setEnabled(False)
        actions.addWidget(self.copy_btn)
        self.save_btn = QPushButton("Save GIF…")
        self.save_btn.clicked.connect(self._save_gif)
        self.save_btn.setEnabled(False)
        actions.addWidget(self.save_btn)
        root.addLayout(actions)

    # ---- open ----------------------------------------------------------
    def _open(self):
        start = str(GARDEN if GARDEN.exists() else ROOT)
        path, _ = QFileDialog.getOpenFileName(
            self, "Open animation", start,
            "Animations (*.gif *.png);;GIF (*.gif);;PNG frame (*.png)")
        if not path:
            return
        try:
            frames, kind, orig_fps = load_animation(path)
        except Exception as e:
            QMessageBox.critical(self, "Could not open", str(e))
            return
        self._path = Path(path)
        self._kind = kind
        self._n = len(frames)
        self.preview.set_frames(frames)
        self.file_lbl.setText(f"{self._path.name}   ({self._n} frames, {kind})")
        self.save_btn.setEnabled(kind == "gif")
        self.copy_btn.setEnabled(True)
        # Starting fps: a GIF's own rate; sprites default to 5 fps (=200 ms/frame,
        # the current in-code Buddy interaction speed) as a reference point.
        self._set_fps(orig_fps if orig_fps else 5.0)

    # ---- linked controls ----------------------------------------------
    def _set_fps(self, fps, src=None):
        fps = max(0.2, float(fps))
        self._fps = fps
        self._guard = True
        if src != "slider":
            self.slider.setValue(int(round(min(60, max(1, fps)))))
        if src != "fps":
            self.fps_spin.setValue(fps)
        if src != "time" and self._n:
            self.time_spin.setValue(self._n / fps)
        self._guard = False
        self._refresh()

    def _on_slider(self, v):
        if not self._guard:
            self._set_fps(v, src="slider")

    def _on_fps(self, v):
        if not self._guard:
            self._set_fps(v, src="fps")

    def _on_time(self, v):
        if not self._guard and v > 0 and self._n:
            self._set_fps(self._n / v, src="time")

    def _refresh(self):
        ms = 1000.0 / self._fps
        total = (self._n / self._fps) if self._n else 0.0
        self.preview.set_interval_ms(ms)
        if self._kind == "sprite":
            head = ("SPRITE SEQUENCE - no file framerate; paste the ms/frame into "
                    "the code (garden_scene.py BUDDY_ACT_FRAME_MS / ITEM_ANIM_FRAME_MS).")
        elif self._kind == "gif":
            head = "GIF - Save writes a new file at this per-frame delay."
        else:
            head = ""
        self.report.setText(
            f"{head}\n\n"
            f"Frames      : {self._n}\n"
            f"Frame rate  : {self._fps:.2f} fps\n"
            f"ms / frame  : {ms:.1f} ms   <-- put this in code for sprites\n"
            f"Total time  : {total:.3f} s")

    # ---- actions -------------------------------------------------------
    def _copy(self):
        QGuiApplication.clipboard().setText(self.report.text())

    def _save_gif(self):
        if self._kind != "gif" or not HAVE_PIL:
            return
        from PIL import Image
        dur = int(round(1000.0 / self._fps))
        default = str(self._path.with_name(
            f"{self._path.stem}_{self._fps:.0f}fps.gif"))
        dest, _ = QFileDialog.getSaveFileName(
            self, "Save GIF as", default, "GIF (*.gif)")
        if not dest:
            return
        try:
            src = Image.open(self._path)
            frames = []
            try:
                while True:
                    frames.append(src.copy())
                    src.seek(src.tell() + 1)
            except EOFError:
                pass
            loop = src.info.get("loop", 0)
            frames[0].save(dest, save_all=True, append_images=frames[1:],
                           duration=dur, loop=loop, disposal=2, optimize=False)
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))
            return
        QMessageBox.information(
            self, "Saved",
            f"Wrote {Path(dest).name}\n{self._fps:.2f} fps ({dur} ms/frame).")


def main():
    app = QApplication(sys.argv)
    w = SpeedTool()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
