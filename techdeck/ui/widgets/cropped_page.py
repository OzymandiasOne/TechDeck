"""
CroppedPage — a viewport for scene pages with a fixed design width.

Scene-like pages (Woogy's Emporium) are pixel-art dioramas whose chrome has a
genuine minimum footprint. Rather than letting that minimum force the whole
window to grow when the page is shown (or squashing the scene), the page is
never laid out narrower than its design width and this viewport crops it:
shrink the window and the scene runs off the sides, centered; drag the window
bigger and more of it comes back into view until the full scene fits.

The design width is an explicit constant, NOT queried from the page's live
minimumSizeHint — scene pages recompute internal letterbox margins from their
own width on resize, so their minimum hint moves with the size we give them
(a feedback loop that ratchets the canvas wider and wider).
"""

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QSizePolicy, QWidget


class CroppedPage(QWidget):
    """Hosts `page` at no less than `design_width`, centered and cropped by
    this widget's edges. Contributes nothing to the minimum-size chain, so a
    wide page never forces the window to grow. Height passes through — scene
    pages already scale vertically."""

    def __init__(self, page: QWidget, design_width: int, parent=None):
        super().__init__(parent)
        self._page = page
        self._design_width = design_width
        page.setParent(self)
        # Ignored: the layout hosting this viewport sizes it from available
        # space alone — the page's minimum stops at this boundary.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

    @property
    def page(self) -> QWidget:
        return self._page

    def sizeHint(self) -> QSize:
        return QSize(self._design_width, self._page.sizeHint().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = max(self.width(), self._design_width)
        # Centered: cropping reveals/hides the scene symmetrically. Children
        # paint clipped to the parent rect, so overhang simply isn't drawn.
        self._page.setGeometry((self.width() - w) // 2, 0, w, self.height())
