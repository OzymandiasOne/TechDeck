"""
TechDeck My Account Page
User profile information and access status.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QFrame, QScrollArea, QMessageBox
)
from PySide6.QtCore import Qt
import os

from techdeck.core.settings import SettingsManager
from techdeck.core.constants import APP_VERSION, DEFAULT_PROFILE_NAME


class AccountPage(QWidget):
    """
    My Account page - display and edit user profile information.
    """
    
    def __init__(self, settings: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        
        # Create scroll area for content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(24)
        
        # ===== Page Title =====
        title = QLabel("My Account")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)
        
        # ===== User Info Section =====
        user_section = self._create_section("User Information")
        
        # Username (read-only, from Windows)
        username_label = QLabel("Username (Windows Login):")
        username_label.setStyleSheet("font-weight: 600; margin-top: 8px;")
        self.username_value = QLabel(os.environ.get('USERNAME', 'unknown'))
        self.username_value.setStyleSheet("color: #888; margin-bottom: 12px;")
        user_section.addWidget(username_label)
        user_section.addWidget(self.username_value)
        
        # Name (editable)
        name_label = QLabel("Full Name:")
        name_label.setStyleSheet("font-weight: 600; margin-top: 8px;")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter your full name")
        self.name_input.setMinimumWidth(400)
        self.name_input.setMinimumHeight(34)
        user_section.addWidget(name_label)
        user_section.addWidget(self.name_input)
        
        # Email (editable)
        email_label = QLabel("Email:")
        email_label.setStyleSheet("font-weight: 600; margin-top: 8px;")
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("your.email@company.com")
        self.email_input.setMinimumWidth(400)
        self.email_input.setMinimumHeight(34)
        user_section.addWidget(email_label)
        user_section.addWidget(self.email_input)
        
        # Job Title (editable)
        title_label = QLabel("Job Title:")
        title_label.setStyleSheet("font-weight: 600; margin-top: 8px;")
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("e.g., Automation Engineer, QA Lead")
        self.title_input.setMinimumWidth(400)
        self.title_input.setMinimumHeight(34)
        user_section.addWidget(title_label)
        user_section.addWidget(self.title_input)
        
        # Save button
        save_btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("Save Changes")
        self.save_btn.setProperty("class", "primary")
        self.save_btn.setMinimumWidth(150)
        self.save_btn.setMinimumHeight(34)
        self.save_btn.clicked.connect(self._save_user_info)
        save_btn_layout.addWidget(self.save_btn)
        save_btn_layout.addStretch()
        user_section.addLayout(save_btn_layout)
        
        layout.addLayout(user_section)
        
        # ===== Access Status Section =====
        access_section = self._create_section("Access Status")
        
        status_label = QLabel("Status:")
        status_label.setStyleSheet("font-weight: 600;")
        self.status_value = QLabel("Active")
        self.status_value.setStyleSheet("color: #10B981; font-size: 14px; font-weight: bold;")
        
        status_row = QHBoxLayout()
        status_row.addWidget(status_label)
        status_row.addWidget(self.status_value)
        status_row.addStretch()
        access_section.addLayout(status_row)
        
        # Placeholder for future access control info
        access_note = QLabel("Access control features coming soon.\n"
                             "This will show your license status, expiry date, and permissions.")
        access_note.setStyleSheet("color: #888; font-size: 12px; margin-top: 8px;")
        access_section.addWidget(access_note)
        
        layout.addLayout(access_section)
        
        # ===== App Info Section =====
        info_section = self._create_section("Application Info")
        
        version_label = QLabel(f"TechDeck Version: {APP_VERSION}")
        version_label.setStyleSheet("font-size: 13px;")
        info_section.addWidget(version_label)
        
        profiles_count = len(self.settings.get_profile_names())
        profiles_label = QLabel(f"Total Profiles: {profiles_count}")
        profiles_label.setStyleSheet("font-size: 13px;")
        info_section.addWidget(profiles_label)
        
        default_profile = self.settings.get_current_profile_name()
        current_profile_label = QLabel(f"Current Profile: {default_profile}")
        current_profile_label.setStyleSheet("font-size: 13px;")
        info_section.addWidget(current_profile_label)
        
        layout.addLayout(info_section)
        
        # ===== Report Issue Button =====
        report_section = QVBoxLayout()
        report_section.setSpacing(8)
        
        report_label = QLabel("Having issues?")
        report_label.setStyleSheet("font-weight: 600;")
        
        self.report_btn = QPushButton("Report an Issue")
        self.report_btn.setMaximumWidth(200)
        self.report_btn.clicked.connect(self._report_issue)
        
        report_section.addWidget(report_label)
        report_section.addWidget(self.report_btn)
        
        layout.addLayout(report_section)
        
        # Add stretch at bottom
        layout.addStretch()
        
        scroll.setWidget(content)
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)
        
        # Load initial data
        self._load_user_data()
    
    def _create_section(self, title: str) -> QVBoxLayout:
        """Create a styled section with title and frame."""
        section = QVBoxLayout()
        section.setSpacing(12)
        
        # Section title
        section_title = QLabel(title)
        section_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        section.addWidget(section_title)
        
        # Divider line
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("background: #2A2A2A; max-height: 1px;")
        section.addWidget(divider)
        
        return section
    
    def _load_user_data(self):
        """Load user data from settings."""
        user_data = self.settings.get_user_data()
        
        self.name_input.setText(user_data.get('name', ''))
        self.email_input.setText(user_data.get('email', ''))
        self.title_input.setText(user_data.get('title', ''))
        
        # Update username display (in case it changed)
        self.username_value.setText(user_data.get('username', os.environ.get('USERNAME', 'unknown')))
    
    def _save_user_info(self):
        """Save user info to settings."""
        name = self.name_input.text().strip()
        email = self.email_input.text().strip()
        title = self.title_input.text().strip()
        
        # Update settings
        self.settings.update_user_data(
            name=name,
            email=email,
            title=title
        )
        
        QMessageBox.information(
            self,
            "Saved",
            "Your profile information has been saved."
        )
    
    def _report_issue(self):
        """Handle report issue button click."""
        QMessageBox.information(
            self,
            "Report an Issue",
            "Issue reporting feature coming soon!\n\n"
            "For now, please contact your administrator or IT support."
        )
    
    def refresh(self):
        """Refresh the page data."""
        self._load_user_data()