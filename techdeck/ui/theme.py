"""
TechDeck Theme System
Centralized color palettes and dynamic stylesheet generation.
Supports built-in and user-defined custom themes.
"""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Optional


@dataclass
class ColorPalette:
    """Color palette for a theme. font_family and extra_stylesheet are optional overrides."""
    # Primary colors
    text: str              # Main text color
    text_secondary: str    # Secondary/dimmed text
    background: str        # Main app background
    surface: str           # Card/panel backgrounds
    surface_hover: str     # Hover state for interactive surfaces

    # Accent colors
    accent: str            # Primary accent (buttons, highlights)
    accent_hover: str      # Accent hover state
    accent_pressed: str    # Accent pressed state

    # Secondary accent (orange for CTAs)
    accent_two: str         # CTA accent
    accent_two_hover: str
    accent_two_pressed: str

    # Borders and dividers
    border: str
    border_strong: str
    divider: str

    # Console/Terminal
    console_bg: str
    console_text: str

    # Status colors
    success: str
    warning: str
    error: str
    info: str

    # Special
    tile_selected: str
    shadow: str

    # Missing tiles
    tile_missing_bg: str
    tile_missing_text: str
    tile_missing_border: str

    # Optional overrides — these have defaults so existing themes don't need to set them
    font_family: str = '"Segoe UI", Arial, sans-serif'
    extra_stylesheet: str = ""
    # Text color drawn ON the saturated accent backgrounds (primary buttons,
    # selected items, etc.). Defaults to white; light-accent themes override.
    accent_text: str = "#FFFFFF"
    accent_two_text: str = "#FFFFFF"


# ── Built-in theme definitions ────────────────────────────────────────────────

THEMES: Dict[str, ColorPalette] = {
    "dark": ColorPalette(
        text="#ECECEC",
        text_secondary="#B4B4B4",
        background="#212121",
        surface="#2A2A2A",
        surface_hover="#343434",

        accent="#2878A8",
        accent_hover="#3189BA",
        accent_pressed="#1F6790",

        accent_two="#C6613F",
        accent_two_hover="#cb7152",
        accent_two_pressed="#AD5234",

        border="#3A3A3A",
        border_strong="#4A4A4A",
        divider="#1E1E1E",

        console_bg="#171717",
        console_text="#ECECEC",

        success="#10B981",
        warning="#F59E0B",
        error="#EF4444",
        info="#3B82F6",

        tile_selected="#474747",
        shadow="rgba(0, 0, 0, 0.3)",

        tile_missing_bg="#1A1A1A",
        tile_missing_text="#666",
        tile_missing_border="#2A2A2A",
    ),

    "light": ColorPalette(
        # Warm parchment, not gray: the neutrals lean cream/taupe instead of the
        # cool slate/blue-gray they used to be, so the whole theme reads like aged
        # paper rather than office-white.
        text="#3A3526",
        text_secondary="#7A6E4E",
        background="#E1D8B2",
        surface="#E8E0C0",
        surface_hover="#EFE8CA",

        accent="#C6613F",
        accent_hover="#CB7152",
        accent_pressed="#AD5234",

        accent_two="#30302e",
        accent_two_hover="#3E3E3C",
        accent_two_pressed="#1F1F1E",

        border="#D5C9A0",
        border_strong="#C7B98A",
        divider="#B6A678",

        console_bg="#F6F0D6",
        console_text="#2F2A1C",

        success="#10B981",
        warning="#F59E0B",
        error="#EF4444",
        info="#3B82F6",

        tile_selected="#D6CBA1",
        shadow="rgba(70, 55, 25, 0.12)",

        tile_missing_bg="#ECE5C6",
        tile_missing_text="#A89A70",
        tile_missing_border="#D5C9A0",
    ),

    "cherry_blossom": ColorPalette(
        text="#2A1008",
        text_secondary="#6A3828",
        background="#D08878",
        surface="#F0C4B2",
        surface_hover="#E4B0A0",

        accent="#C0392B",
        accent_hover="#D44333",
        accent_pressed="#A0301F",

        accent_two="#E07050",
        accent_two_hover="#E8846A",
        accent_two_pressed="#C05C3A",

        border="#B87870",
        border_strong="#A06858",
        divider="#A06858",

        # Light warm console so the colored labels (System/Error/etc.) keep
        # real luminance contrast — the old mid-tone #C87868 sat right at the
        # labels' luminance and made bold text shimmer/"scramble". Kept lighter
        # than `surface` so the active (console_bg) tab still reads as distinct
        # from inactive (surface) tabs.
        console_bg="#FBE5DB",
        console_text="#2A1008",

        success="#10B981",
        warning="#F59E0B",
        error="#C0392B",
        info="#3B82F6",

        tile_selected="#E8A898",
        shadow="rgba(80, 20, 10, 0.22)",

        tile_missing_bg="#F0C4B2",
        tile_missing_text="#7A4040",
        tile_missing_border="#B87870",
    ),

    "blue": ColorPalette(
        text="#E0E7FF",
        text_secondary="#A5B4FC",
        background="#1E1B4B",
        surface="#312E81",
        surface_hover="#3730A3",

        accent="#3B82F6",
        accent_hover="#60A5FA",
        accent_pressed="#2563EB",

        accent_two="#6D28D9",
        accent_two_hover="#7c40dd",
        accent_two_pressed="#5E22BF",

        border="#4338CA",
        border_strong="#4F46E5",
        divider="#2E2870",

        console_bg="#1E1B4B",
        console_text="#E0E7FF",

        success="#10B981",
        warning="#F59E0B",
        error="#EF4444",
        info="#60A5FA",

        tile_selected="#4338CA",
        shadow="rgba(30, 27, 75, 0.5)",

        tile_missing_bg="#2E2870",
        tile_missing_text="#6366F1",
        tile_missing_border="#4338CA",
    ),

    "cyberpunk": ColorPalette(
        text="#FFE100",
        text_secondary="#B89E00",
        background="#0A0012",
        surface="#150020",
        surface_hover="#1E0030",

        accent="#FFE100",
        accent_hover="#FFE833",
        accent_pressed="#CDB300",

        accent_two="#FF006E",
        accent_two_hover="#FF3399",
        accent_two_pressed="#CC0058",

        border="#2A0045",
        border_strong="#500080",
        divider="#1A0030",

        console_bg="#050010",
        console_text="#00E5FF",

        success="#00FF9F",
        warning="#FFE100",
        error="#FF0040",
        info="#00E5FF",

        tile_selected="#2A0045",
        shadow="rgba(255, 0, 110, 0.25)",

        tile_missing_bg="#0D0020",
        tile_missing_text="#500080",
        tile_missing_border="#2A0045",

        accent_text="#0A0012",   # dark text on the bright-yellow accent
        accent_two_text="#FFFFFF",  # white reads fine on the magenta CTA
        font_family='"Consolas", "Courier New", monospace',
        extra_stylesheet="""
QLineEdit:focus, QTextEdit:focus {
    border: 2px solid #FFE100;
}
QPushButton:hover {
    border-color: #FFE100;
}
QPushButton[class="primary"] {
    border: 1px solid #FFE100;
}
QPushButton[class="cta"] {
    border: 1px solid #FF006E;
}
""",
    ),

    "matrix": ColorPalette(
        text="#00FF41",
        text_secondary="#00C034",
        background="#000000",
        surface="#001200",
        surface_hover="#001800",

        accent="#00FF41",
        accent_hover="#33FF66",
        accent_pressed="#00CC33",

        accent_two="#39FF14",
        accent_two_hover="#5CFF3A",
        accent_two_pressed="#2ECC10",

        border="#002800",
        border_strong="#004000",
        divider="#001200",

        console_bg="#000000",
        console_text="#00FF41",

        success="#00FF41",
        warning="#ADFF2F",
        error="#FF0000",
        info="#00FFCC",

        tile_selected="#003A00",
        shadow="rgba(0, 255, 65, 0.15)",

        tile_missing_bg="#000800",
        tile_missing_text="#005000",
        tile_missing_border="#002800",

        accent_text="#000000",      # dark text on the bright-green accents
        accent_two_text="#000000",
        font_family='"Courier New", Consolas, monospace',
        extra_stylesheet="""
QLineEdit:focus, QTextEdit:focus {
    border: 2px solid #00FF41;
}
QPushButton:hover {
    border-color: #00FF41;
}
""",
    ),
}


# ── Custom theme helpers ───────────────────────────────────────────────────────

def palette_to_dict(p: ColorPalette) -> dict:
    return asdict(p)


def palette_from_dict(d: dict) -> ColorPalette:
    # Only pass fields that ColorPalette actually accepts, with safe defaults
    fields = {f.name for f in ColorPalette.__dataclass_fields__.values()}
    filtered = {k: v for k, v in d.items() if k in fields}
    return ColorPalette(**filtered)


def load_custom_themes(custom_dir: Path) -> None:
    """Load all JSON theme files from custom_dir into the THEMES dict."""
    if not custom_dir.exists():
        return
    for path in custom_dir.glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            name = path.stem.lower()
            THEMES[name] = palette_from_dict(data)
        except Exception as e:
            print(f"[theme] Could not load custom theme {path.name}: {e}")


def save_custom_theme(name: str, palette: ColorPalette, custom_dir: Path) -> None:
    """Save a palette as a JSON file in custom_dir."""
    custom_dir.mkdir(parents=True, exist_ok=True)
    path = custom_dir / f"{name.lower()}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(palette_to_dict(palette), f, indent=2)
    THEMES[name.lower()] = palette


def delete_custom_theme(name: str, custom_dir: Path) -> None:
    """Delete a custom theme file and remove it from THEMES."""
    path = custom_dir / f"{name.lower()}.json"
    if path.exists():
        path.unlink()
    THEMES.pop(name.lower(), None)


def is_builtin_theme(name: str) -> bool:
    return name.lower() in ("dark", "light", "cherry_blossom", "blue", "cyberpunk", "matrix")


# ── Stylesheet generator ───────────────────────────────────────────────────────

def generate_stylesheet(theme_name: str = "dark") -> str:
    if theme_name not in THEMES:
        theme_name = "dark"
    theme = THEMES[theme_name]

    base = f"""
/* ===== Global Application Styles ===== */
QWidget {{
    background-color: {theme.background};
    color: {theme.text};
    font-family: {theme.font_family};
    font-size: 13px;
}}

/* ===== Main Window ===== */
QMainWindow {{
    background-color: {theme.background};
}}

QMainWindow > QWidget {{
    background-color: {theme.background};
}}

QStackedWidget {{
    background-color: {theme.background};
}}

QStackedWidget > QWidget {{
    background-color: {theme.background};
}}

QScrollArea {{
    background-color: {theme.background};
    border: none;
    border-radius: 0px;
}}

QScrollArea > QWidget {{
    background-color: {theme.background};
    border-radius: 0px;
}}

QScrollArea > QWidget > QWidget {{
    background-color: {theme.background};
    border-radius: 0px;
}}

/* ===== Buttons ===== */
QPushButton {{
    background-color: {theme.surface};
    color: {theme.text};
    border: 1px solid {theme.border};
    border-radius: 8px;
    padding: 8px 16px;
    outline: none;
}}

QPushButton:hover {{
    background-color: {theme.surface_hover};
}}

QPushButton:pressed {{
    background-color: {theme.border_strong};
}}

QPushButton:disabled {{
    opacity: 0.5;
}}

QPushButton:checked {{
    background-color: {theme.tile_selected};
    border: 1px solid {theme.accent};
}}

QPushButton:checked:hover {{
    background-color: {theme.tile_selected};
    border: 1px solid {theme.accent_hover};
}}

QPushButton[class="primary"] {{
    background-color: {theme.accent};
    color: {theme.accent_text};
    border: none;
    font-weight: 600;
}}

QPushButton[class="primary"]:hover {{
    background-color: {theme.accent_hover};
}}

QPushButton[class="primary"]:pressed {{
    background-color: {theme.accent_pressed};
}}

QPushButton[class="cta"] {{
    background-color: {theme.accent_two};
    color: {theme.accent_two_text};
    border: none;
    font-weight: 600;
    border-radius: 8px;
}}

QPushButton[class="cta"]:hover {{
    background-color: {theme.accent_two_hover};
}}

QPushButton[class="cta"]:pressed {{
    background-color: {theme.accent_two_pressed};
}}

/* ===== Sidebar ===== */
Sidebar {{
    background-color: {theme.background};
    border-right: 1px solid {theme.console_bg};
}}

QWidget[objectName="sidebar"] {{
    background-color: {theme.background};
}}

ConsoleWidget {{
    background-color: {theme.background};
}}

Sidebar > QWidget[class="separator"] {{
    background-color: {theme.console_bg};
}}

QListWidget {{
    background-color: {theme.console_bg};
    color: {theme.text};
    border: none;
    outline: none;
}}

QListWidget::item {{
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 10px 12px;
    margin: 4px 6px;
}}

QListWidget::item:hover {{
    background-color: {theme.surface_hover};
}}

QListWidget::item:selected {{
    background-color: {theme.surface};
}}

/* ===== Dropdowns ===== */
QComboBox {{
    background-color: {theme.surface};
    color: {theme.text};
    border: 1px solid {theme.border};
    border-radius: 8px;
    padding: 6px 10px;
    min-width: 150px;
}}

QComboBox:hover {{
    border-color: {theme.border_strong};
}}

QComboBox::drop-down {{
    border: none;
    background: transparent;
    width: 20px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {theme.text};
    margin-right: 5px;
}}

QComboBox QAbstractItemView {{
    background-color: {theme.surface};
    color: {theme.text};
    border: 1px solid {theme.border};
    selection-background-color: {theme.tile_selected};
    outline: none;
}}

/* ===== Input Fields ===== */
QLineEdit, QTextEdit {{
    background-color: {theme.surface};
    color: {theme.text};
    border: 1px solid {theme.border};
    border-radius: 6px;
    padding: 6px 10px;
}}

QLineEdit:focus, QTextEdit:focus {{
    border-color: {theme.accent};
}}

/* ===== Frames/Panels ===== */
QFrame {{
    background-color: {theme.surface};
    border-radius: 10px;
}}

/* ===== Scrollbars ===== */
QScrollBar:vertical {{
    background-color: {theme.background};
    width: 12px;
    border: none;
}}

QScrollBar::handle:vertical {{
    background-color: {theme.border_strong};
    border-radius: 6px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {theme.text_secondary};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background-color: {theme.background};
    height: 12px;
    border: none;
}}

QScrollBar::handle:horizontal {{
    background-color: {theme.border_strong};
    border-radius: 6px;
    min-width: 30px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {theme.text_secondary};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* ===== Tooltips ===== */
QToolTip {{
    background-color: {theme.console_bg};
    color: {theme.text};
    border: 1px solid {theme.border};
    border-radius: 6px;
    padding: 6px 8px;
}}

/* ===== Dialogs ===== */
QDialog {{
    background-color: {theme.background};
}}

/* ===== Labels ===== */
QLabel {{
    background: transparent;
    color: {theme.text};
}}

/* ===== Splitter ===== */
QSplitter::handle {{
    background-color: {theme.divider};
}}

QSplitter::handle:hover {{
    background-color: {theme.border_strong};
}}

QSplitter::handle:vertical {{
    height: 2px;
}}

/* ===== Sliders ===== */
QSlider::groove:horizontal {{
    background-color: {theme.border};
    height: 4px;
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background-color: {theme.accent};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}

QSlider::sub-page:horizontal {{
    background-color: {theme.accent};
    border-radius: 2px;
}}

QSlider::groove:vertical {{
    background-color: {theme.border};
    width: 4px;
    border-radius: 2px;
}}

QSlider::handle:vertical {{
    background-color: {theme.accent};
    width: 14px;
    height: 14px;
    margin: 0 -5px;
    border-radius: 7px;
}}

QSlider::sub-page:vertical {{
    background-color: {theme.accent};
    border-radius: 2px;
}}
"""
    return base + "\n" + theme.extra_stylesheet


def get_theme_names() -> list:
    return list(THEMES.keys())


def get_current_palette(theme_name: str = "dark") -> ColorPalette:
    return THEMES.get(theme_name, THEMES["dark"])


def get_missing_tile_style(theme_name: str = "dark") -> str:
    theme = THEMES.get(theme_name, THEMES["dark"])
    return f"""
        QPushButton {{
            background-color: {theme.tile_missing_bg};
            color: {theme.tile_missing_text};
            border: 1px solid {theme.tile_missing_border};
            border-radius: 12px;
        }}
        QPushButton:hover {{
            background-color: {theme.tile_missing_bg};
            opacity: 0.9;
        }}
        QPushButton:checked {{
            background-color: {theme.tile_missing_bg};
            border: 1px solid {theme.tile_missing_border};
            border-radius: 12px;
        }}
    """
