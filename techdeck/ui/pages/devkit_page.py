"""
DevKit page — the source-only developer-tools surface.

A left-nav page (below Settings, visible only in dev mode). One slim toolbar
hosts the tool switcher — the selected tool's name doubles as the page title —
plus any action widgets the mounted tool contributes via
`devkit_toolbar_actions()`; below it the selected tool mounts flush inside
TechDeck (no framed picker, no rounded corners).

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
from techdeck.ui.theme import get_current_palette


class DevKitPage(QWidget):
    def __init__(self, settings: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings = settings

        from tools.devkit.registry import DEV_TOOLS
        self._tools = list(DEV_TOOLS)
        self._loaded: dict = {}   # registry index -> built widget

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 14, 20, 14)
        outer.setSpacing(12)

        # Unified toolbar: the tool name is the title, the combo switches tools,
        # and the right side hosts the mounted tool's own action widgets. Bare
        # QLabel/QComboBox inherit the themed text color from the app cascade.
        bar = QHBoxLayout()
        bar.setSpacing(12)
        self._title = QLabel("")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        self._title.setFont(title_font)
        bar.addWidget(self._title)

        self.combo = QComboBox()
        self.combo.setMinimumHeight(30)
        self.combo.setMinimumWidth(170)
        for tool in self._tools:
            self.combo.addItem(tool.label)
        # Selecting a tool mounts it directly. The initial tool mounts on first
        # show (currentIndexChanged doesn't fire for the starting index).
        self.combo.currentIndexChanged.connect(self._mount_tool)
        bar.addWidget(self.combo)
        bar.addStretch()

        # Right-side slot filled from the mounted tool's devkit_toolbar_actions().
        self._action_slot = QWidget()
        self._action_layout = QHBoxLayout(self._action_slot)
        self._action_layout.setContentsMargins(0, 0, 0, 0)
        self._action_layout.setSpacing(8)
        bar.addWidget(self._action_slot)
        outer.addLayout(bar)

        # Host — the selected tool mounts here, flush (no frame / rounded
        # corners, so nothing shows through the corners). Built once and cached
        # so re-selecting a tool keeps its state.
        self.host = QStackedWidget()
        self._placeholder = QLabel("Select a tool to load it here.")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _pal = get_current_palette(self.settings.get_theme())
        self._placeholder.setStyleSheet(f"color: {_pal.text_secondary}; font-size: 13px;")
        self.host.addWidget(self._placeholder)
        outer.addWidget(self.host, 1)

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
