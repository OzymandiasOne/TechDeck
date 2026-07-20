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
        self._visibility_rows = []  # (field_spec, row_index) pairs to show/hide live
        self._form = None          # the active QFormLayout (for setRowVisible)
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
        self._visibility_rows = []
        self._form = None
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

        for row_index, spec in enumerate(calc["fields"]):
            label = QLabel(self._label_text(spec, {}))
            label.setStyleSheet("font-weight: bold;")
            widget = self._make_widget(spec)
            self._fields[spec["key"]] = (spec, widget)
            if callable(spec.get("dynamic_label")):
                self._dynamic_labels.append((spec, label))
            if callable(spec.get("visible_when")):
                self._visibility_rows.append((spec, row_index))
            form.addRow(label, widget)

        self._form = form
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
        self._on_input_change()

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
            combo.currentIndexChanged.connect(self._on_input_change)
            return combo

        # number
        edit = QLineEdit()
        if spec.get("default") is not None:
            edit.setText(str(spec["default"]))
        if spec.get("placeholder"):
            edit.setPlaceholderText(spec["placeholder"])
        edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        edit.textChanged.connect(self._on_input_change)
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

    def _on_input_change(self, *args):
        """Any input changed: refresh live labels and conditional-field visibility."""
        if not self._dynamic_labels and not self._visibility_rows:
            return
        values = self._current_values()
        self._refresh_dynamic_labels(values)
        self._refresh_visibility(values)

    def _refresh_dynamic_labels(self, values=None):
        if not self._dynamic_labels:
            return
        if values is None:
            values = self._current_values()
        for spec, label in self._dynamic_labels:
            label.setText(self._label_text(spec, values))

    def _refresh_visibility(self, values=None):
        if not self._visibility_rows or self._form is None:
            return
        if values is None:
            values = self._current_values()
        for spec, row_index in self._visibility_rows:
            try:
                visible = bool(spec["visible_when"](values))
            except Exception:
                visible = True
            self._form.setRowVisible(row_index, visible)

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
        body = f"{text}{(' ' + unit) if unit else ''}"
        # A calc that computes its own multi-line result string sets a falsy
        # result_label to suppress the "Label: " prefix (e.g. Bend Deduction).
        self._result_box.setText(f"{label}: {body}" if label else body)
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


def _result_table(rows):
    """Render a list of (label, value) rows as an HTML table for a calculator
    that produces several results at once. The LAST row is the headline (bold,
    larger, accent-colored) - mirroring the HTML calculators' bottom "total"
    line. Returned as a string so the engine shows it verbatim (the calc sets a
    falsy result_label to suppress the "Result:" prefix).
    """
    parts = ["<table style='border-collapse:collapse;'>"]
    last = len(rows) - 1
    for i, (label, value) in enumerate(rows):
        headline = i == last
        size = "15pt" if headline else "11pt"
        weight = "bold" if headline else "normal"
        top = "border-top:1px solid #888; padding-top:6px;" if headline else ""
        parts.append(
            f"<tr>"
            f"<td style='text-align:left; padding:3px 18px 3px 0; "
            f"font-size:{size}; font-weight:{weight}; {top}'>{label}</td>"
            f"<td style='text-align:right; font-family:monospace; "
            f"font-size:{size}; font-weight:{weight}; {top}'>{value}</td>"
            f"</tr>"
        )
    parts.append("</table>")
    return "".join(parts)


def _bend_deduction(v):
    """Bend deduction / allowance / setback. Ported from BenDud_01."""
    t = v["thickness"]
    r = v["radius"]
    angle = v["angle"]
    k = v["kfactor_custom"] if v["kfactor_choice"] == "custom" else v["kfactor_choice"]

    if any(math.isnan(x) for x in (t, r, angle, k)):
        raise CalcError("Please enter valid numbers in every field.")
    if t <= 0:
        raise CalcError("Material Thickness must be greater than 0.")
    if not (0 < angle < 180):
        raise CalcError("Bend Angle must be between 0 and 180 degrees.")
    if k <= 0:
        raise CalcError("K-Factor must be greater than 0.")

    angle_rad = math.radians(angle)
    ba = angle_rad * (r + k * t)
    ossb = math.tan(angle_rad / 2.0) * (r + t)
    bd = 2.0 * ossb - ba

    return _result_table([
        ("Outside Setback (OSSB)", f"{ossb:.4f}"),
        ("Bend Allowance (BA)", f"{ba:.4f}"),
        ("Bend Deduction (BD)", f"{bd:.4f}"),
    ])


_WEIGHT_METHOD_LABELS = {
    "sqin": "Total Square Inches (SQ IN)",
    "sqft": "Total Square Feet (SQ FT)",
}


def _material_weight(v):
    """Sheet material weight by sheet size or total area. Ported from
    Mat_Weight_Cal_02."""
    density = v["density_custom"] if v["material"] == "custom" else v["material"]
    t = v["thickness"]
    method = v["method"]

    if math.isnan(density) or density <= 0:
        raise CalcError("Please enter a valid material density greater than 0.")
    if math.isnan(t) or t <= 0:
        raise CalcError("Material Thickness must be greater than 0.")

    if method == "sheet":
        length = v["length"]
        width = v["width"]
        if any(math.isnan(x) for x in (length, width)):
            raise CalcError("Please enter valid Length and Width values.")
        total_sq_in = length * width
    elif method == "sqft":
        if math.isnan(v["area"]):
            raise CalcError("Please enter a valid area.")
        total_sq_in = v["area"] * 144.0
    else:  # sqin
        if math.isnan(v["area"]):
            raise CalcError("Please enter a valid area.")
        total_sq_in = v["area"]

    if total_sq_in <= 0:
        raise CalcError("The sheet area must be greater than 0.")

    total_sq_ft = total_sq_in / 144.0
    total_weight = total_sq_in * t * density
    weight_per_sq_ft = 144.0 * t * density

    return _result_table([
        ("Total Area", f"{total_sq_ft:,.2f} sq ft ({total_sq_in:,.0f} sq in)"),
        ("Unit Weight", f"{weight_per_sq_ft:,.2f} lbs / sq ft"),
        ("Total Weight", f"{total_weight:,.2f} lbs"),
    ])

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
    {
        "id": "bend_deduction",
        "name": "Bend Deduction Calculator",
        "description": (
            "Bend allowance, outside setback, and bend deduction for a single "
            "air bend, from thickness, inside radius, angle, and K-factor."
        ),
        "fields": [
            {
                "key": "thickness",
                "label": "Material Thickness (T)",
                "type": "number",
                "default": 0.063,
                "placeholder": "e.g., 0.063",
            },
            {
                "key": "radius",
                "label": "Inside Bend Radius (R)",
                "type": "number",
                "default": 0.063,
                "placeholder": "e.g., 0.063",
            },
            {
                "key": "angle",
                "label": "Bend Angle (Degrees)",
                "type": "number",
                "default": 90,
                "placeholder": "1 - 179",
            },
            {
                "key": "kfactor_choice",
                "label": "K-Factor",
                "type": "choice",
                "choices": [
                    ("0.44 - Mild Steel (Air Bend)", 0.44),
                    ("0.45 - Stainless Steel (Air Bend)", 0.45),
                    ("0.40 - Aluminum (Air Bend)", 0.40),
                    ("0.38 - Copper / Soft Brass", 0.38),
                    ("0.50 - Bottoming / Coined", 0.50),
                    ("Custom Value...", "custom"),
                ],
                "default": 0.44,
            },
            {
                "key": "kfactor_custom",
                "label": "Custom K-Factor",
                "type": "number",
                "default": 0.44,
                "placeholder": "e.g., 0.42",
                "visible_when": lambda v: v.get("kfactor_choice") == "custom",
            },
        ],
        "compute": _bend_deduction,
        "result_label": None,  # compute returns its own multi-row result
    },
    {
        "id": "material_weight",
        "name": "Material Weight Calculator",
        "description": (
            "Sheet / plate weight from material density and thickness - by sheet "
            "size (L x W) or by a known total area in square inches or square feet."
        ),
        "fields": [
            {
                "key": "material",
                "label": "Material Type",
                "type": "choice",
                "choices": [
                    ("Mild Steel (0.2833 lbs/in3)", 0.2833),
                    ("Aluminum 5052/6061 (0.098 lbs/in3)", 0.0980),
                    ("Stainless 304/316 (0.289 lbs/in3)", 0.2890),
                    ("Copper (0.323 lbs/in3)", 0.3230),
                    ("Brass (0.307 lbs/in3)", 0.3070),
                    ("Custom Density...", "custom"),
                ],
                "default": 0.2833,
            },
            {
                "key": "density_custom",
                "label": "Custom Density (lbs/in3)",
                "type": "number",
                "placeholder": "e.g., 0.2833",
                "visible_when": lambda v: v.get("material") == "custom",
            },
            {
                "key": "thickness",
                "label": "Material Thickness (Inches)",
                "type": "number",
                "default": 0.190,
                "placeholder": "e.g., 0.190",
            },
            {
                "key": "method",
                "label": "Calculation Method",
                "type": "choice",
                "choices": [
                    ("Sheet Size (L x W)", "sheet"),
                    ("Total SQ IN", "sqin"),
                    ("Total SQ FT", "sqft"),
                ],
                "default": "sheet",
            },
            {
                "key": "length",
                "label": "Length (Inches)",
                "type": "number",
                "default": 96,
                "visible_when": lambda v: v.get("method") == "sheet",
            },
            {
                "key": "width",
                "label": "Width (Inches)",
                "type": "number",
                "default": 48,
                "visible_when": lambda v: v.get("method") == "sheet",
            },
            {
                "key": "area",
                "label": "Total Square Inches (SQ IN)",
                "type": "number",
                "default": 4608,
                "dynamic_label": lambda v: _WEIGHT_METHOD_LABELS.get(
                    v.get("method"), "Total Area"
                ),
                "visible_when": lambda v: v.get("method") != "sheet",
            },
        ],
        "compute": _material_weight,
        "result_label": None,  # compute returns its own multi-row result
    },
]
