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

import math
import random
import sys
from pathlib import Path

from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Qt, QRect, QTimer, QPoint
from PySide6.QtGui import QPainter, QPixmap, QColor, QPolygon

from techdeck.ui.sprite_font import font as _sf


# Native UFO50 canvas the whole scene is authored against.
NATIVE_W, NATIVE_H = 384, 216

# The diorama (land + house + sun/moon) is drawn this much larger than the integer
# wallpaper scale, to fill more of the window. The wallpaper tiling is unaffected.
DIORAMA_ZOOM = 1.12

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

# Per-stage tree placement (native top-left), so every growth stage shares the
# same root point as it grows in place. Seeded by aligning each sprite's base;
# fine-tune in the placer's Tree view.
TREE_PLACEMENT = {1: (26, -12), 2: (30, -13), 3: (28, -6), 4: (28, -7), 5: (26, -8)}

# Backgrounds that read as night — the moon shows instead of the sun.
NIGHT_BACKGROUNDS = {"sLibraryBG_7.png"}   # Starry Night

# Where each owned furniture item sits in the house, keyed by its Emporium
# catalog id -> (native_x, native_y) top-left. Bought items appear at their spot;
# unowned ones are absent. First-pass coords (floors: attic ~y70, upper ~y86,
# middle ~y124, ground ~y160) — tune visually.
PLACEMENT = {
    # Native (x,y) top-left per item, dialed in with tools/furniture_placer.py.
    # --- Interior (drawn behind the facade; revealed when the house opens) ---
    "deco_trophy":    (240, 24),
    "deco_chest":     (209, 16),
    "deco_boxes":     (288, 32),
    "deco_cobweb":    (288, 16),
    "deco_trapdoor":  (256, 16),
    "deco_toilet":    (192, 48),
    "deco_tub":       (225, 48),
    "deco_bed":       (257, 47),
    "deco_lamp":      (288, 48),
    "deco_mirror":    (304, 48),
    "deco_telescope": (320, 48),
    "deco_bike":      (225, 24),
    "deco_phone":     (191, 95),
    "deco_desk":      (224, 96),
    "deco_computer":  (256, 96),
    "deco_calendar":  (208, 80),
    "deco_tv":        (288, 96),
    "deco_guitar":    (320, 96),
    "deco_fridge":    (209, 128),
    "deco_stove":     (224, 128),
    "deco_blender":   (224, 128),
    "deco_painting":  (257, 128),
    "deco_books":     (288, 128),
    "deco_plant":     (305, 128),
    "deco_couch":     (256, 144),
    "deco_rug":       (256, 144),
    "deco_hatrack":   (320, 136),
    # --- Exterior (drawn in FRONT of the facade; always visible — yard/roof) ---
    "deco_satellite": (312, 10),
    "deco_bird":      (286, 11),
    "deco_butterfly": (176, 170),
    "deco_flower":    (32, 129),
    "deco_cattails":  (0, 160),
    "deco_watercan":  (200, 163),
    "deco_picnic":    (63, 166),
    "deco_hottub":    (145, 174),
    "deco_gardenplot": (320, 176),
    "deco_lilypad":   (16, 176),
    "deco_jumprope":  (227, 179),
    "deco_anthill":   (256, 192),
    "deco_easel":     (42, 148),
    "deco_sun":       (10, 8),
    "deco_moon":      (9, 8),
    "deco_owl":       (50, 16),
    "deco_monkey":    (34, 86),
}

# Items that live OUTSIDE the house: drawn in front of the facade (so they show
# on the closed house too) and placed in the placer's exterior view, often
# relative to the tree/hedge/roof.
EXTERIOR = {
    "deco_satellite", "deco_bird", "deco_butterfly", "deco_flower", "deco_cattails",
    "deco_watercan", "deco_picnic", "deco_hottub", "deco_gardenplot", "deco_lilypad",
    "deco_jumprope", "deco_anthill", "deco_easel", "deco_sun", "deco_moon",
    "deco_owl", "deco_monkey",
}

# Items whose multi-frame sprite loops as a slow ambient animation (timer-driven).
AMBIENT_ANIM = {
    "deco_sun", "deco_owl", "deco_monkey", "deco_anthill", "deco_lilypad",
}

# Items handled as moving "agents" (their own behaviour, not static placement).
AGENTS = {"deco_bird", "deco_butterfly"}

# Items mounted on the front wall / roof — they lift away with the facade and the
# bird perches on it, so they move (and fade) with the facade when the house opens.
FACADE_ATTACHED = {"deco_satellite"}   # the bird agent is handled separately

# Agent behaviour tuning.
AGENT_MS = 60                 # update tick (frame-rate independent via dt)
BIRD_SPEED = 55               # px/s in flight
BIRD_PERCH = (12.0, 35.0)     # seconds perched before flying off
BIRD_GONE = (5.0, 14.0)       # seconds off-screen before returning

# Buddy the pig — always present, wanders the front yard. sPet_Buddy_* is a
# 4-direction walk cycle (0-3 back, 4-7 front, 8-11 left, 12-15 right).
BUDDY_SPEED = 22              # px/s walk
BUDDY_WALK_MS = 150           # ms per walk frame
BUDDY_X, BUDDY_Y = (135, 300), (170, 182)   # yard ground Buddy roams
BUDDY_PAUSE = (1.5, 5.0)      # seconds idle between strolls
BUDDY_WALK_LEFT = (8, 9, 10, 11)
BUDDY_WALK_RIGHT = (12, 13, 14, 15)
BUDDY_IDLE = 4                # front-facing standing frame

_TICK_MS = 16
_ANIM_MS = 360   # ambient animation frame rate (matches the gallery 3x speed)


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
        self._tree_stage = self._tree_stage_from_settings()
        self._furniture = []          # interior — behind the facade
        self._furniture_ext = []      # exterior — in front of the facade
        self._load_furniture()
        self._bird = None             # moving agents
        self._butterfly = None
        self._buddy = None            # the pig
        self._load_agents()

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
        self._anim_timer = QTimer(self)          # ambient item animations
        self._anim_timer.setInterval(_ANIM_MS)
        self._anim_timer.timeout.connect(self._anim_tick)
        self._agent_timer = QTimer(self)         # moving agents (bird/butterfly)
        self._agent_timer.setInterval(AGENT_MS)
        self._agent_timer.timeout.connect(self._agent_tick)

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
        self._load_furniture()   # day/night swap (sun <-> moon) tracks the bg
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
        self._anim_timer.start()
        self._agent_timer.start()
        self.update()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._timer.stop()
        self._anim_timer.stop()
        self._agent_timer.stop()

    def _anim_tick(self):
        changed = False
        for rec in (*self._furniture, *self._furniture_ext):
            if rec["anim"]:
                rec["idx"] = (rec["idx"] + 1) % len(rec["frames"])
                changed = True
        if changed:
            self.update()

    # ---- animation -----------------------------------------------------------
    def _tick(self):
        # Ease the facade toward its target a step at a time; stop the timer once
        # it settles so a static scene doesn't repaint at 60fps.
        if abs(self._open_progress - self._open_target) <= 0.001:
            self._open_progress = self._open_target
            self._timer.stop()
            return
        # Slow reveal on click so the exterior front lingers. (The pig walking
        # through the door later will use a faster step ~0.06.)
        step = 0.025
        if self._open_progress < self._open_target:
            self._open_progress = min(self._open_target, self._open_progress + step)
        else:
            self._open_progress = max(self._open_target, self._open_progress - step)
        self.update()

    def toggle_house(self):
        opening = self._open_target <= 0.5
        self._open_target = 1.0 if opening else 0.0
        from techdeck.core.audio_manager import (
            get_audio_manager, SOUND_PET_DOOR_OPEN, SOUND_PET_DOOR_CLOSE)
        get_audio_manager().play(SOUND_PET_DOOR_OPEN if opening else SOUND_PET_DOOR_CLOSE)
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
        st = self._tree_stage
        if 1 <= st < len(self._tree) and self._tree[st] is not None:
            tx, ty = TREE_PLACEMENT.get(st, TREE_POS)
            p.drawPixmap(tx, ty, self._tree[st])
        for rec in self._furniture:            # interior — behind the facade
            p.drawPixmap(rec["x"], rec["y"], rec["frames"][rec["idx"]])
        # The facade and anything mounted on it (satellite, perched bird) lift up
        # and fade together when the house opens.
        eased = _ease_out_cubic(self._open_progress)
        facade_dy = -int(FACADE_LIFT * eased)
        facade_op = 1.0 - eased
        if self._facade is not None and facade_op > 0.0:
            p.setOpacity(facade_op)
            p.drawPixmap(0, facade_dy, self._facade)
            p.setOpacity(1.0)
        for rec in self._furniture_ext:        # exterior — in front
            if rec["id"] in FACADE_ATTACHED:
                if facade_op > 0.0:
                    p.setOpacity(facade_op)
                    p.drawPixmap(rec["x"], rec["y"] + facade_dy, rec["frames"][rec["idx"]])
                    p.setOpacity(1.0)
            else:
                p.drawPixmap(rec["x"], rec["y"], rec["frames"][rec["idx"]])
        if self._buddy is not None:            # the pig strolls the yard
            bu = self._buddy
            if bu["state"] == "walk":
                seq = BUDDY_WALK_LEFT if bu["facing"] == "left" else BUDDY_WALK_RIGHT
                frame = bu["frames"][seq[bu["fidx"]]]
            else:
                frame = bu["frames"][BUDDY_IDLE]
            p.drawPixmap(int(bu["x"]), int(bu["y"]), frame)
        if self._butterfly is not None:        # butterfly stays on the lawn
            b = self._butterfly
            p.drawPixmap(int(b["x"]), int(b["y"]), b["frames"][b["idx"]])
        if self._bird is not None and facade_op > 0.0:   # perches on the roof -> lifts with it
            bd = self._bird
            frame = bd["perch"] if bd["state"] == "perch" else bd["fly"][bd["fidx"]]
            p.setOpacity(facade_op)
            p.drawPixmap(int(bd["x"]), int(bd["y"]) + facade_dy, frame)
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
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        # Wallpaper tiles at the integer fit (crisp + unchanged); the diorama is
        # blitted DIORAMA_ZOOM larger over it, centred.
        wscale = max(1, min(self.width() // NATIVE_W, self.height() // NATIVE_H))
        self._scale = wscale * DIORAMA_ZOOM            # diorama scale (for hit-test)
        dw, dh = int(NATIVE_W * self._scale), int(NATIVE_H * self._scale)
        self._origin = QPoint((self.width() - dw) // 2, (self.height() - dh) // 2)
        tile = self._scaled_background(wscale)
        if tile is not None and tile.width() > 0 and tile.height() > 0:
            p.drawTiledPixmap(self.rect(), tile)
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

    def _load_frames(self, sprite):
        """Load an item's whole frame sequence (sPet_X_0.png, _1, _2, ...)."""
        d = _garden_dir()
        if sprite.endswith("_0.png"):
            base = sprite[:-len("_0.png")]
            frames, i = [], 0
            while True:
                pm = self._load(d / f"{base}_{i}.png")
                if pm is None:
                    break
                frames.append(pm)
                i += 1
            if frames:
                return frames
        pm = self._load(d / sprite)
        return [pm] if pm is not None else []

    def _load_furniture(self):
        """Build the placed-furniture lists (interior + exterior) from the items
        the player owns. Each record is {frames, x, y, anim, idx}."""
        from techdeck.ui.pages.emporium_page import CATALOG
        by_id = {c["id"]: c for c in CATALOG}
        night = (self.settings is not None
                 and hasattr(self.settings, "get_equipped_background")
                 and self.settings.get_equipped_background() in NIGHT_BACKGROUNDS)
        interior, exterior = [], []
        for item_id, (x, y) in PLACEMENT.items():
            if item_id in AGENTS:        # bird/butterfly handled as moving agents
                continue
            c = by_id.get(item_id)
            if c is None or self.settings is None or not self.settings.is_unlocked(item_id):
                continue
            # Day/night: the moon replaces the sun on starry backgrounds.
            if (item_id == "deco_sun" and night) or (item_id == "deco_moon" and not night):
                continue
            anim = item_id in AMBIENT_ANIM
            if anim:
                frames = self._load_frames(c["sprite"])
            else:
                pm = self._load(_garden_dir() / c["sprite"])
                frames = [pm] if pm is not None else []
            if not frames:
                continue
            rec = {"id": item_id, "frames": frames, "x": x, "y": y,
                   "anim": anim and len(frames) > 1, "idx": 0}
            (exterior if item_id in EXTERIOR else interior).append(rec)
        self._furniture = interior
        self._furniture_ext = exterior

    # ---- moving agents (bird + butterfly) ------------------------------------
    def _owned(self, item_id):
        return self.settings is not None and self.settings.is_unlocked(item_id)

    def _load_agents(self):
        """Set up the moving agents: Buddy the pig (always), plus the bird +
        butterfly if owned."""
        d = _garden_dir()
        self._butterfly = None
        self._bird = None
        frames = [self._load(d / f"sPet_Buddy_{i}.png") for i in range(16)]
        if all(f is not None for f in frames):
            bx, by = random.uniform(*BUDDY_X), random.uniform(*BUDDY_Y)
            self._buddy = {"x": bx, "y": by, "tx": bx, "ty": by, "frames": frames,
                           "state": "idle", "facing": "right", "fidx": 0, "wt": 0.0,
                           "t": random.uniform(*BUDDY_PAUSE)}
        else:
            self._buddy = None
        if self._owned("deco_butterfly") and "deco_butterfly" in PLACEMENT:
            x, y = PLACEMENT["deco_butterfly"]
            frames = [self._load(d / f"sPet_ItemButterfly_{i}.png") for i in range(2)]
            frames = [f for f in frames if f is not None]
            if frames:
                self._butterfly = {"x": float(x), "y": float(y), "frames": frames,
                                   "idx": 0, "flutter": 0.6}
        if self._owned("deco_bird") and "deco_bird" in PLACEMENT:
            x, y = PLACEMENT["deco_bird"]
            perch = self._load(d / "sPet_ItemBird_0.png")
            fly = [self._load(d / f"sPet_ItemBirdFly_{i}.png") for i in range(2)]
            fly = [f for f in fly if f is not None]
            if perch is not None and fly:
                self._bird = {"x": float(x), "y": float(y), "hx": float(x),
                              "hy": float(y), "tx": float(x), "ty": float(y),
                              "perch": perch, "fly": fly, "fidx": 0, "state": "perch",
                              "t": random.uniform(*BIRD_PERCH), "flap": 0.12}

    def _agent_tick(self):
        moved = False
        if self._butterfly is not None:
            self._update_butterfly(AGENT_MS / 1000.0)
            moved = True
        if self._bird is not None:
            self._update_bird(AGENT_MS / 1000.0)
            moved = True
        if self._buddy is not None:
            self._update_buddy(AGENT_MS / 1000.0)
            moved = True
        if moved:
            self.update()

    def _update_butterfly(self, dt):
        # Sits in one place: mostly wings DOWN (frame 0), opening up (frame 1) now
        # and then for a brief flutter, always settling back down.
        b = self._butterfly
        b["flutter"] -= dt
        if b["flutter"] <= 0:
            if b["idx"] == 0:         # down -> flutter up briefly
                b["idx"], b["flutter"] = 1, random.uniform(0.10, 0.25)
            else:                     # up -> settle back down, sit a while
                b["idx"], b["flutter"] = 0, random.uniform(1.5, 4.0)

    def _update_bird(self, dt):
        bd = self._bird
        bd["t"] -= dt
        st = bd["state"]
        if st == "perch":
            if bd["t"] <= 0:         # take off, up and away
                bd["state"] = "away"
                bd["tx"] = bd["x"] + random.uniform(-30, 30)
                bd["ty"] = -24.0
            return
        if st == "gone":
            if bd["t"] <= 0:         # re-enter from the top, head home
                bd["state"] = "return"
                bd["x"] = bd["hx"] + random.uniform(-30, 30)
                bd["y"] = -24.0
            return
        # away / return: move toward the target, wings flapping
        tx, ty = (bd["tx"], bd["ty"]) if st == "away" else (bd["hx"], bd["hy"])
        dx, dy = tx - bd["x"], ty - bd["y"]
        dist = math.hypot(dx, dy)
        step = BIRD_SPEED * dt
        if dist <= step:
            bd["x"], bd["y"] = tx, ty
            if st == "away":
                bd["state"], bd["t"] = "gone", random.uniform(*BIRD_GONE)
            else:
                bd["state"], bd["t"] = "perch", random.uniform(*BIRD_PERCH)
        else:
            bd["x"] += dx / dist * step
            bd["y"] += dy / dist * step
        bd["flap"] -= dt
        if bd["flap"] <= 0:
            bd["fidx"] ^= 1
            bd["flap"] = 0.12

    def _update_buddy(self, dt):
        bu = self._buddy
        bu["t"] -= dt
        if bu["state"] == "idle":
            if bu["t"] <= 0:                    # pick a new spot and stroll there
                bu["tx"] = random.uniform(*BUDDY_X)
                bu["ty"] = random.uniform(*BUDDY_Y)
                bu["state"], bu["fidx"], bu["wt"] = "walk", 0, 0.0
        else:                                  # walking toward the target
            dx, dy = bu["tx"] - bu["x"], bu["ty"] - bu["y"]
            dist = math.hypot(dx, dy)
            step = BUDDY_SPEED * dt
            if abs(dx) > 0.5:
                bu["facing"] = "left" if dx < 0 else "right"
            if dist <= step:
                bu["x"], bu["y"], bu["state"] = bu["tx"], bu["ty"], "idle"
                bu["t"] = random.uniform(*BUDDY_PAUSE)
                if random.random() < 0.16:      # occasional ambient chirp on arrival
                    from techdeck.core.audio_manager import (
                        get_audio_manager, SOUND_PET_VOICE)
                    get_audio_manager().play(SOUND_PET_VOICE)
            else:
                bu["x"] += dx / dist * step
                bu["y"] += dy / dist * step
                bu["wt"] -= dt
                if bu["wt"] <= 0:              # advance the walk cycle
                    bu["fidx"] = (bu["fidx"] + 1) % 4
                    bu["wt"] = BUDDY_WALK_MS / 1000.0

    def _tree_stage_from_settings(self):
        """Current tree growth stage (0 = none .. 5 = full). Falls back to full
        when there's no settings (tests)."""
        if self.settings is not None and hasattr(self.settings, "get_tree_stage"):
            return self.settings.get_tree_stage()
        return TREE_STAGE_FULL

    def refresh(self):
        """Re-read the equipped wallpaper + owned furniture + agents + tree growth."""
        self._load_background()
        self._load_furniture()
        self._load_agents()
        self._tree_stage = self._tree_stage_from_settings()
        self.update()
