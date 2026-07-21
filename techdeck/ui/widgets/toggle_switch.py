"""
ToggleSwitch — a small animated on/off pill switch.

A checkable control that reads like an iOS/Material toggle: rounded track,
sliding knob, accent fill when on. Theme-aware (pulls the accent from the
active palette at paint time). Emits ``toggled(bool)`` like any checkable
button, so it drops into existing wiring.
"""

from PySide6.QtWidgets import QAbstractButton
from PySide6.QtCore import Qt, QSize, QPropertyAnimation, Property, QRectF
from PySide6.QtGui import QPainter, QColor


class ToggleSwitch(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._track_w = 42
        self._track_h = 22
        self._margin = 3
        self._knob = self._track_h - 2 * self._margin
        self._offset = float(self._off_x())

        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(130)
        self.toggled.connect(self._animate)

    # ---- geometry ------------------------------------------------------------
    def _off_x(self) -> int:
        return self._margin

    def _on_x(self) -> int:
        return self._track_w - self._margin - self._knob

    def sizeHint(self) -> QSize:
        return QSize(self._track_w, self._track_h)

    minimumSizeHint = sizeHint

    # ---- animated knob position (Qt property) --------------------------------
    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, value: float):
        self._offset = value
        self.update()

    offset = Property(float, _get_offset, _set_offset)

    def _animate(self, checked: bool):
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(self._on_x() if checked else self._off_x())
        self._anim.start()

    # ---- paint ---------------------------------------------------------------
    def _accent(self) -> QColor:
        try:
            from techdeck.ui.theme_manager import get_theme_manager
            return QColor(get_theme_manager().get_current_palette().accent)
        except Exception:
            return QColor("#4a9eff")

    def paintEvent(self, _evt):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        radius = self._track_h / 2
        track = QRectF(0, 0, self._track_w, self._track_h)
        if self.isChecked():
            track_color = self._accent()
        else:
            track_color = QColor(127, 127, 127, 90)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track_color)
        p.drawRoundedRect(track, radius, radius)

        knob = QRectF(self._offset, self._margin, self._knob, self._knob)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(knob)
        p.end()
