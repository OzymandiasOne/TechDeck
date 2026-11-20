"""The Assistant, popped out: a small panel that floats over whatever page is showing.

Asked for 2026-10-29: *"Is it possible to have Assistant pop out in a different
window? Sometimes I would like to have it visible, while also being able to run
my apps."* The answer built is not a second window. It is a panel INSIDE the
TechDeck window, because the point is to see it beside the app you are running,
and a separate top-level window is one more thing to lose behind Excel.

What it does:

* **Floats above every page.** It is a child of the main window's central
  widget, not of any page, so switching sidebar tabs cannot take it away.
* **Drags by its title bar**, and never leaves the page area (it cannot cover
  the sidebar, or you could not navigate out from under it).
* **Resizes from any edge or corner.**
* **Snaps to any of the four edges.** Drag it against an edge and let go: it
  docks there, fills that edge, and the page beside it makes room rather than
  being covered. Drag it away again and it goes back to floating at the size it
  had before. Docked, only the edge facing the page resizes it.

The panel hosts the Assistant page's own body, re-parented - not a second copy.
One terminal, one store, one brain; what you typed on the page is what is in
the panel.

Geometry is in the coordinates of the HOST (the central widget). The page area
comes from `bounds_fn` - the shell passes "everything right of the sidebar".
It is deliberately NOT read off the layout: `QLayout.geometry()` goes empty the
moment the layout is invalidated, which is exactly when a dock changes the
margins, and a panel that sizes itself against an empty rect collapses to its
minimum mid-drag. `area_layout` is the nested layout wrapping the page stack;
its contents margins are what reserves the strip a docked panel sits in.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from techdeck.ui.theme_aware import ThemeAware
from techdeck.ui.theme_manager import SCOPE_ASSISTANT

EDGE_NONE, EDGE_LEFT, EDGE_RIGHT, EDGE_TOP, EDGE_BOTTOM = (
    "", "left", "right", "top", "bottom")
EDGES = (EDGE_LEFT, EDGE_RIGHT, EDGE_TOP, EDGE_BOTTOM)

MIN_W, MIN_H = 320, 280             # the smallest the panel is still usable at
DEFAULT_W, DEFAULT_H = 400, 440
FLOAT_GAP = 16                      # a first pop-out sits this far off the edge
FLOAT_TOP = 64                      # ...and this far down, clear of a page's header
SNAP_PX = 14                        # how close to an edge counts as "against it"
RESIZE_MARGIN = 6                   # the ring around the panel that resizes it
DRAG_START_PX = 6                   # travel before a press on the bar is a drag
MAX_DOCK_FRACTION = 0.6             # a docked panel never takes more than this
TITLE_H = 30


class _TitleBar(QWidget):
    """The strip you drag the panel by. Reports presses to the panel."""

    def __init__(self, panel: "AssistantPopout"):
        super().__init__(panel)
        self._panel = panel
        self.setFixedHeight(TITLE_H)
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._panel._begin_drag(event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._panel._drag_to(event.globalPosition().toPoint())
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._panel._end_drag()
            event.accept()


class AssistantPopout(QFrame, ThemeAware):
    """The floating / docked panel. See the module docstring."""

    # Wears the Assistant's own theme when one is pinned, like the page does.
    # Once the body is re-parented in here it is no longer under the page, so
    # this panel has to carry the scoped sheet itself.
    THEME_SCOPE = SCOPE_ASSISTANT

    pop_in_requested = Signal()
    geometry_settled = Signal()     # a drag, resize or dock just finished

    def __init__(self, host: QWidget, area_layout, page_stack=None,
                 bounds_fn=None, watch=()):
        super().__init__(host)
        self.setObjectName("assistantPopout")
        self._host = host
        self._area = area_layout
        self._page_stack = page_stack
        self._bounds_fn = bounds_fn
        # Widgets whose resizing moves the page area without the host itself
        # resizing - the sidebar, when it collapses.
        self._watched = [host, *watch]
        self._body: Optional[QWidget] = None

        self._edge = EDGE_NONE
        self._float_rect = QRect()          # relative to the page area
        self._dock_w, self._dock_h = DEFAULT_W, 300
        self._reserving = False             # is the page making room for us?
        self._content_min_w = MIN_W         # what the tab showing needs
        self._anchoring = False             # re-entrancy guard for reanchor()

        self._drag_origin: Optional[QPoint] = None
        self._drag_offset = QPoint()
        self._dragging = False
        self._pending_edge = EDGE_NONE
        self._resize_edges = ""
        self._resize_origin = QPoint()
        self._resize_start = QRect()

        self.setMouseTracking(True)
        self.setMinimumSize(MIN_W, MIN_H)

        box = QVBoxLayout(self)
        box.setContentsMargins(RESIZE_MARGIN, RESIZE_MARGIN,
                               RESIZE_MARGIN, RESIZE_MARGIN)
        box.setSpacing(0)

        self._bar = _TitleBar(self)
        bar_row = QHBoxLayout(self._bar)
        bar_row.setContentsMargins(8, 0, 2, 0)
        bar_row.setSpacing(6)
        self._title = QLabel("Assistant")
        self._title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        bar_row.addWidget(self._title, 1)
        self._pop_in_btn = QPushButton("Pop back in")
        self._pop_in_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pop_in_btn.setToolTip("Put the Assistant back on its own page")
        self._pop_in_btn.clicked.connect(self.pop_in_requested.emit)
        bar_row.addWidget(self._pop_in_btn)
        box.addWidget(self._bar)

        self._slot = QVBoxLayout()
        self._slot.setContentsMargins(0, 0, 0, 0)
        box.addLayout(self._slot, 1)

        # Where the panel WILL dock if you let go now. A sibling, stacked just
        # under the panel, so it never covers what you are dragging.
        self._ghost = QFrame(host)
        self._ghost.setObjectName("assistantPopoutGhost")
        self._ghost.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._ghost.hide()

        for widget in self._watched:
            widget.installEventFilter(self)
        if page_stack is not None:
            page_stack.currentChanged.connect(lambda _i: self.reanchor())

        self.hide()
        self.setup_theme_awareness()

    # ── hosting the Assistant's body ─────────────────────────────────────────

    def is_out(self) -> bool:
        return self._body is not None

    def pop_out(self, body: QWidget) -> None:
        """Take the Assistant's body and show the panel."""
        self._body = body
        self._slot.addWidget(body)
        body.show()
        self.show()
        self.raise_()
        self.reanchor()

    def pop_in(self) -> Optional[QWidget]:
        """Give the body back (un-parented) and hide the panel."""
        body, self._body = self._body, None
        if body is not None:
            self._slot.removeWidget(body)
            body.setParent(None)
        self._ghost.hide()
        self.hide()
        self._set_reserve(EDGE_NONE, 0)
        return body

    # ── state in and out (the shell persists it) ─────────────────────────────

    def state(self) -> dict:
        return {"edge": self._edge,
                "x": self._float_rect.x(), "y": self._float_rect.y(),
                "w": self._float_rect.width(), "h": self._float_rect.height(),
                "dock_w": self._dock_w, "dock_h": self._dock_h}

    def restore_state(self, data: Optional[dict]) -> None:
        """Take a saved state. Anything missing or absurd is ignored; the
        geometry is clamped to the window when the panel is next shown."""
        data = data if isinstance(data, dict) else {}

        def _num(key, default):
            try:
                return int(data.get(key, default))
            except (TypeError, ValueError):
                return default

        edge = data.get("edge", EDGE_NONE)
        self._edge = edge if edge in EDGES else EDGE_NONE
        w, h = _num("w", 0), _num("h", 0)
        if w >= MIN_W and h >= MIN_H:
            self._float_rect = QRect(_num("x", 0), _num("y", 0), w, h)
        self._dock_w = max(MIN_W, _num("dock_w", self._dock_w))
        self._dock_h = max(MIN_H, _num("dock_h", self._dock_h))

    def edge(self) -> str:
        return self._edge

    def is_reserving(self) -> bool:
        """True while the page beside a docked panel is making room for it."""
        return self._reserving

    def set_content_minimum(self, width: int) -> None:
        """How wide the Assistant tab now showing needs to be.

        The Terminal is happy at 320. Schedule, Tasks and Notes carry a row of
        buttons that needs about 600, and squeezed below that Qt clips their
        labels to a letter or two. So the panel is as wide as you made it OR
        as wide as the tab needs, whichever is more - and because the width
        you chose is remembered separately, going back to a narrow tab puts
        the panel back the way you had it.
        """
        wanted = max(MIN_W, int(width) + 2 * RESIZE_MARGIN)
        if wanted != self._content_min_w:
            self._content_min_w = wanted
            self.reanchor()

    def _min_w(self, bounds: QRect) -> int:
        """The narrowest the panel may be right now: what the tab needs, but
        never more than the page area can hold."""
        return max(MIN_W, min(self._content_min_w, bounds.width()))

    # ── geometry ─────────────────────────────────────────────────────────────

    def bounds(self) -> QRect:
        """The page area, in host coordinates: everything right of the sidebar."""
        if self._bounds_fn is not None:
            return QRect(self._bounds_fn())
        return QRect(self._host.rect())

    def _page_minimum(self) -> QSize:
        if self._page_stack is None:
            return QSize(0, 0)
        return self._page_stack.minimumSizeHint()

    def _dock_rect(self, edge: str, bounds: QRect):
        """(rect, reserve) for a panel docked on `edge`. `reserve` says whether
        the page can give up that strip without the WINDOW having to grow -
        if it cannot, the panel still docks but lies over the page instead."""
        page_min = self._page_minimum()
        if edge in (EDGE_LEFT, EDGE_RIGHT):
            extent, wanted, floor = (bounds.width(), self._dock_w,
                                     self._min_w(bounds))
            spare = extent - page_min.width()
        else:
            extent, wanted, floor = bounds.height(), self._dock_h, MIN_H
            spare = extent - page_min.height()
        cap = max(floor, int(extent * MAX_DOCK_FRACTION))
        reserve = spare >= floor
        thick = max(floor, min(wanted, cap, spare if reserve else cap))
        thick = min(thick, extent)
        if edge == EDGE_LEFT:
            rect = QRect(bounds.left(), bounds.top(), thick, bounds.height())
        elif edge == EDGE_RIGHT:
            rect = QRect(bounds.right() - thick + 1, bounds.top(),
                         thick, bounds.height())
        elif edge == EDGE_TOP:
            rect = QRect(bounds.left(), bounds.top(), bounds.width(), thick)
        else:
            rect = QRect(bounds.left(), bounds.bottom() - thick + 1,
                         bounds.width(), thick)
        return rect, reserve

    def _set_reserve(self, edge: str, thick: int) -> None:
        left = thick if edge == EDGE_LEFT else 0
        right = thick if edge == EDGE_RIGHT else 0
        top = thick if edge == EDGE_TOP else 0
        bottom = thick if edge == EDGE_BOTTOM else 0
        self._reserving = bool(thick)
        margins = self._area.contentsMargins()
        if (margins.left(), margins.top(), margins.right(), margins.bottom()) \
                != (left, top, right, bottom):
            self._area.setContentsMargins(left, top, right, bottom)

    def _clamped_float(self, bounds: QRect) -> QRect:
        """The floating rect, in host coordinates, kept inside the page area."""
        rect = QRect(self._float_rect)
        if rect.width() < MIN_W or rect.height() < MIN_H:
            # First ever pop-out: top-right, under the page's header row.
            # Bottom-right would land on Home's Run Selected button.
            rect = QRect(bounds.width() - DEFAULT_W - FLOAT_GAP, FLOAT_TOP,
                         DEFAULT_W, DEFAULT_H)
            self._float_rect = QRect(rect)
        # `_float_rect` stays what the USER chose. What is shown may be wider
        # (the tab needs it) or moved (the window got smaller); neither is
        # written back, so both undo themselves.
        w = max(self._min_w(bounds), min(rect.width(), bounds.width()))
        h = max(MIN_H, min(rect.height(), bounds.height()))
        x = max(0, min(rect.x(), bounds.width() - w))
        y = max(0, min(rect.y(), bounds.height() - h))
        return QRect(bounds.left() + x, bounds.top() + y, w, h)

    def reanchor(self) -> None:
        """Put the panel where its state says, for the window as it is NOW.
        Called on every resize of the host and every page change."""
        if self._anchoring or not self.is_out():
            return
        self._anchoring = True
        try:
            bounds = self.bounds()
            if bounds.width() <= 0 or bounds.height() <= 0:
                return
            if self._edge in EDGES:
                rect, reserve = self._dock_rect(self._edge, bounds)
                thick = (rect.width() if self._edge in (EDGE_LEFT, EDGE_RIGHT)
                         else rect.height())
                self._set_reserve(self._edge if reserve else EDGE_NONE,
                                  thick if reserve else 0)
            else:
                self._set_reserve(EDGE_NONE, 0)
                rect = self._clamped_float(bounds)
            if self.geometry() != rect:
                self.setGeometry(rect)
            self.raise_()
        finally:
            self._anchoring = False

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize and watched in self._watched:
            self.reanchor()
        return False

    # ── dragging and snapping ────────────────────────────────────────────────

    def _edge_near(self, rect: QRect, bounds: QRect) -> str:
        """Which edge of the page area `rect` is pressed against, if any."""
        gaps = {EDGE_LEFT: rect.left() - bounds.left(),
                EDGE_RIGHT: bounds.right() - rect.right(),
                EDGE_TOP: rect.top() - bounds.top(),
                EDGE_BOTTOM: bounds.bottom() - rect.bottom()}
        edge = min(EDGES, key=lambda e: gaps[e])   # ties go left/right first
        return edge if gaps[edge] <= SNAP_PX else EDGE_NONE

    def _begin_drag(self, global_pos: QPoint) -> None:
        self._drag_origin = global_pos
        self._drag_offset = global_pos - self.mapToGlobal(QPoint(0, 0))
        self._dragging = False
        self._pending_edge = EDGE_NONE

    def _drag_to(self, global_pos: QPoint) -> None:
        if self._drag_origin is None:
            return
        if not self._dragging:
            if (global_pos - self._drag_origin).manhattanLength() < DRAG_START_PX:
                return
            self._dragging = True
            if self._edge in EDGES:
                self._undock_under(global_pos)
        bounds = self.bounds()
        top_left = self._host.mapFromGlobal(global_pos - self._drag_offset)
        x = max(bounds.left(), min(top_left.x(), bounds.right() - self.width() + 1))
        y = max(bounds.top(), min(top_left.y(), bounds.bottom() - self.height() + 1))
        self.move(x, y)
        self._float_rect.moveTo(x - bounds.left(), y - bounds.top())
        self._show_ghost(self._edge_near(self.geometry(), bounds), bounds)

    def _undock_under(self, global_pos: QPoint) -> None:
        """Leave the dock mid-drag: back to the floating size, with the same
        spot on the title bar still under the cursor."""
        fraction = self._drag_offset.x() / max(1, self.width())
        self._edge = EDGE_NONE
        self._set_reserve(EDGE_NONE, 0)
        w = self._float_rect.width() if self._float_rect.width() >= MIN_W else DEFAULT_W
        h = self._float_rect.height() if self._float_rect.height() >= MIN_H else DEFAULT_H
        bounds = self.bounds()
        self._float_rect.setSize(QSize(w, h))
        w = max(self._min_w(bounds), min(w, bounds.width()))
        h = min(h, bounds.height())
        self.resize(w, h)
        self._drag_offset = QPoint(int(w * fraction), min(self._drag_offset.y(), TITLE_H))

    def _show_ghost(self, edge: str, bounds: QRect) -> None:
        self._pending_edge = edge
        if edge not in EDGES:
            self._ghost.hide()
            return
        rect, _reserve = self._dock_rect(edge, bounds)
        self._ghost.setGeometry(rect)
        self._ghost.show()
        self._ghost.raise_()
        self.raise_()

    def _end_drag(self) -> None:
        was_dragging = self._dragging
        self._drag_origin = None
        self._dragging = False
        self._ghost.hide()
        if not was_dragging:
            return
        if self._pending_edge in EDGES:
            self.dock(self._pending_edge)
        else:
            self.reanchor()
        self._pending_edge = EDGE_NONE
        self.geometry_settled.emit()

    def dock(self, edge: str) -> None:
        """Snap to an edge (or float, with "")."""
        self._edge = edge if edge in EDGES else EDGE_NONE
        self.reanchor()

    # ── resizing from the border ─────────────────────────────────────────────

    def _hit_edges(self, pos: QPoint) -> str:
        """Which borders `pos` is on: any of "l", "r", "t", "b". Docked, only
        the border facing the page counts."""
        m = RESIZE_MARGIN + 2
        hit = ""
        if pos.x() <= m:
            hit += "l"
        elif pos.x() >= self.width() - m:
            hit += "r"
        if pos.y() <= m:
            hit += "t"
        elif pos.y() >= self.height() - m:
            hit += "b"
        if self._edge in EDGES:
            inner = {EDGE_LEFT: "r", EDGE_RIGHT: "l",
                     EDGE_TOP: "b", EDGE_BOTTOM: "t"}[self._edge]
            hit = inner if inner in hit else ""
        return hit

    @staticmethod
    def _cursor_for(hit: str):
        if hit in ("lt", "rb"):
            return Qt.CursorShape.SizeFDiagCursor
        if hit in ("rt", "lb"):
            return Qt.CursorShape.SizeBDiagCursor
        if hit in ("l", "r"):
            return Qt.CursorShape.SizeHorCursor
        if hit in ("t", "b"):
            return Qt.CursorShape.SizeVerCursor
        return None

    def mouseMoveEvent(self, event):
        if self._resize_edges:
            self._resize_to(event.globalPosition().toPoint())
            event.accept()
            return
        cursor = self._cursor_for(self._hit_edges(event.position().toPoint()))
        if cursor is None:
            self.unsetCursor()
        else:
            self.setCursor(cursor)

    def leaveEvent(self, event):
        if not self._resize_edges:
            self.unsetCursor()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            hit = self._hit_edges(event.position().toPoint())
            if hit:
                self._resize_edges = hit
                self._resize_origin = event.globalPosition().toPoint()
                self._resize_start = QRect(self.geometry())
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resize_edges and event.button() == Qt.MouseButton.LeftButton:
            self._resize_edges = ""
            self.reanchor()
            # Remember the thickness the dock actually GOT, not the one the
            # drag asked for: the page beside it can refuse some of it, and a
            # remembered wish would jump out on the next page that allows it.
            if self._edge in (EDGE_LEFT, EDGE_RIGHT):
                self._dock_w = self.width()
            elif self._edge in (EDGE_TOP, EDGE_BOTTOM):
                self._dock_h = self.height()
            self.geometry_settled.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _resize_to(self, global_pos: QPoint) -> None:
        delta = global_pos - self._resize_origin
        bounds = self.bounds()
        start = self._resize_start
        left, top, right, bottom = (start.left(), start.top(),
                                    start.right(), start.bottom())
        hit = self._resize_edges
        min_w = self._min_w(bounds)
        if "l" in hit:
            left = max(bounds.left(), min(left + delta.x(), right - min_w + 1))
        if "r" in hit:
            right = min(bounds.right(), max(right + delta.x(), left + min_w - 1))
        if "t" in hit:
            top = max(bounds.top(), min(top + delta.y(), bottom - MIN_H + 1))
        if "b" in hit:
            bottom = min(bounds.bottom(), max(bottom + delta.y(), top + MIN_H - 1))
        rect = QRect(QPoint(left, top), QPoint(right, bottom))
        if self._edge in EDGES:
            # Docked: the drag sets how THICK the dock is; reanchor() does the
            # rest (keeps it flush, keeps the page's reserved strip in step).
            if self._edge in (EDGE_LEFT, EDGE_RIGHT):
                self._dock_w = rect.width()
            else:
                self._dock_h = rect.height()
            self.reanchor()
        else:
            self._float_rect = QRect(rect.x() - bounds.left(), rect.y() - bounds.top(),
                                     rect.width(), rect.height())
            self.setGeometry(rect)

    # ── theme ────────────────────────────────────────────────────────────────

    def apply_theme(self):
        palette = self.get_current_palette()
        # The scoped sheet first (a no-op "" while the Assistant follows the
        # app), then this panel's own rules, the way a top-level Assistant
        # dialog carries it - see "Scoped themes" in docs/ARCHITECTURE.md.
        self.setStyleSheet(self.scope_stylesheet() + f"""
            QFrame#assistantPopout {{
                background: {palette.background};
                border: 1px solid {palette.accent};
                border-radius: 10px;
            }}
        """)
        self._title.setStyleSheet(
            f"color: {palette.text}; font-size: 13px; font-weight: bold;"
            " background: transparent;")
        self._pop_in_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {palette.text_secondary};
                border: 1px solid {palette.border};
                border-radius: 11px;
                padding: 2px 10px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                border-color: {palette.accent};
                color: {palette.accent};
            }}
        """)
        from PySide6.QtGui import QColor
        tint = QColor(palette.accent)
        self._ghost.setStyleSheet(f"""
            QFrame#assistantPopoutGhost {{
                background: rgba({tint.red()}, {tint.green()}, {tint.blue()}, 50);
                border: 2px dashed {palette.accent};
                border-radius: 10px;
            }}
        """)
