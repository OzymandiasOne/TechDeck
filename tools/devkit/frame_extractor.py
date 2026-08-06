"""DevKit Frame Extractor — tools/extract_frames.py behind a picker UI.

Breaks a screen recording into timestamped stills (so a video can be reviewed
frame-by-frame, e.g. by Claude, which cannot watch video). Thin front-end over
the CLI: choose the video, an export rate, and an optional start/end window;
frames land in <video stem>_frames beside the video. Runs as a subprocess via
the shared _DiagnosticsPanel machinery. Source-only — excluded from the build.
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QDoubleSpinBox,
)

from tools.devkit.diagnostics import _DiagnosticsPanel, ROOT

VIDEO_FILTER = "Videos (*.mp4 *.mov *.webm *.mkv *.avi *.gif);;All files (*.*)"


class FrameExtractorPanel(_DiagnosticsPanel):
    """tools/extract_frames.py — video in, timestamped stills out."""

    def _build_controls(self, row: QHBoxLayout):
        row.addWidget(QLabel("Video"))
        self.video = QLineEdit()
        self.video.setPlaceholderText("path to a recording")
        self.video.setMinimumWidth(260)
        row.addWidget(self.video)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)

        row.addWidget(QLabel("FPS"))
        self.fps = QDoubleSpinBox()
        self.fps.setRange(0.1, 30.0)
        self.fps.setValue(1.0)
        self.fps.setDecimals(1)
        self.fps.setToolTip("Frames exported per second of video")
        row.addWidget(self.fps)

        row.addWidget(QLabel("Start"))
        self.start = QLineEdit()
        self.start.setPlaceholderText("0:00")
        self.start.setMaximumWidth(70)
        row.addWidget(self.start)
        row.addWidget(QLabel("End"))
        self.end = QLineEdit()
        self.end.setPlaceholderText("end")
        self.end.setMaximumWidth(70)
        row.addWidget(self.end)

    def _browse(self):
        current = self.video.text().strip()
        start_dir = (str(Path(current).parent) if current
                     else str(Path.home() / "Downloads"))
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose video", start_dir, VIDEO_FILTER)
        if path:
            self.video.setText(path)

    def _start(self):
        video = self.video.text().strip()
        if not video or not Path(video).is_file():
            self._set_status("CHOOSE A VIDEO FILE FIRST", "error")
            return
        super()._start()

    def _command(self) -> list:
        cmd = [sys.executable, str(ROOT / "tools" / "extract_frames.py"),
               self.video.text().strip(), "--fps", f"{self.fps.value():g}"]
        if self.start.text().strip():
            cmd += ["--start", self.start.text().strip()]
        if self.end.text().strip():
            cmd += ["--end", self.end.text().strip()]
        return cmd

    def _verdict(self, exit_code):
        if exit_code == 0:
            return "EXPORTED — frames folder is beside the video (see log)", "success"
        if exit_code == 1:
            return "NO FRAMES EXPORTED (window past end? see log)", "error"
        return f"FAILED (exit {exit_code} — see log)", "error"
