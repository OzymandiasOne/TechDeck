"""
MieTrak Tools - a TechDeck GUI plugin that hosts a LIBRARY of small MieTrak
helpers behind a picker, one window for all of them.

Each tool is a QWidget subclass registered in the TOOLS list at the bottom of
this file. Adding a tool = one class + one registry entry; the window
(MieTrakTools) renders the left-hand picker and swaps the right-hand panel
when the selection changes. The engine mirrors Sheet Metal Calculators.

Tool 1 - Hardware Code Generator: a native port of a colleague's standalone
``ASA_Hardware_Code_Generator.exe`` (PyInstaller + tkinter, 2025). The code
tables and the assembly rule are copied verbatim from that program so the part
numbers it produced keep matching MieTrak's. Pure logic lives in
``build_hardware_code`` so it is testable without Qt.

Tool 2 - Code Reference: the chart behind tool 1, so the scheme is not
folklore - how a code is built, a decoder for a code you already have, and
every option list behind a filter box. Its rendering is pure functions
returning rich text (``anatomy_html``/``decode_html``/``tables_html``),
likewise testable headless.
"""

import html as _html_mod
from collections import namedtuple

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QComboBox, QPushButton, QFormLayout, QFrame, QScrollArea,
    QLineEdit, QApplication,
)
from PySide6.QtCore import Qt

# PluginWindow gives us the auto-applied TechDeck theme + lifecycle handling.
try:
    from techdeck.core.plugin_window import PluginWindow
except ModuleNotFoundError:  # standalone / headless testing
    import sys
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from techdeck.core.plugin_window import PluginWindow

# ============================================================================
# Brand look - fixed MieTrak colors, deliberately NOT the user's theme
# ============================================================================
# Sampled from the MieTrak Solutions logo: ribbon red, wordmark navy, and the
# orange "i" dot. The window paints itself in these on every theme (user's
# call, 2026-09-17); PluginWindow applies the theme sheet first and this
# overrides it.

BRAND_RED = "#D33339"
BRAND_RED_DARK = "#B8262C"
BRAND_RED_DEEP = "#9E1F25"
BRAND_NAVY = "#12284B"
BRAND_ORANGE = "#F08F06"
BRAND_WHITE = "#FFFFFF"
BRAND_EGGSHELL = "#FAF6F0"     # warm off-white for the tool card; fields stay pure white
BRAND_PINK = "#FFD7D9"


BRAND_TEXT = "#1A1A1A"
BRAND_GRAY = "#5A6474"
BRAND_LINE = "#C9CED8"


class _Brand:
    """Duck-types the theme palette attributes the tool panels read.
    The tool panels sit on the WHITE card, so secondary text is gray."""
    text_secondary = BRAND_GRAY
    success = BRAND_ORANGE
    surface = BRAND_NAVY


BRAND_QSS = f"""
QWidget {{ background-color: {BRAND_RED}; color: {BRAND_WHITE};
           font-family: 'Segoe UI'; font-size: 10pt; }}
QLabel {{ background: transparent; }}

/* left: the tool picker card (dark red) */
QListWidget#toolPicker {{ background-color: {BRAND_RED_DARK}; color: {BRAND_WHITE}; border: none;
                          border-radius: 8px; padding: 8px; outline: none; }}
QListWidget#toolPicker::item {{ padding: 8px 10px; border-radius: 4px; }}
QListWidget#toolPicker::item:hover {{ background-color: {BRAND_RED_DEEP}; }}
QListWidget#toolPicker::item:selected {{ background-color: {BRAND_EGGSHELL}; color: {BRAND_RED}; font-weight: bold; }}

/* right: the tool card (white) - everything inside inherits white + dark text */
QFrame#toolCard {{ background-color: {BRAND_EGGSHELL}; border-radius: 8px; }}
QFrame#toolCard QWidget {{ background-color: {BRAND_EGGSHELL}; color: {BRAND_TEXT}; }}
QFrame#toolCard QScrollArea {{ border: none; }}
QFrame#toolCard QComboBox {{ background-color: {BRAND_WHITE}; color: {BRAND_NAVY}; border: 1px solid {BRAND_LINE};
                             border-radius: 4px; padding: 6px 10px; min-height: 22px; }}
QFrame#toolCard QComboBox:hover {{ border-color: {BRAND_NAVY}; }}
QFrame#toolCard QComboBox:disabled {{ color: #8892A6; }}
QFrame#toolCard QComboBox::drop-down {{ border: none; width: 26px; }}
QFrame#toolCard QComboBox QAbstractItemView {{ background-color: {BRAND_WHITE}; color: {BRAND_NAVY};
                               selection-background-color: {BRAND_RED}; selection-color: {BRAND_WHITE};
                               border: 1px solid {BRAND_LINE}; outline: none; }}
QFrame#toolCard QPushButton {{ background-color: {BRAND_RED}; color: {BRAND_WHITE}; border: none; border-radius: 4px;
                               padding: 8px 18px; font-weight: bold; }}
QFrame#toolCard QPushButton:hover {{ background-color: {BRAND_RED_DARK}; }}
QFrame#toolCard QPushButton:pressed {{ background-color: {BRAND_NAVY}; }}
QFrame#toolCard QPushButton:disabled {{ background-color: {BRAND_LINE}; color: {BRAND_WHITE}; }}
QFrame#toolCard QScrollBar:vertical {{ background: {BRAND_EGGSHELL}; width: 10px; border: none; }}
QFrame#toolCard QScrollBar::handle:vertical {{ background: {BRAND_LINE}; border-radius: 5px; min-height: 24px; }}
QFrame#toolCard QScrollBar::add-line:vertical, QFrame#toolCard QScrollBar::sub-line:vertical {{ height: 0; }}

/* Code Reference: the decode box and the filter box */
QFrame#toolCard QLineEdit {{ background-color: {BRAND_WHITE}; color: {BRAND_NAVY};
                             border: 1px solid {BRAND_LINE}; border-radius: 4px;
                             padding: 7px 10px; }}
QFrame#toolCard QLineEdit:focus {{ border: 1px solid {BRAND_RED}; }}
QFrame#toolCard QLineEdit#codeInput {{ font-family: Consolas, monospace;
                                       font-size: 11pt; font-weight: bold; }}

/* Code Reference: imperial|metric, styled as one segmented control */
QFrame#toolCard QPushButton#segLeft, QFrame#toolCard QPushButton#segRight {{
    background-color: {BRAND_WHITE}; color: {BRAND_NAVY};
    border: 1px solid {BRAND_LINE}; font-weight: normal; padding: 7px 18px; }}
QFrame#toolCard QPushButton#segLeft {{ border-top-right-radius: 0;
                                       border-bottom-right-radius: 0; }}
QFrame#toolCard QPushButton#segRight {{ border-left: none; border-top-left-radius: 0;
                                        border-bottom-left-radius: 0; }}
QFrame#toolCard QPushButton#segLeft:hover, QFrame#toolCard QPushButton#segRight:hover {{
    border-color: {BRAND_NAVY}; }}
QFrame#toolCard QPushButton#segLeft:checked, QFrame#toolCard QPushButton#segRight:checked {{
    background-color: {BRAND_NAVY}; color: {BRAND_WHITE}; font-weight: bold; }}
"""

# Module-level reference prevents the window from being garbage collected when
# run() returns (Hard Rule: GUI windows must live in module scope).
_window = None


# ============================================================================
# Hardware Code Generator - data tables (verbatim from the original exe)
# ============================================================================

SYSTEMS = ("IMPERIAL", "METRIC")

MATERIAL_OPTIONS = [
    ("18-8 STAINLESS STEEL", "188"),
    ("304 STAINLESS STEEL", "304"),
    ("316 STAINLESS STEEL", "316"),
    ("A325 PLAIN", "A325"),
    ("BLACK OXIDE", "B"),
    ("GALVANIZED, A325", "GA325"),
    ("GALVANIZED, NO GRADE SPECIFIED", "G"),
    ("PLAIN, GRADE 5", "P5"),
    ("ZINC PLATED, NO GRADE SPECIFIED", "ZP"),
    ("ZINC PLATED, CLASS 8.8", "ZP88"),
    ("ZINC PLATED, CLASS 10.9", "ZP109"),
    ("ZINC PLATED, GRADE 5", "ZP5"),
    ("ZINC PLATED, GRADE 8", "ZP8"),
]

HARDWARE_OPTIONS = [
    ("CAP SCREW, BUTTON HEAD", "BHCS"),
    ("CAP SCREW, FLAT HEAD", "FHCS"),
    ("CAP SCREW, HEX HEAD", "HHCS"),
    ("CAP SCREW, SOCKET HEAD", "SHCS"),
    ("NUT, ACORN", "ANUT"),
    ("NUT, HEAVY HEX", "HHNUT"),
    ("NUT, HEX", "HNUT"),
    # Added 2026-09-17 at the user's request; no code existed in the original
    # program, so "SETSCR" follows the house abbreviation style. Confirm with
    # the hardware buyer. Takes thread + length like a cap screw.
    ("SET SCREW", "SETSCR"),
    ("STUD", "STUD"),
    ("WASHER, FLAT", "FWSH"),
    ("WASHER, LOCK", "LWSH"),
]

# Thread size + pitch (screws, studs, nuts).
THREAD_OPTIONS = {
    "IMPERIAL": [
        ("6-32", "632"), ("8-32", "832"), ("10-24", "1024"), ("10-32", "1032"),
        # NOTE: "F16" for 1/4-20 is what the original program emitted (the
        # same code as 3/8-16). Kept verbatim so generated numbers keep
        # matching MieTrak; confirm with the hardware buyer before changing.
        ("1/4-20", "F16"), ("5/16-18", "E18"), ("3/8-16", "F16"),
        ("7/16-14", "G14"), ("1/2-13", "H13"), ("1/2-20", "H20"),
        ("5/8-11", "M11"), ("3/4-10", "P10"), ("7/8-9", "R9"),
        ("1-8", "18"), ("1-1/4-7", "1D7"),
    ],
    "METRIC": [
        ("M4x0.70", "M4070"), ("M6x1.00", "M6100"), ("M8x1.25", "M8125"),
        ("M10x1.5", "M10150"), ("M12x1.75", "M12175"), ("M14x2.00", "M14200"),
        ("M16x2.00", "M16200"), ("M18x2.50", "M18250"), ("M20x2.50", "M20250"),
        ("M24x3.00", "M24300"),
    ],
}

# Hardware length (screws, studs).
LENGTH_OPTIONS = {
    "IMPERIAL": [
        ("1/16", "A"), ("1/8", "B"), ("3/16", "C"), ("1/4", "D"), ("5/16", "E"),
        ("3/8", "F"), ("7/16", "G"), ("1/2", "H"), ("9/16", "K"), ("5/8", "M"),
        ("11/16", "N"), ("3/4", "P"), ("13/16", "Q"), ("7/8", "R"), ("15/16", "S"),
        ("1", "1"), ("1-1/8", "1B"), ("1-3/16", "1C"), ("1-1/4", "1D"),
        ("1-5/16", "1E"), ("1-3/8", "1F"), ("1-1/2", "1H"), ("1-3/4", "1P"),
        ("2", "2"), ("2-1/4", "2D"), ("2-1/2", "2H"), ("2-3/4", "2P"),
        ("3", "3"), ("3-1/4", "3D"), ("3-1/2", "3H"), ("3-3/4", "3P"),
        ("4", "4"), ("4-1/4", "4D"), ("4-1/2", "4H"), ("4-3/4", "4P"),
        ("5", "5"), ("5-1/4", "5D"), ("5-1/2", "5H"), ("5-3/4", "5P"),
        ("6", "6"), ("6-1/2", "6H"), ("7", "7"), ("7-1/2", "7H"),
        ("8", "8"), ("8-1/2", "8H"), ("9", "9"), ("9-1/2", "9H"), ("10", "10"),
    ],
    "METRIC": [
        ("6mm", "6"), ("8mm", "8"), ("10mm", "10"), ("12mm", "12"), ("14mm", "14"),
        ("16mm", "16"), ("20mm", "20"), ("25mm", "25"), ("30mm", "30"),
        ("35mm", "35"), ("40mm", "40"), ("45mm", "45"), ("50mm", "50"),
        ("55mm", "55"), ("60mm", "60"), ("65mm", "65"), ("70mm", "70"),
        ("75mm", "75"), ("80mm", "80"), ("85mm", "85"), ("90mm", "90"),
        ("95mm", "95"), ("100mm", "100"), ("110mm", "110"), ("120mm", "120"),
        ("130mm", "130"), ("140mm", "140"), ("150mm", "150"), ("160mm", "160"),
        ("170mm", "170"), ("180mm", "180"), ("190mm", "190"), ("200mm", "200"),
        ("220mm", "220"), ("240mm", "240"), ("260mm", "260"), ("280mm", "280"),
        ("300mm", "300"),
    ],
}

# Screw size the washer fits (washers only).
SCREW_OPTIONS = {
    "IMPERIAL": [
        ("#4", "4"), ("#6", "6"), ("#8", "8"), ("#10", "10"),
        ("1/4", "D"), ("5/16", "E"), ("3/8", "F"), ("7/16", "G"), ("1/2", "H"),
        ("9/16", "K"), ("5/8", "M"), ("11/16", "N"), ("3/4", "P"), ("13/16", "Q"),
        ("7/8", "R"), ("15/16", "S"), ("1", "1"), ("1-1/8", "1B"), ("1-3/16", "1C"),
        ("1-1/4", "1D"), ("1-5/16", "1E"), ("1-3/8", "1F"), ("1-1/2", "1H"),
    ],
    "METRIC": [
        ("M4", "M4"), ("M6", "M6"), ("M8", "M8"), ("M10", "M10"), ("M12", "M12"),
        ("M14", "M14"), ("M16", "M16"), ("M18", "M18"), ("M20", "M20"),
        ("M24", "M24"),
    ],
}

WASHER_CODES = ("FWSH", "LWSH")
NUT_CODES = ("ANUT", "HHNUT", "HNUT")


class HardwareCodeError(ValueError):
    """A required field is blank - message is shown to the user."""


def hardware_fields_needed(hardware_code: str) -> tuple:
    """Which extra fields a hardware type needs, in order.

    Washers take the screw size they fit; nuts take a thread; screws and
    studs take a thread AND a length. Mirrors the original program's
    show/hide logic exactly.
    """
    if hardware_code in WASHER_CODES:
        return ("screw",)
    if hardware_code in NUT_CODES:
        return ("thread",)
    return ("thread", "length")


def build_hardware_code(material_code: str, hardware_code: str, *,
                        thread_code: str = "", length_code: str = "",
                        screw_code: str = "") -> str:
    """Assemble the MieTrak hardware part number.

    ``HW<material>-<hardware>`` then, by hardware type:
      washer -> ``-<screw size>``
      nut    -> ``-<thread>``
      other  -> ``-<thread>-<length>``
    Every piece the type needs must be non-blank, else HardwareCodeError.
    """
    if not material_code or not hardware_code:
        raise HardwareCodeError("Please complete all fields.")
    code = f"HW{material_code}-{hardware_code}"
    needed = hardware_fields_needed(hardware_code)
    values = {"thread": thread_code, "length": length_code, "screw": screw_code}
    for key in needed:
        if not values[key]:
            raise HardwareCodeError("Please complete all fields.")
        code += f"-{values[key]}"
    return code


# ============================================================================
# Reverse lookup + the reference sheet - the Code Reference tool's brain
# ============================================================================
# The generator answers "what is the code for this part?". Everything below
# answers the two questions a user actually turns up with: "what IS this code
# I am looking at?" and "what are my choices?". Kept pure and HTML-only so it
# is unit-testable without Qt, and so the panel is one QLabel per block - a
# keystroke in the filter box rebuilds a string instead of syncing a table
# widget.

ROLE_TABLES = {"thread": THREAD_OPTIONS, "length": LENGTH_OPTIONS,
               "screw": SCREW_OPTIONS}
ROLE_TITLES = {"thread": "Thread size and pitch", "length": "Length",
               "screw": "Screw size it fits"}

# hardware_fields_needed(), written out for a person.
NEEDS_ROWS = (
    ("Cap screw, set screw, stud", "Thread size, then length."),
    ("Nut - acorn, heavy hex, hex", "Thread size only. A nut has no length."),
    ("Washer - flat, lock", "The screw size it fits. No thread, no length."),
)

# How the thread and length codes are spelled, in the user's own terms. The
# letter IS the diameter, and it is the same alphabet the length column uses
# (see LENGTH_OPTIONS), so learning it once covers both suffixes.
READING_ROWS = (
    ("1024", "Small screws (#6, #8, #10): the screw number, then the threads "
             "per inch. 10-24 becomes 1024."),
    ("E18", "Bigger screws: the size letter, then the threads per inch. "
            "E is 5/16, so E18 is 5/16-18."),
    ("M20250", "Metric threads: drop the x and the dot. M20x2.50 becomes M20250."),
    ("C", "Length uses the same size letters on their own. C is 3/16 inch, "
          "1D is 1-1/4 inch, 2 is 2 inches."),
    ("40", "Metric length is just the millimetres. 40 is 40 mm."),
)

F16_NOTE = (
    "Two threads share the code <b>F16</b>: <b>1/4-20</b> and <b>3/8-16</b>. "
    "That is how the original hardware code program spelled it, and it is kept "
    "the same so codes match what is already in MieTrak. Check with the "
    "hardware buyer before you enter a 1/4-20."
)

CodeSegment = namedtuple("CodeSegment", "code role title meanings")


def with_units(pairs, role, system):
    """Spell the unit out on labels that are bare numbers in the tables.

    The generator can leave imperial lengths as "2" because the System row
    is right there on screen saying inches. A reference sheet has no such
    context, and "2" next to metric "40mm" reads as a mistake.
    """
    if system != "IMPERIAL" or role not in ("length", "screw"):
        return list(pairs)
    # A washer screw size may be a gauge (#4, #6); only the fractions are inches.
    return [(label if label.startswith("#") else label + '"', value)
            for label, value in pairs]


def _labels_for(pairs, code):
    """Every human label in ``pairs`` that maps to ``code``.

    A LIST, not a string: the inherited 1/4-20 -> F16 quirk makes one code mean
    two different threads, and a reference has to be able to say so.
    """
    return [label for label, value in pairs if value == code]


def decode_hardware_code(code: str):
    """Read a MieTrak hardware code back out in plain English.

    Returns ``(segments, system, problem)``:
      * ``segments`` - a CodeSegment per piece, left to right. ``meanings`` is
        empty for a piece that is in no table.
      * ``system``   - "IMPERIAL"/"METRIC", whichever table set explains more of
        the code, or "" when neither explains any of it.
      * ``problem``  - "" when the code is complete and understood, else one
        plain-English sentence.

    Never raises. A user pastes whatever MieTrak shows them, typos included, so
    a piece we cannot place is reported as unknown rather than failing the whole
    decode - the point is to show them WHICH piece is wrong.
    """
    raw = (code or "").strip().upper()
    if not raw:
        return [], "", ""
    parts = [p.strip() for p in raw.split("-")]
    head = parts[0]
    if not head.startswith("HW"):
        return [], "", "Every hardware code starts with HW."

    material = head[2:]
    hardware = parts[1] if len(parts) > 1 else ""
    extras = list(parts[2:])

    segments = [
        CodeSegment("HW", "prefix", "Prefix", ["Hardware"]),
        CodeSegment(material, "material", "Material and coating",
                    _labels_for(MATERIAL_OPTIONS, material)),
        CodeSegment(hardware, "hardware", "Hardware type",
                    _labels_for(HARDWARE_OPTIONS, hardware)),
    ]

    known_type = bool(_labels_for(HARDWARE_OPTIONS, hardware))
    # An unrecognised type still gets read on the common shape, so the user sees
    # the rest of the code decoded and the bad piece flagged.
    roles = hardware_fields_needed(hardware) if known_type else ("thread", "length")

    def _hits(system):
        return sum(1 for role, piece in zip(roles, extras)
                   if _labels_for(ROLE_TABLES[role][system], piece))

    scores = {s: _hits(s) for s in SYSTEMS}
    system = max(SYSTEMS, key=lambda s: scores[s])
    if not scores[system]:
        system = ""

    for i, piece in enumerate(extras):
        if i < len(roles):
            role = roles[i]
            used = system or "IMPERIAL"
            table = with_units(ROLE_TABLES[role][used], role, used)
            segments.append(CodeSegment(piece, role, ROLE_TITLES[role],
                                        _labels_for(table, piece)))
        else:
            segments.append(CodeSegment(piece, "extra", "Extra piece", []))

    if not material:
        problem = "Nothing between HW and the first hyphen - the material is missing."
    elif not hardware:
        problem = "No hardware type after the material."
    elif not known_type:
        problem = "%s is not a hardware type in the list." % hardware
    elif len(extras) < len(roles):
        missing = ", ".join(ROLE_TITLES[r].lower() for r in roles[len(extras):])
        problem = "This type also needs: %s." % missing
    elif len(extras) > len(roles):
        problem = ("There are %d more pieces than this type uses."
                   % (len(extras) - len(roles)))
    else:
        unknown = [s.code for s in segments if not s.meanings]
        problem = ("Not in the lists: " + ", ".join(unknown) + ".") if unknown else ""
    return segments, system, problem


# -- rich-text rendering -----------------------------------------------------
# Qt's QLabel understands enough HTML4 table markup to lay the sheet out in
# columns, which costs a fraction of what a QTableWidget grid would and
# re-renders on every filter keystroke for free.

_ROW_SHADE = "#F2EDE6"      # the eggshell card one step down, for zebra rows
_SPACER = '<table cellpadding="4"><tr><td></td></tr></table>'


def _esc(text) -> str:
    return _html_mod.escape(str(text))


def _bar_html(title: str) -> str:
    """A navy section header bar."""
    return ('<table width="100%%" cellspacing="0" cellpadding="6"><tr>'
            '<td bgcolor="%s"><font color="%s" size="4"><b>%s</b></font>'
            '</td></tr></table>' % (BRAND_NAVY, BRAND_WHITE, _esc(title)))


def _note_html(body_html: str) -> str:
    """A soft callout for a caveat. ``body_html`` is author-written markup."""
    return ('<table width="100%%" cellspacing="0" cellpadding="8"><tr>'
            '<td bgcolor="#FDF3E3"><font color="%s" size="2">'
            '<font color="%s"><b>Heads up</b></font> &nbsp;%s</font>'
            '</td></tr></table>' % (BRAND_TEXT, BRAND_ORANGE, body_html))


def _problem_html(text: str) -> str:
    return ('<table width="100%%" cellspacing="0" cellpadding="8"><tr>'
            '<td bgcolor="%s"><font color="%s"><b>%s</b></font></td></tr></table>'
            % (BRAND_PINK, BRAND_RED_DEEP, _esc(text)))


def _pair_table_html(pairs, columns=2, code_color=None, mono=True) -> str:
    """Zebra-striped ``code -> meaning`` rows laid out in ``columns`` columns.

    ``mono=False`` for a left column that is prose rather than a code - the
    fixed-pitch face is a signal that the cell is something you TYPE.
    """
    code_color = code_color or BRAND_RED
    face = ' face="Consolas"' if mono else ""
    # The pair widths must SUM to the column's share, or the rightmost column
    # stops short of the edge and the sheet reads as misaligned.
    share = 100 // columns
    code_w = max(8, int(share * 0.38))
    mean_w = share - code_w
    out = ['<table width="100%" cellspacing="0" cellpadding="5">']
    for i in range(0, len(pairs), columns):
        chunk = pairs[i:i + columns]
        shade = BRAND_WHITE if (i // columns) % 2 == 0 else _ROW_SHADE
        cells = ""
        for label, value in chunk:
            cells += ('<td bgcolor="%s" width="%d%%"><font%s '
                      'color="%s"><b>%s</b></font></td>'
                      '<td bgcolor="%s" width="%d%%"><font color="%s">%s</font></td>'
                      % (shade, code_w, face, code_color, _esc(value),
                         shade, mean_w, BRAND_TEXT, _esc(label)))
        for _ in range(columns - len(chunk)):   # pad so the stripe runs full width
            cells += ('<td bgcolor="%s" width="%d%%"></td>'
                      '<td bgcolor="%s" width="%d%%"></td>'
                      % (shade, code_w, shade, mean_w))
        out.append("<tr>%s</tr>" % cells)
    out.append("</table>")
    return "".join(out)


def _section_html(title, pairs, columns=2, note="") -> str:
    """A titled block, or "" when the filter left it with no rows."""
    if not pairs:
        return ""
    return (_bar_html(title) + _pair_table_html(pairs, columns)
            + (_note_html(note) if note else "") + _SPACER)


def anatomy_html() -> str:
    """The shape of a code, with one worked example read piece by piece."""
    pieces = (
        ("HW", "Always HW", "hardware"),
        ("188", "Material", "18-8 stainless"),
        ("SETSCR", "Type", "set screw"),
        ("1024", "Thread", "10-24"),
        ("C", "Length", "3/16 inch"),
    )
    chips = roles = notes = ""
    width = int(100 / len(pieces))
    for code, role, meaning in pieces:
        chips += ('<td width="%d%%" align="center" bgcolor="%s">'
                  '<font face="Consolas" color="%s" size="5"><b>%s</b></font></td>'
                  % (width, BRAND_NAVY, BRAND_WHITE, _esc(code)))
        roles += ('<td width="%d%%" align="center"><font color="%s" size="3">'
                  '<b>%s</b></font></td>' % (width, BRAND_RED, _esc(role)))
        notes += ('<td width="%d%%" align="center"><font color="%s" size="2">%s'
                  '</font></td>' % (width, BRAND_GRAY, _esc(meaning)))
    return (_bar_html("How a hardware code is built")
            + '<p><font color="%s">Every code reads left to right: <b>HW</b>, '
              'the material, the hardware type, then the rows that type needs - '
              'joined with hyphens.</font></p>' % BRAND_TEXT
            + '<table width="100%" cellspacing="5" cellpadding="6">'
            + "<tr>%s</tr><tr>%s</tr><tr>%s</tr></table>" % (chips, roles, notes)
            + _SPACER
            + _bar_html("Which rows each type needs")
            + _pair_table_html([(meaning, kind) for kind, meaning in NEEDS_ROWS],
                               columns=1, code_color=BRAND_NAVY, mono=False)
            + _SPACER
            + _bar_html("Reading the last two pieces")
            + _pair_table_html([(meaning, code) for code, meaning in READING_ROWS],
                               columns=1)
            + _SPACER)


def decode_html(code: str) -> str:
    """The plain-English read-out for a code the user pasted in."""
    if not (code or "").strip():
        return ('<font color="%s">Paste a code from MieTrak and it is read out '
                'piece by piece here.</font>' % BRAND_GRAY)
    segments, system, problem = decode_hardware_code(code)
    if not segments:
        return _problem_html(problem or "That does not look like a hardware code.")
    joiner = ' <font color="%s">or</font> ' % BRAND_GRAY
    rows = []
    for seg in segments:
        if seg.meanings:
            meaning = joiner.join(_esc(m) for m in seg.meanings)
            color = BRAND_TEXT
        else:
            meaning, color = "not in any list", BRAND_RED
        shade = BRAND_WHITE if len(rows) % 2 == 0 else _ROW_SHADE
        rows.append('<tr><td bgcolor="%s" width="20%%"><font face="Consolas" '
                    'color="%s"><b>%s</b></font></td>'
                    '<td bgcolor="%s" width="32%%"><font color="%s" size="2">%s'
                    '</font></td>'
                    '<td bgcolor="%s"><font color="%s">%s</font></td></tr>'
                    % (shade, BRAND_RED, _esc(seg.code) or "&nbsp;",
                       shade, BRAND_GRAY, _esc(seg.title),
                       shade, color, meaning))
    out = ('<table width="100%%" cellspacing="0" cellpadding="6">%s</table>'
           % "".join(rows))
    if system:
        out += ('<p><font color="%s" size="2">Read against the <b>%s</b> lists.'
                '</font></p>' % (BRAND_GRAY, system.lower()))
    if problem:
        out += _problem_html(problem)
    return out


def tables_html(system="IMPERIAL", query="") -> str:
    """Every option list for ``system``, narrowed to rows matching ``query``."""
    needle = (query or "").strip().lower()

    def keep(pairs):
        if not needle:
            return list(pairs)
        return [(label, value) for label, value in pairs
                if needle in label.lower() or needle in value.lower()]

    word = system.lower()
    blocks = [
        _section_html("Material and coating", keep(MATERIAL_OPTIONS), 2),
        _section_html("Hardware type", keep(HARDWARE_OPTIONS), 2),
        _section_html("Thread size and pitch - %s" % word,
                      keep(THREAD_OPTIONS[system]), 3,
                      note=F16_NOTE if system == "IMPERIAL" else ""),
        _section_html("Length - %s" % word,
                      keep(with_units(LENGTH_OPTIONS[system], "length", system)), 4),
        _section_html("Screw size a washer fits - %s" % word,
                      keep(with_units(SCREW_OPTIONS[system], "screw", system)), 3),
    ]
    body = "".join(b for b in blocks if b)
    if not body:
        return ('<font color="%s">Nothing in the %s lists matches "%s".</font>'
                % (BRAND_GRAY, word, _esc(query)))
    return body


def breakdown_html(code: str) -> str:
    """The live "what this code says" strip under the generated code.

    The generator's own teaching moment: the user watches the code they just
    built get read back to them, so the scheme is learned by using it.
    """
    segments, _system, _problem = decode_hardware_code(code)
    if not segments:
        return ""
    rows = []
    for seg in segments:
        if seg.code == "HW":
            continue                     # the prefix teaches nothing here
        meaning = " or ".join(seg.meanings) if seg.meanings else "-"
        rows.append('<tr><td width="18%%"><font face="Consolas" color="%s"><b>%s'
                    '</b></font></td>'
                    '<td width="30%%"><font color="%s" size="2">%s</font></td>'
                    '<td><font color="%s">%s</font></td></tr>'
                    % (BRAND_RED, _esc(seg.code), BRAND_GRAY, _esc(seg.title),
                       BRAND_TEXT, _esc(meaning)))
    return ('<p><font color="%s" size="2"><b>WHAT THIS CODE SAYS</b></font></p>'
            '<table width="100%%" cellspacing="0" cellpadding="3">%s</table>'
            '<p><font color="%s" size="2">Full chart, a decoder and every option '
            'list: pick <b>Code Reference</b> in the list on the left.</font></p>'
            % (BRAND_GRAY, "".join(rows), BRAND_GRAY))


# ============================================================================
# The engine
# ============================================================================

def run(params: dict, progress_callback, cancel_event):
    """TechDeck plugin entrypoint - opens the MieTrak Tools window."""
    log = params.get("log", print)
    on_success = params.get("on_success")

    log("Opening MieTrak Tools...")
    progress_callback(10)

    global _window
    _window = MieTrakTools(on_success=on_success)
    _window.show()

    progress_callback(100)
    log(f"MieTrak Tools window opened ({len(TOOLS)} tool(s)).")


class MieTrakTools(PluginWindow):
    """Left: a picker list of tools. Right: the selected tool's panel."""

    def __init__(self, on_success=None):
        super().__init__("mietrak_tools", "MieTrak Tools")
        self._on_success = on_success
        self._pal = _Brand          # brand colors, not the theme palette
        self.setStyleSheet(BRAND_QSS)
        self.setMinimumSize(760, 560)
        self._active = None
        self._build_ui()

    def _build_ui(self):
        root = QWidget()
        row = QHBoxLayout(root)
        row.setContentsMargins(16, 16, 16, 16)
        row.setSpacing(16)

        self._list = QListWidget()
        self._list.setObjectName("toolPicker")
        self._list.setFixedWidth(230)
        for tool in TOOLS:
            item = QListWidgetItem(tool["name"])
            item.setData(Qt.UserRole, tool["id"])
            self._list.addItem(item)
        self._list.currentRowChanged.connect(self._on_pick)
        row.addWidget(self._list)

        self._panel = QWidget()
        self._panel_layout = QVBoxLayout(self._panel)
        self._panel_layout.setContentsMargins(0, 0, 0, 0)
        self._panel_layout.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self._panel)

        # The white card the tool sits on; the red behind it reads as a frame.
        card = QFrame()
        card.setObjectName("toolCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.addWidget(scroll)
        row.addWidget(card, 1)

        self._main_layout.addWidget(root)

        if TOOLS:
            self._list.setCurrentRow(0)

    def _on_pick(self, index: int):
        if index < 0 or index >= len(TOOLS):
            return
        while self._panel_layout.count():
            item = self._panel_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        tool = TOOLS[index]

        title = QLabel(tool["name"])
        title.setStyleSheet(f"font-size: 16pt; font-weight: bold; color: {BRAND_NAVY};")
        self._panel_layout.addWidget(title)
        if tool.get("description"):
            desc = QLabel(tool["description"])
            desc.setWordWrap(True)
            if self._pal:
                desc.setStyleSheet(f"color: {self._pal.text_secondary};")
            self._panel_layout.addWidget(desc)

        self._active = tool["widget"](palette=self._pal, on_success=self._on_success)
        self._panel_layout.addWidget(self._active)
        self._panel_layout.addStretch(1)


# ============================================================================
# Tool 1 - Hardware Code Generator
# ============================================================================

class HardwareCodeGenerator(QWidget):
    """System / material / hardware type up top; the thread, length and screw
    rows show or hide by hardware type. The code updates live and a Copy
    button puts it on the clipboard (that is the success moment)."""

    def __init__(self, palette=None, on_success=None, parent=None):
        super().__init__(parent)
        self._pal = palette
        self._on_success = on_success
        self._build()

    def _combo(self, pairs, placeholder="- select -") -> QComboBox:
        combo = QComboBox()
        combo.addItem(placeholder, "")
        for label, value in pairs:
            combo.addItem(label, value)
        combo.currentIndexChanged.connect(self._refresh)
        return combo

    def _refill(self, combo: QComboBox, pairs):
        keep = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("- select -", "")
        for label, value in pairs:
            combo.addItem(label, value)
        idx = combo.findData(keep) if keep else 0
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        self._form = form

        self.system = QComboBox()
        for s in SYSTEMS:
            self.system.addItem(s, s)
        self.system.currentIndexChanged.connect(self._on_system_change)
        self.material = self._combo(MATERIAL_OPTIONS)
        self.hardware = self._combo(HARDWARE_OPTIONS)
        self.thread_size = self._combo(THREAD_OPTIONS["IMPERIAL"])
        self.screw = self._combo(SCREW_OPTIONS["IMPERIAL"])
        self.length = self._combo(LENGTH_OPTIONS["IMPERIAL"])

        self._rows = {}
        for key, label, widget in (
            ("system", "System of Measurement", self.system),
            ("material", "Material and Coating", self.material),
            ("hardware", "Hardware Type", self.hardware),
            ("thread", "Thread Size and Pitch", self.thread_size),
            ("screw", "Screw Size", self.screw),
            ("length", "Hardware Length", self.length),
        ):
            lab = QLabel(label)
            lab.setStyleSheet("font-weight: bold;")
            form.addRow(lab, widget)
            self._rows[key] = form.rowCount() - 1
        layout.addLayout(form)

        self._hint = QLabel("Pick a material and hardware type to build the code.")
        self._hint.setWordWrap(True)
        if self._pal:
            self._hint.setStyleSheet(f"color: {self._pal.text_secondary};")
        layout.addWidget(self._hint)

        self._result = QLabel("")
        self._result.setAlignment(Qt.AlignCenter)
        self._result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        accent = self._pal.success if self._pal else "#10B981"
        surface = self._pal.surface if self._pal else "#2A2A2A"
        self._result.setStyleSheet(
            f"background-color: {surface}; color: {BRAND_WHITE};"
            f" border-left: 5px solid {accent};"
            " border-radius: 4px; padding: 14px; font-size: 18pt;"
            " font-weight: bold; font-family: Consolas, monospace;"
        )
        self._result.hide()
        layout.addWidget(self._result)

        # Reads the code back out as it is built - the scheme gets learned by
        # using the tool, and it points at the Code Reference tool for the rest.
        self._breakdown = QLabel("")
        self._breakdown.setWordWrap(True)
        self._breakdown.setTextFormat(Qt.RichText)
        self._breakdown.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._breakdown.hide()
        layout.addWidget(self._breakdown)

        buttons = QHBoxLayout()
        self._copy_btn = QPushButton("Copy Code")
        self._copy_btn.clicked.connect(self._copy)
        self._copy_btn.setEnabled(False)
        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self._reset)
        buttons.addWidget(self._copy_btn)
        buttons.addWidget(reset_btn)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self._copied = QLabel("")
        if self._pal:
            self._copied.setStyleSheet(f"color: {self._pal.success};")
        layout.addWidget(self._copied)

        self._refresh()

    # -- behaviour ---------------------------------------------------------
    def current_code(self) -> str:
        """The code for the current selections; raises HardwareCodeError if
        a needed field is still blank."""
        return build_hardware_code(
            self.material.currentData() or "",
            self.hardware.currentData() or "",
            thread_code=self.thread_size.currentData() or "",
            length_code=self.length.currentData() or "",
            screw_code=self.screw.currentData() or "",
        )

    def _on_system_change(self, *_):
        system = self.system.currentData()
        self._refill(self.thread_size, THREAD_OPTIONS[system])
        self._refill(self.screw, SCREW_OPTIONS[system])
        self._refill(self.length, LENGTH_OPTIONS[system])
        self._refresh()

    def _refresh(self, *_):
        hardware = self.hardware.currentData() or ""
        needed = set(hardware_fields_needed(hardware)) if hardware else set()
        for key in ("thread", "screw", "length"):
            self._form.setRowVisible(self._rows[key], key in needed)

        self._copied.setText("")
        try:
            code = self.current_code()
        except HardwareCodeError:
            self._result.hide()
            self._breakdown.hide()
            self._copy_btn.setEnabled(False)
            self._hint.show()
            return
        self._hint.hide()
        self._result.setText(code)
        self._result.show()
        self._breakdown.setText(breakdown_html(code))
        self._breakdown.show()
        self._copy_btn.setEnabled(True)

    def _copy(self):
        try:
            code = self.current_code()
        except HardwareCodeError as e:
            self._copied.setText(str(e))
            return
        QApplication.clipboard().setText(code)
        self._copied.setText(f"Copied {code} to the clipboard.")
        if callable(self._on_success):
            self._on_success()

    def _reset(self):
        for combo in (self.material, self.hardware, self.thread_size,
                      self.screw, self.length):
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        self._refresh()


# ============================================================================
# Tool 2 - Code Reference
# ============================================================================

class HardwareCodeReference(QWidget):
    """The chart behind the generator, so the scheme is not folklore.

    Three blocks: how a code is built (with the last two suffixes spelled out,
    the pieces people ask about most), a decoder for a code they already have,
    and the full option lists behind a filter box. Each block is one rich-text
    QLabel, so a keystroke in the filter rebuilds a string rather than rebuilding
    a grid of widgets.
    """

    def __init__(self, palette=None, on_success=None, parent=None):
        super().__init__(parent)
        self._pal = palette
        self._system = SYSTEMS[0]
        self._build()

    # -- construction ------------------------------------------------------
    def _rich(self, text="") -> QLabel:
        lab = QLabel(text)
        lab.setWordWrap(True)
        lab.setTextFormat(Qt.RichText)
        lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
        return lab

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        layout.addWidget(self._rich(anatomy_html()))

        # -- decoder: the "what am I looking at?" half
        layout.addWidget(self._rich(_bar_html("Decode a code you already have")))
        self._code_in = QLineEdit()
        self._code_in.setObjectName("codeInput")
        self._code_in.setPlaceholderText("Paste a code, e.g. HW188-SETSCR-1024-C")
        self._code_in.setClearButtonEnabled(True)
        self._code_in.textChanged.connect(self._on_code_changed)
        layout.addWidget(self._code_in)
        self._decoded = self._rich(decode_html(""))
        layout.addWidget(self._decoded)

        # -- the lists: the "what are my choices?" half
        layout.addWidget(self._rich(_bar_html("Every option, by code")))
        bar = QHBoxLayout()
        bar.setSpacing(0)
        self._sys_buttons = {}
        for i, system in enumerate(SYSTEMS):
            btn = QPushButton(system.capitalize())
            btn.setObjectName("segLeft" if i == 0 else "segRight")
            btn.setCheckable(True)
            btn.setChecked(system == self._system)
            btn.clicked.connect(lambda _checked=False, s=system: self._set_system(s))
            bar.addWidget(btn)
            self._sys_buttons[system] = btn
        bar.addSpacing(12)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText('Filter the lists - try 3/8, stainless, washer')
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._render_tables)
        bar.addWidget(self._filter, 1)
        layout.addLayout(bar)

        self._tables = self._rich()
        layout.addWidget(self._tables)
        self._render_tables()

    # -- behaviour ---------------------------------------------------------
    def _on_code_changed(self, text: str):
        self._decoded.setText(decode_html(text))

    def _set_system(self, system: str):
        self._system = system
        for name, btn in self._sys_buttons.items():
            # A checkable button toggles itself on click; force the pair to read
            # as one segmented control instead of two independent toggles.
            btn.setChecked(name == system)
        self._render_tables()

    def _render_tables(self, *_):
        self._tables.setText(tables_html(self._system, self._filter.text()))


# ============================================================================
# Registry - add a tool here (a QWidget class taking palette= and on_success=)
# ============================================================================

TOOLS = [
    {
        "id": "hardware_code_generator",
        "name": "Hardware Code Generator",
        "description": (
            "Builds the MieTrak part number for a piece of hardware from its "
            "material, type, thread, and length. Copy it straight into MieTrak."
        ),
        "widget": HardwareCodeGenerator,
    },
    {
        "id": "hardware_code_reference",
        "name": "Code Reference",
        "description": (
            "The chart behind the generator: how a hardware code is built, a "
            "decoder for a code you already have, and every option list with a "
            "filter box."
        ),
        "widget": HardwareCodeReference,
    },
]
