"""
TechDeck My Account Page
User profile information and access status.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QScrollArea, QMessageBox, QTabWidget
)
from PySide6.QtCore import Qt
import os

from techdeck.core.settings import SettingsManager
from techdeck.core.constants import APP_VERSION
from techdeck.ui.theme_aware import ThemeAware


# Themes with light/warm backgrounds where the bright #10B981 success green
# sits too close in luminance to the surface — bold text on those tones
# antialiases into a shimmery/fuzzy ring. Pick a darker green there.
_LIGHT_BG_THEMES = {"light", "cherry_blossom"}
_STATUS_DARK_GREEN = "#0F7A55"


class AccountPage(QWidget, ThemeAware):
    """
    My Account page - display and edit user profile information.
    """

    def __init__(self, settings: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        # Dimmed labels that should track the theme's secondary-text color
        # (was a hardcoded #888 gray — illegible on warm/light themes).
        self._secondary_labels = []

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
        self._style_secondary(self.username_value, "margin-bottom: 12px;")
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
        self._apply_status_style()
        
        status_row = QHBoxLayout()
        status_row.addWidget(status_label)
        status_row.addWidget(self.status_value)
        status_row.addStretch()
        access_section.addLayout(status_row)
        
        # Placeholder for future access control info
        access_note = QLabel("Access control features coming soon.\n"
                             "This will show your license status, expiry date, and permissions.")
        self._style_secondary(access_note, "font-size: 12px; margin-top: 8px;")
        access_section.addWidget(access_note)
        
        layout.addLayout(access_section)
        
        # ===== App Info Section =====
        info_section = self._create_section("Application Info")
        
        version_label = QLabel(f"TechDeck Version: {APP_VERSION}")
        version_label.setStyleSheet("font-size: 13px;")
        info_section.addWidget(version_label)

        layout.addLayout(info_section)

        # Add stretch at bottom
        layout.addStretch()

        scroll.setWidget(content)

        # Tabbed: account info + ticket counter + locker + achievements + house.
        from techdeck.ui.pages.emporium_page import EmporiumPage
        from techdeck.ui.pages.mystuff_page import MyStuffPage
        from techdeck.ui.pages.achievements_page import AchievementsPage
        from techdeck.ui.widgets.garden_scene import GardenScene
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setDrawBase(False)
        self.tabs.tabBar().setExpanding(False)
        self.tabs.addTab(scroll, "My Account")
        self.emporium = EmporiumPage(self.settings)
        # The Emporium scene never lays out below its design width; a smaller
        # window crops it symmetrically (drag bigger to reveal) instead of being
        # forced to grow. 760 = the scene's natural minimum (banner + a 4-digit
        # ticket balance) AFTER the banner dropped to scale 3; it must stay <=
        # the default window's ~824px content width or the too-wide page gets
        # centre-cropped and the banner's left edge (and balance's right) clip.
        from techdeck.ui.widgets.cropped_page import CroppedPage
        self.tabs.addTab(CroppedPage(self.emporium, design_width=760),
                         "Ticket Counter")
        self.my_stuff = MyStuffPage(self.settings)
        self.tabs.addTab(self.my_stuff, "My Stuff")
        # Claiming a reward changes the balance the Emporium shows, so refresh it.
        self.achievements = AchievementsPage(
            self.settings, on_claim=lambda: self.emporium.refresh())
        self.tabs.addTab(self.achievements, "Achievements")
        self.my_house = GardenScene(self.settings)
        self.tabs.addTab(self.my_house, "My House")
        # A purchase on one tab changes ownership/balance the other reflects, so
        # refresh whichever tab is being shown.
        self.tabs.currentChanged.connect(self._on_tab_changed)
        # Hidden tabs (the wide Emporium scene especially) must not lock the
        # window's minimum width while another tab/page is showing.
        from techdeck.ui.utils import limit_min_size_to_current_page
        limit_min_size_to_current_page(self.tabs)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.tabs)

        # Load initial data
        self._load_user_data()

        # Re-stamp the Status label whenever the theme switches so the green
        # tracks the active palette and dodges the light/salmon shimmer.
        self.setup_theme_awareness()

    def apply_theme(self):
        self._apply_status_style()
        self._style_tabs()
        self._apply_professional()
        self._restyle_secondary_labels()

    def _style_secondary(self, label, extra: str = ""):
        """Style a dimmed label with the theme's secondary text + register it
        to follow theme changes."""
        self._secondary_labels.append((label, extra))
        t = self.get_current_palette()
        label.setStyleSheet(f"color: {t.text_secondary}; {extra}")

    def _restyle_secondary_labels(self):
        t = self.get_current_palette()
        for label, extra in list(self._secondary_labels):
            try:
                label.setStyleSheet(f"color: {t.text_secondary}; {extra}")
            except RuntimeError:
                self._secondary_labels.remove((label, extra))

    def _apply_professional(self):
        """Professional theme hides the playful tabs (Ticket Counter, My Stuff,
        Achievements, My House) so client demos show only the account info."""
        if not hasattr(self, "tabs"):
            return
        prof = self.settings.is_professional()
        for i in range(1, self.tabs.count()):   # everything except My Account
            self.tabs.setTabVisible(i, not prof)
        if prof and self.tabs.currentIndex() != 0:
            self.tabs.setCurrentIndex(0)

    def _style_tabs(self):
        """Clearly mark the active tab: inactive tabs use the surface fill +
        muted text; the selected tab takes the accent colour and an accent
        underline so it's obvious which page you're on."""
        if not hasattr(self, "tabs"):
            return
        t = self.get_current_palette()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background-color: {t.background};
            }}
            QTabBar::tab {{
                background-color: {t.surface};
                color: {t.text_secondary};
                font-weight: bold;
                padding: 8px 18px;
                margin-right: 3px;
                border: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                border-bottom: 3px solid transparent;
            }}
            QTabBar::tab:selected {{
                background-color: {t.background};
                color: {t.accent};
                border-bottom: 3px solid {t.accent};
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {t.surface_hover};
                color: {t.text};
            }}
        """)

    def _apply_status_style(self):
        """Style the 'Active' status label with a green that has real luminance
        contrast against the current theme's surface. Bold #10B981 on the warm
        light/salmon backgrounds shimmered (same root cause as the salmon
        console_bg fix) — drop the boldness and shift to a darker green there."""
        theme_name = self.settings.get_theme()
        if theme_name in _LIGHT_BG_THEMES:
            color = _STATUS_DARK_GREEN
            weight = "600"
        else:
            color = "#10B981"
            weight = "bold"
        self.status_value.setStyleSheet(
            f"color: {color}; font-size: 14px; font-weight: {weight};"
        )
    
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
    
    def _on_tab_changed(self, _i):
        """Keep the playful tabs in sync as ownership/balance/progress change,
        and click the UFO50 tab-select sound."""
        from techdeck.core.audio_manager import get_audio_manager, SOUND_UI_TAB
        get_audio_manager().play(SOUND_UI_TAB)
        if hasattr(self, "emporium"):
            self.emporium.refresh()
        if hasattr(self, "my_stuff"):
            self.my_stuff.refresh()
        if hasattr(self, "achievements"):
            self.achievements.refresh()
        if hasattr(self, "my_house"):
            self.my_house.refresh()

    def refresh(self):
        """Refresh the page data."""
        self._load_user_data()
        if hasattr(self, "emporium"):
            self.emporium.refresh()
        if hasattr(self, "my_stuff"):
            self.my_stuff.refresh()
        if hasattr(self, "achievements"):
            self.achievements.refresh()
        if hasattr(self, "my_house"):
            self.my_house.refresh()