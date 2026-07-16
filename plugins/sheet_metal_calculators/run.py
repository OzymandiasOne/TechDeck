"""
Sheet Metal Calculators - a TechDeck GUI plugin that hosts a LIBRARY of shop
calculators behind a picker.

Each calculator is a declarative spec: a list of input fields + a compute()
function. Adding a new calculator is a single entry in the CALCULATORS list at
the bottom of this file - no UI code required. The engine (SheetMetalCalculators
window) builds the form, wires validation, and shows the result for whichever
calculator is selected.

The first calculator (flat_length) is a straight port of the HTML/JS
"Flat Length Calculator" - same bend-allowance math, native + themed.
"""

import math

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QLineEdit, QComboBox, QPushButton, QFormLayout, QFrame,
    QScrollArea, QSizePolicy,
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


class CalcError(Exception):
    """Raised by a calculator's compute() with a plain-English message shown to
    the user in the form's error line (bad/missing inputs, impossible geometry).
    """


# ============================================================================
# The engine
# ============================================================================

def run(params: dict, progress_callback, cancel_event):
    """TechDeck plugin entrypoint - opens the calculators window."""
    log = params.get("log", print)
    on_success = params.get("on_success")

    log("Opening Sheet Metal Calculators...")
    progress_callback(10)

    global _window
    _window = SheetMetalCalculators(on_success=on_success)
    _window.show()

    progress_callback(100)
    log(f"Sheet Metal Calculators window opened ({len(CALCULATORS)} calculator(s)).")


def _palette():
    """Return the current theme palette, or None if the manager is unavailable."""
    if get_theme_manager is None:
        return None
    try:
        return get_theme_manager().get_current_palette()
    except Exception:
        return None


class SheetMetalCalculators(PluginWindow):
    """Left: a picker list of calculators. Right: the selected calculator's
    form + result. Rebuilds the right panel whenever the selection changes."""

    def __init__(self, on_success=None):
        super().__init__("sheet_metal_calculators", "Sheet Metal Calculators")
        self._on_success = on_success
        self._pal = _palette()
        self.setMinimumSize(760, 560)

        # Per-form runtime state, rebuilt on each calculator selection.
        self._fields = {}          # key -> (spec, widget)
        self._dynamic_labels = []  # (field_spec, QLabel) pairs to refresh live
        self._result_box = None
        self._error_label = None

        self._build_ui()

    # -- layout ------------------------------------------------------------
    def _build_ui(self):
        root = QWidget()
        row = QHBoxLayout(root)
        row.setContentsMargins(16, 16, 16, 16)
        row.setSpacing(16)

        # Left: calculator picker.
        self._list = QListWidget()
        self._list.setFixedWidth(230)
        for calc in CALCULATORS:
            item = QListWidgetItem(calc["name"])
            item.setData(Qt.UserRole, calc["id"])
            self._list.addItem(item)
        self._list.currentRowChanged.connect(self._on_pick)
        row.addWidget(self._list)

        # Right: the form panel, inside a scroll area for small screens.
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

        if CALCULATORS:
            self._list.setCurrentRow(0)

    def _clear_panel(self):
        self._fields = {}
        self._dynamic_labels = []
        self._result_box = None
        self._error_label = None
        while self._panel_layout.count():
            item = self._panel_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_pick(self, index: int):
        if index < 0 or index >= len(CALCULATORS):
            return
        self._build_form(CALCULATORS[index])

    def _build_form(self, calc: dict):
        self._clear_panel()
        self._active = calc

        title = QLabel(calc["name"])
        title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        self._panel_layout.addWidget(title)

        if calc.get("description"):
            desc = QLabel(calc["description"])
            desc.setWordWrap(True)
            if self._pal:
                desc.setStyleSheet(f"color: {self._pal.text_secondary};")
            self._panel_layout.addWidget(desc)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        for spec in calc["fields"]:
            label = QLabel(self._label_text(spec, {}))
            label.setStyleSheet("font-weight: bold;")
            widget = self._make_widget(spec)
            self._fields[spec["key"]] = (spec, widget)
            if callable(spec.get("dynamic_label")):
                self._dynamic_labels.append((spec, label))
            form.addRow(label, widget)

        self._panel_layout.addLayout(form)

        calc_btn = QPushButton(calc.get("button_text", "Calculate"))
        calc_btn.clicked.connect(self._calculate)
        self._panel_layout.addWidget(calc_btn)

        # Error line (hidden until there's something to say).
        self._error_label = QLabel("")
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet("color: #E24A4A; font-weight: bold;")
        self._error_label.hide()
        self._panel_layout.addWidget(self._error_label)

        # Result box (hidden until a successful calc).
        self._result_box = QLabel("")
        self._result_box.setAlignment(Qt.AlignCenter)
        self._result_box.setWordWrap(True)
        accent = self._pal.success if self._pal else "#10B981"
        surface = self._pal.surface if self._pal else "#2A2A2A"
        self._result_box.setStyleSheet(
            f"background-color: {surface}; border-left: 5px solid {accent};"
            " border-radius: 4px; padding: 14px; font-size: 14pt; font-weight: bold;"
        )
        self._result_box.hide()
        self._panel_layout.addWidget(self._result_box)

        self._panel_layout.addStretch(1)
        self._refresh_dynamic_labels()

    def _make_widget(self, spec: dict) -> QWidget:
        ftype = spec.get("type", "number")
        if ftype == "choice":
            combo = QComboBox()
            default_index = 0
            for i, (label, value) in enumerate(spec["choices"]):
                combo.addItem(label, value)
                if value == spec.get("default"):
                    default_index = i
            combo.setCurrentIndex(default_index)
            combo.currentIndexChanged.connect(self._refresh_dynamic_labels)
            return combo

        # number
        edit = QLineEdit()
        if spec.get("default") is not None:
            edit.setText(str(spec["default"]))
        if spec.get("placeholder"):
            edit.setPlaceholderText(spec["placeholder"])
        edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return edit

    # -- values / labels ---------------------------------------------------
    def _label_text(self, spec: dict, values: dict) -> str:
        fn = spec.get("dynamic_label")
        if callable(fn):
            try:
                return fn(values)
            except Exception:
                pass
        return spec["label"]

    def _current_values(self) -> dict:
        """Resolve every field to a native value: choice -> its data value,
        number -> float (NaN if blank/unparseable, mirroring the JS parseFloat).
        """
        values = {}
        for key, (spec, widget) in self._fields.items():
            if spec.get("type") == "choice":
                values[key] = widget.currentData()
            else:
                raw = widget.text().strip()
                try:
                    values[key] = float(raw)
                except (ValueError, TypeError):
                    values[key] = float("nan")
        return values

    def _refresh_dynamic_labels(self):
        if not self._dynamic_labels:
            return
        values = self._current_values()
        for spec, label in self._dynamic_labels:
            label.setText(self._label_text(spec, values))

    # -- compute -----------------------------------------------------------
    def _calculate(self):
        self._error_label.hide()
        self._result_box.hide()
        values = self._current_values()
        try:
            result = self._active["compute"](values)
        except CalcError as e:
            self._error_label.setText(str(e))
            self._error_label.show()
            return
        except Exception as e:  # unexpected - surface it rather than swallow
            self._error_label.setText(f"Unexpected error: {e}")
            self._error_label.show()
            return

        decimals = self._active.get("decimals", 3)
        text = result if isinstance(result, str) else f"{result:,.{decimals}f}"
        unit = self._active.get("result_unit", "")
        label = self._active.get("result_label", "Result")
        self._result_box.setText(f"{label}: {text}{(' ' + unit) if unit else ''}")
        self._result_box.show()

        if callable(self._on_success):
            self._on_success()


# ============================================================================
# Calculator specs - add a new calculator by appending one dict here.
#
#   fields: list of
#     {"key","label","type": "number"|"choice", ...}
#       number: optional "default", "placeholder"
#       choice: "choices": [(display, value), ...], optional "default" (a value)
#       any field may set "dynamic_label": fn(values) -> str  (live-updating)
#   compute(values) -> float | str      (raise CalcError for user-fixable input)
#   result_label / result_unit / decimals: how the result line reads
# ============================================================================

def _flat_length(v):
    """Bend-allowance flat length. Ported from ROLLEDFLAT_CAL_01."""
    k = v["material"]
    t = v["thickness"]
    dim_type = v["dimType"]
    dim_value = v["dimValue"]
    angle = v["angle"]

    if any(math.isnan(x) for x in (t, dim_value, angle)) or t <= 0 or dim_value <= 0:
        raise CalcError("Please enter valid numbers greater than 0.")

    if dim_type == "radius":
        inside_radius = dim_value
    elif dim_type == "id":
        inside_radius = dim_value / 2.0
    else:  # od
        inside_radius = dim_value / 2.0 - t
        if inside_radius < 0:
            raise CalcError(
                "Outside Diameter is too small for the specified thickness."
            )

    return (math.pi / 180.0) * angle * (inside_radius + k * t)


_DIM_LABELS = {
    "radius": "Inside Radius",
    "id": "Inside Diameter (ID)",
    "od": "Outside Diameter (OD)",
}

CALCULATORS = [
    {
        "id": "flat_length",
        "name": "Flat Length Calculator",
        "description": (
            "Rolled / bent flat length from the bend-allowance formula: "
            "(pi/180) x angle x (inside radius + K x thickness)."
        ),
        "fields": [
            {
                "key": "material",
                "label": "Material Type (K-Factor)",
                "type": "choice",
                "choices": [
                    ("Steel (K = 0.33)", 0.33),
                    ("Stainless Steel (K = 0.40)", 0.40),
                    ("Aluminum (K = 0.44)", 0.44),
                ],
                "default": 0.40,
            },
            {
                "key": "thickness",
                "label": "Material Thickness",
                "type": "number",
                "placeholder": "e.g., 2.5",
            },
            {
                "key": "dimType",
                "label": "Dimension Type",
                "type": "choice",
                "choices": [
                    ("Inside Radius", "radius"),
                    ("Inside Diameter (ID)", "id"),
                    ("Outside Diameter (OD)", "od"),
                ],
                "default": "radius",
            },
            {
                "key": "dimValue",
                "label": "Inside Radius",
                "type": "number",
                "placeholder": "e.g., 50",
                "dynamic_label": lambda v: _DIM_LABELS.get(v.get("dimType"), "Value"),
            },
            {
                "key": "angle",
                "label": "Bend Angle (Degrees)",
                "type": "number",
                "default": 360,
                "placeholder": "360 for full roll, 90 for partial",
            },
        ],
        "compute": _flat_length,
        "result_label": "Flat Length",
        "decimals": 3,
    },
]
