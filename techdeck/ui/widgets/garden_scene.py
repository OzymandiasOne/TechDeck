"""
My House — the Garden scene.

A recreation of UFO 50's "The Garden" pet/home screen, built entirely from the
ripped sprites vendored under assets/garden/ (sPet_* PNGs). The player's house +
yard; clicking the house "pulls away" the front facade to reveal the cutaway
interior, which the player slowly furnishes with items bought at Woogy's.

Rendering model
---------------
The original runs on a fixed 384x216 pixel canvas, so we compose every layer at
that NATIVE resolution into a small buffer, then blit the buffer once, scaled by
an INTEGER factor with nearest-neighbour (no smoothing) so it stays pixel-crisp
at any window size. Letterboxed + centred in whatever space the tab gives us.

Layers (back -> front):
    BG_0            yard + EMPTY house interior (floors/rooms/stairs baked in)
    tree            6-frame idle sway, standing in the left yard
    furniture       data-driven sprites placed into the interior rooms
    HouseFG_0       the closed front facade; lifts up + fades on "open"

Furniture placement is a plain data table (FURNITURE) in native pixel coords —
first-pass estimates, easy to nudge. Later this becomes owned-item driven (buy a
couch at Woogy's -> it appears in a room here).
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Qt, QRect, QTimer, QPoint
from PySide6.QtGui import QPainter, QPixmap, QColor, QPolygon

from techdeck.ui.sprite_font import font as _sf


# Native UFO50 canvas the whole scene is authored against.
NATIVE_W, NATIVE_H = 384, 216

# House facade bounding box in native coords (the clickable "front" — the right
# portion of the canvas; the left half is transparent yard). Used for hit-test.
HOUSE_RECT = QRect(184, 6, 200, 204)

# How far (native px) the facade lifts when opened — fully off the top edge.
FACADE_LIFT = 216

# Tree stands in the left yard; its base rests near the fence line. The 6 tree
# sprites are a GROWTH sequence (0 = unplanted/empty, 5 = full grown), not a sway
# loop — so we draw a single stage. Default to full grown; later this stage can
# track house progression so the tree visibly grows as the player invests.
TREE_POS = (16, 7)
TREE_STAGE_FULL = 5

# Where each owned furniture item sits in the house, keyed by its Emporium
# catalog id -> (native_x, native_y) top-left. Bought items appear at their spot;
# unowned ones are absent. First-pass coords (floors: attic ~y70, upper ~y86,
# middle ~y124, ground ~y160) — tune visually.
PLACEMENT = {
    # Attic
    "deco_trophy":    (288, 54),
    "deco_telescope": (312, 40),
    # Upper floor — bathroom (left), bedroom (right)
    "deco_toilet":    (220, 54),
    "deco_tub":       (242, 54),
    "deco_bed":       (300, 54),
    "deco_lamp":      (340, 54),
    "deco_mirror":    (320, 54),
    # Middle floor — study (left), living (right)
    "deco_books":     (220, 92),
    "deco_desk":      (248, 92),
    "deco_painting":  (224, 96),
    "deco_phone":     (276, 92),
    "deco_tv":        (326, 100),
    # Ground floor — kitchen (left), den (right)
    "deco_fridge":    (222, 128),
    "deco_stove":     (246, 128),
    "deco_couch":     (300, 144),
    "deco_rug":       (308, 128),
    "deco_plant":     (342, 128),
    "deco_hatrack":   (330, 136),
    "deco_guitar":    (350, 144),
    # Yard
    "deco_hottub":    (120, 179),
}

_TICK_MS = 16


def _garden_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets" / "garden"
    return Path(__file__).resolve().parents[3] / "assets" / "garden"


def _ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


class GardenScene(QWidget):
    """The clickable house/yard scene. Click the house to open/close the front."""

    def __init__(self, settings=None, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(NATIVE_W, NATIVE_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        d = _garden_dir()
        self._bg = self._load(d / "sPet_BG_0.png")
        self._facade = self._load(d / "sPet_HouseFG_0.png")
        # Background-switcher arrow sprites (white = best contrast on the dark
        # pill), pre-scaled crisp. Fall back to drawn triangles if missing.
        self._arrow_l = self._scaled_arrow(self._load(d / "ui_arrow_left.png"))
        self._arrow_r = self._scaled_arrow(self._load(d / "ui_arrow_right.png"))
        # The wallpaper behind the floating yard/house island (shows through BG_0's
        # transparent corners). Equippable; defaults to sLibraryBG_4.
        self._bg_name = None
        self._background = None
        self._bg_scaled = None        # cache: wallpaper pre-scaled to the blit factor
        self._bg_scaled_key = None
        self._name_pm = None          # current background's name, sprite-font pixmap
        # Friendly names for the background switcher (default + catalog backgrounds).
        from techdeck.ui.pages.emporium_page import CATALOG
        self._bg_names = {"sLibraryBG_4.png": "Red Check"}
        for c in CATALOG:
            if c.get("kind") == "background":
                self._bg_names[c["sprite"]] = c["name"]
        # Fixed name-slot width (widest name) so the arrows stay locked in place
        # regardless of the current background's name length.
        self._name_slot_w = max(
            (_sf().render(n.upper(), 3, "#ffffff").width()
             for n in self._bg_names.values()), default=80)
        self._load_background()
        self._tree = [self._load(d / f"sPet_Tree_{i}.png") for i in range(6)]
        self._tree_stage = TREE_STAGE_FULL
        self._furniture = []
        self._load_furniture()

        # Reveal state: progress 0 = closed, 1 = fully open; animates toward target.
        self._open_progress = 0.0
        self._open_target = 0.0

        # Cached blit geometry (filled each paint) so mouse hit-test can map
        # widget coords back to native coords.
        self._scale = 1
        self._origin = QPoint(0, 0)

        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)

    # ---- assets --------------------------------------------------------------
    @staticmethod
    def _load(path: Path):
        pm = QPixmap(str(path))
        return None if pm.isNull() else pm

    @staticmethod
    def _scaled_arrow(pm):
        """Integer-scale a tiny arrow sprite up to ~22px tall, crisp."""
        if pm is None:
            return None
        scale = max(1, round(22 / pm.height()))
        return pm.scaled(pm.width() * scale, pm.height() * scale,
                         Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.FastTransformation)

    def _load_background(self) -> bool:
        """(Re)load the equipped wallpaper. Returns True if it changed."""
        name = "sLibraryBG_4.png"
        if self.settings is not None and hasattr(self.settings, "get_equipped_background"):
            name = self.settings.get_equipped_background()
        if name == self._bg_name:
            return False
        self._bg_name = name
        self._background = self._load(_garden_dir() / name)
        self._name_pm = _sf().render(self._bg_names.get(name, "?").upper(), 3, "#ffffff")
        return True

    # ---- background switcher -------------------------------------------------
    def _owned_backgrounds(self):
        """Sprite filenames of the backgrounds the player can switch between:
        the free default plus any bought at Woogy's."""
        from techdeck.ui.pages.emporium_page import CATALOG
        owned = ["sLibraryBG_4.png"]
        if self.settings is not None:
            for c in CATALOG:
                if (c.get("kind") == "background"
                        and self.settings.is_unlocked(c["id"])):
                    owned.append(c["sprite"])
        return owned

    def _switch_bg(self, delta):
        owned = self._owned_backgrounds()
        if len(owned) <= 1:
            return
        cur = self._bg_name if self._bg_name in owned else owned[0]
        nxt = owned[(owned.index(cur) + delta) % len(owned)]
        if self.settings is not None and hasattr(self.settings, "set_equipped_background"):
            self.settings.set_equipped_background(nxt)
        self._load_background()
        self.update()

    def _switcher_layout(self):
        """Rects for the top background switcher (◀ name ▶), or None when the
        player owns only the default (nothing to switch between)."""
        if self._name_pm is None or len(self._owned_backgrounds()) <= 1:
            return None
        aw = ah = 34
        gap = 12
        slot = self._name_slot_w          # fixed -> arrows never move
        total = aw + gap + slot + gap + aw
        x0 = (self.width() - total) // 2
        y = 14
        left = QRect(x0, y, aw, ah)
        slot_x = x0 + aw + gap
        right = QRect(slot_x + slot + gap, y, aw, ah)
        pill = QRect(x0 - 12, y - 6, total + 24, ah + 12)
        # Name centred within its fixed slot.
        name_x = slot_x + (slot - self._name_pm.width()) // 2
        return left, right, name_x, y, ah, pill

    # ---- lifecycle (only animate while the tab is visible) -------------------
    def showEvent(self, e):
        super().showEvent(e)
        self.update()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._timer.stop()

    # ---- animation -----------------------------------------------------------
    def _tick(self):
        # Ease the facade toward its target a step at a time; stop the timer once
        # it settles so a static scene doesn't repaint at 60fps.
        if abs(self._open_progress - self._open_target) <= 0.001:
            self._open_progress = self._open_target
            self._timer.stop()
            return
        step = 0.06
        if self._open_progress < self._open_target:
            self._open_progress = min(self._open_target, self._open_progress + step)
        else:
            self._open_progress = max(self._open_target, self._open_progress - step)
        self.update()

    def toggle_house(self):
        self._open_target = 0.0 if self._open_target > 0.5 else 1.0
        if not self._timer.isActive():
            self._timer.start()

    # ---- input ---------------------------------------------------------------
    def mousePressEvent(self, e):
        pos = e.position().toPoint()
        # Background switcher arrows take priority over the house toggle.
        sw = self._switcher_layout()
        if sw is not None:
            left, right = sw[0], sw[1]
            if left.contains(pos):
                self._switch_bg(-1)
                return
            if right.contains(pos):
                self._switch_bg(+1)
                return
        # Map the click back into native coords and toggle if it hit the house.
        if self._scale > 0:
            nx = (e.position().x() - self._origin.x()) / self._scale
            ny = (e.position().y() - self._origin.y()) / self._scale
            if HOUSE_RECT.contains(int(nx), int(ny)) or self._open_target > 0.5:
                self.toggle_house()
        super().mousePressEvent(e)

    # ---- rendering -----------------------------------------------------------
    def _compose_native(self) -> QPixmap:
        """Draw every layer at native 384x216 into one buffer."""
        # Transparent base: the island's see-through corners let the tiled
        # wallpaper (painted across the whole widget in paintEvent) show through.
        buf = QPixmap(NATIVE_W, NATIVE_H)
        buf.fill(Qt.GlobalColor.transparent)
        p = QPainter(buf)
        if self._bg is not None:
            p.drawPixmap(0, 0, self._bg)
        if 0 <= self._tree_stage < len(self._tree) and self._tree[self._tree_stage]:
            p.drawPixmap(TREE_POS[0], TREE_POS[1], self._tree[self._tree_stage])
        for pm, x, y in self._furniture:
            if pm is not None:
                p.drawPixmap(x, y, pm)
        if self._facade is not None:
            eased = _ease_out_cubic(self._open_progress)
            if eased < 1.0:
                p.setOpacity(1.0 - eased)
                p.drawPixmap(0, -int(FACADE_LIFT * eased), self._facade)
                p.setOpacity(1.0)
        p.end()
        return buf

    def _scaled_background(self, scale):
        """Wallpaper pre-scaled by the blit factor (nearest-neighbour), cached.
        Used as the repeating tile that fills the whole window."""
        if self._background is None:
            return None
        key = (self._bg_name, scale)
        if self._bg_scaled_key != key:
            self._bg_scaled = self._background.scaled(
                self._background.width() * scale, self._background.height() * scale,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.FastTransformation)
            self._bg_scaled_key = key
        return self._bg_scaled

    def paintEvent(self, _e):
        p = QPainter(self)
        # Largest integer scale that fits, centred.
        self._scale = max(1, min(self.width() // NATIVE_W, self.height() // NATIVE_H))
        dw, dh = NATIVE_W * self._scale, NATIVE_H * self._scale
        self._origin = QPoint((self.width() - dw) // 2, (self.height() - dh) // 2)
        # Pixel-perfect: no smoothing.
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        # Tile the wallpaper across the ENTIRE window (it repeats behind the
        # diorama and shows through the island's transparent corners), aligned so
        # a tile boundary lands on the diorama origin.
        tile = self._scaled_background(self._scale)
        if tile is not None and tile.width() > 0 and tile.height() > 0:
            sx = (-self._origin.x()) % tile.width()
            sy = (-self._origin.y()) % tile.height()
            p.drawTiledPixmap(self.rect(), tile, QPoint(sx, sy))
        else:
            p.fillRect(self.rect(), QColor("#12121c"))
        p.drawPixmap(QRect(self._origin.x(), self._origin.y(), dw, dh),
                     self._compose_native())
        self._draw_switcher(p)
        p.end()

    def _draw_switcher(self, p):
        sw = self._switcher_layout()
        if sw is None:
            return
        left, right, name_x, y, ah, pill = sw
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 160))
        p.drawRoundedRect(pill, 9, 9)
        self._draw_arrow(p, left, self._arrow_l, -1)
        self._draw_arrow(p, right, self._arrow_r, +1)
        p.drawPixmap(name_x, y + (ah - self._name_pm.height()) // 2, self._name_pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    def _draw_arrow(self, p, rect, pm, d):
        """Draw the arrow sprite centred in its button (triangle fallback)."""
        if pm is not None:
            p.drawPixmap(rect.center().x() - pm.width() // 2,
                         rect.center().y() - pm.height() // 2, pm)
        else:
            self._draw_tri(p, rect, d)

    @staticmethod
    def _draw_tri(p, rect, d):
        cx, cy = rect.center().x(), rect.center().y()
        s = 8
        if d < 0:   # left-pointing
            pts = [QPoint(cx + 4, cy - s), QPoint(cx + 4, cy + s), QPoint(cx - 5, cy)]
        else:       # right-pointing
            pts = [QPoint(cx - 4, cy - s), QPoint(cx - 4, cy + s), QPoint(cx + 5, cy)]
        p.setBrush(QColor("#ffffff"))
        p.drawPolygon(QPolygon(pts))

    def _load_furniture(self):
        """Build the list of placed furniture from the items the player owns."""
        from techdeck.ui.pages.emporium_page import CATALOG
        by_id = {c["id"]: c for c in CATALOG}
        items = []
        for item_id, (x, y) in PLACEMENT.items():
            c = by_id.get(item_id)
            if c is None or self.settings is None:
                continue
            if not self.settings.is_unlocked(item_id):
                continue
            pm = self._load(_garden_dir() / c["sprite"])
            if pm is not None:
                items.append((pm, x, y))
        self._furniture = items

    def refresh(self):
        """Re-read the equipped wallpaper + owned furniture (both can change)."""
        self._load_background()
        self._load_furniture()
        self.update()
