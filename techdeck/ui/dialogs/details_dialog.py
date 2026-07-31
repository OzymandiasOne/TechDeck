"""
TechDeck App Details Dialog
===========================
The scrollable pop-up behind the `/moredetails` console command. Renders one
or more apps' deep details in an instructional voice, in three sections:

    - "Before you run it"  <- plugin.json details.setup
    - "What it does"       <- plugin.json details.how_it_works
    - "What you get"       <- plugin.json details.output

Each section is a list of plain strings in the plugin's plugin.json under a
top-level "details" object, e.g.:

    "details": {
      "setup":        ["Sync the '911 QTDR' folder in OneDrive.", ...],
      "how_it_works": ["Reads the BATCH LIST to find every nest.", ...],
      "output":       ["One folder per nest, each with ...", ...]
    }

Plugins without a details block fall back to their short description so the
dialog always shows *something*. `/moredetails` (selected tiles) and
`/moredetails all` (every installed app) both open this same dialog; the
command decides which Plugin objects to pass in.
"""

import html
from typing import List

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QFrame,
)
from PySide6.QtCore import Qt

from techdeck.ui.theme_manager import get_theme_manager


# (details key, instructional heading) in display order.
_SECTIONS = [
    ("setup", "Before you run it"),
    ("how_it_works", "What it does"),
    ("output", "What you get"),
]


class DetailsDialog(QDialog):
    """Scrollable reference pop-up describing one or more apps in depth."""

    def __init__(self, plugins: List, parent=None):
        super().__init__(parent)
        self.theme = get_theme_manager().get_current_palette()

        n = len(plugins)
        self.setWindowTitle("App Details" if n != 1 else f"{plugins[0].name}")
        self.setModal(False)  # reference pop-up; don't block the console
        self.setMinimumSize(460, 400)
        self.resize(600, 680)

        t = self.theme
        self.setStyleSheet(f"QDialog {{ background-color: {t.background}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        # --- Header -------------------------------------------------------
        title = "App Details" if n != 1 else plugins[0].name
        header = QLabel(title)
        header.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {t.text};")
        layout.addWidget(header)

        subhead = QLabel(
            "What each app needs, what it does, and what it produces."
            if n != 1 else
            "What it needs, what it does, and what it produces.")
        subhead.setWordWrap(True)
        subhead.setStyleSheet(
            f"color: {t.text_secondary}; font-size: 12px;")
        layout.addWidget(subhead)

        # --- Scrollable body ----------------------------------------------
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{
                background: transparent; width: 10px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {t.border_strong}; border-radius: 5px; min-height: 30px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0; background: none;
            }}
        """)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 4, 6, 4)
        body_layout.setSpacing(14)

        for i, plugin in enumerate(plugins):
            body_layout.addWidget(self._plugin_block(plugin))
            if i < n - 1:
                divider = QFrame()
                divider.setFrameShape(QFrame.Shape.HLine)
                divider.setFixedHeight(1)
                divider.setStyleSheet(f"background-color: {t.divider}; border: none;")
                body_layout.addWidget(divider)

        body_layout.addStretch()
        scroll.setWidget(body)
        layout.addWidget(scroll, stretch=1)

        # --- Close button -------------------------------------------------
        button_row = QHBoxLayout()
        button_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setMinimumHeight(34)
        close_btn.setMinimumWidth(110)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t.accent}; color: {t.accent_text};
                border: none; border-radius: 6px; font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {t.accent_hover}; }}
            QPushButton:pressed {{ background-color: {t.accent_pressed}; }}
        """)
        close_btn.clicked.connect(self.accept)
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)

    # ------------------------------------------------------------------ #
    #  One app's block: name + family tag, then the three sections.
    # ------------------------------------------------------------------ #
    def _plugin_block(self, plugin) -> QWidget:
        t = self.theme
        block = QWidget()
        col = QVBoxLayout(block)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(8)

        # Name + family tag on one row.
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name = QLabel(plugin.name)
        name.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {t.text};")
        name_row.addWidget(name)

        family = getattr(plugin, "family", "") or ""
        if family:
            tag = QLabel(family.upper())
            tag.setStyleSheet(f"""
                color: {t.text_secondary};
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 1px 8px;
                font-size: 10px; font-weight: 700;
            """)
            name_row.addWidget(tag)
        name_row.addStretch()
        col.addLayout(name_row)

        details = getattr(plugin, "details", None)
        if not isinstance(details, dict):
            details = None

        # No details yet -> fall back to the short one-line description.
        if details is None:
            desc = (getattr(plugin, "description", "") or "").strip()
            fallback = QLabel(desc or "No detailed write-up for this app yet.")
            fallback.setWordWrap(True)
            fallback.setStyleSheet(
                f"color: {t.text_secondary}; font-size: 12px; font-style: italic;")
            col.addWidget(fallback)
            return block

        any_section = False
        for key, heading in _SECTIONS:
            items = details.get(key) or []
            if isinstance(items, str):
                items = [items]
            items = [str(x).strip() for x in items if str(x).strip()]
            if not items:
                continue
            any_section = True

            sec_title = QLabel(heading)
            sec_title.setStyleSheet(
                f"color: {t.accent}; font-size: 11px; font-weight: 700; "
                f"text-transform: uppercase; margin-top: 2px;")
            col.addWidget(sec_title)

            lis = "".join(
                f"<li style='margin-bottom:4px;'>{html.escape(it)}</li>"
                for it in items)
            body = QLabel(
                f"<ul style='margin:0 0 0 -18px; padding:0;'>{lis}</ul>")
            body.setWordWrap(True)
            body.setTextFormat(Qt.TextFormat.RichText)
            body.setStyleSheet(
                f"color: {t.text}; font-size: 12px;")
            col.addWidget(body)

        if not any_section:
            desc = (getattr(plugin, "description", "") or "").strip()
            fallback = QLabel(desc or "No detailed write-up for this app yet.")
            fallback.setWordWrap(True)
            fallback.setStyleSheet(
                f"color: {t.text_secondary}; font-size: 12px; font-style: italic;")
            col.addWidget(fallback)

        return block
