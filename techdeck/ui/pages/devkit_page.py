"""
DevKit page — the source-only developer-tools surface.

A left-nav page (below Settings, visible only in dev mode) that hosts a tool
picker + Run button and an embedded area where the selected tool mounts INSIDE
TechDeck. Seeded with the Pixel Studio; the tool list is tools/devkit/registry.

This page is only ever constructed in source builds (the shell gates it on
techdeck.ui.dev_mode.is_dev_build), so importing the source-only tools/devkit
package here is safe — it never runs in a frozen exe.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QStackedWidget, QMessageBox, QFrame,
)
from PySide6.QtCore import Qt

from techdeck.core.settings import SettingsManager


class DevKitPage(QWidget):
    def __init__(self, settings: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings = settings

        from tools.devkit.registry import DEV_TOOLS
        self._tools = list(DEV_TOOLS)
        self._loaded: dict = {}   # registry index -> built widget

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(12)

        title = QLabel("DevKit")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        outer.addWidget(title)

        # Picker bar — a distinct control strip so it's clear the tool window
        # begins below it.
        picker = QFrame()
        picker.setObjectName("devkitPicker")
        picker.setStyleSheet(
            "#devkitPicker { background: rgba(127, 127, 127, 0.10); "
            "border: 1px solid rgba(127, 127, 127, 0.25); border-radius: 8px; }")
        row = QHBoxLayout(picker)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(10)
        tool_label = QLabel("Tool")
        tool_label.setStyleSheet("font-weight: 600; background: transparent; border: none;")
        row.addWidget(tool_label)
        self.combo = QComboBox()
        self.combo.setMinimumHeight(34)
        self.combo.setMinimumWidth(240)
        for tool in self._tools:
            self.combo.addItem(tool.label)
        row.addWidget(self.combo)
        run_btn = QPushButton("Run")
        run_btn.setMinimumHeight(34)
        run_btn.setMinimumWidth(90)
        run_btn.clicked.connect(self._run_tool)
        row.addWidget(run_btn)
        row.addStretch()
        outer.addWidget(picker)

        # Tool window — the selected tool mounts inside this framed area, built
        # once and cached so re-selecting a tool keeps its state.
        host_frame = QFrame()
        host_frame.setObjectName("devkitHost")
        host_frame.setStyleSheet(
            "#devkitHost { border: 1px solid rgba(127, 127, 127, 0.25); "
            "border-radius: 8px; }")
        host_layout = QVBoxLayout(host_frame)
        host_layout.setContentsMargins(2, 2, 2, 2)
        self.host = QStackedWidget()
        self._placeholder = QLabel("Select a tool and press Run to load it here.")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet("color: #888; font-size: 13px;")
        self.host.addWidget(self._placeholder)
        host_layout.addWidget(self.host)
        outer.addWidget(host_frame, 1)

    def _run_tool(self):
        """Build (once) and show the selected DevKit tool in the embed host."""
        idx = self.combo.currentIndex()
        if idx < 0:
            return
        tool = self._tools[idx]
        widget = self._loaded.get(idx)
        if widget is None:
            try:
                widget = tool.build()
            except Exception as e:
                QMessageBox.critical(
                    self, "DevKit", f"Could not load {tool.label}:\n{e}")
                return
            self._loaded[idx] = widget
            self.host.addWidget(widget)
        self.host.setCurrentWidget(widget)
