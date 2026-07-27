"""
DevKit page — the source-only developer-tools surface.

A left-nav page (below Settings, visible only in dev mode). A full-width header
BAR (surface, with a divider under it) hosts the tool switcher — the selected
tool's name doubles as the page title — plus any action widgets the mounted tool
contributes via `devkit_toolbar_actions()`. The selected tool then mounts flush
edge-to-edge below the bar (no framed picker, no inset panel, no rounded
corners), so the header reads as a header and the tool as the canvas.

This page is only ever constructed in source builds (the shell gates it on
techdeck.ui.dev_mode.is_dev_build), so importing the source-only tools/devkit
package here is safe — it never runs in a frozen exe.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QStackedWidget, QMessageBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from techdeck.core.settings import SettingsManager
from techdeck.ui.theme_manager import get_theme_manager


class DevKitPage(QWidget):
    def __init__(self, settings: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings = settings

        from tools.devkit.registry import DEV_TOOLS
        self._tools = list(DEV_TOOLS)
        self._loaded: dict = {}   # registry index -> built widget

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header bar — a defined surface band the controls sit ON, with a
        # divider under it. Full-width and square (no rounded corners, no inset
        # frame), so nothing reads as a cut-out.
        self._header = QWidget()
        self._header.setObjectName("devkitHeader")
        hbar = QHBoxLayout(self._header)
        hbar.setContentsMargins(20, 10, 20, 10)
        hbar.setSpacing(12)

        self._title = QLabel("")
        title_font = QFont()
        title_font.setPointSize(15)
        title_font.setBold(True)
        self._title.setFont(title_font)
        hbar.addWidget(self._title)

        self.combo = QComboBox()
        self.combo.setMinimumHeight(30)
        self.combo.setMinimumWidth(170)
        for tool in self._tools:
            self.combo.addItem(tool.label)
        # Selecting a tool mounts it directly. The initial tool mounts on first
        # show (currentIndexChanged doesn't fire for the starting index).
        self.combo.currentIndexChanged.connect(self._mount_tool)
        hbar.addWidget(self.combo)
        hbar.addStretch()

        # Right-side slot filled from the mounted tool's devkit_toolbar_actions().
        # Must be transparent: the global stylesheet paints bare QWidgets with
        # the page background, which shows as a wrong-colored patch on the
        # surface-colored header bar.
        self._action_slot = QWidget()
        self._action_slot.setObjectName("devkitActionSlot")
        self._action_slot.setStyleSheet(
            "#devkitActionSlot { background: transparent; }")
        self._action_layout = QHBoxLayout(self._action_slot)
        self._action_layout.setContentsMargins(0, 0, 0, 0)
        self._action_layout.setSpacing(8)
        hbar.addWidget(self._action_slot)
        outer.addWidget(self._header)

        # Host — the selected tool mounts here, flush and full-bleed. Built once
        # and cached so re-selecting a tool keeps its state.
        self.host = QStackedWidget()
        self._placeholder = QLabel("Select a tool to load it here.")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.host.addWidget(self._placeholder)
        outer.addWidget(self.host, 1)

        self._restyle()
        get_theme_manager().theme_changed.connect(lambda _name: self._restyle())

    def _restyle(self):
        pal = get_theme_manager().get_current_palette()
        # Header sits on `surface` with a divider; the tool canvas below is the
        # app `background`, so the two read as header + content, not a cut-out.
        self._header.setStyleSheet(
            f"#devkitHeader {{ background-color: {pal.surface}; "
            f"border-bottom: 1px solid {pal.border}; }}")
        self._placeholder.setStyleSheet(
            f"color: {pal.text_secondary}; font-size: 13px;")

    def showEvent(self, event):
        super().showEvent(event)
        if self.host.currentWidget() is self._placeholder:
            self._mount_tool()

    def _mount_tool(self):
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
        self._title.setText(tool.label.upper())
        self._populate_actions(widget)

    def _populate_actions(self, widget):
        """Move the mounted tool's toolbar action widgets into the shared slot.
        The widgets are owned by their tool (which is cached), so we detach —
        never delete — the previous tool's actions."""
        while self._action_layout.count():
            item = self._action_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        getter = getattr(widget, "devkit_toolbar_actions", None)
        if callable(getter):
            for w in getter():
                self._action_layout.addWidget(w)
                w.show()
