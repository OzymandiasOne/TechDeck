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
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QComboBox, QPushButton, QMessageBox, QFrame
)
from PySide6.QtCore import Qt

from techdeck.core.feedback_writer import submit_feedback

logger = logging.getLogger(__name__)


class FeedbackDialog(QDialog):
    """Modal dialog: Which Feature + Suggestion -> append to shared workbook."""

    # Drop-down options for "Which Feature?". Keep in sync with the values
    # already in use in TechDeck_Suggestions.xlsx column B for consistency.
    FEATURE_OPTIONS = [
        "TechDeck (General)",
        "911 Setup",
        "911 Repeater",
        "922 Pallet Stamper",
        "Batch Repeater",
        "LST Organizer",
        "PO Packet Extractor",
        "Part Sketch Extractor",
        "QR Code Generator",
        "New - Suggestion Box",
        "Other",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Report Feedback")
        self.setModal(True)
        self.setMinimumWidth(480)

        # Pull theme for accent styling on the submit button
        from techdeck.ui.theme_manager import get_theme_manager
        self.theme = get_theme_manager().get_current_palette()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header
        header = QLabel("Report Feedback")
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

        # Which Feature?
        layout.addWidget(self._field_label("Which Feature?"))
        self.feature_combo = QComboBox()
        self.feature_combo.addItems(self.FEATURE_OPTIONS)
        self.feature_combo.setMinimumHeight(32)
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

    def _field_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: 600; margin-top: 4px;")
        return lbl

    def _submit_button_qss(self) -> str:
        # Use the orange CTA accent that's already defined in every theme
        return f"""
            QPushButton {{
                background-color: {self.theme.accent_two};
                color: white;
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
            path = submit_feedback(
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

        QMessageBox.information(
            self, "Feedback Submitted",
            f"Thanks - your suggestion was saved to {path.name}."
        )
        self.accept()
