"""
Pseudo-3D pie chart (custom QPainter).

QtCharts has no true 3D pie, so this draws a tilted, extruded pie by hand:
an elliptical (foreshortened) top face, front-facing side walls in a darker
shade, and a side legend with each slice's label + percentage. Colors are
passed in by the caller (so the dashboard can theme it from the palette).
"""
from __future__ import annotations

import math

from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPolygonF, QPen, QFont, QFontMetrics


class Pie3DWidget(QWidget):
    def __init__(self, slices, text_color="#ECECEC", subtext_color="#B4B4B4", parent=None):
        """slices: list of (label: str, value: float, color: QColor|str)."""
        super().__init__(parent)
        self._slices = [
            (str(lbl), float(val), QColor(col))
            for (lbl, val, col) in slices if float(val) > 0
        ]
        self._text = QColor(text_color)
        self._subtext = QColor(subtext_color)
        self.setMinimumHeight(150)
        # Preferred width (caller sets min/max) so it never collapses to zero in
        # a non-stretched container; expanding height fills the panel.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def paintEvent(self, event):
        if not self._slices:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        total = sum(v for _, v, _ in self._slices) or 1.0
        w = self.width()
        h = self.height()

        # Pie occupies the left half, legend the right. The radius is clamped by
        # BOTH width and height so a wide-but-short panel never clips the tilt +
        # extrusion (total vertical extent ~= 2*ry + depth ~= 1.3*rx).
        pie_w = w * 0.5
        rx = max(24.0, min(pie_w * 0.36, h * 0.60))
        ry = rx * 0.52          # foreshortened (tilt)
        depth = ry * 0.5        # extrusion thickness
        cx = pie_w * 0.5 + 4
        cy = h * 0.5 - depth * 0.5

        def pt(deg: float, dy: float = 0.0) -> QPointF:
            r = math.radians(deg)
            return QPointF(cx + rx * math.cos(r), cy - ry * math.sin(r) + dy)

        # Slice angle ranges (degrees, 0=east, CCW), starting at the top.
        ranges = []
        a = 90.0
        for label, val, color in self._slices:
            span = 360.0 * (val / total)
            ranges.append((a, a + span, color, label, val))
            a += span

        # --- Side walls: only the front-facing arc (lower half, sin<0) ---
        step = 2.0
        for a0, a1, color, _lbl, _v in ranges:
            wall = color.darker(150)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(wall)
            d = a0
            while d < a1:
                d2 = min(d + step, a1)
                mid = math.radians((d + d2) / 2.0)
                if math.sin(mid) < 0:  # front of the ellipse
                    poly = QPolygonF([pt(d), pt(d2), pt(d2, depth), pt(d, depth)])
                    p.drawPolygon(poly)
                d = d2

        # --- Top faces ---
        top_rect = QRectF(cx - rx, cy - ry, 2 * rx, 2 * ry)
        for a0, a1, color, _lbl, _v in ranges:
            p.setPen(QPen(color.darker(115), 1))
            p.setBrush(color)
            p.drawPie(top_rect, int(round(a0 * 16)), int(round((a1 - a0) * 16)))

        # --- Legend (right side): swatch, label, and % right next to the label ---
        lx = pie_w + 8
        sw = 11  # swatch size
        line_h = 20
        legend_h = len(ranges) * line_h
        ly = (h - legend_h) / 2.0
        font = QFont(self.font())
        font.setPointSize(9)
        p.setFont(font)
        fm = QFontMetrics(font)
        for a0, a1, color, label, val in ranges:
            pct = 100.0 * (val / total)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(lx, ly + (line_h - sw) / 2, sw, sw), 2, 2)
            tx = lx + sw + 8
            name = label if len(label) <= 16 else label[:15] + "…"
            p.setPen(self._text)
            p.drawText(QRectF(tx, ly, w - tx, line_h),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name)
            name_w = fm.horizontalAdvance(name)
            p.setPen(self._subtext)
            p.drawText(QRectF(tx + name_w + 10, ly, w - (tx + name_w + 10), line_h),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       f"{pct:.0f}%")
            ly += line_h
        p.end()
