"""
TechDeck Sidebar Navigation - With SVG Icon Support and Theme Integration
Collapsible sidebar with SVG icons, tooltips, proper layout resizing, and
live theme integration.

The bottom slot holds My Account plus an accent-styled Submit Feedback action
button (restored to the sidebar 2026-07 by user request — "easy access on the
left panel"; it also stays available in Settings → Help & Feedback).
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
)
from PySide6.QtCore import Signal, Qt, QPropertyAnimation, QEasingCurve, QSize, QByteArray
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer
import logging
import re
from pathlib import Path

from techdeck.ui.theme_aware import ThemeAware

logger = logging.getLogger(__name__)


def _icon_folder_for_theme(theme_name: str) -> str:
    """Light icons for dark backgrounds, dark icons for light backgrounds."""
    return "light" if theme_name in ("dark", "blue", "cyberpunk", "matrix") else "dark"


def _tint_svg(path: Path, color: str, size: int = 20) -> QPixmap:
    """Read an SVG, replace its stroke/fill with `color`, render to pixmap."""
    with open(path, "r", encoding="utf-8") as f:
        svg_content = f.read()
    svg_content = svg_content.replace("currentColor", color)
    svg_content = re.sub(
        r'(stroke|fill)="#[0-9A-Fa-f]{3,6}"',
        rf'\1="{color}"',
        svg_content,
    )
    renderer = QSvgRenderer(QByteArray(svg_content.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


class NavButton(QPushButton):
    """Custom navigation button with icon and text.

    Lives inside the Sidebar; the Sidebar feeds it fresh palette colors
    and icon paths on theme changes via update_theme().
    """

    def __init__(self, icon_path: str, text: str, page_id: str,
                 icon_color: str = "#ECECEC", parent=None,
                 accent_style: bool = False, accent_color: str = None,
                 accent_color_hover: str = None):
        super().__init__(parent)
        self.icon_path = icon_path
        self.text = text
        self.page_id = page_id
        self.icon_color = icon_color
        self.text_color = icon_color
        self.collapsed = False
        self.accent_style = accent_style
        self.accent_color = accent_color
        self.accent_color_hover = accent_color_hover

        # Accent-styled buttons are actions, not toggleable nav items
        self.setCheckable(not accent_style)
        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(12)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(20, 20)
        self.icon_label.setStyleSheet("background: transparent; border: none;")
        self._load_icon(icon_path, icon_color)

        self.text_label = QLabel(text)
        self._apply_text_style()

        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)
        layout.addStretch()

        self.update_style()

    def _apply_text_style(self):
        if self.accent_style and self.accent_color:
            self.text_label.setStyleSheet(
                f"font-size: 13px; font-weight: 600; color: {self.accent_color}; "
                f"background: transparent; border: none;"
            )
        else:
            self.text_label.setStyleSheet(
                f"font-size: 13px; color: {self.text_color}; "
                f"background: transparent; border: none;"
            )

    def _load_icon(self, icon_path: str, color: str):
        """Load icon from SVG with custom color or use emoji/text fallback."""
        if icon_path.endswith('.svg'):
            path = Path(icon_path)
            if path.exists():
                try:
                    self.icon_label.setPixmap(_tint_svg(path, color, 20))
                    return
                except Exception as e:
                    logger.warning("Error loading icon %s: %s", icon_path, e)
            else:
                logger.warning("Icon file not found: %s", icon_path)
        # Fallback bullet
        self.icon_label.setText("•")
        self.icon_label.setStyleSheet(f"font-size: 18px; color: {color};")

    def update_theme(self, icon_path: str, icon_color: str, text_color: str,
                     accent_color: str = None, accent_color_hover: str = None):
        """Re-tint icon and re-color text for a new theme."""
        self.icon_path = icon_path
        self.icon_color = icon_color
        self.text_color = text_color
        if accent_color is not None:
            self.accent_color = accent_color
        if accent_color_hover is not None:
            self.accent_color_hover = accent_color_hover
        self._load_icon(icon_path, icon_color)
        self._apply_text_style()
        self.update_style()

    def set_collapsed(self, collapsed: bool):
        """Toggle between icon-only and full display."""
        self.collapsed = collapsed
        self.text_label.setVisible(not collapsed)

        if collapsed:
            self.setToolTip(self.text)
            self.setFixedWidth(50)
        else:
            self.setToolTip("")
            self.setMinimumWidth(0)
            self.setMaximumWidth(16777215)  # let layout fill the container

    def update_style(self):
        """Update button styling."""
        if self.accent_style and self.accent_color:
            # Theme-accent treatment (used by the Submit Feedback button)
            hover = self.accent_color_hover or self.accent_color
            self.setStyleSheet(f"""
                NavButton {{
                    background-color: transparent;
                    border: 1px solid {self.accent_color};
                    border-radius: 8px;
                    text-align: left;
                }}
                NavButton:hover {{
                    background-color: {hover};
                }}
                NavButton:hover QLabel {{
                    color: white;
                }}
            """)
        else:
            # Neutral rgba for hover/checked reads well on both light
            # and dark surfaces.
            self.setStyleSheet("""
                NavButton {
                    background-color: transparent;
                    border: none;
                    border-radius: 8px;
                    text-align: left;
                }
                NavButton:hover {
                    background-color: rgba(127, 127, 127, 0.12);
                }
                NavButton:checked {
                    background-color: rgba(127, 127, 127, 0.20);
                }
            """)


class Sidebar(QWidget, ThemeAware):
    """
    Collapsible sidebar with SVG icon support and live theme integration.

    Signals:
        page_changed(str): Emitted when page selection changes
    """

    page_changed = Signal(str)

    def __init__(self, parent=None, settings_manager=None):
        """
        Args:
            parent: Parent widget (Qt convention - comes first)
            settings_manager: SettingsManager instance for theme access
        """
        super().__init__(parent)

        if settings_manager is None:
            raise ValueError("Sidebar requires a SettingsManager instance")

        self.settings = settings_manager

        # State
        self.collapsed = False
        self.expanded_width = 200
        self.collapsed_width = 50
        self.setFixedWidth(self.expanded_width)

        from techdeck.ui.theme_manager import get_theme_manager
        theme_manager = get_theme_manager()
        self.theme = theme_manager.get_current_palette()
        self._project_root = Path(__file__).parent.parent.parent.parent

        # Main layout
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ===== Header =====
        self.header = QWidget()
        self.header.setFixedHeight(48)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(8, 0, 8, 0)
        header_layout.setSpacing(8)

        self.toggle_btn = QPushButton()
        self.toggle_btn.setFixedSize(34, 34)
        self.toggle_btn.setToolTip("Collapse sidebar")
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.setIconSize(QSize(16, 16))
        self.toggle_btn.clicked.connect(self.toggle_collapse)

        self.app_name = QLabel("TechDeck")
        self.app_name.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        header_layout.addWidget(self.toggle_btn)
        header_layout.addWidget(self.app_name)
        header_layout.addStretch()

        outer.addWidget(self.header)

        # ===== Navigation Buttons =====
        self.nav_container = QWidget()
        nav_layout = QVBoxLayout(self.nav_container)
        nav_layout.setContentsMargins(4, 8, 4, 8)
        nav_layout.setSpacing(2)

        icons_dir = self._current_icons_dir()
        self.nav_buttons = []
        pages = [
            ("home.svg", "Home", "home"),
            ("library.svg", "Library", "library"),
            ("assistant.svg", "Assistant", "assistant"),
            ("settings.svg", "Settings", "settings"),
        ]
        for icon_name, text, page_id in pages:
            btn = NavButton(
                str(icons_dir / icon_name), text, page_id,
                icon_color=self.theme.text,
            )
            btn.clicked.connect(lambda checked, pid=page_id: self._on_nav_clicked(pid))
            self.nav_buttons.append(btn)
            nav_layout.addWidget(btn)

        self.nav_buttons[0].setChecked(True)
        self._current_page_id = "home"

        # DevKit — developer-tools page (source builds only). Sits just below
        # Settings, hidden until the Home dev-mode toggle is switched on. Never
        # constructed in a frozen exe.
        from techdeck.ui.dev_mode import is_dev_build, get_dev_mode
        self.devkit_btn = None
        if is_dev_build():
            self.devkit_btn = NavButton(
                str(icons_dir / "devkit.svg"), "DevKit", "devkit",
                icon_color=self.theme.text,
            )
            self.devkit_btn.clicked.connect(
                lambda checked: self._on_nav_clicked("devkit"))
            self.devkit_btn.setVisible(get_dev_mode().is_active())
            self.nav_buttons.append(self.devkit_btn)
            nav_layout.addWidget(self.devkit_btn)
            get_dev_mode().changed.connect(self._on_dev_mode_changed)

        # Push My Account + Submit Feedback to the bottom.
        nav_layout.addStretch()

        account_btn = NavButton(
            str(icons_dir / "account.svg"), "My Account", "account",
            icon_color=self.theme.text,
        )
        account_btn.clicked.connect(lambda checked: self._on_nav_clicked("account"))
        self.nav_buttons.append(account_btn)
        nav_layout.addWidget(account_btn)

        # ===== Submit Feedback (accent-styled action button) =====
        self.feedback_btn = NavButton(
            icon_path=str(self._feedback_icon_path(icons_dir)),
            text="Submit Feedback",
            page_id="feedback",
            icon_color=self.theme.accent_two,
            accent_style=True,
            accent_color=self.theme.accent_two,
            accent_color_hover=self.theme.accent_two_hover,
        )
        self.feedback_btn.clicked.connect(self._open_feedback_dialog)
        nav_layout.addWidget(self.feedback_btn)

        # nav_container stretches so the sidebar surface color paints
        # to the bottom of the window regardless of nav content height.
        outer.addWidget(self.nav_container, 1)

        # Width animation
        self.animation = QPropertyAnimation(self, b"minimumWidth")
        self.animation.setDuration(200)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animation.valueChanged.connect(self.setMaximumWidth)

        # Subscribes to theme_changed and applies immediately.
        self.setup_theme_awareness()

    # ========== Theme handling ==========================================

    def _current_icons_dir(self) -> Path:
        from techdeck.ui.theme_manager import get_theme_manager
        theme_name = get_theme_manager().get_current_theme()
        return self._project_root / "assets" / "icons" / _icon_folder_for_theme(theme_name)

    @staticmethod
    def _feedback_icon_path(icons_dir: Path) -> Path:
        """feedback.svg, falling back to account.svg so the button always renders."""
        path = icons_dir / "feedback.svg"
        return path if path.exists() else icons_dir / "account.svg"

    def apply_theme(self):
        """Rebuild every theme-sensitive surface on theme change."""
        self.theme = self.get_current_palette()
        icons_dir = self._current_icons_dir()

        # Sidebar bg + right border
        self.setStyleSheet(f"""
            Sidebar {{
                background-color: {self.theme.surface};
                border-right: 1px solid {self.theme.border};
            }}
        """)
        self.header.setStyleSheet(f"background-color: {self.theme.surface};")
        self.nav_container.setStyleSheet(f"background-color: {self.theme.surface};")

        # Toggle button
        toggle_icon = (self._expand_icon_path() if self.collapsed
                       else self._collapse_icon_path())
        if toggle_icon.exists():
            try:
                pix = _tint_svg(toggle_icon, self.theme.text, 16)
                self.toggle_btn.setIcon(QIcon(pix))
                self.toggle_btn.setText("")
            except Exception:
                self.toggle_btn.setIcon(QIcon())
                self.toggle_btn.setText("→" if self.collapsed else "←")
        else:
            self.toggle_btn.setIcon(QIcon())
            self.toggle_btn.setText("→" if self.collapsed else "←")
        self.toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                font-size: 14px;
                border-radius: 6px;
                color: {self.theme.text};
            }}
            QPushButton:hover {{
                background-color: rgba(127, 127, 127, 0.12);
            }}
        """)

        # Wordmark
        self.app_name.setStyleSheet(f"""
            font-size: 15px;
            font-weight: 600;
            color: {self.theme.text};
            background-color: transparent;
            border: none;
            padding: 0px;
            margin: 0px;
        """)

        # Nav buttons
        for btn in self.nav_buttons:
            new_icon_path = str(icons_dir / Path(btn.icon_path).name)
            btn.update_theme(
                icon_path=new_icon_path,
                icon_color=self.theme.text,
                text_color=self.theme.text,
            )

        # Submit Feedback keeps the theme's CTA accent
        self.feedback_btn.update_theme(
            icon_path=str(self._feedback_icon_path(icons_dir)),
            icon_color=self.theme.accent_two,
            text_color=self.theme.accent_two,
            accent_color=self.theme.accent_two,
            accent_color_hover=self.theme.accent_two_hover,
        )

    def _collapse_icon_path(self) -> Path:
        return self._current_icons_dir() / "collapse.svg"

    def _expand_icon_path(self) -> Path:
        return self._current_icons_dir() / "expand.svg"

    # ========== Collapse / expand ======================================

    def toggle_collapse(self):
        """Toggle sidebar collapse state."""
        if self.collapsed:
            self.expand()
        else:
            self.collapse()

    def collapse(self):
        """Collapse sidebar to icon-only mode."""
        if self.collapsed:
            return
        self.collapsed = True
        self._refresh_toggle_icon()
        self.toggle_btn.setToolTip("Expand sidebar")
        self.app_name.hide()
        for btn in self.nav_buttons:
            btn.set_collapsed(True)
        self.feedback_btn.set_collapsed(True)
        self.animation.setStartValue(self.expanded_width)
        self.animation.setEndValue(self.collapsed_width)
        self.animation.start()

    def expand(self):
        """Expand sidebar to full mode."""
        if not self.collapsed:
            return
        self.collapsed = False
        self._refresh_toggle_icon()
        self.toggle_btn.setToolTip("Collapse sidebar")
        self.app_name.show()
        for btn in self.nav_buttons:
            btn.set_collapsed(False)
        self.feedback_btn.set_collapsed(False)
        self.raise_()
        self.animation.setStartValue(self.collapsed_width)
        self.animation.setEndValue(self.expanded_width)
        self.animation.start()

    def _refresh_toggle_icon(self):
        toggle_icon = (self._expand_icon_path() if self.collapsed
                       else self._collapse_icon_path())
        if toggle_icon.exists():
            try:
                pix = _tint_svg(toggle_icon, self.theme.text, 16)
                self.toggle_btn.setIcon(QIcon(pix))
                self.toggle_btn.setText("")
                return
            except Exception:
                pass
        self.toggle_btn.setIcon(QIcon())
        self.toggle_btn.setText("→" if self.collapsed else "←")

    def _on_dev_mode_changed(self, active: bool):
        """Reveal/hide the DevKit nav item as dev mode flips (source only)."""
        if self.devkit_btn is not None:
            self.devkit_btn.setVisible(active)

    def _on_nav_clicked(self, page_id: str):
        """Handle navigation button click."""
        for btn in self.nav_buttons:
            if btn.page_id != page_id:
                btn.setChecked(False)

        if page_id != self._current_page_id:
            from techdeck.core.audio_manager import get_audio_manager, SOUND_NAV
            get_audio_manager().play(SOUND_NAV)
            self._current_page_id = page_id

        self.page_changed.emit(page_id)

    def _open_feedback_dialog(self):
        """Open the Submit Feedback modal."""
        from techdeck.ui.dialogs.feedback_dialog import FeedbackDialog
        dlg = FeedbackDialog(parent=self.window(), settings=self.settings)
        dlg.exec()

    def set_current_page(self, page_id: str):
        """Programmatically set current page (no click sound — not user-initiated)."""
        for btn in self.nav_buttons:
            btn.setChecked(btn.page_id == page_id)
        self._current_page_id = page_id
