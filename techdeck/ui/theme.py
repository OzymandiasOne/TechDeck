"""
TechDeck Theme System
Centralized color palettes and dynamic stylesheet generation.
UPDATED: Added orange accent colors for CTA buttons (Claude-style orange for dark theme)
"""

from dataclasses import dataclass
from typing import Dict


@dataclass
class ColorPalette:
    """Color palette for a theme."""
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
    accent_two: str         # Orange accent for primary actions
    accent_two_hover: str   # Orange hover state
    accent_two_pressed: str # Orange pressed state
    
    # Borders and dividers
    border: str            # Subtle borders
    border_strong: str     # Emphasized borders
    divider: str           # Horizontal rules, separators
    
    # Console/Terminal
    console_bg: str        # Console background
    console_text: str      # Console text
    
    # Status colors
    success: str
    warning: str
    error: str
    info: str
    
    # Special
    tile_selected: str     # Highlighted tile background
    shadow: str            # Drop shadows (rgba)
    
    # Missing tiles
    tile_missing_bg: str   # Missing tile background
    tile_missing_text: str # Missing tile text color
    tile_missing_border: str # Missing tile border


# Theme definitions
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
        
        # Claude.ai style orange accent
        accent_two="#C6613F",      # Claude's orange
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
        
        tile_selected="#3A3A3A",
        shadow="rgba(0, 0, 0, 0.3)",
        
        tile_missing_bg="#1A1A1A",
        tile_missing_text="#666",
        tile_missing_border="#2A2A2A",
    ),
    
    "light": ColorPalette(
        text="#3D3D3A", #1F2937
        text_secondary="#6B7280",
        background="#D6CDC1",
        surface="#DDD6CC",
        surface_hover="#DAD2C7",
        
        accent="#C6613F", 
        accent_hover="#CB7152", 
        accent_pressed="#AD5234", 
        
        # Light theme
        accent_two="#30302e",      #1b67b2"
        accent_two_hover="#3E3E3C", #1d70c3
        accent_two_pressed="#1F1F1E", #15528e
        
        border="#E5E7EB",
        border_strong="#EBE9E4",
        divider="#7A8190",
        
        console_bg="#F9FAFB",
        console_text="#1F2937",
        
        success="#10B981",
        warning="#F59E0B",
        error="#EF4444",
        info="#3B82F6",
        
        tile_selected="#DAD2C7",
        shadow="rgba(0, 0, 0, 0.1)",
        
        tile_missing_bg="#F3F4F6",
        tile_missing_text="#9CA3AF",
        tile_missing_border="#D1D5DB",
    ),

    "salmon": ColorPalette(
        text="#3D3D3A", #1F2937
        text_secondary="#808078",
        background="#EEEADD",
        surface="#F3F0E9",
        surface_hover="#E7E6E0",
        
        accent="#30302e",      
        accent_hover="#3E3E3C", 
        accent_pressed="#1F1F1E", 
        
        # Salmon theme
        
        accent_two="#FF4852", 
        accent_two_hover="#FF5C64", 
        accent_two_pressed="#FF1F2A", 
        
        border="#E5E7EB",
        border_strong="#D1D5DB",
        divider="#7A8190",
        
        console_bg="#F3F0E9",
        console_text="#3D3D3A",
        
        success="#10B981",
        warning="#F59E0B",
        error="#EF4444",
        info="#3B82F6",
        
        tile_selected="#E0E7FF",
        shadow="rgba(0, 0, 0, 0.1)",
        
        tile_missing_bg="#F3F0E9",
        tile_missing_text="#808078",
        tile_missing_border="#E7E6E0",
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
        
        # Blue theme: vibrant purple
        accent_two="#6D28D9",      #6D28D9 #712FDA
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
}


def generate_stylesheet(theme_name: str = "dark") -> str:
    """
    Generate complete Qt stylesheet for the given theme.
    
    Args:
        theme_name: Name of theme from THEMES dict
        
    Returns:
        Complete Qt stylesheet as string
    """
    if theme_name not in THEMES:
        theme_name = "dark"
    
    theme = THEMES[theme_name]
    
    return f"""
/* ===== Global Application Styles ===== */
QWidget {{
    background-color: {theme.background};
    color: {theme.text};
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}}

/* ===== Main Window ===== */
QMainWindow {{
    background-color: {theme.background};
}}

/* Central widget and all children */
QMainWindow > QWidget {{
    background-color: {theme.background};
}}

/* Pages */
QStackedWidget {{
    background-color: {theme.background};
}}

QStackedWidget > QWidget {{
    background-color: {theme.background};
}}

/* Scroll areas */
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

/* Checkable buttons (tiles) */
QPushButton:checked {{
    background-color: {theme.tile_selected};
    border: 1px solid {theme.accent};
}}

QPushButton:checked:hover {{
    background-color: {theme.tile_selected};
    border: 1px solid {theme.accent_hover};
}}

/* Primary/Accent buttons */
QPushButton[class="primary"] {{
    background-color: {theme.accent};
    color: #FFFFFF;
    border: none;
    font-weight: 600;
}}

QPushButton[class="primary"]:hover {{
    background-color: {theme.accent_hover};
}}

QPushButton[class="primary"]:pressed {{
    background-color: {theme.accent_pressed};
}}

/* Second accent color  buttons for CTAs */
QPushButton[class="cta"] {{
    background-color: {theme.accent_two};
    color: #FFFFFF;
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

/* Force sidebar to use background color */
QWidget[objectName="sidebar"] {{
    background-color: {theme.background};
}}

/* Console Widget - match page background */
ConsoleWidget {{
    background-color: {theme.background};
}}

/* Sidebar separator line */
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

/* ===== Splitter (for resizable console) ===== */
QSplitter::handle {{
    background-color: {theme.divider};
}}

QSplitter::handle:hover {{
    background-color: {theme.border_strong};
}}

QSplitter::handle:vertical {{
    height: 2px;
}}
"""


def get_theme_names() -> list[str]:
    """Get list of available theme names."""
    return list(THEMES.keys())


def get_current_palette(theme_name: str = "dark") -> ColorPalette:
    """Get color palette for theme."""
    return THEMES.get(theme_name, THEMES["dark"])


def get_missing_tile_style(theme_name: str = "dark") -> str:
    """
    Get inline stylesheet for missing tiles.
    
    Args:
        theme_name: Theme to get colors from
        
    Returns:
        Inline stylesheet string for missing tiles
    """
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