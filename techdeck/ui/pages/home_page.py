"""
TechDeck Home Page - Professional Card Design
PHASE 3: Enhanced tiles with elevation, hover effects, status indicators, and modern card styling
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QScrollArea, QMessageBox, QCheckBox, QFrame,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QApplication,
)
from PySide6.QtCore import (
    Signal, Qt, QPropertyAnimation, QEasingCurve, Property,
    QVariantAnimation, QSequentialAnimationGroup, QTimer,
    QPoint, QObject,
)
from PySide6.QtGui import QFont, QColor, QCursor

import math
import queue as _queue

from techdeck.core.settings import SettingsManager
from techdeck.core.plugin_loader import PluginLoader
from techdeck.core.plugin_executor import PluginExecutor, PluginResult
from pathlib import Path
from techdeck.ui.utils import make_tinted_svg_copy
from techdeck.ui.theme_aware import ThemeAware
from techdeck.ui.theme_manager import get_theme_manager
from techdeck.ui.plugin_icon import plugin_icon_pixmap, eye_follow_key, pack_icon_pixmap

# Windows-Settings-style tile geometry: a centered icon over the app name.
# The Library keeps the compact, borderless tiles (TILE_*). The Home page uses
# larger, solid carded tiles (HOME_TILE_*) with the old border-based selection.
# library_page imports the TILE_* set, so those must stay the Library sizes.
TILE_W = 120
TILE_H = 110
TILE_ICON = 48          # rendered icon pixmap size (px)
TILE_ICON_BOX = 58      # icon container size

HOME_TILE_W = 140      # square tiles
HOME_TILE_H = 140
HOME_TILE_ICON = 64
HOME_TILE_ICON_BOX = 72

# Fixed family-tag colors for the Home tile corner badge (every family gets one).
_FAMILY_BADGE_COLORS = {"902": "#06B6D4", "911": "#3B82F6", "922": "#F59E0B",
                        "QA": "#10B981", "Games": "#A855F7", "General": "#8B5CF6"}


def _strip_family_prefix(name: str, family: str) -> str:
    """Drop a leading "911 "/"922 "/"QA " from a tile name (family shows as a badge)."""
    if family in _FAMILY_BADGE_COLORS and name.startswith(family + " "):
        return name[len(family) + 1:]
    return name


class _EyeFollow(QObject):
    """Makes a tile icon's pupils track the cursor (Mr Beans on the Home grid).

    Polls the global cursor while the icon is visible and swaps the label's
    pixmap among the 9 directional pack sprites: <key>.png looks straight at
    the camera (shown when the cursor is on/near the tile), <key>_<dir>.png
    for the 8 compass directions. Sprites are cached at construction and the
    label only repaints when the direction actually changes, so the steady
    state is a no-op timer tick. Disabled while the professional theme is
    active (playful features hide for client demos).
    """

    _DIRS = ("right", "down_right", "down", "down_left",
             "left", "up_left", "up", "up_right")
    _DEADZONE = 48   # px from the icon center inside which he makes eye contact

    def __init__(self, label: QLabel, key: str, size: int):
        super().__init__(label)
        self._label = label
        self._current = ""
        self._pixmaps = {}
        base = pack_icon_pixmap(key, size)
        if base is None:
            return  # art missing -> leave the static icon alone, no timer
        self._pixmaps[""] = base
        for d in self._DIRS:
            pm = pack_icon_pixmap(f"{key}_{d}", size)
            if pm is not None:
                self._pixmaps[d] = pm
        self._timer = QTimer(self)
        self._timer.setInterval(90)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def refresh(self):
        """Forget the cached direction (the label's pixmap was reset externally)."""
        self._current = ""

    def _tick(self):
        if not self._label.isVisible():
            return
        if get_theme_manager().get_current_theme() == "professional":
            return  # apply_theme already reset the label to the static base icon
        center = self._label.mapToGlobal(self._label.rect().center())
        cur = QCursor.pos()
        dx, dy = cur.x() - center.x(), cur.y() - center.y()
        if dx * dx + dy * dy <= self._DEADZONE * self._DEADZONE:
            d = ""
        else:
            # Screen y grows downward, so atan2(dy, dx) sweeps right -> down ->
            # left -> up; eight 45-degree sectors centered on each direction.
            d = self._DIRS[round(math.atan2(dy, dx) / (math.pi / 4)) % 8]
        if d != self._current and d in self._pixmaps:
            self._current = d
            self._label.setPixmap(self._pixmaps[d])


class PluginCard(QFrame, ThemeAware):
    """Professional plugin card with shadow elevation, hover lift, pulse, and flash animations."""

    toggled = Signal(bool)
    # Drag signals: emitted as the user picks up, drags, and drops this card on the
    # Home page tile grid. TileGridController receives them and animates the grid.
    drag_started = Signal(object, QPoint)   # (card, press_pos_local)
    drag_moved = Signal(QPoint)             # global cursor pos
    drag_dropped = Signal(QPoint)           # global cursor pos at release

    STATUS_IDLE = "idle"
    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_ERROR = "error"
    STATUS_CANCELLED = "cancelled"
    STATUS_TIMEOUT = "timeout"
    STATUS_PAUSED = "paused"   # parked by /pause or auto-idle; resumes via /resume

    def __init__(self, plugin, plugin_desc: str, tile_id: str, theme, parent=None):
        super().__init__(parent)
        self.tile_id = tile_id
        self.theme = theme
        self._plugin = plugin
        self._is_checked = False
        self._status = self.STATUS_IDLE
        self._flash_anim = None
        self._entrance_anim = None
        # Drag state: armed on press, promoted to dragging once movement exceeds
        # QApplication.startDragDistance(). _can_drag is a callable so HomePage can
        # gate drags on "not currently running a plugin" without coupling.
        self._drag_armed = False
        self._dragging = False
        self._press_pos = QPoint()
        self._press_global = QPoint()
        self._can_drag = lambda: True

        self.setFixedSize(HOME_TILE_W, HOME_TILE_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 10, 6, 10)
        layout.setSpacing(6)

        # Icon over name (Windows-Settings layout) on a solid carded tile.
        # Pure-highlight selection — no checkbox; clicking toggles _is_checked.
        self.icon_label = QLabel()
        self.icon_label.setObjectName("cardIcon")
        self.icon_label.setFixedSize(HOME_TILE_ICON_BOX, HOME_TILE_ICON_BOX)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setPixmap(plugin_icon_pixmap(plugin, HOME_TILE_ICON))
        # Transparent so the solid card background shows through behind the icon.
        self.icon_label.setStyleSheet("#cardIcon { background: transparent; }")

        # Icons with directional sprites (mr_beans) get cursor-tracking pupils.
        key = eye_follow_key(plugin)
        self._eye_follow = _EyeFollow(self.icon_label, key, HOME_TILE_ICON) if key else None

        # Name without the family prefix (the family shows as a corner badge).
        self._family = getattr(plugin, "family", "General")
        self.name_label = QLabel(_strip_family_prefix(getattr(plugin, "name", tile_id), self._family))
        self.name_label.setWordWrap(True)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        name_font = QFont()  # old tile design font
        name_font.setPointSize(11)
        name_font.setWeight(QFont.Weight.DemiBold)
        self.name_label.setFont(name_font)
        self.name_label.setStyleSheet(f"color: {theme.text}; background-color: transparent;")

        layout.addStretch()
        layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.name_label, 0)
        layout.addStretch()

        # Family badge in the top-left corner (902/911/922/QA/Games/General).
        # Absolutely-positioned child so it overlays the corner without affecting
        # the centered icon/name layout.
        self.family_badge = QLabel(self._family if self._family in _FAMILY_BADGE_COLORS else "", self)
        self.family_badge.move(7, 5)
        self.family_badge.setVisible(bool(self.family_badge.text()))
        self._style_family_badge()

        # No hover tooltip on Home tiles — descriptions are available via /info
        # after selecting a tile (the `plugin_desc` arg is kept for signature
        # compatibility but intentionally unused here).

        self._update_card_style()

        # --- Card shadow (activated after entrance) ---
        # On the card itself (old behavior): the tile has a SOLID background, so
        # the shadow casts off the opaque card silhouette, not the text — no fuzz.
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(8)
        self._shadow.setOffset(0, 3)
        self._shadow_base_color = self._parse_shadow_color(theme.shadow)
        self._shadow.setColor(self._shadow_base_color)

        # Hover lift animations
        self._hover_in = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._hover_in.setDuration(150)
        self._hover_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_in.setEndValue(20.0)

        self._hover_out = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._hover_out.setDuration(200)
        self._hover_out.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_out.setEndValue(8.0)

        # Running pulse (shadow breathes)
        pulse_up = QPropertyAnimation(self._shadow, b"blurRadius", self)
        pulse_up.setDuration(700)
        pulse_up.setStartValue(10.0)
        pulse_up.setEndValue(22.0)
        pulse_up.setEasingCurve(QEasingCurve.Type.InOutSine)

        pulse_dn = QPropertyAnimation(self._shadow, b"blurRadius", self)
        pulse_dn.setDuration(700)
        pulse_dn.setStartValue(22.0)
        pulse_dn.setEndValue(10.0)
        pulse_dn.setEasingCurve(QEasingCurve.Type.InOutSine)

        self._pulse_group = QSequentialAnimationGroup(self)
        self._pulse_group.addAnimation(pulse_up)
        self._pulse_group.addAnimation(pulse_dn)
        self._pulse_group.setLoopCount(-1)

        # Entrance fade uses a temporary opacity effect on the whole card; it's
        # removed once the fade finishes so it never nests with the icon shadow.
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)

        self.setup_theme_awareness()

    @staticmethod
    def _parse_shadow_color(shadow_str: str) -> QColor:
        import re
        m = re.match(r'rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)', shadow_str)
        if m:
            a = int(float(m.group(4)) * 255)
            return QColor(int(m.group(1)), int(m.group(2)), int(m.group(3)), a)
        return QColor(0, 0, 0, 60)

    def start_entrance(self, delay_ms: int):
        """Trigger staggered fade-in entrance."""
        self._entrance_anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._entrance_anim.setStartValue(0.0)
        self._entrance_anim.setEndValue(1.0)
        self._entrance_anim.setDuration(280)
        self._entrance_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._entrance_anim.finished.connect(self._on_entrance_done)
        QTimer.singleShot(delay_ms, self._entrance_anim.start)

    def _on_entrance_done(self):
        """Swap the entrance opacity effect for the card shadow effect."""
        self._entrance_anim = None
        self._opacity_effect = None
        self.setGraphicsEffect(self._shadow)
        if self._status == self.STATUS_RUNNING:
            self._start_pulse()

    def apply_theme(self):
        self.theme = self.get_current_palette()
        self._update_card_style()
        self._shadow_base_color = self._parse_shadow_color(self.theme.shadow)
        if self._status != self.STATUS_RUNNING:
            self._shadow.setColor(self._shadow_base_color)
        self.name_label.setStyleSheet(f"color: {self.theme.text}; background-color: transparent;")
        # Icons are theme-matched; swap to the new theme's variant.
        self.icon_label.setPixmap(plugin_icon_pixmap(self._plugin, HOME_TILE_ICON))
        if self._eye_follow:
            self._eye_follow.refresh()
        # Family tag text uses the theme accent, so re-style it on theme change.
        self._style_family_badge()

    def is_checked(self) -> bool:
        return self._is_checked

    def set_checked(self, checked: bool):
        if checked == self._is_checked:
            return
        self._is_checked = checked
        self._update_card_style()
        self.toggled.emit(checked)

    def set_status(self, status: str):
        prev = self._status
        self._status = status

        if status == self.STATUS_RUNNING:
            self._start_pulse()
        elif prev == self.STATUS_RUNNING:
            self._stop_pulse()

        if status == self.STATUS_SUCCESS:
            self._flash_success()
        else:
            self._update_card_style()

    def _start_pulse(self):
        if self.graphicsEffect() is self._shadow:
            c = QColor(self.theme.accent)
            c.setAlpha(160)
            self._shadow.setColor(c)
            self._pulse_group.start()

    def _stop_pulse(self):
        self._pulse_group.stop()
        if self.graphicsEffect() is self._shadow:
            self._shadow.setBlurRadius(8)
            self._shadow.setColor(self._shadow_base_color)

    def _flash_success(self):
        """Flash green background then fade to normal."""
        self._flash_anim = QVariantAnimation(self)
        self._flash_anim.setStartValue(QColor(self.theme.success))
        self._flash_anim.setEndValue(QColor(self.theme.surface))
        self._flash_anim.setDuration(700)
        self._flash_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._flash_anim.valueChanged.connect(self._on_flash_color)
        self._flash_anim.finished.connect(self._on_flash_done)
        self._flash_anim.start()

    def _on_flash_color(self, color: QColor):
        hex_color = color.name()
        self.setStyleSheet(
            f"PluginCard {{ background-color: {hex_color}; border-radius: 12px; }}"
        )

    def _on_flash_done(self):
        self._flash_anim = None
        self._update_card_style()

    def _style_family_badge(self):
        """Style the corner family tag. Currently TEXT-ONLY: transparent chip
        background (blends with the tile in every state) and the text colored with
        the active theme's accent, so the tag matches each theme. `_FAMILY_BADGE_COLORS`
        gates which families get a tag (all of them now: 902/911/922/QA/Games/General);
        to bring a colored chip back later, set `background-color` to that family
        color and text `#FFFFFF`."""
        if self._family not in _FAMILY_BADGE_COLORS:   # unknown family -> no badge
            self.family_badge.setVisible(False)
            return
        self.family_badge.setStyleSheet(
            f"QLabel {{ background-color: transparent; color: {self.theme.accent}; "
            f"font-size: 8pt; font-weight: bold; border-radius: 5px; padding: 0px 4px; }}"
        )
        self.family_badge.adjustSize()
        self.family_badge.raise_()

    def _update_card_style(self):
        # No tile border and no icon ring (users found the status ring
        # distracting). The icon box stays transparent/borderless in every state;
        # status reads from the card-shadow pulse (running) and the success flash.
        # Selection + hover show as the tile background color.
        self.icon_label.setStyleSheet("#cardIcon { background: transparent; }")

        bg = self.theme.tile_selected if self._is_checked else self.theme.surface
        self.setStyleSheet(f"""
            PluginCard {{
                background-color: {bg};
                border-radius: 12px;
            }}
            PluginCard:hover {{
                background-color: {self.theme.surface_hover};
            }}
        """)

    def is_running(self) -> bool:
        """Whether this card's plugin is currently executing (drag is blocked while running)."""
        return self._status == self.STATUS_RUNNING

    def enterEvent(self, event):
        # While dragging, the controller is animating the shadow; don't fight it.
        if (self.graphicsEffect() is self._shadow
                and self._status != self.STATUS_RUNNING
                and not self._dragging):
            self._hover_out.stop()
            self._hover_in.setStartValue(self._shadow.blurRadius())
            self._hover_in.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if (self.graphicsEffect() is self._shadow
                and self._status != self.STATUS_RUNNING
                and not self._dragging):
            self._hover_in.stop()
            self._hover_out.setStartValue(self._shadow.blurRadius())
            self._hover_out.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        # Arm a potential drag. We don't toggle the checkbox here anymore —
        # that moves to mouseReleaseEvent so we can distinguish click from drag.
        if event.button() == Qt.MouseButton.LeftButton and not self.is_running() and self._can_drag():
            self._press_pos = event.position().toPoint()
            self._press_global = event.globalPosition().toPoint()
            self._drag_armed = True
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_armed and not self._dragging:
            delta = (event.globalPosition().toPoint() - self._press_global).manhattanLength()
            if delta >= QApplication.startDragDistance():
                self._dragging = True
                self.drag_started.emit(self, self._press_pos)
        if self._dragging:
            self.drag_moved.emit(event.globalPosition().toPoint())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._drag_armed and not self._dragging:
                # True click — toggle the pure-highlight selection.
                self.set_checked(not self._is_checked)
            elif self._dragging:
                self.drag_dropped.emit(event.globalPosition().toPoint())
            self._drag_armed = False
            self._dragging = False
        super().mouseReleaseEvent(event)


class _MissingTile(QFrame):
    """Placeholder card for a tile whose plugin folder is no longer on disk.

    Mirrors PluginCard's drag protocol so the user can still rearrange or remove
    the slot; clicking does nothing (no checkbox), but the "Remove from Kit"
    button still works.
    """

    drag_started = Signal(object, QPoint)
    drag_moved = Signal(QPoint)
    drag_dropped = Signal(QPoint)

    def __init__(self, tile_id: str, theme, on_remove, parent=None):
        super().__init__(parent)
        self.tile_id = tile_id
        self.setFixedSize(HOME_TILE_W, HOME_TILE_H)

        self._drag_armed = False
        self._dragging = False
        self._press_global = QPoint()
        self._press_pos = QPoint()
        self._can_drag = lambda: True

        card_layout = QVBoxLayout(self)
        card_layout.setContentsMargins(8, 12, 8, 10)
        card_layout.setSpacing(6)

        icon_box = QLabel("?")
        icon_box.setObjectName("missingIcon")
        icon_box.setFixedSize(HOME_TILE_ICON_BOX, HOME_TILE_ICON_BOX)
        icon_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_box = icon_box

        missing_label = QLabel("Missing")
        missing_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        missing_label.setWordWrap(True)
        missing_label.setToolTip(f"{tile_id}\n(plugin missing from disk)")
        self._missing_label = missing_label

        remove_btn = QPushButton("Remove")
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #EF4444;
                border: 1px solid #EF4444;
                border-radius: 4px;
                font-size: 10px;
                padding: 3px 10px;
            }
            QPushButton:hover {
                background-color: #EF4444;
                color: white;
            }
        """)
        remove_btn.clicked.connect(lambda _checked=False, tid=tile_id: on_remove(tid))

        card_layout.addStretch()
        card_layout.addWidget(icon_box, 0, Qt.AlignmentFlag.AlignHCenter)
        card_layout.addWidget(missing_label)
        card_layout.addWidget(remove_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        card_layout.addStretch()

        self.restyle(theme)

    def restyle(self, theme):
        """Apply theme colors. Called at construction and on live theme change
        (this widget isn't ThemeAware, so HomePage.apply_theme re-stamps it)."""
        self._icon_box.setStyleSheet(
            f"#missingIcon {{ color: {theme.tile_missing_text}; "
            f"font-size: 24px; font-weight: bold; background: transparent; "
            f"border: 2px dashed {theme.tile_missing_border}; border-radius: 16px; }}"
        )
        self._missing_label.setStyleSheet(
            f"color: {theme.tile_missing_text}; font-size: 10pt; font-weight: bold; "
            f"background: transparent;"
        )
        self.setStyleSheet(
            f"_MissingTile {{ background-color: {theme.surface}; border-radius: 12px; }}"
        )

    def is_running(self) -> bool:
        return False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._can_drag():
            self._press_pos = event.position().toPoint()
            self._press_global = event.globalPosition().toPoint()
            self._drag_armed = True
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_armed and not self._dragging:
            delta = (event.globalPosition().toPoint() - self._press_global).manhattanLength()
            if delta >= QApplication.startDragDistance():
                self._dragging = True
                self.drag_started.emit(self, self._press_pos)
        if self._dragging:
            self.drag_moved.emit(event.globalPosition().toPoint())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._dragging:
                self.drag_dropped.emit(event.globalPosition().toPoint())
            self._drag_armed = False
            self._dragging = False
        super().mouseReleaseEvent(event)


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


class HomePage(QWidget, ThemeAware):
    profile_changed = Signal(str)
    kit_changed = Signal()  # tile membership of the current kit changed from Home (e.g. missing-tile Remove)
    open_library = Signal()
    run_selected = Signal(list)
    plugin_log = Signal(str, str)
    plugin_progress = Signal(str, int)
    plugin_completed = Signal(str)
    plugin_status_updated = Signal(str, str)  # tile_id, status — safe to emit from any thread
    all_plugins_done = Signal()               # emitted on main thread after every plugin in a run finishes
    _plugins_all_done = Signal()              # internal — emitted from worker thread, handled on main thread
    # Fired by the executor watchdog (background thread) when a plugin's input
    # prompt has been idle past the auto-pause threshold. We route it through
    # a Qt signal so the actual pause work runs on the GUI thread.
    _input_idle_requested = Signal()

    def __init__(self, settings: SettingsManager, parent=None, plugin_loader: 'PluginLoader' = None):
        super().__init__(parent)
        self.settings = settings
        self.selected_tiles = set()
        self.tile_cards = {}  # PHASE 3: Track card widgets by tile_id
        self._missing_tiles: dict = {}  # tile_id -> _MissingTile for tiles whose plugin folder is gone
        self._is_running = False  # True while any plugin is executing
        self._restoring = False   # True during programmatic tile checks (no click sound)

        # Use the shared loader if MainWindow gave us one; otherwise scan now.
        if plugin_loader is None:
            plugin_loader = PluginLoader()
            plugin_loader.discover_plugins()
        self.plugin_loader = plugin_loader
        self.plugin_executor = PluginExecutor(self.plugin_loader)
        self._plugin_queue: list = []
        self._plugin_params: dict = {}
        # Per-run, per-family scratch dict. plugin_sdk.request_batch_number
        # caches the first answer here and subsequent same-family plugins reuse
        # it. Cleared when the whole multi-plugin run completes.
        self._shared_state: dict = {"911": {}, "922": {}, "General": {}}
        self.plugin_status_updated.connect(self._apply_plugin_status)
        self._plugins_all_done.connect(self._check_run_complete)
        self._input_idle_requested.connect(self._on_input_idle_requested)

        # Pause / resume state — Phase C. _paused is True between a pause
        # event and the following /resume. _paused_tile_id is the plugin
        # that was running when pause hit; it's re-inserted at the head of
        # _plugin_queue in _on_plugin_complete so /resume picks it up first.
        self._paused: bool = False
        self._paused_tile_id = None
        # Deferred-shelve flag — Phase D. When /shelve is called mid-run, we
        # let the current plugin finish, then save the remainder. The check
        # lives in _on_plugin_complete after the normal-status branches.
        self._shelve_after_current: bool = False

        # Log buffer: worker threads put messages here; drain timer delivers them
        # to the main thread in batches so the Qt event queue never floods.
        self._log_buffer: _queue.Queue = _queue.Queue()
        self._log_drain_timer = QTimer(self)
        self._log_drain_timer.setInterval(50)
        self._log_drain_timer.timeout.connect(self._drain_log_buffer)
        self._log_drain_timer.start()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Profile Controls Container
        self._profile_container = QWidget()
        self._profile_container.setFixedHeight(50)
        profile_layout = QHBoxLayout(self._profile_container)
        profile_layout.setContentsMargins(20, 8, 20, 8)
        profile_layout.setSpacing(12)

        self._profile_label = QLabel("Active Kit   /")

        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(200)
        self.profile_combo.setMinimumHeight(36)
        self.profile_combo.currentTextChanged.connect(self._on_profile_selected)

        self.btn_add = QPushButton("+ Apps")
        self.btn_add.setMinimumHeight(36)
        self.btn_add.clicked.connect(self._on_add_tiles)

        profile_layout.addWidget(self._profile_label)
        profile_layout.addWidget(self.profile_combo)
        profile_layout.addStretch()
        # Dev-mode toggle (source builds only). Switches the shell into dev
        # mode, which reveals the DevKit page in the left nav. Session-only —
        # resets off each launch. Never constructed in a frozen exe, so a
        # shipped build has no way to reach DevKit.
        from techdeck.ui.dev_mode import is_dev_build, get_dev_mode
        if is_dev_build():
            from techdeck.ui.widgets.toggle_switch import ToggleSwitch
            self._dev_label = QLabel("Dev Mode")
            self.dev_switch = ToggleSwitch()
            self.dev_switch.setToolTip(
                "Developer mode (source builds only): reveals the DevKit page "
                "in the sidebar. Resets off each launch.")
            self.dev_switch.toggled.connect(get_dev_mode().set_active)
            profile_layout.addWidget(self._dev_label)
            profile_layout.addWidget(self.dev_switch)
        profile_layout.addWidget(self.btn_add)

        layout.addWidget(self._profile_container)

        # Tile Grid Container (scrollable). Replaces QGridLayout with absolute
        # positioning managed by TileGridController so we can animate per-tile
        # pos for drag-reorder (Phase A.2 of multi-plugin-run UX overhaul).
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._grid_widget = _GridSurface()
        self._scroll.setWidget(self._grid_widget)
        layout.addWidget(self._scroll, 1)

        self._tile_ctrl = TileGridController(self._grid_widget, self.settings, self)
        self._tile_ctrl.set_scroll_area(self._scroll)

        # Empty-state label is a child of the surface (not managed by the controller).
        self._empty_label = QLabel("", self._grid_widget)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.hide()
        self._grid_widget.resized.connect(self._reposition_empty_label)

        # Subscribes to theme_changed and applies immediately.
        self.setup_theme_awareness()

        self.refresh_profiles()

    # ========== Theme handling =====================================

    def apply_theme(self):
        """Re-style every theme-sensitive surface owned by HomePage.

        Tile cards subscribe individually (PluginCard mixes in
        ThemeAware). This method covers the profile bar, scroll area,
        and the run button.
        """
        from techdeck.ui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_palette()
        theme_name = get_theme_manager().get_current_theme()

        self.setStyleSheet(f"HomePage {{ background-color: {theme.background}; }}")

        self._profile_container.setStyleSheet(f"""
            QWidget {{
                background-color: {theme.background};
                border-radius: 0px;
            }}
            QWidget QLabel {{
                background-color: transparent;
            }}
        """)
        self._profile_label.setStyleSheet(
            f"font-size: 14px; color: {theme.text}; background: transparent;"
        )

        icon_folder = "light" if theme_name in ["dark", "blue", "cyberpunk", "matrix"] else "dark"
        icons_dir = Path(__file__).resolve().parents[3] / "assets" / "icons" / icon_folder
        arrow_path = make_tinted_svg_copy(icons_dir / "chevron-down.svg", theme.text)

        self.profile_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {theme.surface};
                color: {theme.text};
                border: 1px solid {theme.border};
                border-radius: 8px;
                padding: 6px 12px;
                padding-right: 30px;
            }}
            QComboBox:hover {{
                background-color: {theme.surface_hover};
                border: 1px solid {theme.border_strong};
            }}
            QComboBox::drop-down {{
                width: 30px;
                border: none;
                background: transparent;
                subcontrol-origin: padding;
                subcontrol-position: center right;
            }}
            QComboBox::down-arrow {{
                image: url("{arrow_path}");
                width: 12px;
                height: 12px;
                background: transparent;
                border: none;
                margin-right: 6px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {theme.surface};
                color: {theme.text};
                border: 1px solid {theme.border_strong};
                border-radius: 8px;
                selection-background-color: {theme.surface_hover};
                padding: 4px;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 8px 12px;
                border-radius: 6px;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {theme.surface_hover};
            }}
        """)

        self.btn_add.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.accent};
                color: {theme.accent_text};
                border: none;
                border-radius: 8px;
                font-weight: 600;
                padding: 6px 16px;
            }}
            QPushButton:hover {{
                background-color: {theme.accent_hover};
            }}
            QPushButton:pressed {{
                background-color: {theme.accent_pressed};
            }}
        """)

        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {theme.background};
                border: none;
            }}
            QScrollBar:vertical {{
                background-color: {theme.surface};
                width: 12px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {theme.border_strong};
                border-radius: 6px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {theme.text_secondary};
            }}
        """)
        self._grid_widget.setStyleSheet(f"background-color: {theme.background};")

        # Missing-tile placeholders bake their colors in, so re-stamp them here
        # (PluginCards re-theme themselves via ThemeAware).
        for tile in self._missing_tiles.values():
            tile.restyle(theme)

        # Run button (shell hands this off to us via set_run_button).
        # Re-style based on its current mode (Run vs Cancel).
        if hasattr(self, "run_btn") and self.run_btn:
            if self._is_running:
                self._set_button_cancel_mode()
            else:
                self._set_button_run_mode()
    
    def refresh_profiles(self):
        profiles = self.settings.get_profile_names()
        current_profile = self.settings.get_current_profile_name()
        
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItems(profiles)
        
        if current_profile in profiles:
            self.profile_combo.setCurrentText(current_profile)
        
        self.profile_combo.blockSignals(False)
        
        self._refresh_tiles()
    
    def _refresh_tiles(self):
        # Tear down any previous widgets the controller was managing.
        self._tile_ctrl.clear()
        for w in list(self._managed_tile_widgets()):
            w.setParent(None)
            w.deleteLater()
        self.tile_cards.clear()
        self._missing_tiles = {}

        tile_ids = self.settings.get_profile_tiles()

        from techdeck.ui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_palette()

        if not tile_ids:
            self._empty_label.setText("No apps in this kit.\n\nClick '+ Apps' to add some!")
            self._empty_label.setStyleSheet(
                f"color: {theme.text_secondary}; font-size: 14px; padding: 40px; "
                f"background: transparent;"
            )
            self._empty_label.show()
            self._reposition_empty_label()
            return

        self._empty_label.hide()

        order: list = []
        widgets: dict = {}
        for tile_id in tile_ids:
            plugin = self.plugin_loader.get_plugin(tile_id)

            if plugin:
                desc = plugin.description
                if len(desc) > 60:
                    desc = desc[:60] + "..."
                card = PluginCard(
                    plugin=plugin,
                    plugin_desc=desc,
                    tile_id=tile_id,
                    theme=theme,
                    parent=self._grid_widget,
                )
                card.toggled.connect(lambda checked, tid=tile_id: self._on_tile_toggled(tid, checked))
                card._can_drag = lambda: not self._is_running
                card.drag_started.connect(self._tile_ctrl.on_drag_started)
                card.drag_moved.connect(self._tile_ctrl.on_drag_moved)
                card.drag_dropped.connect(self._tile_ctrl.on_drag_dropped)
                self.tile_cards[tile_id] = card
                widgets[tile_id] = card
                # Yield to event loop between cards so the splash GIF can advance
                QApplication.processEvents()
            else:
                tile = _MissingTile(
                    tile_id=tile_id,
                    theme=theme,
                    on_remove=self._remove_missing_plugin,
                    parent=self._grid_widget,
                )
                tile._can_drag = lambda: not self._is_running
                tile.drag_started.connect(self._tile_ctrl.on_drag_started)
                tile.drag_moved.connect(self._tile_ctrl.on_drag_moved)
                tile.drag_dropped.connect(self._tile_ctrl.on_drag_dropped)
                self._missing_tiles[tile_id] = tile
                widgets[tile_id] = tile

            order.append(tile_id)

        self._tile_ctrl.set_tiles(order, widgets)

        # Staggered entrance for the live PluginCards (missing tiles stay solid).
        for i, tid in enumerate(tid for tid in order if tid in self.tile_cards):
            self.tile_cards[tid].start_entrance(i * 50)

    def _managed_tile_widgets(self):
        """Generator over both live cards and missing-tile placeholders for cleanup."""
        for w in self.tile_cards.values():
            yield w
        for w in getattr(self, "_missing_tiles", {}).values():
            yield w

    def _reposition_empty_label(self):
        if not self._empty_label.isVisible():
            return
        w = self._grid_widget.width()
        h = self._grid_widget.height()
        lw = min(400, max(200, w - 80))
        # Height from the wrapped content, not a fixed constant — the fixed
        # 120px clipped the message (3 text lines + the QSS padding > 120).
        hfw = self._empty_label.heightForWidth(lw)
        lh = max(150, hfw if hfw > 0 else 0)
        self._empty_label.setGeometry((w - lw) // 2, max(20, (h - lh) // 2), lw, lh)
    
    def _on_tile_toggled(self, tile_id: str, checked: bool):
        if checked:
            self.selected_tiles.add(tile_id)
        else:
            self.selected_tiles.discard(tile_id)

        # Only a genuine user click should click; programmatic restores (e.g.
        # resuming a shelved run, which checks every queued tile) stay silent.
        if not self._restoring:
            from techdeck.core.audio_manager import get_audio_manager, SOUND_CLICK
            get_audio_manager().play(SOUND_CLICK)

        if self._is_running:
            return  # don't disturb button state while plugins are running

        has_selection = len(self.selected_tiles) > 0
        if hasattr(self, 'run_btn') and self.run_btn:
            self.run_btn.setEnabled(has_selection)
        if hasattr(self, '_btn_pulse') and self._btn_pulse:
            self._btn_pulse.stop()
            self._btn_glow.setBlurRadius(0)
            if has_selection:
                self._btn_pulse.start()
    
    def _on_profile_selected(self, profile_name: str):
        if not profile_name:
            return

        from techdeck.core.audio_manager import get_audio_manager, SOUND_CLICK
        get_audio_manager().play(SOUND_CLICK)

        self.settings.set_current_profile(profile_name)
        self.selected_tiles.clear()

        if not self._is_running:
            if hasattr(self, 'run_btn') and self.run_btn:
                self.run_btn.setEnabled(False)
            if hasattr(self, '_btn_pulse') and self._btn_pulse:
                self._btn_pulse.stop()
                self._btn_glow.setBlurRadius(0)

        self._refresh_tiles()
        self.profile_changed.emit(profile_name)
    
    def _on_add_tiles(self):
        self.open_library.emit()
    
    def set_run_button(self, btn: QPushButton):
        """Store reference to Run Selected button and wire up glow animation."""
        self.run_btn = btn
        self.run_btn.setEnabled(False)
        self.run_btn.clicked.connect(self._run_selected_plugins)

        from techdeck.ui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_palette()

        self._btn_glow = QGraphicsDropShadowEffect(self.run_btn)
        self._btn_glow.setBlurRadius(0)
        self._btn_glow.setOffset(0, 0)
        glow_color = QColor(theme.accent)
        glow_color.setAlpha(200)
        self._btn_glow.setColor(glow_color)
        self.run_btn.setGraphicsEffect(self._btn_glow)

        pulse_up = QPropertyAnimation(self._btn_glow, b"blurRadius", self)
        pulse_up.setDuration(600)
        pulse_up.setStartValue(0.0)
        pulse_up.setEndValue(14.0)
        pulse_up.setEasingCurve(QEasingCurve.Type.InOutSine)

        pulse_dn = QPropertyAnimation(self._btn_glow, b"blurRadius", self)
        pulse_dn.setDuration(600)
        pulse_dn.setStartValue(14.0)
        pulse_dn.setEndValue(0.0)
        pulse_dn.setEasingCurve(QEasingCurve.Type.InOutSine)

        self._btn_pulse = QSequentialAnimationGroup(self)
        self._btn_pulse.addAnimation(pulse_up)
        self._btn_pulse.addAnimation(pulse_dn)
        self._btn_pulse.setLoopCount(-1)
    
    def _run_selected_plugins(self):
        """Run selected plugins, or cancel all if already running."""
        if self._is_running:
            # User clicked Cancel — clear queue and abandon any pending shelve.
            self._plugin_queue.clear()
            self._shelve_after_current = False
            self.plugin_executor.cancel_all()
            console = (self._plugin_params or {}).get('console') if hasattr(self, '_plugin_params') else None
            # A plugin blocked at a console prompt never polls cancel_event —
            # abort the input too, or Cancel does nothing until the prompt is
            # answered (bit FormingFinder at its batch prompt, FTOURIGNY-LT).
            if console is not None and getattr(console, 'waiting_for_input', False):
                try:
                    console.abort_input(reason="cancelled")
                except Exception:
                    pass
            # Give immediate feedback — cancellation is cooperative, so the active
            # plugin may take a moment to notice the flag and stop.
            if console is not None:
                console.append_system("Cancelling run — waiting for the current step to stop...")
            # Acknowledge the click on the button itself and swallow further
            # clicks until the run actually reports completion. Without this a
            # double-click's second press could land on the freshly-restored
            # Run Selected button and instantly start a NEW run (FTOURIGNY-LT:
            # run #2 started 32ms after run #1's cancel completed).
            if hasattr(self, 'run_btn') and self.run_btn:
                self.run_btn.setText("Cancelling...")
                self.run_btn.setEnabled(False)
            return  # button resets when the last plugin reports completion

        if not self.selected_tiles:
            return

        # A fresh "Run Selected" overrides any prior paused state — the user
        # is starting a new run, not resuming. Clear paused tile visual too.
        if self._paused:
            if self._paused_tile_id and self._paused_tile_id in self.tile_cards:
                self.tile_cards[self._paused_tile_id].set_status(PluginCard.STATUS_IDLE)
            self._paused = False
            self._paused_tile_id = None
            self._plugin_queue.clear()
            self._shelve_after_current = False

        self.run_selected.emit(list(self.selected_tiles))

        console = None
        parent = self.parent()
        while parent:
            if hasattr(parent, 'console'):
                console = parent.console
                break
            parent = parent.parent()

        from techdeck.core.audio_manager import get_audio_manager, SOUND_SUCCESS
        # Run plugins in the user-controlled order shown on the Home page
        # (left-to-right, top-to-bottom) — not arbitrary set-iteration order.
        ordered = self.settings.get_profile_tiles()
        self._plugin_queue = [tid for tid in ordered if tid in self.selected_tiles]
        # Append any selected tiles that aren't in the saved order (defensive;
        # shouldn't happen, but don't silently drop selections).
        for tid in self.selected_tiles:
            if tid not in self._plugin_queue:
                self._plugin_queue.append(tid)
        # Remember the largest multi-run for the "run N at once" achievements.
        self.settings.record_run_batch(len(self._plugin_queue))
        # Reset family-shared scratch state at the start of every multi-run.
        self._shared_state = {"911": {}, "922": {}, "General": {}}
        self._plugin_params = {
            'console': console,
            # GUI plugins (requires_main_thread) suppress the auto success sound and call
            # this instead at a meaningful action point (e.g. file saved, code generated).
            'on_success': lambda: get_audio_manager().play(SOUND_SUCCESS),
            # Family-aware shared scratch (mutated by SDK helpers — same dict
            # is reused across every plugin in this run).
            'shared_state': self._shared_state,
            # Thread-safe hook called by the executor watchdog when a plugin's
            # input prompt has been idle past INPUT_IDLE_PAUSE_THRESHOLD.
            'on_input_idle': self._input_idle_callback,
        }
        self._set_button_cancel_mode()
        if not self._start_next_plugin():
            # Nothing could start (e.g. every queued plugin failed validation)
            # — unwind immediately so the button doesn't stick on Cancel.
            self._plugins_all_done.emit()

    def _start_next_plugin(self) -> bool:
        """Start the next queued plugin. Returns True if a plugin was started."""
        while self._plugin_queue:
            tile_id = self._plugin_queue.pop(0)
            plugin = self.plugin_executor.plugin_loader.get_plugin(tile_id)
            plugin_timeout = getattr(plugin, "timeout", None) if plugin else None

            self.plugin_status_updated.emit(tile_id, PluginCard.STATUS_RUNNING)

            # Games get their own launch jingle (ASA: The Video Game, etc.).
            if plugin is not None and getattr(plugin, "family", "") == "Games":
                from techdeck.core.audio_manager import get_audio_manager, SOUND_GAME_START
                get_audio_manager().play(SOUND_GAME_START)

            started = self.plugin_executor.execute_plugin(
                tile_id,
                params=self._plugin_params,
                log_callback=lambda msg, tid=tile_id: self._log_buffer.put((tid, msg)),
                progress_callback=lambda prog, tid=tile_id: self.plugin_progress.emit(tid, prog),
                completion_callback=lambda result, tid=tile_id: self._on_plugin_complete(tid, result),
                timeout=plugin_timeout
            )
            if started:
                return True

            # The executor refused to start (e.g. validation failed) and will
            # never fire the completion callback, so unwind here — otherwise
            # the run sticks in Cancel mode with nothing to cancel and the
            # user can't start anything else (bit customer_dxf_quoting when a
            # frozen build was missing a hiddenimport).
            self.plugin_status_updated.emit(tile_id, PluginCard.STATUS_ERROR)
            self.plugin_completed.emit(tile_id)
        return False

    def _remove_missing_plugin(self, tile_id: str):
        """Remove a missing plugin from the current kit and refresh the grid."""
        current_tiles = list(self.settings.get_profile_tiles())
        if tile_id in current_tiles:
            current_tiles.remove(tile_id)
            self.settings.set_profile_tiles(current_tiles)
        self._refresh_tiles()
        # Keep the Library page in sync — it doesn't refresh on navigation, so
        # without this it keeps showing (and re-saving!) the removed tile.
        self.kit_changed.emit()

    def _drain_log_buffer(self):
        """Drain buffered log messages in batches to avoid flooding the Qt event queue."""
        count = 0
        while count < 15:
            try:
                tid, msg = self._log_buffer.get_nowait()
            except _queue.Empty:
                break
            self.plugin_log.emit(tid, msg)
            count += 1

    def _drain_log_buffer_all(self):
        """Drain all buffered log messages immediately (called before showing an input prompt)."""
        while True:
            try:
                tid, msg = self._log_buffer.get_nowait()
            except _queue.Empty:
                break
            self.plugin_log.emit(tid, msg)

    def _apply_plugin_status(self, tile_id: str, status: str):
        """Update a card's status indicator. Always runs on main thread via signal."""
        if tile_id in self.tile_cards:
            self.tile_cards[tile_id].set_status(status)

    def _on_plugin_complete(self, tile_id: str, result: PluginResult):
        """Handle plugin completion. Called from background thread."""
        status = result.status.value if result else PluginCard.STATUS_ERROR
        # Success: return card to idle. Failures persist visually until next run.
        final_status = PluginCard.STATUS_IDLE if status == "success" else status
        self.plugin_status_updated.emit(tile_id, final_status)
        self.plugin_completed.emit(tile_id)

        # Paused: re-queue this tile at the head, halt the run, reset the
        # button — but do NOT start the next plugin. /resume picks up here.
        if status == "paused":
            if not self._plugin_queue or self._plugin_queue[0] != tile_id:
                self._plugin_queue.insert(0, tile_id)
            self._paused = True
            self._paused_tile_id = tile_id
            self._set_button_run_mode()
            # Don't emit _plugins_all_done — the run is parked, not finished.
            return

        # Deferred shelve — Phase D. /shelve was called mid-run; we let the
        # current plugin finish, now save the remaining queue + shared_state.
        if self._shelve_after_current:
            self._shelve_after_current = False
            if self._plugin_queue:
                tiles = list(self._plugin_queue)
                existed = self.settings.get_shelf() is not None
                self._save_shelf(tiles)
                self._plugin_queue.clear()
                prefix = "[SHELF] (Overwriting prior shelf) " if existed else "[SHELF] "
                plural = "s" if len(tiles) != 1 else ""
                self._console_log(
                    f"{prefix}Saved {len(tiles)} plugin{plural}. Type /resume "
                    f"next session to continue."
                )
                self._plugins_all_done.emit()
                return
            self._console_log(
                "[SHELF] Run finished before any plugin remained — nothing to save."
            )

        # Kick off the next plugin; if nothing started, the whole run is done.
        # _plugins_all_done is the ONLY thing that stops the shell's run spinner
        # (see _check_run_complete), so an exception while starting the next
        # plugin must never skip the terminal emit — otherwise the spinner spins
        # forever after the run is effectively over.
        try:
            started_another = self._start_next_plugin()
        except Exception as exc:
            self._console_log(f"[ERROR] Could not start the next plugin: {exc}")
            started_another = False
        if not started_another:
            self._plugins_all_done.emit()

    def _check_run_complete(self):
        """Called on the main thread via queued signal when no more plugins remain."""
        # all_plugins_done is the ONLY thing that stops the shell's run spinner.
        # Restoring the button must never be able to strand the spinner, so emit
        # the completion signal even if _set_button_run_mode raises (a botched
        # refactor once left a NameError there, spinning "Galvanizing..." forever).
        try:
            self._set_button_run_mode()
        finally:
            self.all_plugins_done.emit()

    # ─── Pause / Resume (Phase C) ─────────────────────────────────────

    def _input_idle_callback(self):
        """Thread-safe — fired by the executor watchdog (background thread) when
        the current input prompt has been idle past
        INPUT_IDLE_PAUSE_THRESHOLD. Routes to the GUI thread via signal."""
        self._input_idle_requested.emit()

    def _on_input_idle_requested(self):
        """Main-thread handler for auto-pause."""
        self.pause_run(source="auto-idle")

    def pause_run(self, source: str = "user") -> None:
        """Park the current run at the active input prompt.

        Aborts ``console.request_input`` with reason="paused"; the worker
        raises ``InputAborted("paused")``, the executor marks the result
        ``PluginStatus.PAUSED``, and ``_on_plugin_complete`` re-inserts the
        tile at the head of the queue. ``/resume`` (or resume_run) restarts
        from there.

        ``source``: "user" for an explicit /pause, "auto-idle" for the
        watchdog hitting the idle threshold. Used only for the console
        message — the mechanism is identical.
        """
        if not self._is_running:
            self._console_log("Nothing to pause.")
            return
        console = (self._plugin_params or {}).get('console')
        if console is None or not getattr(console, 'waiting_for_input', False):
            self._console_log(
                "Can only pause while a plugin is waiting for input — try /pause again at the next prompt."
            )
            return
        active = self.plugin_executor.get_active_plugins()
        if not active:
            return  # race: plugin finished between check and now
        tid = active[0]
        self._paused_tile_id = tid
        if source == "auto-idle":
            self._console_log(
                "[AUTO-PAUSE] No response for 60s. Run paused — type /resume to continue."
            )
        else:
            self._console_log("[PAUSED] Run paused — type /resume to continue.")
        console.abort_input(reason="paused")

    def resume_run(self) -> None:
        """Continue a paused run, or load a shelved run from disk.

        Order of preference:
        1. In-memory paused run — pick up the parked plugin.
        2. Else, if the shelf has content and nothing's running, load it.
        3. Else, "Nothing to resume."

        Re-runs the parked/shelved plugin from its start (any pre-input work
        it had done is lost — accepted trade-off per the plan).
        """
        if self._paused and self._plugin_queue:
            self._paused = False
            self._paused_tile_id = None
            next_tile = self._plugin_queue[0]
            plugin = self.plugin_executor.plugin_loader.get_plugin(next_tile)
            name = plugin.name if plugin else next_tile
            self._console_log(f"[RESUMED] Continuing with {name}.")
            self._set_button_cancel_mode()
            if not self._start_next_plugin():
                self._plugins_all_done.emit()
            return
        if self._paused:
            # Paused flag set but queue is empty — clean up the inconsistency.
            self._paused = False
            self._paused_tile_id = None

        # No in-memory paused run; fall back to the disk shelf if present.
        if not self._is_running:
            shelf = self.settings.get_shelf()
            if shelf is not None:
                self._load_shelf_and_run(shelf)
                return

        self._console_log("Nothing to resume.")

    def _console_log(self, msg: str) -> None:
        """Emit a system message to the shared console. Used by pause/resume
        and shelve flows where we don't want to go through plugin_log (which
        is meant for plugin output)."""
        console = (self._plugin_params or {}).get('console')
        if console is None:
            parent = self.parent()
            while parent is not None:
                if hasattr(parent, 'console'):
                    console = parent.console
                    break
                parent = parent.parent()
        if console is not None and hasattr(console, 'append_system'):
            console.append_system(msg)

    # ─── Shelve (Phase D) ─────────────────────────────────────────────

    def shelve_run(self) -> None:
        """Save the rest of the current run to disk so it can be resumed
        across a TechDeck restart. Three cases:

        * **Paused** — snapshot immediately (queue + shared_state), clear
          paused state.
        * **Running** — defer: let the current plugin finish, then snapshot
          the remainder. Acts on the _shelve_after_current flag, consumed
          in _on_plugin_complete.
        * **Idle** — log "Nothing to shelve."
        """
        if self._paused:
            tiles = list(self._plugin_queue)  # already starts with paused tile
            if not tiles:
                self._console_log("Nothing to shelve.")
                return
            existed = self.settings.get_shelf() is not None
            self._save_shelf(tiles)
            self._plugin_queue.clear()
            # Reset paused-tile visual since the run is no longer parked.
            if self._paused_tile_id and self._paused_tile_id in self.tile_cards:
                self.tile_cards[self._paused_tile_id].set_status(PluginCard.STATUS_IDLE)
            self._paused = False
            self._paused_tile_id = None
            prefix = "[SHELF] (Overwriting prior shelf) " if existed else "[SHELF] "
            plural = "s" if len(tiles) != 1 else ""
            self._console_log(
                f"{prefix}Saved {len(tiles)} plugin{plural}. Type /resume next session to continue."
            )
            return
        if self._is_running:
            self._shelve_after_current = True
            self._console_log(
                "[SHELF] Will shelve the remainder after the current plugin finishes."
            )
            return
        self._console_log("Nothing to shelve.")

    def view_shelf(self) -> None:
        """Print the current shelf contents."""
        shelf = self.settings.get_shelf()
        if shelf is None:
            self._console_log("Shelf is empty.")
            return
        tile_ids = shelf.get("remaining_tile_ids", [])
        stored_at = shelf.get("stored_at", "?")
        profile = shelf.get("originating_profile", "?")
        shared = shelf.get("shared_state", {})
        lines = [
            f"[SHELF] {len(tile_ids)} plugin{'s' if len(tile_ids) != 1 else ''} "
            f"(saved {stored_at}, profile '{profile}')"
        ]
        for i, tid in enumerate(tile_ids, 1):
            plugin = self.plugin_loader.get_plugin(tid)
            name = plugin.name if plugin else f"{tid} (missing from disk)"
            lines.append(f"  {i}. {name}")
        captured = [
            (fam, info.get("batch_number"))
            for fam, info in shared.items()
            if isinstance(info, dict) and info.get("batch_number")
        ]
        if captured:
            lines.append("  Captured batch numbers:")
            for fam, bn in captured:
                lines.append(f"    {fam}: {bn}")
        self._console_log("\n".join(lines))

    def clear_shelf(self) -> None:
        """Drop any persisted shelf entry."""
        had_one = self.settings.get_shelf() is not None
        self.settings.clear_shelf()
        if had_one:
            self._console_log("[SHELF] Cleared.")
        else:
            self._console_log("Shelf was already empty.")

    def _save_shelf(self, tile_ids: list) -> None:
        """Persist tile_ids + current shared_state as the single shelf entry."""
        from datetime import datetime, timezone
        entry = {
            "stored_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "remaining_tile_ids": list(tile_ids),
            "shared_state": {
                k: dict(v) for k, v in (self._shared_state or {}).items()
            },
            "originating_profile": self.settings.get_current_profile_name(),
        }
        self.settings.set_shelf(entry)

    def _load_shelf_and_run(self, shelf: dict) -> None:
        """Pull tiles + shared_state out of a shelf entry and start the run.

        Plugins that no longer exist on disk are skipped with a note (the
        installed plugin set can drift between sessions). The shelf entry
        is cleared as soon as we load it — a partially-failed resume would
        otherwise leave a stale entry around forever.
        """
        tile_ids = shelf.get("remaining_tile_ids", [])
        available = [tid for tid in tile_ids if self.plugin_loader.get_plugin(tid)]
        missing = [tid for tid in tile_ids if not self.plugin_loader.get_plugin(tid)]
        if not available:
            self._console_log(
                "Shelved plugins are all missing from disk; cannot resume. "
                "Use /shelf clear to drop the entry."
            )
            return
        if missing:
            self._console_log(
                f"Skipping {len(missing)} shelved plugin(s) missing from disk: "
                f"{', '.join(missing)}"
            )

        self._plugin_queue = available

        # Restore shared_state, but only into the canonical buckets we know
        # about. A future family added between shelve and resume would be
        # ignored — that's fine; worst case the user gets prompted again.
        shared = shelf.get("shared_state", {})
        self._shared_state = {"911": {}, "922": {}, "General": {}}
        for fam, info in shared.items():
            if fam in self._shared_state and isinstance(info, dict):
                self._shared_state[fam].update(info)

        # Reflect the loaded queue in the UI so the user can see what will run.
        # Programmatic — suppress the per-tile click sound (was a rapid-fire burst).
        self._restoring = True
        try:
            for tid in available:
                self.selected_tiles.add(tid)
                if tid in self.tile_cards:
                    self.tile_cards[tid].set_checked(True)
        finally:
            self._restoring = False

        # Find the console for plugin_params.
        console = None
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, 'console'):
                console = parent.console
                break
            parent = parent.parent()

        from techdeck.core.audio_manager import get_audio_manager, SOUND_SUCCESS
        self._plugin_params = {
            'console': console,
            'on_success': lambda: get_audio_manager().play(SOUND_SUCCESS),
            'shared_state': self._shared_state,
            'on_input_idle': self._input_idle_callback,
        }

        # Loaded — consume the shelf entry. If TechDeck crashes mid-run the
        # entry is gone, which is the trade-off we accept for not leaving a
        # stale entry behind forever.
        self.settings.clear_shelf()

        plural = "s" if len(available) != 1 else ""
        self._console_log(
            f"[RESUMED FROM SHELF] Starting {len(available)} plugin{plural} "
            f"(shared state restored)."
        )
        self._set_button_cancel_mode()
        if not self._start_next_plugin():
            self._plugins_all_done.emit()

    def _set_button_cancel_mode(self):
        """Switch the Run Selected button to Cancel (red) while plugins run."""
        from techdeck.ui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_palette()
        self._is_running = True
        if not hasattr(self, 'run_btn') or not self.run_btn:
            return
        self.run_btn.setText("Cancel")
        self.run_btn.setEnabled(True)
        self.run_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.error};
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                font-weight: 600;
                padding: 6px 12px;
            }}
            QPushButton:hover {{
                background-color: {theme.error};
                color: #FFFFFF;
            }}
            QPushButton:pressed {{
                background-color: {theme.error};
                color: #FFFFFF;
            }}
        """)
        if hasattr(self, '_btn_pulse') and self._btn_pulse:
            self._btn_pulse.stop()
        if hasattr(self, '_btn_glow') and self._btn_glow:
            self._btn_glow.setBlurRadius(0)

    def _set_button_run_mode(self):
        """Restore the button to Run Selected (accent) after all plugins finish."""
        from techdeck.ui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_palette()
        self._is_running = False
        if not hasattr(self, 'run_btn') or not self.run_btn:
            return
        self.run_btn.setText("Run Selected")
        # Cooldown before accepting clicks again: a double-clicked Cancel's
        # second press must not land on the restored Run Selected button and
        # start a brand-new run (FTOURIGNY-LT: 32ms between cancel completion
        # and the accidental restart).
        self.run_btn.setEnabled(False)

        def _reenable():
            if (not self._is_running and hasattr(self, 'run_btn')
                    and self.run_btn is not None):
                self.run_btn.setEnabled(len(self.selected_tiles) > 0)
        QTimer.singleShot(400, _reenable)
        self.run_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.accent};
                color: {theme.accent_text};
                border: none;
                border-radius: 6px;
                font-weight: 600;
                padding: 6px 12px;
            }}
            QPushButton:hover {{
                background-color: {theme.accent_hover};
            }}
            QPushButton:pressed {{
                background-color: {theme.accent_pressed};
            }}
            QPushButton:disabled {{
                opacity: 0.5;
            }}
        """)
        if len(self.selected_tiles) > 0 and hasattr(self, '_btn_pulse') and self._btn_pulse:
            self._btn_pulse.start()
