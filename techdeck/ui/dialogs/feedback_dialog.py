"""
TechDeck Feedback Dialog
========================
Modal dialog for submitting user feedback. Writes via feedback_writer to the
shared TechDeck_Suggestions.xlsx in the OneDrive-synced SharePoint folder.

The dialog collects two fields:
    - Which Feature?  (dropdown of known plugins + Other)
    - Suggestion      (free-form text)

Date Logged is auto-filled to today's date on submit. The "Action Taken?"
column is left blank for the maintainer.
"""

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QComboBox, QPushButton, QMessageBox, QFrame
)
from PySide6.QtCore import Qt

from techdeck.core.feedback_writer import submit_feedback
from techdeck.core.feedback_features import get_feature_options
from techdeck.ui.utils import make_tinted_svg_copy

logger = logging.getLogger(__name__)


class FeedbackDialog(QDialog):
    """Modal dialog: Which Feature + Suggestion -> append to shared workbook."""

    # Fallback options for "Which Feature?" — used ONLY if the live app-library
    # list can't be built. The real dropdown is generated dynamically from the
    # installed plugins so it never goes stale (new apps auto-appear, retired
    # ones linger as "(RETIRED)"); see techdeck.core.feedback_features.
    FEATURE_OPTIONS = [
        "TechDeck (General)",
        "New - Suggestion Box",
        "Other",
    ]

    def __init__(self, parent=None, settings=None, plugin_loader=None):
        super().__init__(parent)
        self.settings = settings   # SettingsManager, for the ticket reward
        self.plugin_loader = plugin_loader   # shared loader when the caller has one

        self.setWindowTitle("Submit Feedback")
        self.setModal(True)
        self.setMinimumWidth(480)

        # Pull theme for styling
        from techdeck.ui.theme_manager import get_theme_manager
        _tm = get_theme_manager()
        self.theme = _tm.get_current_palette()
        _theme_name = _tm.get_current_theme()
        _icon_folder = "light" if _theme_name in ["dark", "blue", "cyberpunk", "matrix"] else "dark"
        _icons_dir = (
            Path(sys._MEIPASS) / "assets" / "icons" / _icon_folder
            if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
            else Path(__file__).resolve().parents[3] / "assets" / "icons" / _icon_folder
        )
        self._arrow_path = make_tinted_svg_copy(_icons_dir / "chevron-down.svg", self.theme.text)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header
        header = QLabel("Submit Feedback")
        header.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(header)

        subhead = QLabel(
            "Your suggestion is saved to the shared TechDeck_Suggestions "
            "workbook and reviewed by the TechDeck maintainer."
        )
        subhead.setWordWrap(True)
        subhead.setStyleSheet(f"color: {self.theme.text_secondary}; font-size: 12px;")
        layout.addWidget(subhead)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"color: {self.theme.divider};")
        layout.addWidget(line)

        # Which Feature? — built live from the installed app library so the list
        # never goes stale (new plugins auto-appear; retired ones show as
        # "(RETIRED)" until purged). Falls back to the static list on any error.
        layout.addWidget(self._field_label("Which Feature?"))
        self.feature_combo = QComboBox()
        try:
            options = get_feature_options(self.settings, self.plugin_loader)
        except Exception:
            logger.exception("Feedback: could not build live feature list; "
                             "using fallback options")
            options = self.FEATURE_OPTIONS
        self.feature_combo.addItems(options)
        self.feature_combo.setMinimumHeight(32)
        self.feature_combo.setStyleSheet(self._combo_qss())
        layout.addWidget(self.feature_combo)

        # Suggestion
        layout.addWidget(self._field_label("Suggestion"))
        self.suggestion_input = QTextEdit()
        self.suggestion_input.setPlaceholderText(
            "Describe the bug, feature request, or improvement. Steps to "
            "reproduce help if it's a bug."
        )
        self.suggestion_input.setMinimumHeight(160)
        layout.addWidget(self.suggestion_input)

        # Buttons
        button_row = QHBoxLayout()
        button_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumHeight(34)
        cancel_btn.setMinimumWidth(100)
        cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(cancel_btn)

        self.submit_btn = QPushButton("Submit")
        self.submit_btn.setMinimumHeight(34)
        self.submit_btn.setMinimumWidth(120)
        self.submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.submit_btn.setStyleSheet(self._submit_button_qss())
        self.submit_btn.clicked.connect(self._on_submit)
        button_row.addWidget(self.submit_btn)

        layout.addLayout(button_row)

    # --- styling helpers ----------------------------------------------------

    def _combo_qss(self) -> str:
        t = self.theme
        return f"""
            QComboBox {{
                background-color: {t.surface};
                color: {t.text};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 6px 10px;
                padding-right: 28px;
            }}
            QComboBox:hover {{ border-color: {t.border_strong}; }}
            QComboBox::drop-down {{
                width: 24px; border: none; background: transparent;
                subcontrol-origin: padding; subcontrol-position: center right;
            }}
            QComboBox::down-arrow {{
                image: url("{self._arrow_path}"); width: 12px; height: 12px;
                background: transparent; border: none; margin-right: 6px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {t.surface}; color: {t.text};
                border: 1px solid {t.border}; border-radius: 4px;
                selection-background-color: {t.tile_selected}; outline: none;
            }}
        """

    def _field_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: 600; margin-top: 4px;")
        return lbl

    def _submit_button_qss(self) -> str:
        # Use the orange CTA accent that's already defined in every theme
        return f"""
            QPushButton {{
                background-color: {self.theme.accent_two};
                color: {self.theme.accent_two_text};
                border: none;
                border-radius: 6px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {self.theme.accent_two_hover};
            }}
            QPushButton:pressed {{
                background-color: {self.theme.accent_two_pressed};
            }}
            QPushButton:disabled {{
                background-color: {self.theme.border};
                color: {self.theme.text_secondary};
            }}
        """

    # --- submit logic -------------------------------------------------------

    def _on_submit(self):
        which_feature = self.feature_combo.currentText()
        suggestion = self.suggestion_input.toPlainText().strip()

        if not suggestion:
            QMessageBox.warning(
                self, "Missing Suggestion",
                "Please describe your suggestion or bug report."
            )
            self.suggestion_input.setFocus()
            return

        self.submit_btn.setEnabled(False)
        self.submit_btn.setText("Submitting...")

        try:
            destination = submit_feedback(
                suggestion=suggestion,
                which_feature=which_feature,
            )
        except FileNotFoundError as e:
            self.submit_btn.setEnabled(True)
            self.submit_btn.setText("Submit")
            QMessageBox.critical(
                self, "Workbook Not Found",
                f"{e}\n\nMake sure you have synced the SharePoint site to "
                f"OneDrive on this machine."
            )
            return
        except PermissionError:
            self.submit_btn.setEnabled(True)
            self.submit_btn.setText("Submit")
            QMessageBox.critical(
                self, "File Locked",
                "TechDeck_Suggestions.xlsx is currently open in Excel "
                "(yours or someone else's). Close it and try again."
            )
            return
        except ValueError as e:
            self.submit_btn.setEnabled(True)
            self.submit_btn.setText("Submit")
            QMessageBox.critical(
                self, "Workbook Schema Error",
                f"Could not submit feedback:\n\n{e}"
            )
            return
        except Exception as e:
            self.submit_btn.setEnabled(True)
            self.submit_btn.setText("Submit")
            logger.exception("Feedback submission failed")
            QMessageBox.critical(
                self, "Submission Failed",
                f"Could not save feedback:\n\n{e}"
            )
            return

        reward = ""
        if self.settings is not None:
            from techdeck.core.constants import TICKETS_PER_FEEDBACK
            bal = self.settings.add_tickets(TICKETS_PER_FEEDBACK)
            reward = (f"\n\nYou earned {TICKETS_PER_FEEDBACK} tickets for the "
                      f"feedback (balance: {bal}) - spend them at Woogy's Emporium.")
        QMessageBox.information(
            self, "Feedback Submitted",
            f"Thanks - your suggestion was {destination}.{reward}"
        )
        self.accept()
