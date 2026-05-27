"""
TechDeck Dashboard View
=======================
Renders a plain-data dashboard "spec" (KPI cards + QtCharts pie/bar charts) so
plugins can present visual results in the console without touching Qt directly.

A spec is a dict:
    {
      "title": "922 Batch 473 - Readiness",
      "cards": [
          {"label": "Orders", "value": "48/50", "status": "warning"},
          ...
      ],
      "charts": [
          {"type": "pie", "title": "Overall",
           "slices": [("Ready", 40, "ok"), ("Issues", 8, "warning")]},
          {"type": "bar", "title": "Issues by category",
           "categories": ["Orders", "Prints"], "values": [2, 1]},
      ],
    }

status is one of: ok | warning | error | info (mapped to palette colors).
Charts are themed from the active ColorPalette and rebuilt on theme change.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame, QScrollArea,
    QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush, QPainter
from PySide6.QtCharts import (
    QChart, QChartView, QPieSeries, QBarSeries, QBarSet,
    QBarCategoryAxis, QValueAxis,
)

from techdeck.ui.theme_aware import ThemeAware
from techdeck.ui.widgets.pie3d import Pie3DWidget


# status string -> ColorPalette field
_STATUS_FIELD = {"ok": "success", "warning": "warning", "error": "error", "info": "info"}

_CARDS_PER_ROW = 4


def _status_color(palette, status: str) -> str:
    return getattr(palette, _STATUS_FIELD.get(status, "info"))


class DashboardView(QWidget, ThemeAware):
    """Scrollable area that renders a dashboard spec. Theme-aware: re-renders
    with the active palette whenever the theme changes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._spec: dict | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(self._scroll, 1)

        self._content = QWidget()
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._layout.setSpacing(12)
        self._scroll.setWidget(self._content)

        # Series color cycle for slices/bars without an explicit status.
        self._cycle_fields = ["accent", "accent_two", "success", "info", "warning", "error"]

        # Supplies the idle (no-plugin) dashboard data: usage / bankroll / quip.
        self._idle_provider = None

        self.setup_theme_awareness()  # triggers initial apply_theme() -> render

    def set_idle_provider(self, fn):
        """Set a callable returning the idle dashboard data dict
        ({'usage': [(name, count), ...], 'bankroll': int, 'sal_message': str})."""
        self._idle_provider = fn

    def refresh_idle(self):
        """Re-render the idle view (e.g. when the Dashboard tab is opened) so
        usage counts and bankroll are current. No-op while a plugin spec is shown."""
        if not self._spec:
            self._rebuild()

    # ── Public API ──────────────────────────────────────────────────────────
    def render_spec(self, spec: dict | None):
        self._spec = spec
        self._rebuild()

    def clear_dashboard(self):
        self._spec = None
        self._rebuild()

    # ThemeAware hook — rebuild so chart colors follow the new palette.
    def apply_theme(self):
        self._rebuild()

    # ── Rendering ─────────────────────────────────────────────────────────────
    def _clear_layout(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
            else:
                child = item.layout()
                if child is not None:
                    self._purge_layout(child)

    def _purge_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
            elif item.layout() is not None:
                self._purge_layout(item.layout())

    def _rebuild(self):
        palette = self.get_current_palette()
        # Match the console body so switching tabs keeps one background color.
        self._content.setStyleSheet(f"background: {palette.console_bg};")
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background: {palette.console_bg}; border: none; }}"
            f"QScrollArea > QWidget > QWidget {{ background: {palette.console_bg}; }}"
        )
        self._clear_layout()

        if not self._spec:
            self._render_idle(palette)
            return

        title = self._spec.get("title")
        if title:
            lbl = QLabel(str(title))
            lbl.setStyleSheet(
                f"color: {palette.text}; font-size: 16px; font-weight: bold; "
                f"background: transparent;"
            )
            self._layout.addWidget(lbl)

        cards = self._spec.get("cards") or []
        if cards:
            grid = QGridLayout()
            grid.setSpacing(8)
            for i, card in enumerate(cards):
                grid.addWidget(self._make_card(card, palette),
                               i // _CARDS_PER_ROW, i % _CARDS_PER_ROW)
            self._layout.addLayout(grid)

        for chart_spec in (self._spec.get("charts") or []):
            view = self._make_chart(chart_spec, palette)
            if view is not None:
                self._layout.addWidget(view)

        self._layout.addStretch(1)

    # ── Idle (no-plugin) dashboard ───────────────────────────────────────────
    def _mascot_label(self, palette) -> QLabel:
        """The deck-droid ASCII mascot, monospace + accent-tinted."""
        art = (
            "   [^]\n"
            " .-----.\n"
            " | O O |\n"
            " |  _  |\n"
            " '-----'\n"
            "  /|_|\\"
        )
        lbl = QLabel(art)
        lbl.setTextFormat(Qt.TextFormat.PlainText)
        lbl.setStyleSheet(
            f"color: {palette.accent}; font-family: Consolas, monospace; "
            "font-size: 12px; background: transparent;"
        )
        return lbl

    def _vline(self, palette) -> QFrame:
        line = QFrame()
        line.setFixedWidth(1)
        line.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        line.setStyleSheet(f"background-color: {palette.divider};")
        return line

    def _hline(self, palette) -> QFrame:
        line = QFrame()
        line.setFixedHeight(1)
        line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        line.setStyleSheet(f"background-color: {palette.divider};")
        return line

    def _render_idle(self, palette):
        data = self._idle_provider() if self._idle_provider else None

        if not data:
            hint = QLabel("Run a tool and your usage will chart here.")
            hint.setWordWrap(True)
            hint.setStyleSheet(
                f"color: {palette.text_secondary}; font-size: 13px; background: transparent;"
            )
            self._layout.addStretch(1)
            self._layout.addWidget(hint)
            self._layout.addStretch(1)
            return

        usage = data.get("usage") or []
        row = QHBoxLayout()
        row.setSpacing(16)

        # Left section: the usage pie (or a placeholder). Bounded width so it
        # neither collapses to nothing nor sprawls across a maximized window.
        if usage:
            cycle = [getattr(palette, f) for f in self._cycle_fields]
            slices = [(name, cnt, cycle[i % len(cycle)]) for i, (name, cnt) in enumerate(usage)]
            pie = Pie3DWidget(slices, text_color=palette.text,
                              subtext_color=palette.text_secondary)
            pie.setMinimumWidth(380)
            pie.setMaximumWidth(520)
            row.addWidget(pie)
        else:
            none_lbl = QLabel("No tool usage yet.\nRun something to chart it here.")
            none_lbl.setMinimumWidth(380)
            none_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            none_lbl.setStyleSheet(
                f"color: {palette.text_secondary}; font-size: 13px; background: transparent;"
            )
            row.addWidget(none_lbl)

        # Vertical divider between sections
        row.addWidget(self._vline(palette))

        # Right section: droid + greeting, a horizontal divider, then Sal
        right = QVBoxLayout()
        right.setSpacing(10)
        right.setContentsMargins(4, 0, 0, 0)

        drow = QHBoxLayout()
        drow.setSpacing(10)
        drow.addWidget(self._mascot_label(palette), 0, Qt.AlignmentFlag.AlignTop)
        greet = QLabel("Beep boop.\nHello Human.")
        greet.setStyleSheet(
            f"color: {palette.text}; font-size: 13px; background: transparent;"
        )
        drow.addWidget(greet, 0, Qt.AlignmentFlag.AlignVCenter)
        drow.addStretch()
        right.addLayout(drow)

        right.addWidget(self._hline(palette))
        right.addWidget(self._sal_panel(data.get("bankroll", 0),
                                        data.get("sal_message", ""), palette))
        right.addStretch()

        right_w = QWidget()
        right_w.setMinimumWidth(280)
        right_w.setMaximumWidth(380)
        right_w.setLayout(right)
        row.addWidget(right_w)

        row.addStretch(1)  # absorb extra width on wide screens — keeps content left-grouped

        # Center the block vertically.
        self._layout.addStretch(1)
        self._layout.addLayout(row)
        self._layout.addStretch(1)

    def _sal_panel(self, bankroll: int, message: str, palette) -> QWidget:
        """Compact, text-only Sal: 'Blackjack Bankroll' header, then the amount
        inline with a Sal one-liner."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        header = QLabel("Blackjack Bankroll")
        header.setStyleSheet(
            f"color: {palette.text}; font-size: 12px; font-weight: bold; background: transparent;"
        )
        lay.addWidget(header)

        try:
            bank_txt = f"${int(bankroll):,}"
        except (TypeError, ValueError):
            bank_txt = f"${bankroll}"
        line = QLabel(
            f'<span style="color:{palette.accent}; font-weight:bold;">{bank_txt}</span>'
            f'<span style="color:{palette.text_secondary};">'
            f'&nbsp;&nbsp;&mdash; Sal: "{message}"</span>'
        )
        line.setTextFormat(Qt.TextFormat.RichText)
        line.setWordWrap(True)
        line.setStyleSheet("background: transparent; font-size: 12px;")
        lay.addWidget(line)
        return w

    def _make_card(self, card: dict, palette) -> QFrame:
        status = card.get("status", "info")
        color = _status_color(palette, status)
        frame = QFrame()
        frame.setObjectName("kpiCard")
        frame.setStyleSheet(
            f"QFrame#kpiCard {{ background: {palette.surface}; "
            f"border: 1px solid {palette.border}; border-left: 4px solid {color}; "
            f"border-radius: 6px; }}"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(2)
        value = QLabel(str(card.get("value", "")))
        value.setStyleSheet(
            f"color: {color}; font-size: 20px; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        label = QLabel(str(card.get("label", "")))
        label.setStyleSheet(
            f"color: {palette.text_secondary}; font-size: 11px; "
            f"background: transparent; border: none;"
        )
        lay.addWidget(value)
        lay.addWidget(label)
        return frame

    def _make_chart(self, chart_spec: dict, palette):
        kind = (chart_spec.get("type") or "").lower()
        if kind == "pie":
            return self._make_pie(chart_spec, palette)
        if kind == "bar":
            return self._make_bar(chart_spec, palette)
        return None

    def _cycle_color(self, palette, index: int) -> QColor:
        field = self._cycle_fields[index % len(self._cycle_fields)]
        return QColor(getattr(palette, field))

    def _make_pie(self, chart_spec: dict, palette):
        series = QPieSeries()
        for i, entry in enumerate(chart_spec.get("slices", [])):
            label, value = entry[0], entry[1]
            status = entry[2] if len(entry) > 2 else None
            sl = series.append(f"{label} ({value})", float(value))
            sl.setColor(QColor(_status_color(palette, status)) if status
                        else self._cycle_color(palette, i))
            sl.setLabelColor(QColor(palette.text))
        series.setLabelsVisible(True)

        chart = QChart()
        chart.addSeries(series)
        self._style_chart(chart, chart_spec.get("title", ""), palette)
        return self._chart_view(chart)

    def _make_bar(self, chart_spec: dict, palette):
        categories = [str(c) for c in chart_spec.get("categories", [])]
        values = [float(v) for v in chart_spec.get("values", [])]

        bar_set = QBarSet(chart_spec.get("title", ""))
        for v in values:
            bar_set.append(v)
        bar_set.setColor(QColor(palette.accent))

        series = QBarSeries()
        series.append(bar_set)

        chart = QChart()
        chart.addSeries(series)
        self._style_chart(chart, chart_spec.get("title", ""), palette)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setRange(0, max(values, default=0) or 1)
        axis_y.setLabelFormat("%d")
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)

        for axis in (axis_x, axis_y):
            axis.setLabelsColor(QColor(palette.text_secondary))
            axis.setGridLineColor(QColor(palette.divider))
            axis.setLinePenColor(QColor(palette.divider))

        chart.legend().setVisible(False)  # single series; title carries meaning
        return self._chart_view(chart)

    def _style_chart(self, chart: QChart, title: str, palette):
        chart.setBackgroundBrush(QBrush(QColor(palette.surface)))
        chart.setPlotAreaBackgroundVisible(False)
        chart.setMargins(chart.margins())
        if title:
            chart.setTitle(title)
            chart.setTitleBrush(QBrush(QColor(palette.text)))
            font = chart.titleFont()
            font.setBold(True)
            chart.setTitleFont(font)
        legend = chart.legend()
        legend.setLabelColor(QColor(palette.text_secondary))
        legend.setAlignment(Qt.AlignmentFlag.AlignBottom)

    def _chart_view(self, chart: QChart) -> QChartView:
        view = QChartView(chart)
        view.setRenderHint(QPainter.RenderHint.Antialiasing)
        view.setMinimumHeight(260)
        view.setStyleSheet("background: transparent; border: none;")
        return view
