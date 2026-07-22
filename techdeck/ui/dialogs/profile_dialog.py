"""ProfileDialog — create/edit a Library kit (profile), with delete on edit."""

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox, QDialog,
    QLineEdit, QDialogButtonBox,
)


class ProfileDialog(QDialog):
    """Dialog for creating or editing a profile."""

    def __init__(self, mode: str, current_name: str = "", parent=None):
        """
        Args:
            mode: "create" or "edit"
            current_name: Current profile name (for edit mode)
        """
        super().__init__(parent)
        self.mode = mode
        self.current_name = current_name
        self.delete_requested = False

        self.setWindowTitle("Create Profile" if mode == "create" else "Edit Profile")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Title
        title = QLabel("Create New Profile" if mode == "create" else "Edit Profile")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # Name input
        name_layout = QVBoxLayout()
        name_layout.setSpacing(6)

        name_label = QLabel("Profile Name:")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., Engineering, QA, Weekend...")

        if mode == "edit":
            self.name_input.setText(current_name)

        name_layout.addWidget(name_label)
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)

        # Buttons
        button_layout = QHBoxLayout()

        if mode == "edit":
            # Delete button on left for edit mode
            self.delete_btn = QPushButton("Delete")
            self.delete_btn.setStyleSheet("""
                QPushButton {
                    background-color: #DC2626;
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background-color: #B91C1C;
                }
            """)
            self.delete_btn.clicked.connect(self._on_delete)
            button_layout.addWidget(self.delete_btn)

        button_layout.addStretch()

        # Standard buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)

        button_layout.addWidget(button_box)
        layout.addLayout(button_layout)

    def _on_save(self):
        """Validate and accept the dialog."""
        name = self.name_input.text().strip()

        if not name:
            QMessageBox.warning(self, "Invalid Name", "Please enter a profile name.")
            return

        self.accept()

    def _on_delete(self):
        """Handle delete button click."""
        reply = QMessageBox.question(
            self,
            "Delete Profile",
            f"Delete profile '{self.current_name}'?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.delete_requested = True
            self.reject()

    def get_name(self) -> str:
        """Get the entered profile name."""
        return self.name_input.text().strip()
