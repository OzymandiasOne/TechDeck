"""
Home tile-grid layout controller, extracted from home_page.py.

`TileGridController` owns the Home tile grid's absolute positioning: column
reflow on resize, slot geometry, the drag-reorder lifecycle (with push-aside
animation and auto-scroll near the edges), and persistence of tile order via
the injected SettingsManager. `_GridSurface` is the bare surface widget that
reports resizes so the controller can recompute columns.

HomePage owns the controller instance and forwards each card's drag signals to
`on_drag_started/on_drag_moved/on_drag_dropped`; all geometry lives here.
"""

from PySide6.QtWidgets import QWidget, QScrollArea
from PySide6.QtCore import (
    Signal, QObject, QTimer, QPropertyAnimation, QEasingCurve, QPoint,
)

from techdeck.ui.widgets.plugin_card import HOME_TILE_W, HOME_TILE_H


class _GridSurface(QWidget):
    """QWidget that emits `resized` so TileGridController can recompute columns."""
    resized = Signal()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resized.emit()


class TileGridController(QObject):
    """Absolute-position grid manager for draggable plugin tiles.

    Replaces QGridLayout on the Home page surface. Each tile is placed via
    `widget.move()` based on its logical index in `_order`. Drag-and-drop is
    handled by animating other tiles' `pos` properties as the dragged tile
    moves between slots, giving the smartphone/Teams-card "push aside" feel.
    """

    CELL_W = HOME_TILE_W
    CELL_H = HOME_TILE_H
    SPACING = 16
    MARGIN = 24
    # Columns reflow to fill the available width (computed in _recompute_cols).
    # MAX_COLS is just a sane upper ceiling for very wide monitors.
    MAX_COLS = 12

    # Auto-scroll while dragging a tile near the viewport's top/bottom edge.
    AUTOSCROLL_ZONE = 56       # px from edge that activates scrolling
    AUTOSCROLL_MAX_SPEED = 22  # px per tick at the very edge (ramps from 1)
    AUTOSCROLL_INTERVAL = 15   # ms between scroll ticks

    def __init__(self, surface: _GridSurface, settings, parent=None):
        super().__init__(parent)
        self._surface = surface
        self._settings = settings
        self._order: list = []
        self._widgets: dict = {}
        self._cols = self.MAX_COLS
        self._anims: list = []  # keep refs so QPropertyAnimations don't GC

        # Drag state
        self._drag_card = None
        self._drag_widget_id = None
        self._drag_origin_index = -1
        self._hover_index = -1
        self._grab_offset = QPoint(0, 0)
        self._restore_shadow = None  # (blur, x_offset, y_offset)

        # Auto-scroll state. The scroll area is wired in by HomePage after
        # construction via set_scroll_area. A timer drives continuous scrolling
        # while the cursor sits in an edge zone (drag-move events alone stop
        # firing if the user holds still, so a timer is required).
        self._scroll_area = None
        self._autoscroll_velocity = 0
        self._last_drag_global = QPoint(0, 0)
        self._autoscroll_timer = QTimer(self)
        self._autoscroll_timer.setInterval(self.AUTOSCROLL_INTERVAL)
        self._autoscroll_timer.timeout.connect(self._on_autoscroll_tick)

        surface.resized.connect(self._on_resized)

    def set_scroll_area(self, scroll_area):
        """Wire the QScrollArea so drag-near-edge can auto-scroll the grid."""
        self._scroll_area = scroll_area

    # ---- setup / teardown ------------------------------------------------

    def set_tiles(self, order: list, widgets: dict):
        """Replace the current set of managed tiles. Caller owns lifecycle of evicted widgets."""
        self._cancel_active_drag()
        self._order = list(order)
        self._widgets = dict(widgets)
        for w in widgets.values():
            if w.parent() is not self._surface:
                w.setParent(self._surface)
            w.show()
        self._recompute_cols()
        self.relayout(animated=False)

    def clear(self):
        self._cancel_active_drag()
        self._order = []
        self._widgets = {}
        self._anims = []

    def _cancel_active_drag(self):
        self._stop_autoscroll()
        self._clear_drag_state()

    def _clear_drag_state(self):
        """Reset all drag bookkeeping and restore the dragged card's shadow.
        Safe to call whether or not a drag is active. `_order` is NOT touched —
        it always holds the full tile set, so a tile can never be lost even if a
        drop event is missed (the grid self-heals on the next relayout)."""
        card = self._drag_card
        if (card is not None and self._restore_shadow is not None
                and hasattr(card, "_shadow") and card.graphicsEffect() is card._shadow):
            blur, ox, oy = self._restore_shadow
            card._shadow.setBlurRadius(blur)
            card._shadow.setOffset(ox, oy)
        self._restore_shadow = None
        self._drag_card = None
        self._drag_widget_id = None
        self._drag_origin_index = -1
        self._hover_index = -1

    # ---- geometry --------------------------------------------------------

    def slot_pos(self, index: int, cols: int) -> QPoint:
        row, col = divmod(index, cols)
        x = self.MARGIN + col * (self.CELL_W + self.SPACING)
        y = self.MARGIN + row * (self.CELL_H + self.SPACING)
        return QPoint(x, y)

    def _recompute_cols(self) -> bool:
        w = self._surface.width()
        available = max(self.CELL_W, w - 2 * self.MARGIN + self.SPACING)
        new_cols = max(1, available // (self.CELL_W + self.SPACING))
        new_cols = min(self.MAX_COLS, new_cols)
        if new_cols != self._cols:
            self._cols = new_cols
            return True
        return False

    def _on_resized(self):
        changed = self._recompute_cols()
        if changed:
            self.relayout(animated=False)
        else:
            self._update_min_size()

    def _index_for_point(self, p: QPoint) -> int:
        stride_x = self.CELL_W + self.SPACING
        stride_y = self.CELL_H + self.SPACING
        # +SPACING//2 puts the snap boundary at the midpoint between tiles, so
        # cursor "between" slots picks the next slot rather than the current one.
        col = (p.x() - self.MARGIN + self.SPACING // 2) // stride_x
        row = (p.y() - self.MARGIN + self.SPACING // 2) // stride_y
        col = max(0, min(self._cols - 1, int(col)))
        row = max(0, int(row))
        idx = row * self._cols + col
        # `_order` keeps the dragged tile, so there are len(_order)-1 OTHER tiles;
        # the dragged tile can be inserted at any slot 0..(that count).
        max_slot = max(0, len(self._order) - 1)
        return max(0, min(idx, max_slot))

    def _update_min_size(self):
        # `_order` always holds every tile (including the one being dragged), so
        # the count is just its length.
        n = len(self._order)
        if n == 0:
            self._surface.setMinimumHeight(self.MARGIN * 2 + self.CELL_H)
            return
        rows = (n + self._cols - 1) // self._cols
        h = self.MARGIN * 2 + rows * self.CELL_H + max(0, rows - 1) * self.SPACING
        self._surface.setMinimumHeight(h)

    # ---- layout ---------------------------------------------------------

    def relayout(self, animated: bool = True):
        """Move every tile to its slot. During drag, the dragged card is skipped
        (it's following the cursor) and other tiles shift to make room."""
        dragging = self._drag_card is not None and self._drag_widget_id is not None
        if dragging:
            # Build the visible order from the OTHER tiles, then slot the dragged
            # tile in at the hover position. `_order` itself is left intact.
            display_order = [t for t in self._order if t != self._drag_widget_id]
            insert_at = max(0, min(self._hover_index, len(display_order)))
            display_order.insert(insert_at, self._drag_widget_id)
        else:
            display_order = list(self._order)

        new_anims = []
        for i, tid in enumerate(display_order):
            if self._drag_widget_id is not None and tid == self._drag_widget_id:
                continue  # dragged card follows cursor, not slots
            card = self._widgets.get(tid)
            if card is None:
                continue
            target = self.slot_pos(i, self._cols)
            if card.pos() == target:
                continue
            if animated:
                anim = QPropertyAnimation(card, b"pos", self)
                anim.setDuration(180)
                anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                anim.setStartValue(card.pos())
                anim.setEndValue(target)
                anim.start()
                new_anims.append(anim)
            else:
                card.move(target)

        self._anims = new_anims
        self._update_min_size()

    # ---- drag lifecycle -------------------------------------------------

    def on_drag_started(self, card, press_pos: QPoint):
        tid = getattr(card, "tile_id", None)
        if tid is None or tid not in self._widgets:
            return
        if tid not in self._order:
            return
        # If a previous drag never delivered its drop (missed release / re-entrant
        # press), finalize it first so its tile snaps back to its slot instead of
        # being left floating. _order is intact, so nothing was lost.
        if self._drag_card is not None and self._drag_card is not card:
            self._stop_autoscroll()
            self._clear_drag_state()
            self.relayout(animated=False)
        self._drag_card = card
        self._drag_widget_id = tid
        self._drag_origin_index = self._order.index(tid)
        self._hover_index = self._drag_origin_index
        self._grab_offset = QPoint(press_pos)

        # Lift visually: bump the card's shadow effect. A widget can only host
        # one QGraphicsEffect, so we mutate the existing shadow rather than adding
        # an overlay effect.
        if hasattr(card, "_shadow") and card.graphicsEffect() is card._shadow:
            self._restore_shadow = (
                card._shadow.blurRadius(),
                card._shadow.xOffset(),
                card._shadow.yOffset(),
            )
            # Stop any in-flight hover animation that targets the same property.
            if hasattr(card, "_hover_in"):
                card._hover_in.stop()
            if hasattr(card, "_hover_out"):
                card._hover_out.stop()
            card._shadow.setBlurRadius(30)
            card._shadow.setOffset(0, 8)
        else:
            self._restore_shadow = None

        card.raise_()
        self.relayout(animated=True)

    def on_drag_moved(self, global_pos: QPoint):
        if self._drag_card is None:
            return
        self._last_drag_global = QPoint(global_pos)
        self._reposition_drag(global_pos)
        self._update_autoscroll(global_pos)

    def _reposition_drag(self, global_pos: QPoint):
        """Move the dragged card to follow the cursor and update the hover slot.
        Recomputed from the (unchanging) global cursor pos so it stays correct
        even as auto-scroll shifts the surface beneath the cursor."""
        if self._drag_card is None:
            return
        local = self._surface.mapFromGlobal(global_pos)
        self._drag_card.move(local - self._grab_offset)
        new_idx = self._index_for_point(local)
        if new_idx != self._hover_index:
            self._hover_index = new_idx
            self.relayout(animated=True)

    # ---- auto-scroll-near-edge ------------------------------------------

    def _update_autoscroll(self, global_pos: QPoint):
        """Set scroll velocity from the cursor's distance into an edge zone."""
        scroll = self._scroll_area
        if scroll is None:
            return
        vp = scroll.viewport()
        y = vp.mapFromGlobal(global_pos).y()
        zone = self.AUTOSCROLL_ZONE
        height = vp.height()

        vel = 0
        if y < zone:
            frac = min(1.0, max(0.0, (zone - y) / zone))
            vel = -max(1, round(self.AUTOSCROLL_MAX_SPEED * frac))
        elif y > height - zone:
            frac = min(1.0, max(0.0, (y - (height - zone)) / zone))
            vel = max(1, round(self.AUTOSCROLL_MAX_SPEED * frac))

        self._autoscroll_velocity = vel
        if vel != 0 and not self._autoscroll_timer.isActive():
            self._autoscroll_timer.start()
        elif vel == 0 and self._autoscroll_timer.isActive():
            self._autoscroll_timer.stop()

    def _on_autoscroll_tick(self):
        if self._drag_card is None or self._autoscroll_velocity == 0 \
                or self._scroll_area is None:
            self._stop_autoscroll()
            return
        sb = self._scroll_area.verticalScrollBar()
        old = sb.value()
        new = max(sb.minimum(), min(sb.maximum(), old + self._autoscroll_velocity))
        if new == old:
            return  # already at the end in this direction; nothing to scroll
        sb.setValue(new)
        # The cursor's global pos didn't change, but the surface moved under it,
        # so re-derive the card position and hover slot from the stored global.
        self._reposition_drag(self._last_drag_global)

    def _stop_autoscroll(self):
        self._autoscroll_velocity = 0
        if self._autoscroll_timer.isActive():
            self._autoscroll_timer.stop()

    def on_drag_dropped(self, global_pos: QPoint):
        if self._drag_card is None:
            return
        self._stop_autoscroll()
        tid = self._drag_widget_id

        # Move the tile to its drop slot within the OTHER tiles. remove()+insert()
        # is balanced, so _order keeps every tile (no duplicates, no losses).
        max_slot = max(0, len(self._order) - 1)
        drop_idx = max(0, min(self._hover_index, max_slot))
        if tid in self._order:
            self._order.remove(tid)
        self._order.insert(drop_idx, tid)

        # Clear drag state (restores the card's shadow) BEFORE relaying out so the
        # dropped card is treated as a normal tile and animated into its slot.
        self._clear_drag_state()
        self.relayout(animated=True)

        try:
            self._settings.set_profile_tiles(list(self._order))
        except Exception:
            # Don't crash the UI if persistence fails — drag still completes.
            pass

    def get_order(self) -> list:
        return list(self._order)
