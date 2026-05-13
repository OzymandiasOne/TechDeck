"""
Update notification and download dialog.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton, 
    QProgressBar, QHBoxLayout, QMessageBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont


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
        
        self.setWindowTitle("Update Available" if not mandatory else "Update Required")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(200)
        
        # Prevent closing if mandatory
        if mandatory:
            self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Create UI elements."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title_text = f"TechDeck {self.update_info.version} is available!"
        if self.mandatory:
            title_text = f"TechDeck {self.update_info.version} is required"
        
        title = QLabel(title_text)
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        
        # Mandatory warning
        if self.mandatory:
            warning = QLabel("This update is required to continue using TechDeck.")
            warning.setStyleSheet("color: #D97706; font-weight: bold;")
            layout.addWidget(warning)
        
        # Release notes
        if self.update_info.release_notes:
            notes = QLabel(self.update_info.release_notes)
            notes.setWordWrap(True)
            notes.setStyleSheet("color: #666; margin: 10px 0;")
            layout.addWidget(notes)
        
        # Progress bar (hidden initially)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ccc;
                border-radius: 8px;
                text-align: center;
                height: 25px;
            }
            QProgressBar::chunk {
                background-color: #D97706;
                border-radius: 7px;
            }
        """)
        layout.addWidget(self.progress_bar)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setVisible(False)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.update_btn = QPushButton("Update Now")
        self.update_btn.clicked.connect(self._start_download)
        self.update_btn.setMinimumHeight(40)
        self.update_btn.setStyleSheet("""
            QPushButton {
                background-color: #D97706;
                color: white;
                border: none;
                padding: 10px 30px;
                border-radius: 8px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #B45309;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
        
        if not self.mandatory:
            self.later_btn = QPushButton("Later")
            self.later_btn.clicked.connect(self.reject)  # Simple reject now that threading is fixed
            self.later_btn.setMinimumHeight(40)
            self.later_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #666;
                    border: 1px solid #ccc;
                    padding: 10px 30px;
                    border-radius: 8px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #f5f5f5;
                }
                QPushButton:disabled {
                    color: #ccc;
                    border-color: #e5e5e5;
                }
            """)
            button_layout.addWidget(self.later_btn)
        else:
            # Add quit button for mandatory updates
            self.quit_btn = QPushButton("Quit TechDeck")
            self.quit_btn.clicked.connect(self._quit_app)
            self.quit_btn.setMinimumHeight(40)
            self.quit_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #999;
                    border: 1px solid #ccc;
                    padding: 10px 30px;
                    border-radius: 8px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #f5f5f5;
                }
            """)
            button_layout.addWidget(self.quit_btn)
        
        button_layout.addStretch()
        button_layout.addWidget(self.update_btn)
        
        layout.addLayout(button_layout)
    
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
        self.status_label.setStyleSheet("")
        
        self.downloader = UpdateDownloader(
            self.update_info.download_url,
            self.update_info.version
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
        print(f"[DIALOG] _on_complete called! Installer path: {installer_path}", flush=True)
        from techdeck.core.update_downloader import run_installer_and_exit
        
        self.status_label.setText("Download complete! Launching installer...")
        self.progress_bar.setValue(100)
        
        print("[DIALOG] Setting up QTimer to launch installer in 1 second...", flush=True)
        # Give user a moment to see completion, then launch installer
        QTimer.singleShot(1000, lambda: run_installer_and_exit(installer_path))
    
    def _on_error(self, error_msg):
        """Download failed (called from background thread)."""
        self.is_downloading = False
        QTimer.singleShot(0, lambda: self._update_error_ui(error_msg))
    
    def _update_error_ui(self, error_msg):
        """Update UI to show error (must be called on main thread)."""
        self.status_label.setText(f"Download failed: {error_msg}")
        self.progress_bar.setVisible(False)
        
        self.update_btn.setEnabled(False)
        
        if hasattr(self, 'later_btn') and self.later_btn is not None:
            self.later_btn.setEnabled(True)
            self.later_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #666;
                    border: 1px solid #ccc;
                    padding: 10px 30px;
                    border-radius: 8px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #f5f5f5;
                }
            """)
        
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
