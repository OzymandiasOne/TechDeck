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
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QComboBox, QPushButton, QFormLayout, QFrame, QScrollArea,
    QApplication,
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

try:
    from techdeck.ui.theme_manager import get_theme_manager
except Exception:  # pragma: no cover - theme is a nicety, never load-critical
    get_theme_manager = None

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


def _palette():
    """Return the current theme palette, or None if the manager is unavailable."""
    if get_theme_manager is None:
        return None
    try:
        return get_theme_manager().get_current_palette()
    except Exception:
        return None


class MieTrakTools(PluginWindow):
    """Left: a picker list of tools. Right: the selected tool's panel."""

    def __init__(self, on_success=None):
        super().__init__("mietrak_tools", "MieTrak Tools")
        self._on_success = on_success
        self._pal = _palette()
        self.setMinimumSize(760, 560)
        self._active = None
        self._build_ui()

    def _build_ui(self):
        root = QWidget()
        row = QHBoxLayout(root)
        row.setContentsMargins(16, 16, 16, 16)
        row.setSpacing(16)

        self._list = QListWidget()
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
        row.addWidget(scroll, 1)

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
        title.setStyleSheet("font-size: 16pt; font-weight: bold;")
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
            f"background-color: {surface}; border-left: 5px solid {accent};"
            " border-radius: 4px; padding: 14px; font-size: 18pt;"
            " font-weight: bold; font-family: Consolas, monospace;"
        )
        self._result.hide()
        layout.addWidget(self._result)

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
            self._copy_btn.setEnabled(False)
            self._hint.show()
            return
        self._hint.hide()
        self._result.setText(code)
        self._result.show()
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
]
