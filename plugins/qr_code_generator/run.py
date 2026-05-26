"""
QR Code Generator Plugin for TechDeck
Generates QR codes for URLs, text, and contact info with library management
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any
import qrcode
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTableWidget,
    QTableWidgetItem, QPushButton, QLabel, QLineEdit, QComboBox,
    QFormLayout, QFileDialog, QMessageBox, QTextEdit, QHeaderView,
    QGroupBox, QSpinBox, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QPixmap, QIcon, QDesktopServices

try:
    from techdeck.ui.theme_manager import get_theme_manager
    _theme_manager = get_theme_manager()
except Exception:
    _theme_manager = None

DATA_FILE = Path.home() / ".techdeck" / "qr_generator" / "entrypoints.json"

# Module-level reference prevents the window from being garbage collected when run() returns
_window = None


def run(params: dict, progress_callback, cancel_event):
    """
    TechDeck plugin entrypoint.
    Opens the QR Code Generator window.

    Args:
        params: Plugin parameters dict (includes 'settings' and 'log' injected by executor)
        progress_callback: Callable to report progress (0-100)
        cancel_event: threading.Event signalling cancellation
    """
    log = params.get("log", print)
    settings = params.get("settings", {})
    on_success = params.get("on_success")  # called when a QR code is actually generated

    try:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

        log("Opening QR Code Generator...")
        progress_callback(10)

        global _window
        _window = QRGeneratorWindow(settings, DATA_FILE, on_success=on_success)
        _window.show()

        progress_callback(100)
        log("QR Code Generator window opened.")

    except Exception as e:
        log(f"Error launching QR Code Generator: {e}")
        raise


class QRGeneratorWindow(QWidget):
    """Main window for QR Code Generator"""

    def __init__(self, config: dict, data_file: Path, on_success=None):
        super().__init__()
        self.config = config
        self.data_file = data_file
        self.entrypoints = self.load_entrypoints()
        self.current_qr_pixmap = None
        self._on_success = on_success  # callable; fired after each successful QR generation

        self.setWindowTitle("QR Code Generator")
        self.setMinimumSize(800, 600)

        self.init_ui()

    def init_ui(self):
        """Initialize user interface"""
        layout = QVBoxLayout()

        # Create tab widget
        tabs = QTabWidget()

        # Style tabs to match the surface/button color used throughout the plugin
        if _theme_manager:
            p = _theme_manager.get_current_palette()
            accent      = p.accent
            accent_hov  = p.accent_hover
            surface     = p.surface
            bg          = p.background
            text        = p.text
            border      = p.border
        else:
            accent      = "#2878A8"
            accent_hov  = "#3189BA"
            surface     = "#2A2A2A"
            bg          = "#212121"
            text        = "#ECECEC"
            border      = "#3A3A3A"

        tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {border};
                background-color: {bg};
                border-radius: 6px;
            }}
            QTabBar::tab {{
                background-color: {surface};
                color: {text};
                border: 1px solid {border};
                border-bottom: none;
                border-radius: 6px 6px 0 0;
                padding: 8px 18px;
                margin-right: 2px;
            }}
            QTabBar::tab:hover {{
                background-color: {accent_hov};
                color: #FFFFFF;
            }}
            QTabBar::tab:selected {{
                background-color: {accent};
                color: #FFFFFF;
                border-color: {accent};
            }}
        """)

        # Tab 1: Library
        library_tab = self.create_library_tab()
        tabs.addTab(library_tab, "QR Library")

        # Tab 2: Generator
        generator_tab = self.create_generator_tab()
        tabs.addTab(generator_tab, "Generate QR Code")

        layout.addWidget(tabs)
        self.setLayout(layout)

    def create_library_tab(self) -> QWidget:
        """Create the library management tab"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Header
        header = QLabel("QR Code Entry Points - Quick Access Library")
        header.setStyleSheet("font-size: 14pt; font-weight: bold; padding: 10px;")
        layout.addWidget(header)

        # Table for entrypoints
        self.library_table = QTableWidget()
        self.library_table.setColumnCount(5)
        self.library_table.setHorizontalHeaderLabels(["Name", "URL/Content", "Type", "Created", "Actions"])
        self.library_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.library_table.setAlternatingRowColors(True)
        self.library_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.library_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.library_table.verticalHeader().setVisible(False)
        self.library_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.library_table.setColumnWidth(4, 170)

        self.populate_library_table()

        layout.addWidget(self.library_table)

        # Refresh button
        refresh_btn = QPushButton("Refresh Library")
        refresh_btn.clicked.connect(self.populate_library_table)
        layout.addWidget(refresh_btn)

        widget.setLayout(layout)
        return widget

    def create_generator_tab(self) -> QWidget:
        """Create the QR code generator tab"""
        widget = QWidget()
        main_layout = QHBoxLayout()

        # Left side: Input form
        form_widget = QWidget()
        form_layout = QVBoxLayout()

        # QR Type selection
        type_group = QGroupBox("QR Code Type")
        type_layout = QVBoxLayout()

        self.qr_type_combo = QComboBox()
        self.qr_type_combo.addItems(["URL", "Text", "Contact Info (vCard)"])
        self.qr_type_combo.currentTextChanged.connect(self.on_qr_type_changed)
        # Use the same SVG arrow approach as the home page combo boxes.
        # Derive the assets path from utils.py's location so it works regardless
        # of where the plugin is installed.
        try:
            import techdeck.ui.utils as _td_utils
            from techdeck.ui.utils import make_tinted_svg_copy
            from techdeck.ui.theme_manager import get_theme_manager as _get_tm
            _p = _get_tm().get_current_palette()
            _theme_name = _get_tm().get_current_theme()
            _icon_folder = "light" if _theme_name in ["dark", "blue"] else "dark"
            # utils.py lives at <root>/techdeck/ui/utils.py - go up 3 levels to reach root
            _td_root = Path(_td_utils.__file__).resolve().parents[2]
            _icons_dir = _td_root / "assets" / "icons" / _icon_folder
            _arrow_path = make_tinted_svg_copy(_icons_dir / "chevron-down.svg", _p.text)
            _surface = _p.surface
            _text = _p.text
            _border = _p.border
            _border_strong = _p.border_strong
        except Exception as _e:
            _arrow_path = None
            _surface = "#2A2A2A"
            _text = "#ECECEC"
            _border = "#3A3A3A"
            _border_strong = "#4A4A4A"

        _arrow_rule = f'image: url("{_arrow_path}"); width: 12px; height: 12px; background: transparent; border: none; margin-right: 6px;' if _arrow_path else "image: none;"

        self.qr_type_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {_surface};
                color: {_text};
                border: 1px solid {_border};
                border-radius: 8px;
                padding: 6px 10px;
            }}
            QComboBox:hover {{
                border-color: {_border_strong};
            }}
            QComboBox::drop-down {{
                width: 24px;
                border: none;
                background: transparent;
                subcontrol-origin: padding;
                subcontrol-position: center right;
            }}
            QComboBox::down-arrow {{
                {_arrow_rule}
            }}
        """)
        type_layout.addWidget(self.qr_type_combo)
        type_group.setLayout(type_layout)
        form_layout.addWidget(type_group)

        # Dynamic input area (changes based on QR type)
        self.input_stack = QWidget()
        self.input_layout = QVBoxLayout()
        self.input_stack.setLayout(self.input_layout)
        form_layout.addWidget(self.input_stack)

        # Output settings
        output_group = QGroupBox("Output Settings")
        output_layout = QFormLayout()

        self.output_folder_edit = QLineEdit(self.config.get("default_output_folder", ""))
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_output_folder)

        folder_layout = QHBoxLayout()
        folder_layout.addWidget(self.output_folder_edit)
        folder_layout.addWidget(browse_btn)

        self.filename_edit = QLineEdit("qr_code")

        self.save_to_library_check = QCheckBox("Save to Library (URLs only)")
        self.save_to_library_check.setChecked(True)

        output_layout.addRow("Output Folder:", folder_layout)
        output_layout.addRow("Filename:", self.filename_edit)
        output_layout.addRow("", self.save_to_library_check)

        output_group.setLayout(output_layout)
        form_layout.addWidget(output_group)

        # Generate button
        self.generate_btn = QPushButton("Generate QR Code")
        self.generate_btn.setStyleSheet("font-size: 12pt; padding: 10px; background-color: #4CAF50; color: white;")
        self.generate_btn.clicked.connect(self.generate_qr_code)
        form_layout.addWidget(self.generate_btn)

        form_layout.addStretch()
        form_widget.setLayout(form_layout)

        # Right side: Preview
        preview_widget = QWidget()
        preview_layout = QVBoxLayout()

        preview_label = QLabel("QR Code Preview")
        preview_label.setStyleSheet("font-size: 12pt; font-weight: bold;")
        preview_layout.addWidget(preview_label)

        self.qr_preview = QLabel()
        self.qr_preview.setAlignment(Qt.AlignCenter)
        self.qr_preview.setMinimumSize(300, 300)
        self.qr_preview.setStyleSheet("border: 2px dashed #ccc; background-color: #f9f9f9;")
        self.qr_preview.setText("QR code will appear here")
        preview_layout.addWidget(self.qr_preview)

        preview_widget.setLayout(preview_layout)

        # Add to main layout
        main_layout.addWidget(form_widget, 1)
        main_layout.addWidget(preview_widget, 1)

        widget.setLayout(main_layout)

        # Initialize with URL input
        self.on_qr_type_changed("URL")

        return widget

    def on_qr_type_changed(self, qr_type: str):
        """Handle QR type selection change"""
        # Clear existing inputs
        while self.input_layout.count():
            child = self.input_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        input_group = QGroupBox("Input Fields")
        input_form = QFormLayout()

        if qr_type == "URL":
            self.url_edit = QLineEdit()
            self.url_edit.setPlaceholderText("https://example.com")

            self.url_name_edit = QLineEdit()
            self.url_name_edit.setPlaceholderText("My Website")

            input_form.addRow("URL:", self.url_edit)
            input_form.addRow("Name (for library):", self.url_name_edit)

            self.save_to_library_check.setEnabled(True)

        elif qr_type == "Text":
            self.text_edit = QTextEdit()
            self.text_edit.setPlaceholderText("Enter any text content...")
            self.text_edit.setMaximumHeight(150)

            input_form.addRow("Text Content:", self.text_edit)

            self.save_to_library_check.setEnabled(False)
            self.save_to_library_check.setChecked(False)

        elif qr_type == "Contact Info (vCard)":
            self.vcard_firstname = QLineEdit()
            self.vcard_lastname = QLineEdit()
            self.vcard_org = QLineEdit()
            self.vcard_phone = QLineEdit()
            self.vcard_email = QLineEdit()
            self.vcard_url = QLineEdit()

            input_form.addRow("First Name:", self.vcard_firstname)
            input_form.addRow("Last Name:", self.vcard_lastname)
            input_form.addRow("Organization:", self.vcard_org)
            input_form.addRow("Phone:", self.vcard_phone)
            input_form.addRow("Email:", self.vcard_email)
            input_form.addRow("Website:", self.vcard_url)

            self.save_to_library_check.setEnabled(False)
            self.save_to_library_check.setChecked(False)

        input_group.setLayout(input_form)
        self.input_layout.addWidget(input_group)

    def browse_output_folder(self):
        """Browse for output folder"""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Output Folder",
            self.output_folder_edit.text()
        )
        if folder:
            self.output_folder_edit.setText(folder)

    def generate_qr_code(self):
        """Generate QR code based on current inputs"""
        try:
            qr_type = self.qr_type_combo.currentText()
            output_folder = Path(self.output_folder_edit.text())
            filename = self.filename_edit.text()

            # Validate output folder
            if not output_folder.exists():
                output_folder.mkdir(parents=True, exist_ok=True)

            # Get content based on type
            content = ""
            name = filename

            if qr_type == "URL":
                url = self.url_edit.text().strip()
                if not url:
                    QMessageBox.warning(self, "Input Error", "Please enter a URL")
                    return

                # Ensure URL has proper schema
                if not url.startswith(("http://", "https://")):
                    url = "https://" + url

                content = url
                name = self.url_name_edit.text().strip() or filename

            elif qr_type == "Text":
                content = self.text_edit.toPlainText().strip()
                if not content:
                    QMessageBox.warning(self, "Input Error", "Please enter text content")
                    return

            elif qr_type == "Contact Info (vCard)":
                # Build vCard 3.0 format
                vcard_parts = ["BEGIN:VCARD", "VERSION:3.0"]

                firstname = self.vcard_firstname.text().strip()
                lastname = self.vcard_lastname.text().strip()

                if firstname or lastname:
                    vcard_parts.append(f"N:{lastname};{firstname};;;")
                    vcard_parts.append(f"FN:{firstname} {lastname}".strip())

                if self.vcard_org.text().strip():
                    vcard_parts.append(f"ORG:{self.vcard_org.text().strip()}")

                if self.vcard_phone.text().strip():
                    vcard_parts.append(f"TEL;TYPE=WORK,VOICE:{self.vcard_phone.text().strip()}")

                if self.vcard_email.text().strip():
                    vcard_parts.append(f"EMAIL;TYPE=WORK:{self.vcard_email.text().strip()}")

                if self.vcard_url.text().strip():
                    url = self.vcard_url.text().strip()
                    if not url.startswith(("http://", "https://")):
                        url = "https://" + url
                    vcard_parts.append(f"URL:{url}")

                vcard_parts.append("END:VCARD")
                content = "\n".join(vcard_parts)

                if not any([firstname, lastname, self.vcard_org.text().strip()]):
                    QMessageBox.warning(self, "Input Error", "Please enter at least a name or organization")
                    return

            # Generate QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=10,
                border=4,
            )
            qr.add_data(content)
            qr.make(fit=True)

            # Create image
            img = qr.make_image(fill_color="black", back_color="white")

            # Save to file
            output_path = output_folder / f"{filename}.png"
            img.save(str(output_path))

            # Display preview
            pixmap = QPixmap(str(output_path))
            scaled_pixmap = pixmap.scaled(
                self.qr_preview.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.qr_preview.setPixmap(scaled_pixmap)
            self.current_qr_pixmap = pixmap

            # Save to library if URL and checkbox is checked
            if qr_type == "URL" and self.save_to_library_check.isChecked():
                self.add_to_library(name, content, str(output_path), qr_type)

            # Fire the success sound - this is the meaningful completion point for a GUI plugin
            if callable(self._on_success):
                self._on_success()

            QMessageBox.information(
                self,
                "Success",
                f"QR code generated successfully!\n\nSaved to: {output_path}"
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to generate QR code:\n{str(e)}"
            )

    def add_to_library(self, name: str, url: str, qr_path: str, qr_type: str):
        """Add entry to library"""
        entry = {
            "name": name,
            "url": url,
            "qr_path": qr_path,
            "type": qr_type,
            "created": datetime.now().isoformat()
        }

        self.entrypoints.append(entry)
        self.save_entrypoints()
        self.populate_library_table()

    def populate_library_table(self):
        """Populate the library table with entrypoints"""
        self.entrypoints = self.load_entrypoints()
        self.library_table.setRowCount(0)

        for idx, entry in enumerate(self.entrypoints):
            row = self.library_table.rowCount()
            self.library_table.insertRow(row)
            self.library_table.setRowHeight(row, 38)

            # Name
            self.library_table.setItem(row, 0, QTableWidgetItem(entry.get("name", "Unnamed")))

            # URL/Content
            content = entry.get("url", "")
            if len(content) > 50:
                content = content[:47] + "..."
            self.library_table.setItem(row, 1, QTableWidgetItem(content))

            # Type
            self.library_table.setItem(row, 2, QTableWidgetItem(entry.get("type", "URL")))

            # Created date
            created = entry.get("created", "")
            if created:
                try:
                    dt = datetime.fromisoformat(created)
                    created = dt.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    pass
            self.library_table.setItem(row, 3, QTableWidgetItem(created))

            # Action buttons
            actions_widget = QWidget()
            actions_layout = QHBoxLayout()
            actions_layout.setContentsMargins(4, 2, 4, 2)
            actions_layout.setSpacing(6)

            open_btn = QPushButton("Open")
            open_btn.clicked.connect(lambda checked, i=idx: self.open_url(i))
            open_btn.setFixedSize(70, 30)
            open_btn.setStyleSheet(
                "QPushButton { padding: 0px; margin: 0px; qproperty-alignment: AlignCenter; }"
            )

            delete_btn = QPushButton("Delete")
            delete_btn.clicked.connect(lambda checked, i=idx: self.delete_entry(i))
            delete_btn.setFixedSize(70, 30)
            delete_btn.setStyleSheet(
                "QPushButton { background-color: #f44336; color: white; border: none;"
                " padding: 0px; margin: 0px; qproperty-alignment: AlignCenter; }"
            )

            actions_layout.addWidget(open_btn)
            actions_layout.addWidget(delete_btn)
            actions_layout.addStretch()
            actions_widget.setLayout(actions_layout)

            self.library_table.setCellWidget(row, 4, actions_widget)

    def open_url(self, index: int):
        """Open URL from library entry"""
        if 0 <= index < len(self.entrypoints):
            entry = self.entrypoints[index]
            url = entry.get("url", "")

            if url:
                QDesktopServices.openUrl(QUrl(url))

    def delete_entry(self, index: int):
        """Delete entry from library"""
        if 0 <= index < len(self.entrypoints):
            entry = self.entrypoints[index]
            name = entry.get("name", "Unnamed")

            reply = QMessageBox.question(
                self,
                "Confirm Delete",
                f"Are you sure you want to delete '{name}'?",
                QMessageBox.Yes | QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                self.entrypoints.pop(index)
                self.save_entrypoints()
                self.populate_library_table()

    def load_entrypoints(self) -> List[Dict[str, Any]]:
        """Load entrypoints from JSON file"""
        if self.data_file.exists():
            try:
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    return data.get("entrypoints", [])
            except Exception as e:
                print(f"Error loading entrypoints: {e}")
                return []
        return []

    def save_entrypoints(self):
        """Save entrypoints to JSON file"""
        try:
            with open(self.data_file, 'w') as f:
                json.dump({"entrypoints": self.entrypoints}, f, indent=2)
        except Exception as e:
            QMessageBox.warning(
                self,
                "Save Error",
                f"Failed to save entrypoints:\n{str(e)}"
            )
