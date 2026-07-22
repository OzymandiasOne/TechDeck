"""FlowLayout — a left-packed wrapping layout (standard Qt flow layout).

Used by the Library tile grid; reusable anywhere tiles should keep CONSTANT
spacing and fill each row before wrapping, instead of being stretched apart
when the window is wide or wrapping too early when it's narrow.
"""

from PySide6.QtWidgets import QLayout
from PySide6.QtCore import Qt, QPoint, QRect, QSize


class FlowLayout(QLayout):
    """Left-packed wrapping layout for the tile grid (standard Qt flow layout).

    Replaces QGridLayout's fixed 5-column wrap: tiles keep CONSTANT spacing and
    fill each row before wrapping, instead of being stretched apart when the
    window is wide (maximized) or wrapping too early when it's narrow.
    """

    def __init__(self, parent=None, margin=24, hspacing=20, vspacing=20):
        super().__init__(parent)
        self._items = []
        self._h = hspacing
        self._v = vspacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        self._items.append(item)
        # Mark the layout dirty so the next show/activate lays the new item
        # out. Without this, items added while the page is hidden (startup
        # warmup rebuild) can keep their default geometry — every card stacks
        # at the same spot and only the last-added one is visible.
        self.invalidate()

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            item = self._items.pop(index)
            self.invalidate()
            return item
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect, test_only):
        m = self.contentsMargins()
        x = rect.x() + m.left()
        y = rect.y() + m.top()
        right = rect.right() - m.right()
        line_height = 0
        for item in self._items:
            hint = item.sizeHint()
            if line_height > 0 and x + hint.width() > right + 1:
                x = rect.x() + m.left()
                y += line_height + self._v
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._h
            line_height = max(line_height, hint.height())
        return y + line_height + m.bottom() - rect.y()
