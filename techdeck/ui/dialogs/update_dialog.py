"""
Update notification and download dialog.
"""

import logging

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton,
    QProgressBar, QHBoxLayout, QMessageBox, QFrame, QScrollArea
)
from PySide6.QtCore import Qt, QTimer

logger = logging.getLogger(__name__)


class UpdateDialog(QDialog):
    """Dialog for update notification and download."""

    def __init__(self, update_info, mandatory=False, parent=None):
        """
        Initialize update dialog.

        Args:
            update_info: UpdateInfo object from update_checker
            mandatory: If True, user cannot skip update
            parent: Parent widget
        """
        super().__init__(parent)
        self.update_info = update_info
        self.mandatory = mandatory
        self.downloader = None
        self.is_downloading = False  # Track download state

        # Pull the active theme so colors adapt to whatever theme is set.
        from techdeck.ui.theme_manager import get_theme_manager
        self.theme = get_theme_manager().get_current_palette()

        self.setWindowTitle("Update Available" if not mandatory else "Update Required")
        self.setModal(True)
        # Width floor only here. Do NOT hardcode a minimum HEIGHT: the old
        # setMinimumHeight(200) sat BELOW what the content actually needs
        # (~295px), and on a display with fractional scaling the dialog would
        # open toward that too-low floor and clip the fixed top/bottom rows
        # (header + buttons). The real height floor is pinned from the laid-out
        # content below, after _setup_ui.
        self.setMinimumWidth(500)

        # Prevent closing if mandatory
        if mandatory:
            self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)

        self._setup_ui()

        # Pin the window's minimum HEIGHT to what the content actually needs,
        # then open at the full preferred size. The layout's minimum accounts
        # for the fixed title/labels/buttons plus the notes area, so the top
        # and bottom rows can never be clipped no matter the display scaling
        # (Qt6 defaults to fractional High-DPI scaling; on a coworker's
        # non-100% display the old 200px floor sat below the content and let
        # the dialog open too short). The width floor (500) is left intact.
        self.layout().activate()
        self.setMinimumHeight(self.layout().minimumSize().height())
        self.resize(self.sizeHint())

    def _setup_ui(self):
        """Create UI elements."""
        t = self.theme
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 24, 24, 24)

        # Title
        title_text = f"TechDeck {self.update_info.version} is available"
        if self.mandatory:
            title_text = f"TechDeck {self.update_info.version} is required"

        title = QLabel(title_text)
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(title)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet(f"background-color: {t.divider}; border: none;")
        layout.addWidget(line)

        # Mandatory warning
        if self.mandatory:
            warning = QLabel("This update is required to continue using TechDeck.")
            warning.setStyleSheet(f"color: {t.warning}; font-weight: 600;")
            layout.addWidget(warning)

        # Release notes. A bare word-wrapped QLabel under-reports its height
        # in the dialog's initial sizeHint pass, so the dialog opened too
        # short and clipped the text until a manual resize forced a relayout.
        # Hosting it in a scroll area sized from the wrapped text fixes the
        # initial height, and very long notes scroll instead of ballooning.
        if self.update_info.release_notes:
            notes = QLabel(self.update_info.release_notes)
            notes.setWordWrap(True)
            notes.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            notes.setStyleSheet(f"color: {t.text_secondary}; font-size: 12px;")
            notes_scroll = QScrollArea()
            notes_scroll.setWidgetResizable(True)
            notes_scroll.setFrameShape(QFrame.NoFrame)
            notes_scroll.setStyleSheet(
                "QScrollArea { background: transparent; }"
                "QScrollArea > QWidget > QWidget { background: transparent; }")
            notes_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            notes_scroll.setWidget(notes)
            # 452 = the 500px dialog width minus the 24px content margins.
            # Measure at the width the text actually wraps to: if the vertical
            # scrollbar appears it steals ~17px, wrapping the text one line
            # taller than a bare 452px estimate — the extra line then clipped
            # mid-height against the widget below (looked like the progress
            # bar overlapping the notes). Reserve the scrollbar width up front
            # and round up to whole text lines so a line can never be half-cut.
            wrap_w = 452 - notes_scroll.verticalScrollBar().sizeHint().width() - 4
            line_h = max(1, notes.fontMetrics().lineSpacing())
            needed = notes.heightForWidth(wrap_w)
            needed = -(-needed // line_h) * line_h + 10
            notes_scroll.setMinimumHeight(max(40, min(needed, 380)))
            notes_scroll.setMaximumHeight(380)
            layout.addWidget(notes_scroll)

        # Progress bar (hidden initially, but its layout slot is reserved from
        # the start — retainSizeWhenHidden — so revealing it at download time
        # never triggers a relayout that squeezes into the notes above).
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet(self._progress_qss())
        pb_policy = self.progress_bar.sizePolicy()
        pb_policy.setRetainSizeWhenHidden(True)
        self.progress_bar.setSizePolicy(pb_policy)
        layout.addWidget(self.progress_bar)

        # Status label (slot reserved for the same reason as the progress bar)
        self.status_label = QLabel("")
        self.status_label.setVisible(False)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet(f"color: {t.text_secondary}; font-size: 12px;")
        sl_policy = self.status_label.sizePolicy()
        sl_policy.setRetainSizeWhenHidden(True)
        self.status_label.setSizePolicy(sl_policy)
        layout.addWidget(self.status_label)

        layout.addStretch()

        # Reopen note
        reopen_note = QLabel("TechDeck will automatically reopen after installation.")
        reopen_note.setStyleSheet(f"color: {t.text_secondary}; font-size: 11px;")
        layout.addWidget(reopen_note)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch()

        if not self.mandatory:
            self.later_btn = QPushButton("Later")
            self.later_btn.clicked.connect(self.reject)
            self.later_btn.setMinimumHeight(40)
            self.later_btn.setMinimumWidth(110)
            button_layout.addWidget(self.later_btn)
        else:
            # Add quit button for mandatory updates
            self.quit_btn = QPushButton("Quit TechDeck")
            self.quit_btn.clicked.connect(self._quit_app)
            self.quit_btn.setMinimumHeight(40)
            self.quit_btn.setMinimumWidth(110)
            button_layout.addWidget(self.quit_btn)

        self.update_btn = QPushButton("Update Now")
        self.update_btn.clicked.connect(self._start_download)
        self.update_btn.setMinimumHeight(40)
        self.update_btn.setMinimumWidth(140)
        self.update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_btn.setStyleSheet(self._cta_button_qss())
        button_layout.addWidget(self.update_btn)

        layout.addLayout(button_layout)

    # --- styling helpers ----------------------------------------------------

    def _cta_button_qss(self) -> str:
        """Primary call-to-action button styled with the theme's CTA accent."""
        t = self.theme
        return f"""
            QPushButton {{
                background-color: {t.accent_two};
                color: {t.accent_two_text};
                border: none;
                padding: 10px 30px;
                border-radius: 8px;
                font-weight: 600;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {t.accent_two_hover};
            }}
            QPushButton:pressed {{
                background-color: {t.accent_two_pressed};
            }}
            QPushButton:disabled {{
                background-color: {t.border};
                color: {t.text_secondary};
            }}
        """

    def _progress_qss(self) -> str:
        t = self.theme
        return f"""
            QProgressBar {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 8px;
                text-align: center;
                color: {t.text};
                height: 25px;
            }}
            QProgressBar::chunk {{
                background-color: {t.accent_two};
                border-radius: 7px;
            }}
        """

    def _start_download(self):
        """Start downloading installer."""
        self.is_downloading = True

        # Disconnect old downloader if it exists
        if self.downloader is not None:
            try:
                self.downloader.progress_updated.disconnect()
                self.downloader.download_complete.disconnect()
                self.downloader.download_failed.disconnect()
            except RuntimeError:
                pass
            self.downloader = None

        from techdeck.core.update_downloader import UpdateDownloader

        self.update_btn.setEnabled(False)
        if hasattr(self, 'later_btn'):
            self.later_btn.setEnabled(False)
        if hasattr(self, 'quit_btn'):
            self.quit_btn.setEnabled(False)

        self.progress_bar.setVisible(True)
        self.status_label.setVisible(True)
        self.status_label.setText("Downloading update...")
        self.status_label.setStyleSheet(f"color: {self.theme.text_secondary}; font-size: 12px;")

        self.downloader = UpdateDownloader(
            self.update_info.download_url,
            self.update_info.version,
            getattr(self.update_info, "sha256", "")
        )
        self.downloader.progress_updated.connect(self._on_progress, Qt.ConnectionType.QueuedConnection)
        self.downloader.download_complete.connect(self._on_complete, Qt.ConnectionType.QueuedConnection)
        self.downloader.download_failed.connect(self._on_error, Qt.ConnectionType.QueuedConnection)
        self.downloader.start()

    def _on_progress(self, downloaded, total):
        """Update progress bar."""
        if total > 0:
            percent = int((downloaded / total) * 100)
            self.progress_bar.setValue(percent)

            # Show MB downloaded
            downloaded_mb = downloaded / (1024 * 1024)
            total_mb = total / (1024 * 1024)
            self.status_label.setText(
                f"Downloading... {downloaded_mb:.1f} MB / {total_mb:.1f} MB"
            )

    def _on_complete(self, installer_path):
        """Download complete - launch installer."""
        logger.info("Download complete, launching installer: %s", installer_path)
        from techdeck.core.update_downloader import run_installer_and_exit

        self.status_label.setText("Download complete! Launching installer...")
        self.progress_bar.setValue(100)

        # Give user a moment to see completion, then launch installer
        QTimer.singleShot(1000, lambda: run_installer_and_exit(installer_path))

    def _on_error(self, error_msg):
        """Download failed (called from background thread)."""
        self.is_downloading = False
        QTimer.singleShot(0, lambda: self._update_error_ui(error_msg))

    def _update_error_ui(self, error_msg):
        """Update UI to show error (must be called on main thread).

        The Update button is RE-ENABLED as "Try Again" — it used to stay
        disabled, so a dropped connection meant reopening the dialog to
        retry, and on a MANDATORY update the only live button left was
        "Quit TechDeck". _start_download already tears down and rebuilds
        the downloader, so retrying is just clicking again."""
        self.status_label.setText(f"Download failed: {error_msg}")
        self.status_label.setStyleSheet(f"color: {self.theme.error}; font-size: 12px;")
        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0)

        self.update_btn.setEnabled(True)
        self.update_btn.setText("Try Again")

        if hasattr(self, 'later_btn') and self.later_btn is not None:
            self.later_btn.setEnabled(True)

        if hasattr(self, 'quit_btn') and self.quit_btn is not None:
            self.quit_btn.setEnabled(True)

    def _quit_app(self):
        """Quit the application."""
        import sys
        sys.exit(0)


    def closeEvent(self, event):
        """Handle dialog close."""
        if self.is_downloading:
            # Don't allow closing while downloading
            event.ignore()
        elif self.mandatory and not self.progress_bar.isVisible():
            # Don't allow closing mandatory update dialog (unless download finished)
            event.ignore()
        else:
            event.accept()
