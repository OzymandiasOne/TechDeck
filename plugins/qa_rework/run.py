"""
QA Rework Tracker
=================
A GUI plugin for the QA team. Two jobs:

  1. Log Entry  - a quick form that appends one rework event as a row to a single
                  shared workbook (one flat sheet, no formulas/charts in the file).
  2. Charts     - reads that workbook back and renders pie / column / stacked-column
                  views with toggles (time window, group-by dimension, %-threshold,
                  best-fit line), plus a one-click "Gemba Pack" PDF of the four
                  standard meeting charts.

Design notes:
  - Charts use the bundled PySide6.QtCharts (NOT matplotlib) so nothing new has to be
    installed on locked-down laptops and the build stays small.
  - PDF export uses Qt's native QPdfWriter/QPainter - also zero new dependencies.
  - The FAILURE MODE cell keeps the team's existing "Category - Subcategory" string
    (e.g. "Laser - Angle"); we split it on the first " - " for category vs. detailed
    grouping, so the file stays compatible with their Master Rework Log.
"""

import datetime
import random
import re
import time
from collections import Counter, OrderedDict
from pathlib import Path

# --- SDK bootstrap (works under the app and for headless CLI testing) -------------
try:
    from techdeck.core import plugin_sdk as sdk
except ModuleNotFoundError:
    import sys
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from techdeck.core import plugin_sdk as sdk

from techdeck.core.plugin_window import PluginWindow

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout, QTabWidget,
    QComboBox, QLineEdit, QPushButton, QLabel, QDateEdit, QDoubleSpinBox,
    QCheckBox, QFileDialog, QMessageBox, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import (
    QColor, QBrush, QPainter, QPdfWriter, QPageSize, QPageLayout, QFont,
)
from PySide6.QtCharts import (
    QChart, QChartView, QPieSeries, QBarSeries, QStackedBarSeries, QBarSet,
    QBarCategoryAxis, QValueAxis, QLineSeries,
)

# Module-level reference so Qt does not garbage-collect the window (Hard Rule).
_window = None

# ---------------------------------------------------------------------------------
# Controlled vocabulary (mirrors the team's "Tables & Formulae" dropdowns)
# ---------------------------------------------------------------------------------
DATA_FILENAME = "QA Rework Log.xlsx"
SHEET_NAME = "Master Rework Log"
HEADERS = [
    "BATCH (PO)", "DATE", "ITEM NUMBER (DYPN)", "SOURCE MATERIAL",
    "RECUT? (Y/N)", "FAILURE MODE", "COMMENTS",
]

# Category -> subcategories. "" = the bare "Other" with no subcategory.
FAILURE_CATEGORIES = OrderedDict([
    ("Form",   ["Angle", "Location"]),
    ("Grind",  ["Angle", "Surface Finish"]),
    ("Laser",  ["Angle", "Blowout", "Length"]),
    ("Saw",    ["Angle", "Length"]),
    ("Scribe", ["Illegible", "Incorrect Information"]),
    ("Other",  ["", "Material Not Provided", "Product Damaged",
                "Product Not Inspected", "Product Not Processed / Step(s) Skipped"]),
])
MATERIALS = ["CLEVIS", "LUG", "MISC.", "PLATE", "ROD", "TUBE", "OTHER"]
RECUT_OPTIONS = ["NO", "YES"]

GROUP_BY = ["Failure category", "Failure mode (detailed)", "Material", "Recut"]
WINDOWS = [
    "Year-to-date", "Last 7 days", "Last 10 days",
    "Last business week (Mon-Fri)", "All time",
]
DAY_WINDOWS = {"Last 7 days", "Last 10 days", "Last business week (Mon-Fri)"}

# Print palette for PDFs - white background + dark ink so Gemba printouts read well.
PRINT_BG = "#FFFFFF"
PRINT_TEXT = "#1A1A1A"
PRINT_CYCLE = [
    "#2E5EAA", "#D7791F", "#3E8E41", "#B23A48", "#6A4C93",
    "#1C8C9C", "#C9A227", "#8C5E3C", "#5A5A5A", "#A03E78",
]


# ---------------------------------------------------------------------------------
# Failure-mode parsing
# ---------------------------------------------------------------------------------
def split_mode(mode):
    """'Laser - Angle' -> ('Laser', 'Angle'); 'Other' -> ('Other', '')."""
    mode = (mode or "").strip()
    if " - " in mode:
        cat, sub = mode.split(" - ", 1)
        return cat.strip(), sub.strip()
    return mode, ""


def compose_mode(category, subcategory):
    category = (category or "").strip()
    subcategory = (subcategory or "").strip()
    return f"{category} - {subcategory}" if subcategory else category


# ---------------------------------------------------------------------------------
# Data layer
# ---------------------------------------------------------------------------------
def resolve_data_path(settings, log=print):
    """Return the workbook path, creating its folder. Defaults to a 'QA Rework Log'
    folder under the Pilot Program library so every laptop syncs to one file."""
    configured = ((settings or {}).get("data_dir") or "").strip()
    if configured:
        folder = Path(configured)
    else:
        roots = []
        try:
            roots = sdk.pilot_program_roots()
        except Exception:
            roots = []
        if roots:
            folder = Path(roots[0]) / "QA Rework Log"
        else:
            folder = Path.home() / "TechDeck QA Rework"
            log(f"Pilot Program library not found; using local folder {folder}")
    folder.mkdir(parents=True, exist_ok=True)
    return folder / DATA_FILENAME


def _norm(s):
    return re.sub(r"\s+", " ", str(s if s is not None else "").strip()).upper()


def load_records(path, log=print):
    """Read the log into a list of dicts. Empty list if the file does not exist yet."""
    path = Path(path)
    if not path.exists():
        return []
    wb = sdk.load_workbook_resilient(path, log=log, data_only=True, read_only=True)
    try:
        ws = wb[SHEET_NAME] if SHEET_NAME in wb.sheetnames else wb.active
        rows = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()
    if not rows:
        return []

    # Locate the header row + map our known columns by normalized name.
    wanted = {_norm(h) for h in HEADERS}
    header_idx, col = 0, {}
    for i, row in enumerate(rows[:10]):
        hits = {_norm(v): j for j, v in enumerate(row) if v is not None}
        if len(wanted & set(hits)) >= 4:
            header_idx, col = i, hits
            break
    else:
        col = {_norm(v): j for j, v in enumerate(rows[0]) if v is not None}

    def cell(row, header):
        j = col.get(_norm(header))
        return row[j] if j is not None and j < len(row) else None

    records = []
    for row in rows[header_idx + 1:]:
        if row is None or all(v is None for v in row):
            continue
        mode = str(cell(row, "FAILURE MODE") or "").strip()
        cat, sub = split_mode(mode)
        if not mode and not cell(row, "ITEM NUMBER (DYPN)"):
            continue
        records.append({
            "batch": _as_str(cell(row, "BATCH (PO)")),
            "date": _as_date(cell(row, "DATE")),
            "item": _as_str(cell(row, "ITEM NUMBER (DYPN)")),
            "material": _as_str(cell(row, "SOURCE MATERIAL")).upper(),
            "recut": _as_str(cell(row, "RECUT? (Y/N)")).upper(),
            "mode": mode,
            "category": cat,
            "subcategory": sub,
            "comments": _as_str(cell(row, "COMMENTS")),
        })
    return records


def _as_str(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _as_date(v):
    if isinstance(v, datetime.datetime):
        return v
    if isinstance(v, datetime.date):
        return datetime.datetime(v.year, v.month, v.day)
    if isinstance(v, str):
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y"):
            try:
                return datetime.datetime.strptime(v.strip(), fmt)
            except ValueError:
                continue
    return None


def append_record(path, record, log=print, attempts=12):
    """Append one row. Open->append->save->close fast; retry if the file is briefly
    locked (someone has it open in Excel, OneDrive mid-sync, or a concurrent write)."""
    import openpyxl
    path = Path(path)
    ordered = [
        record["batch"], record["date"], record["item"], record["material"],
        record["recut"], record["mode"], record["comments"],
    ]
    last_err = None
    for attempt in range(attempts):
        try:
            if path.exists():
                wb = sdk.load_workbook_resilient(path, log=log)
                ws = wb[SHEET_NAME] if SHEET_NAME in wb.sheetnames else wb.active
            else:
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = SHEET_NAME
                ws.append(HEADERS)
            ws.append(ordered)
            wb.save(path)
            try:
                wb.close()
            except Exception:
                pass
            return
        except (PermissionError, OSError) as e:
            last_err = e
            time.sleep(0.35 + random.random() * 0.5)
    raise last_err if last_err else RuntimeError("append failed")


# ---------------------------------------------------------------------------------
# Time windows + aggregation
# ---------------------------------------------------------------------------------
def filter_window(records, window, today=None):
    today = today or datetime.date.today()
    def d(r):
        return r["date"].date() if r["date"] else None

    if window == "All time":
        return [r for r in records if d(r)]
    if window == "Year-to-date":
        start = datetime.date(today.year, 1, 1)
        return [r for r in records if d(r) and d(r) >= start]
    if window == "Last 7 days":
        start = today - datetime.timedelta(days=6)
        return [r for r in records if d(r) and start <= d(r) <= today]
    if window == "Last 10 days":
        start = today - datetime.timedelta(days=9)
        return [r for r in records if d(r) and start <= d(r) <= today]
    if window == "Last business week (Mon-Fri)":
        this_monday = today - datetime.timedelta(days=today.weekday())
        last_monday = this_monday - datetime.timedelta(days=7)
        last_friday = last_monday + datetime.timedelta(days=4)
        return [r for r in records if d(r) and last_monday <= d(r) <= last_friday]
    return [r for r in records if d(r)]


def dimension_key(rec, dim):
    if dim == "Failure category":
        return rec["category"] or "(blank)"
    if dim == "Failure mode (detailed)":
        return rec["mode"] or "(blank)"
    if dim == "Material":
        return rec["material"] or "(blank)"
    if dim == "Recut":
        return rec["recut"] or "(blank)"
    return "(blank)"


def counts_by(records, dim):
    c = Counter()
    for r in records:
        c[dimension_key(r, dim)] += 1
    return c


def pie_slices(counts, threshold_pct):
    """Sorted (label, value) list; anything below threshold_pct rolls into 'Other'."""
    total = sum(counts.values()) or 1
    big, other = {}, 0
    for k, v in counts.items():
        if (v / total * 100.0) < threshold_pct:
            other += v
        else:
            big[k] = v
    items = sorted(big.items(), key=lambda kv: -kv[1])
    if other:
        items.append((f"Other (<{threshold_pct:g}%)", other))
    return items, total


def _month_label(key, all_keys):
    multi_year = len({k[0] for k in all_keys}) > 1
    y, m = key
    base = datetime.date(y, m, 1)
    return base.strftime("%b '%y") if multi_year else base.strftime("%b")


def time_buckets(records, window):
    """Return (labels, key_of_record_fn) bucketing by day for short windows else month."""
    if window in DAY_WINDOWS:
        days = sorted({r["date"].date() for r in records if r["date"]})
        labels = [d.strftime("%a %m/%d") for d in days]
        idx = {d: i for i, d in enumerate(days)}
        return labels, (lambda r: idx.get(r["date"].date()) if r["date"] else None)
    months = sorted({(r["date"].year, r["date"].month) for r in records if r["date"]})
    labels = [_month_label(m, months) for m in months]
    idx = {m: i for i, m in enumerate(months)}
    return labels, (lambda r: idx.get((r["date"].year, r["date"].month))
                    if r["date"] else None)


def bucket_totals(records, window):
    labels, key_fn = time_buckets(records, window)
    totals = [0] * len(labels)
    for r in records:
        i = key_fn(r)
        if i is not None:
            totals[i] += 1
    return labels, totals


def bucket_matrix(records, window, dim):
    """Return (labels, OrderedDict[dim_value -> [counts per bucket]]) for stacking."""
    labels, key_fn = time_buckets(records, window)
    dims = sorted({dimension_key(r, dim) for r in records})
    matrix = OrderedDict((d, [0] * len(labels)) for d in dims)
    for r in records:
        i = key_fn(r)
        if i is not None:
            matrix[dimension_key(r, dim)][i] += 1
    return labels, matrix


def linregress(ys):
    """Least-squares slope/intercept over x = 0..n-1. Flat line if <2 points."""
    n = len(ys)
    if n < 2:
        return 0.0, (ys[0] if ys else 0.0)
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs) or 1.0
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
    return slope, my - slope * mx


# ---------------------------------------------------------------------------------
# Chart builders (return a QChart; colors/bg/text are caller-supplied so the same
# code drives both the on-screen themed view and the white-background PDF)
# ---------------------------------------------------------------------------------
def _style_chart(chart, title, bg, text):
    chart.setBackgroundBrush(QBrush(QColor(bg)))
    chart.setPlotAreaBackgroundVisible(False)
    if title:
        chart.setTitle(title)
        chart.setTitleBrush(QBrush(QColor(text)))
        f = chart.titleFont()
        f.setBold(True)
        f.setPointSize(max(f.pointSize() + 1, 11))
        chart.setTitleFont(f)
    lg = chart.legend()
    lg.setLabelColor(QColor(text))
    lg.setAlignment(Qt.AlignmentFlag.AlignBottom)


def _style_axes(axes, text):
    for ax in axes:
        ax.setLabelsColor(QColor(text))
        ax.setTitleBrush(QBrush(QColor(text)))
        ax.setGridLineColor(QColor(text).lighter(180) if QColor(text).lightness() < 128
                            else QColor(text).darker(140))
        ax.setLinePenColor(QColor(text))


def build_pie(items, total, title, cycle, bg, text):
    series = QPieSeries()
    for i, (label, value) in enumerate(items):
        pct = value / (total or 1) * 100.0
        sl = series.append(f"{label}  {pct:.0f}%", float(value))
        sl.setColor(QColor(cycle[i % len(cycle)]))
        sl.setLabelColor(QColor(text))
    series.setLabelsVisible(True)
    chart = QChart()
    chart.addSeries(series)
    _style_chart(chart, title, bg, text)
    chart.legend().setVisible(True)
    return chart


def build_column(labels, totals, title, cycle, bg, text, bestfit=False):
    bar_set = QBarSet("Reworks")
    for v in totals:
        bar_set.append(float(v))
    bar_set.setColor(QColor(cycle[0]))
    series = QBarSeries()
    series.append(bar_set)

    chart = QChart()
    chart.addSeries(series)
    _style_chart(chart, title, bg, text)

    cat_axis = QBarCategoryAxis()
    cat_axis.append(labels or [""])
    chart.addAxis(cat_axis, Qt.AlignmentFlag.AlignBottom)
    series.attachAxis(cat_axis)

    ymax = max(totals, default=0) or 1
    val_axis = QValueAxis()
    val_axis.setRange(0, ymax * 1.15)
    val_axis.setLabelFormat("%d")
    chart.addAxis(val_axis, Qt.AlignmentFlag.AlignLeft)
    series.attachAxis(val_axis)

    chart.legend().setVisible(False)

    if bestfit and len(totals) >= 2:
        slope, intercept = linregress([float(t) for t in totals])
        line = QLineSeries()
        line.setName("Best fit")
        for i in range(len(totals)):
            line.append(i + 0.5, slope * i + intercept)
        pen = line.pen()
        pen.setWidth(3)
        pen.setColor(QColor("#B23A48"))
        line.setPen(pen)
        chart.addSeries(line)
        hidden_x = QValueAxis()
        hidden_x.setRange(0, len(totals))
        hidden_x.setVisible(False)
        chart.addAxis(hidden_x, Qt.AlignmentFlag.AlignBottom)
        line.attachAxis(hidden_x)
        line.attachAxis(val_axis)
        chart.legend().setVisible(True)

    _style_axes([cat_axis, val_axis], text)
    return chart


def build_stacked(labels, matrix, title, cycle, bg, text):
    series = QStackedBarSeries()
    for i, (name, values) in enumerate(matrix.items()):
        bs = QBarSet(str(name))
        for v in values:
            bs.append(float(v))
        bs.setColor(QColor(cycle[i % len(cycle)]))
        series.append(bs)

    chart = QChart()
    chart.addSeries(series)
    _style_chart(chart, title, bg, text)

    cat_axis = QBarCategoryAxis()
    cat_axis.append(labels or [""])
    chart.addAxis(cat_axis, Qt.AlignmentFlag.AlignBottom)
    series.attachAxis(cat_axis)

    stacked_max = max((sum(col) for col in zip(*matrix.values())), default=0) \
        if matrix else 0
    val_axis = QValueAxis()
    val_axis.setRange(0, (stacked_max or 1) * 1.15)
    val_axis.setLabelFormat("%d")
    chart.addAxis(val_axis, Qt.AlignmentFlag.AlignLeft)
    series.attachAxis(val_axis)

    chart.legend().setVisible(True)
    _style_axes([cat_axis, val_axis], text)
    return chart


def empty_chart(message, bg, text):
    chart = QChart()
    _style_chart(chart, message, bg, text)
    chart.legend().setVisible(False)
    return chart


# ---------------------------------------------------------------------------------
# The window content (two tabs)
# ---------------------------------------------------------------------------------
class QAReworkContent(QWidget):
    def __init__(self, data_path, log=print, parent=None):
        super().__init__(parent)
        self.data_path = Path(data_path)
        self.log = log
        self.records = []
        self._palette = self._theme_palette()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        tabs = QTabWidget()
        tabs.addTab(self._build_entry_tab(), "Log Entry")
        tabs.addTab(self._build_charts_tab(), "Charts")
        layout.addWidget(tabs)
        self._tabs = tabs
        tabs.currentChanged.connect(self._on_tab_changed)

        self.reload_records()

    # ---- theme -----------------------------------------------------------------
    def _theme_palette(self):
        try:
            from techdeck.ui.theme_manager import get_theme_manager
            return get_theme_manager().get_current_palette()
        except Exception:
            return None

    def _screen_colors(self):
        p = self._palette
        if p is None:
            return (PRINT_CYCLE, "#202020", "#EAEAEA")
        cycle = [getattr(p, f) for f in
                 ("accent", "accent_two", "success", "info", "warning", "error")
                 if hasattr(p, f)] or PRINT_CYCLE
        return (cycle, getattr(p, "surface", "#202020"),
                getattr(p, "text", "#EAEAEA"))

    # ---- entry tab -------------------------------------------------------------
    def _build_entry_tab(self):
        tab = QWidget()
        outer = QVBoxLayout(tab)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.in_batch = QLineEdit()
        self.in_batch.setPlaceholderText("e.g. 100")
        self.in_date = QDateEdit()
        self.in_date.setCalendarPopup(True)
        self.in_date.setDisplayFormat("MM/dd/yyyy")
        self.in_date.setDate(QDate.currentDate())
        self.in_item = QLineEdit()
        self.in_item.setPlaceholderText("e.g. DYPN404")
        self.in_material = QComboBox()
        self.in_material.addItems(MATERIALS)
        self.in_recut = QComboBox()
        self.in_recut.addItems(RECUT_OPTIONS)
        self.in_category = QComboBox()
        self.in_category.addItems(list(FAILURE_CATEGORIES.keys()))
        self.in_subcategory = QComboBox()
        self.in_category.currentTextChanged.connect(self._refresh_subcategories)
        self._refresh_subcategories(self.in_category.currentText())
        self.in_comments = QLineEdit()
        self.in_comments.setPlaceholderText("Optional")

        form.addRow("Batch (PO):", self.in_batch)
        form.addRow("Date:", self.in_date)
        form.addRow("Item Number (DYPN):", self.in_item)
        form.addRow("Source Material:", self.in_material)
        form.addRow("Recut?:", self.in_recut)
        form.addRow("Failure Category:", self.in_category)
        form.addRow("Failure Subcategory:", self.in_subcategory)
        form.addRow("Comments:", self.in_comments)
        outer.addLayout(form)

        btn_row = QHBoxLayout()
        submit = QPushButton("Log Rework  ➜")
        submit.clicked.connect(self._submit)
        btn_row.addWidget(submit)
        btn_row.addStretch(1)
        outer.addLayout(btn_row)

        self.entry_status = QLabel("")
        self.entry_status.setWordWrap(True)
        outer.addWidget(self.entry_status)

        self.file_label = QLabel(f"Logging to: {self.data_path}")
        self.file_label.setWordWrap(True)
        self.file_label.setStyleSheet("color: gray; font-size: 11px;")
        outer.addStretch(1)
        outer.addWidget(self.file_label)
        return tab

    def _refresh_subcategories(self, category):
        self.in_subcategory.clear()
        for sub in FAILURE_CATEGORIES.get(category, []):
            self.in_subcategory.addItem(sub if sub else "(none)", sub)

    def _submit(self):
        batch = self.in_batch.text().strip()
        item = self.in_item.text().strip()
        if not batch or not item:
            self._set_status("Batch (PO) and Item Number are required.", ok=False)
            return
        category = self.in_category.currentText()
        sub = self.in_subcategory.currentData()
        mode = compose_mode(category, sub if sub is not None else "")
        qd = self.in_date.date()
        record = {
            "batch": batch,
            "date": datetime.datetime(qd.year(), qd.month(), qd.day()),
            "item": item,
            "material": self.in_material.currentText(),
            "recut": self.in_recut.currentText(),
            "mode": mode,
            "comments": self.in_comments.text().strip(),
        }
        try:
            append_record(self.data_path, record, log=self.log)
        except Exception as e:
            self._set_status(
                f"Could not write to the log (it may be open in Excel). {e}", ok=False)
            return
        self.log(f"Logged {item}: {mode} (batch {batch})")
        self._set_status(f"✓ Logged {item} — {mode}", ok=True)
        # Keep batch + date for fast repeat entry; clear the rest.
        self.in_item.clear()
        self.in_comments.clear()
        self.in_item.setFocus()
        self.reload_records()

    def _set_status(self, msg, ok=True):
        color = "#3E8E41" if ok else "#B23A48"
        self.entry_status.setStyleSheet(f"color: {color}; font-weight: bold;")
        self.entry_status.setText(msg)

    # ---- charts tab ------------------------------------------------------------
    def _build_charts_tab(self):
        tab = QWidget()
        outer = QVBoxLayout(tab)

        controls = QGridLayout()
        self.c_type = QComboBox()
        self.c_type.addItems(["Pie", "Column", "Stacked column"])
        self.c_window = QComboBox()
        self.c_window.addItems(WINDOWS)
        self.c_group = QComboBox()
        self.c_group.addItems(GROUP_BY)
        self.c_xaxis = QComboBox()
        self.c_xaxis.addItems(["By time (month/day)", "By group"])
        self.c_threshold = QDoubleSpinBox()
        self.c_threshold.setRange(0.0, 50.0)
        self.c_threshold.setValue(5.0)
        self.c_threshold.setSuffix(" %")
        self.c_bestfit = QCheckBox("Best-fit line")
        self.c_bestfit.setChecked(True)

        for w in (self.c_type, self.c_window, self.c_group, self.c_xaxis):
            w.currentIndexChanged.connect(self.render_chart)
        self.c_threshold.valueChanged.connect(self.render_chart)
        self.c_bestfit.stateChanged.connect(self.render_chart)

        controls.addWidget(QLabel("Chart:"), 0, 0)
        controls.addWidget(self.c_type, 0, 1)
        controls.addWidget(QLabel("Time:"), 0, 2)
        controls.addWidget(self.c_window, 0, 3)
        controls.addWidget(QLabel("Group by:"), 0, 4)
        controls.addWidget(self.c_group, 0, 5)
        controls.addWidget(QLabel("Column X:"), 1, 0)
        controls.addWidget(self.c_xaxis, 1, 1)
        controls.addWidget(QLabel("Pie hide <"), 1, 2)
        controls.addWidget(self.c_threshold, 1, 3)
        controls.addWidget(self.c_bestfit, 1, 4, 1, 2)
        outer.addLayout(controls)

        self.chart_view = QChartView()
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.chart_view.setMinimumHeight(420)
        self.chart_view.setSizePolicy(QSizePolicy.Policy.Expanding,
                                      QSizePolicy.Policy.Expanding)
        outer.addWidget(self.chart_view, 1)

        btn_row = QHBoxLayout()
        refresh = QPushButton("↻ Reload data")
        refresh.clicked.connect(self.reload_records)
        export_one = QPushButton("Export this chart (PDF)")
        export_one.clicked.connect(self._export_current)
        export_pack = QPushButton("Export Gemba Pack (PDF)")
        export_pack.clicked.connect(self._export_gemba_pack)
        btn_row.addWidget(refresh)
        btn_row.addStretch(1)
        btn_row.addWidget(export_one)
        btn_row.addWidget(export_pack)
        outer.addLayout(btn_row)

        self.chart_status = QLabel("")
        outer.addWidget(self.chart_status)
        return tab

    def _on_tab_changed(self, idx):
        if self._tabs.tabText(idx) == "Charts":
            self.render_chart()

    def reload_records(self):
        try:
            self.records = load_records(self.data_path, log=self.log)
        except Exception as e:
            self.records = []
            self.log(f"Could not read the log: {e}")
            if hasattr(self, "chart_status"):
                self.chart_status.setText(f"Could not read the log: {e}")
        if hasattr(self, "chart_view"):
            self.render_chart()

    # ---- rendering -------------------------------------------------------------
    def render_chart(self):
        if not hasattr(self, "chart_view"):
            return
        cycle, bg, text = self._screen_colors()
        chart = self._build_selected_chart(cycle, bg, text)
        old = self.chart_view.chart()
        self.chart_view.setChart(chart)
        if old is not None:
            old.deleteLater()
        n = len(filter_window(self.records, self.c_window.currentText()))
        self.chart_status.setText(
            f"{n} rework events in '{self.c_window.currentText()}' "
            f"({len(self.records)} total logged).")

    def _build_selected_chart(self, cycle, bg, text):
        window = self.c_window.currentText()
        group = self.c_group.currentText()
        recs = filter_window(self.records, window)
        if not recs:
            return empty_chart("No data in this time window yet.", bg, text)

        ctype = self.c_type.currentText()
        if ctype == "Pie":
            items, total = pie_slices(counts_by(recs, group), self.c_threshold.value())
            return build_pie(items, total, f"{group} — {window}", cycle, bg, text)

        if ctype == "Stacked column":
            labels, matrix = bucket_matrix(recs, window, group)
            return build_stacked(labels, matrix,
                                 f"{group} by {'day' if window in DAY_WINDOWS else 'month'} — {window}",
                                 cycle, bg, text)

        # Column
        if self.c_xaxis.currentText() == "By group":
            counts = counts_by(recs, group)
            ordered = sorted(counts.items(), key=lambda kv: -kv[1])
            labels = [k for k, _ in ordered]
            totals = [v for _, v in ordered]
            return build_column(labels, totals, f"{group} — {window}", cycle, bg, text,
                                bestfit=False)
        labels, totals = bucket_totals(recs, window)
        return build_column(labels, totals, f"Reworks by "
                            f"{'day' if window in DAY_WINDOWS else 'month'} — {window}",
                            cycle, bg, text, bestfit=self.c_bestfit.isChecked())

    # ---- PDF export ------------------------------------------------------------
    def _export_current(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save chart as PDF",
            str(Path.home() / "QA Rework Chart.pdf"), "PDF files (*.pdf)")
        if not path:
            return
        chart = self._build_selected_chart(PRINT_CYCLE, PRINT_BG, PRINT_TEXT)
        try:
            self._write_pdf(path, [("", [chart])])
            self.chart_status.setText(f"Saved {path}")
        except Exception as e:
            self.chart_status.setText(f"Export failed: {e}")

    def _export_gemba_pack(self):
        if not self.records:
            self.chart_status.setText("Nothing to export yet — log some data first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Gemba Pack PDF",
            str(Path.home() / "QA Gemba Pack.pdf"), "PDF files (*.pdf)")
        if not path:
            return
        try:
            self._write_pdf(path, self._gemba_pages())
            self.chart_status.setText(f"Saved Gemba Pack: {path}")
            self.log(f"Exported Gemba Pack to {path}")
        except Exception as e:
            self.chart_status.setText(f"Export failed: {e}")

    def _gemba_pages(self):
        """The four standard meeting charts, two per page."""
        cy, bg, tx = PRINT_CYCLE, PRINT_BG, PRINT_TEXT
        ytd = filter_window(self.records, "Year-to-date")
        lastwk = filter_window(self.records, "Last business week (Mon-Fri)")

        # Page 1 - Year to date
        ytd_labels, ytd_totals = bucket_totals(ytd, "Year-to-date")
        col = build_column(ytd_labels, ytd_totals, "YTD Reworks by Month",
                           cy, bg, tx, bestfit=True) if ytd \
            else empty_chart("No YTD data", bg, tx)
        items, total = pie_slices(counts_by(ytd, "Failure category"), 5.0)
        ytd_pie = build_pie(items, total, "YTD Failure Category %", cy, bg, tx) if ytd \
            else empty_chart("No YTD data", bg, tx)

        # Page 2 - Last business week
        if lastwk:
            labels, matrix = bucket_matrix(lastwk, "Last business week (Mon-Fri)",
                                           "Failure mode (detailed)")
            wk_col = build_stacked(labels, matrix, "Last Week Reworks by Failure Mode",
                                   cy, bg, tx)
            it2, tot2 = pie_slices(counts_by(lastwk, "Failure mode (detailed)"), 5.0)
            wk_pie = build_pie(it2, tot2, "Last Week Failure Mode %", cy, bg, tx)
        else:
            wk_col = empty_chart("No data for last business week", bg, tx)
            wk_pie = empty_chart("No data for last business week", bg, tx)

        return [("Year-to-Date", [col, ytd_pie]),
                ("Last Week", [wk_col, wk_pie])]

    def _write_pdf(self, path, pages):
        """pages = list of (page_title, [charts]); charts laid out stacked per page."""
        writer = QPdfWriter(str(path))
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        writer.setPageOrientation(QPageLayout.Orientation.Landscape)
        writer.setResolution(150)
        painter = QPainter(writer)
        try:
            for pi, (title, charts) in enumerate(pages):
                if pi > 0:
                    writer.newPage()
                self._paint_page(painter, writer, title, charts)
        finally:
            painter.end()

    def _paint_page(self, painter, writer, title, charts):
        page = painter.viewport()
        margin = int(min(page.width(), page.height()) * 0.04)
        x = page.left() + margin
        y = page.top() + margin
        w = page.width() - 2 * margin
        h = page.height() - 2 * margin

        title_h = 0
        if title:
            font = QFont()
            font.setBold(True)
            font.setPointSize(16)
            painter.setFont(font)
            painter.setPen(QColor(PRINT_TEXT))
            title_h = int(h * 0.07)
            painter.drawText(x, y, w, title_h,
                             int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                             title)

        charts = [c for c in charts if c is not None]
        if not charts:
            return
        avail_h = h - title_h
        gap = margin // 2
        each_h = (avail_h - gap * (len(charts) - 1)) // len(charts)
        cy = y + title_h
        for chart in charts:
            self._render_chart_into(painter, chart, x, cy, w, each_h)
            cy += each_h + gap

    def _render_chart_into(self, painter, chart, x, y, w, h):
        view = QChartView(chart)
        view.setRenderHint(QPainter.RenderHint.Antialiasing)
        view.setStyleSheet("background: white; border: none;")
        view.resize(w, h)
        view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        view.show()
        painter.save()
        painter.translate(x, y)
        view.render(painter)
        painter.restore()
        view.hide()
        view.setChart(QChart())  # detach so deleteLater doesn't take our chart
        view.deleteLater()


# ---------------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------------
def run(params, progress_callback, cancel_event):
    global _window
    log = params.get("log", print)
    settings = params.get("settings", {})
    try:
        data_path = resolve_data_path(settings, log)
    except Exception as e:
        log(f"Could not resolve the QA rework data folder: {e}")
        return
    log(f"QA Rework log file: {data_path}")

    _window = PluginWindow("qa_rework", "QA Rework Tracker")
    content = QAReworkContent(data_path, log)
    _window.set_content(content)
    _window.resize(1120, 780)
    _window.show()
    progress_callback(100)
