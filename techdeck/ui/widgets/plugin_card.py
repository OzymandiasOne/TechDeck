"""
Home-page tile widgets, extracted from home_page.py.

`PluginCard` is the Home tile (icon + name + family badge, selection/hover/
pulse/entrance/flash animation, and the mouse-drag protocol the grid controller
consumes). `_MissingTile` is the placeholder for a tile whose plugin folder is
gone. `_EyeFollow` drives the cursor-tracking pupils on the `mr_beans` icon.

The tile-geometry constants live here (the Library keeps the compact TILE_*
sizes; Home uses the larger HOME_TILE_* sizes). `home_page.py` and
`library_page.py` import these names back, so they stay the single source.
"""

import math

from PySide6.QtWidgets import (
    QVBoxLayout, QLabel, QPushButton, QFrame, QApplication,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
)
from PySide6.QtCore import (
    Signal, Qt, QPropertyAnimation, QEasingCurve,
    QVariantAnimation, QSequentialAnimationGroup, QTimer, QPoint, QObject,
)
from PySide6.QtGui import QFont, QColor, QCursor

from techdeck.ui.theme_aware import ThemeAware
from techdeck.ui.theme_manager import get_theme_manager
from techdeck.ui.plugin_icon import plugin_icon_pixmap, eye_follow_key, pack_icon_pixmap


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
        # FIXED blur radius — never animated. Animating a shadow's SIZE makes
        # Qt re-rasterize the card into a differently-sized rect every frame;
        # on fractional Windows display scaling the rounding lands on
        # different pixels frame to frame and the tile visibly shivers
        # (reported 2026-09-03, alongside the Run button). Hover lift and the
        # running pulse now animate the shadow's COLOR at constant geometry.
        # (The drag code's one-shot setBlurRadius in tile_grid.py is fine —
        # it's a single change, not a per-frame animation.)
        # Gate: tests/ui/test_no_blur_animations.py.
        self._shadow.setBlurRadius(20)
        self._shadow.setOffset(0, 3)
        self._shadow_base_color = self._parse_shadow_color(theme.shadow)
        self._shadow.setColor(self._shadow_base_color)

        # Hover lift: deepen the shadow colour at constant size.
        self._hover_in = QPropertyAnimation(self._shadow, b"color", self)
        self._hover_in.setDuration(150)
        self._hover_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_in.setEndValue(self._hover_shadow_color())

        self._hover_out = QPropertyAnimation(self._shadow, b"color", self)
        self._hover_out.setDuration(200)
        self._hover_out.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_out.setEndValue(self._shadow_base_color)

        # Running pulse (accent glow breathes by alpha; values are set fresh
        # from the active theme each time _start_pulse runs).
        self._pulse_up = QPropertyAnimation(self._shadow, b"color", self)
        self._pulse_up.setDuration(700)
        self._pulse_up.setEasingCurve(QEasingCurve.Type.InOutSine)

        self._pulse_dn = QPropertyAnimation(self._shadow, b"color", self)
        self._pulse_dn.setDuration(700)
        self._pulse_dn.setEasingCurve(QEasingCurve.Type.InOutSine)

        self._pulse_group = QSequentialAnimationGroup(self)
        self._pulse_group.addAnimation(self._pulse_up)
        self._pulse_group.addAnimation(self._pulse_dn)
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

    def _hover_shadow_color(self) -> QColor:
        """The hover-lift shadow: the base shadow at double strength (the old
        blur-8→20 'lift', expressed as colour so the geometry never changes)."""
        c = QColor(self._shadow_base_color)
        c.setAlpha(min(255, c.alpha() * 2))
        return c

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
        # The hover animations bake colours in as end values — refresh them so
        # a theme change doesn't leave the tile lifting to the old theme's shadow.
        self._hover_in.setEndValue(self._hover_shadow_color())
        self._hover_out.setEndValue(self._shadow_base_color)
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
            hi = QColor(self.theme.accent)
            hi.setAlpha(160)
            lo = QColor(self.theme.accent)
            lo.setAlpha(50)
            self._pulse_up.setStartValue(lo)
            self._pulse_up.setEndValue(hi)
            self._pulse_dn.setStartValue(hi)
            self._pulse_dn.setEndValue(lo)
            self._shadow.setColor(hi)
            self._pulse_group.start()

    def _stop_pulse(self):
        self._pulse_group.stop()
        if self.graphicsEffect() is self._shadow:
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
            self._hover_in.setStartValue(self._shadow.color())
            self._hover_in.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if (self.graphicsEffect() is self._shadow
                and self._status != self.STATUS_RUNNING
                and not self._dragging):
            self._hover_in.stop()
            self._hover_out.setStartValue(self._shadow.color())
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
