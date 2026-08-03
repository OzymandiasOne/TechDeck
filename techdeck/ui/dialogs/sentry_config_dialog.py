"""
Sentry Drone loadout — pick which apps the drone flies for.

Opened from the Sentry Drone gadget tile in My Stuff (SET UP). Lists every
Sentry-compatible app — any plugin whose plugin.json declares the
``sentry_drone`` field (``techdeck.core.sentry_mode.compatible_plugins``) —
grouped by family, with an on/off toggle each. Saving writes straight to those
per-plugin settings, so this window and Settings -> Apps are two views of ONE
value and can never drift apart.

Themed like SelectionDialog / GroupedToggleDialog (the app's own look, not the
arcade palette) — it configures apps, so it belongs to the app chrome even
though it's reached from the arcade.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QWidget,
)
from PySide6.QtCore import Qt

from techdeck.core import sentry_mode
from techdeck.ui.widgets.toggle_switch import ToggleSwitch


class _AppRow(QFrame):
    """One app: name + family badge on the left, toggle on the right."""

    def __init__(self, app, theme, parent=None):
        super().__init__(parent)
        self.app = app
        self.setObjectName("sentryAppRow")

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(10)

        name = QLabel(app["name"])
        name.setStyleSheet("font-size: 14px; font-weight: 600; background: transparent;")
        row.addWidget(name)
        row.addStretch(1)

        self.toggle = ToggleSwitch()
        self.toggle.setChecked(bool(app.get("enabled")))
        row.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignVCenter)

        self.setStyleSheet(
            f"#sentryAppRow {{ background: {theme.surface}; "
            f"border: 1px solid {theme.divider}; border-radius: 8px; }}"
        )

    def is_on(self) -> bool:
        return self.toggle.isChecked()


class SentryConfigDialog(QDialog):
    """Per-app Sentry Drone switches. ``exec()`` returns Accepted once saved."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings

        from techdeck.ui.theme_manager import get_theme_manager
        self.theme = get_theme_manager().get_current_palette()

        self.setWindowTitle("Sentry Drone - Loadout")
        self.setModal(True)
        self.setMinimumWidth(500)

        self._apps = sentry_mode.compatible_plugins(settings=settings)
        self._rows = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        header = QLabel("Sentry Drone Loadout")
        header.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(header)

        subhead = QLabel(
            "Choose which apps hand their file and folder picking to the drone. "
            "Everything else keeps the normal Explorer dialog. Each app's switch "
            "also lives in Settings - Apps."
        )
        subhead.setWordWrap(True)
        subhead.setStyleSheet(
            f"color: {self.theme.text_secondary}; font-size: 12px;")
        layout.addWidget(subhead)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {self.theme.divider};")
        layout.addWidget(line)

        layout.addWidget(self._build_list(), 1)

        button_row = QHBoxLayout()
        for text, on in (("All on", True), ("All off", False)):
            btn = QPushButton(text)
            btn.setMinimumHeight(34)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, v=on: self._set_all(v))
            button_row.addWidget(btn)
        button_row.addStretch(1)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumHeight(34)
        cancel_btn.setMinimumWidth(100)
        cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setMinimumHeight(34)
        save_btn.setMinimumWidth(140)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(self._save_button_qss())
        save_btn.clicked.connect(self._save)
        button_row.addWidget(save_btn)

        layout.addLayout(button_row)

        # Content-sized minimum height: on a scaled display a fixed guess clips
        # the footer (see LESSONS_LEARNED, high-DPI content-sized widgets).
        self.setMinimumHeight(min(620, max(320, self.sizeHint().height())))

    # ---- list ---------------------------------------------------------------
    def _build_list(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        host = QWidget()
        host.setStyleSheet("background: transparent;")
        col = QVBoxLayout(host)
        col.setContentsMargins(0, 0, 8, 0)
        col.setSpacing(8)

        if not self._apps:
            empty = QLabel(
                "No installed app supports the Sentry Drone yet. Apps advertise "
                "support by declaring a Sentry Drone setting."
            )
            empty.setWordWrap(True)
            empty.setStyleSheet(
                f"color: {self.theme.text_secondary}; font-size: 12px;")
            col.addWidget(empty)
        else:
            family = None
            for app in self._apps:
                if app["family"] != family:
                    family = app["family"]
                    head = QLabel(family.upper())
                    head.setStyleSheet(
                        f"color: {self.theme.text_secondary}; font-size: 11px; "
                        f"font-weight: 700; letter-spacing: 1px; "
                        f"margin-top: 6px; background: transparent;")
                    col.addWidget(head)
                row = _AppRow(app, self.theme)
                self._rows.append(row)
                col.addWidget(row)
        col.addStretch(1)

        scroll.setWidget(host)
        return scroll

    def _set_all(self, on: bool):
        for row in self._rows:
            row.toggle.setChecked(on)

    # ---- save ---------------------------------------------------------------
    def _save(self):
        for row in self._rows:
            sentry_mode.set_enabled(row.app["id"], row.is_on(), self.settings)
        self.accept()

    def enabled_count(self) -> int:
        """How many apps are switched on right now (drives the My Stuff tile)."""
        return sum(1 for r in self._rows if r.is_on())

    def _save_button_qss(self) -> str:
        return (
            f"QPushButton {{ background: {self.theme.accent}; "
            f"color: {self.theme.accent_text}; border: none; border-radius: 6px; "
            f"font-weight: 600; }}"
            f"QPushButton:hover {{ background: {self.theme.accent_hover}; }}"
        )
