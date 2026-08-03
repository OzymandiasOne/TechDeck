"""
Woogy's Emporium — the ticket redemption counter.

A pixel-art arcade prize-counter scene (wall + kiosk + Woogy + an animated
arcade cabinet) with a grid of purchasable tiles laid over it. Earn tickets by
running apps / sending feedback; spend them here. Fixed arcade palette (does NOT
follow the user theme), with motion (marquee chase lights + neon flicker on the
sign, animated cabinet screen) and a typewriter dialogue box.

ALL text uses the UFO50 sprite font (techdeck.ui.sprite_font), rendered to
tinted pixmaps — labels/buttons carry pixmaps, painted text blits directly.
Chrome (sign, balance, tiles, dialogue) is drawn from editable 9-slice
word-bubble sprites via techdeck.ui.arcade_chrome (the shared arcade-look
layer); the merchandise data lives in techdeck.ui.emporium_catalog and the
store widgets (StoreTile / CategoryBox / ShopWindow) in
techdeck.ui.widgets.store_tiles.

This module holds only the EmporiumPage scene itself, and re-exports the
extracted names so existing imports (`from ...emporium_page import CATALOG,
EMP, PixelDialog, ...`) keep resolving unchanged.
"""

import math
import random

from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QScrollArea,
)
from PySide6.QtCore import Qt, QRect, QTimer, QPoint
from PySide6.QtGui import QPainter, QColor, QPolygon

from techdeck.ui.sprite_font import font as _sf
# Re-exported for back-compat (achievements/mystuff/garden_scene/tools import
# these from here) — noqa: F401 on the ones EmporiumPage itself doesn't use.
from techdeck.ui.arcade_chrome import (      # noqa: F401
    EMP, PixelDialog, _SoldStamp, _ascii, _brighten, _default_spinner_pixmap,
    _draw_bubble, _equipped_badge, _garden_dir, _greyed, _load_art,
    _load_pixmap, _marquee, _sprites_dir, _tile_ring, _trim_v,
)
from techdeck.ui.emporium_catalog import CATALOG
from techdeck.ui.widgets.store_tiles import CategoryBox, ShopWindow, StoreTile


class EmporiumPage(QWidget):
    """The redemption-counter scene + the catalog grid, with arcade animation."""

    DEFAULT_DIALOGUE = "WOOGY: WHAT'LL IT BE, FELLAS?"

    # A little something Woogy says for every item he rings up. Keyed by item id;
    # falls back to GENERIC_COMMENT for anything not listed.
    WOOGY_COMMENTS = {
        "spinner_beyblade":
            "WOOGY: A BEYBLADE! GO ON, LET IT RIP. OH, UM, HAVE A GOOD DAY.",
        "spinner_shuriken":
            "WOOGY: A SHURIKEN! SO SHARP, SO COOL. PLEASE DON'T POKE OL' WOOGY.",
        "game_asa_the_video_game":
            "WOOGY: WOOGY DON'T KNOW HOW TO PLAY THIS GAME, WOOGY JUST CLICK BUTTONS.",
        "friend_buddy":
            "WOOGY: BUDDY IS A GOOD PIG. TREAT HIM RIGHT AND HE'LL KEEP YOUR YARD COMPANY.",
        "toy_sentry_drone":
            "WOOGY: IT FOLLOWS YOU AROUND AND BLOWS UP FOLDERS. WOOGY DOES NOT ASK "
            "QUESTIONS ABOUT THE MERCHANDISE.",
    }
    GENERIC_COMMENT = "WOOGY: V-VERY GOOD! WOOGY APPROVES."

    # How Woogy fetches each family of item (the SOLD! box flavor). Keyed by the
    # item's "kind"; "{name}" is filled in. Falls back to GRAB_DEFAULT.
    GRAB_DESCRIPTIONS = {
        "spinner": ("Woogy plucks the {name} from a high shelf, gives it a wary "
                    "little test-spin that nearly takes his eye out, and sets it "
                    "down still humming."),
        "game": ("Woogy heaves the {name} cartridge out of the locked glass case, "
                 "blows the dust off it, and slides it over with a proud grin."),
        "friends": ("Woogy gives a sharp whistle and {name} trots out from the back, "
                    "snuffling happily. Woogy pats him once and sends him your way."),
        "gadget": ("Woogy unlocks the case behind the counter, lifts the {name} out "
                   "with both hands, and sets it down. It powers up, sweeps the room "
                   "once, and settles on you."),
    }
    GRAB_DEFAULT = ("Woogy grabs the {name} off the shelf with effort and wobbles "
                    "back to the counter. He slides it towards you with a huff.")

    DIALOGUE_W = 440        # word-bubble width (px)
    DIALOGUE_H = 104        # word-bubble height (px)
    LINES_PER_PAGE = 3      # lines that fit in the bubble before it paginates

    # Store categories (id, label), shown as a segmented bar above the grid. Each
    # CATALOG item's "category" routes it to one of these. Empty ones show
    # "COMING SOON". Default to a category that actually has stock so the store
    # isn't empty on open.
    CATEGORIES = [("friends", "Friends"), ("toys", "Toys"),
                  ("decorations", "Decorations")]
    DEFAULT_CATEGORY = "toys"
    GRID_COLS = 4

    # The scene is tuned for a roughly square window (default content ~1.1:1). A
    # very wide window (fullscreen) would stretch the wall/counter/Woogy, so we
    # cap the scene to this width:height ratio and centre it, letterboxing the
    # sides with the wall colour instead of stretching.
    DESIGN_RATIO = 1.25

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._phase = 0
        self._set_dialogue(self.DEFAULT_DIALOGUE)
        self._neon_bright = True
        self._bg = _load_pixmap("emporium_background.tdart", 128)
        self._counter = _load_pixmap("emporium_counter.tdart", 128)
        self._woogy = _load_pixmap("woogy.tdart", 230)
        self._cabinet = _load_pixmap("arcade_cabinet.tdart", 64)
        # 9-slice word-bubble panels (editable .tdart; see tools/generate_bubbles.py)
        self._bubbles = {
            "tile": _load_art("bubble_tile.tdart"),
            "banner": _load_art("bubble_banner.tdart"),
            "balance": _load_art("bubble_balance.tdart"),
            "dialogue": _load_art("bubble_dialogue.tdart"),
        }
        # Pre-render the neon sign (bright + dim) once. Scale 3 (not 4) so the
        # banner + a 4-digit ticket balance both fit the top bar within the
        # default window's content width (~824px after the sidebar) — at scale 4
        # the row needed ~866px and got centre-cropped ~28px on each side by the
        # CroppedPage host, clipping the banner's left edge (and the balance's
        # right). See account_page.py's CroppedPage design_width.
        self._sign_on = _trim_v(_sf().render("WOOGY'S EMPORIUM", 3, EMP["neon_on"]))
        self._sign_off = _trim_v(_sf().render("WOOGY'S EMPORIUM", 3, EMP["neon_off"]))

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        self._root = root   # margins re-inset to the stage on resize

        bar = QHBoxLayout()
        self.banner = QLabel()
        self.banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.banner.setStyleSheet("background: transparent; border: none;")
        self.banner.setFixedSize(self._sign_on.width() + 44, self._sign_on.height() + 22)
        bar.addWidget(self.banner)
        bar.addStretch()
        self.balance_lbl = QLabel()
        self.balance_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.balance_lbl.setStyleSheet("background: transparent; border: none;")
        self.balance_lbl.setFixedSize(150, self._sign_on.height() + 18)
        bar.addWidget(self.balance_lbl)
        root.addLayout(bar)
        self._set_banner_bright(True)

        # --- category bar: each button OPENS a floating shop window over the
        # scene (closable via its X), rather than filtering an inline grid -------
        self._category = self.DEFAULT_CATEGORY
        self._open_category = None
        cat_bar = QHBoxLayout()
        cat_bar.setSpacing(12)
        self.cat_buttons = {}
        # Uniform box width that fits the longest category name (no clipping).
        name_w = max(_sf().render(lbl.upper(), 2, EMP["tile_text"]).width()
                     for _, lbl in self.CATEGORIES)
        box_w = max(CategoryBox.MIN_W, name_w + 28)
        for cat_id, label in self.CATEGORIES:
            box = CategoryBox(cat_id, label, self._category_icon(cat_id),
                              self, box_w, icon_dy=(8 if cat_id == "decorations" else 0))
            self.cat_buttons[cat_id] = box
            cat_bar.addWidget(box)
        cat_bar.addStretch()
        root.addLayout(cat_bar)

        # --- merchandise grid, in a vertical scroll area (the "scroll wheel") ---
        self.tiles = [StoreTile(item, self) for item in CATALOG]
        self.grid_host = QWidget()
        self.grid_host.setStyleSheet("background: transparent;")
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(12)

        self._coming_soon = QLabel()
        self._coming_soon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._coming_soon.setStyleSheet("background: transparent; border: none;")
        self._coming_soon.setPixmap(_trim_v(_sf().render("COMING SOON", 4, EMP["neon_off"])))
        self._coming_soon.hide()

        host = QWidget()
        host.setStyleSheet("background: transparent;")
        host_v = QVBoxLayout(host)
        host_v.setContentsMargins(0, 0, 0, 0)
        host_v.setSpacing(0)
        host_v.addSpacing(8)
        host_v.addWidget(self._coming_soon, 0, Qt.AlignmentFlag.AlignHCenter)
        host_v.addWidget(self.grid_host, 0, Qt.AlignmentFlag.AlignTop)
        host_v.addStretch()

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.scroll.viewport().setStyleSheet("background: transparent;")
        self.scroll.setWidget(host)
        # The grid/scroll lives inside a floating, closable window over the scene.
        self.shop_window = ShopWindow(self, self.scroll)
        root.addStretch()
        self._style_category_buttons()

        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._tick)
        self.refresh()

    # ---- Woogy's word bubble (paginated typewriter) --------------------------
    def _set_dialogue(self, text):
        """Point Woogy's bubble at `text`, wrapped into pages, typed from the top."""
        self._dialogue = text
        # Reserve room for the "..." continuation marker so it never spills past
        # the right edge when appended to a near-full line on a non-final page.
        avail = self.DIALOGUE_W - 28 - _sf().text_width("...", 3)
        self._lines = _sf().wrap_lines(text, 3, avail)
        self._page = 0
        self._reveal = 0

    def _dialogue_rect(self):
        sx, _ = self._stage()
        return QRect(sx + 40, self.height() - (self.DIALOGUE_H + 26),
                     self.DIALOGUE_W, self.DIALOGUE_H)

    def _page_lines(self):
        lpp = self.LINES_PER_PAGE
        return self._lines[self._page * lpp: self._page * lpp + lpp]

    def _page_chars(self):
        return sum(len(ln) for ln in self._page_lines())

    def _has_more_pages(self):
        return (self._page + 1) * self.LINES_PER_PAGE < len(self._lines)

    def _set_banner_bright(self, bright):
        self._neon_bright = bright
        self.banner.setPixmap(self._sign_on if bright else self._sign_off)

    def refresh(self):
        bal = _trim_v(_sf().render(f"{self.settings.get_tickets()} TICKETS", 3,
                                   EMP["ticket"]))
        self.balance_lbl.setFixedSize(max(150, bal.width() + 28),
                                      self._sign_on.height() + 18)
        self.balance_lbl.setPixmap(bal)
        for t in self.tiles:
            t.refresh()

    # ---- categories (each opens a floating window over the scene) -------------
    def _category_icon(self, cat_id):
        """Representative icon pixmap for a category box (size tuned per icon)."""
        if cat_id == "toys":
            return _default_spinner_pixmap(48)               # slightly larger
        if cat_id == "decorations":
            return _brighten(_load_pixmap("sPet_ItemCouch_0.png", 88), 1.3)
        return _load_pixmap("sPet_Buddy_4.png", 52)          # Friends = the pet

    def _select_category(self, cat_id):
        from techdeck.core.audio_manager import get_audio_manager, SOUND_UI_FILTER
        get_audio_manager().play(SOUND_UI_FILTER)
        # Clicking the already-open category closes its window again (toggle).
        if self._open_category == cat_id and self.shop_window.isVisible():
            self._close_window()
            return
        self._category = cat_id
        self._open_category = cat_id
        self._populate_grid()
        self.shop_window.set_title(dict(self.CATEGORIES)[cat_id])
        self.shop_window.show()
        self.shop_window.raise_()
        self._position_shop_window()
        self._style_category_buttons()

    def _close_window(self):
        """Close the shop window, revealing Woogy underneath."""
        from techdeck.core.audio_manager import get_audio_manager, SOUND_UI_CLOSE
        get_audio_manager().play(SOUND_UI_CLOSE)
        self.shop_window.hide()
        self._open_category = None
        self._style_category_buttons()

    def _style_category_buttons(self):
        """Light up (accent ring + neon name) the box whose window is open; the
        rest sit normal. Nothing is lit while the window is closed."""
        for cid, box in self.cat_buttons.items():
            box.set_selected(cid == self._open_category)

    def _stage(self):
        """(x, width) of the scene area: capped to DESIGN_RATIO and centred so a
        wide window letterboxes instead of stretching. Full height is used."""
        w, h = self.width(), self.height()
        sw = min(w, int(h * self.DESIGN_RATIO))
        return (w - sw) // 2, sw

    def _position_shop_window(self):
        """Centre the floating window below the category bar, spanning down over
        Woogy (it floats on top of him)."""
        if not self.shop_window.isVisible():
            return
        sx, sw = self._stage()
        cat_btns = list(self.cat_buttons.values())
        top = (cat_btns[0].geometry().bottom() if cat_btns else 90) + 12
        cols = self.GRID_COLS
        inner_w = cols * StoreTile.SIZE + (cols - 1) * 12
        ww = min(sw - 40, inner_w + 76)
        # Height fits the content, up to 2 rows (more than that scrolls).
        n = sum(1 for t in self.tiles if t.item.get("category") == self._category)
        if n:
            vis_rows = min(2, math.ceil(n / cols))
            content_h = vis_rows * StoreTile.HEIGHT + (vis_rows - 1) * 12
        else:
            content_h = 80   # just the COMING SOON plate
        wh = min(self.height() - top - 24, 64 + content_h + 34)
        x = sx + (sw - ww) // 2
        self.shop_window.setGeometry(x, top, ww, max(200, wh))

    def _item_available(self, item):
        """Is this item purchasable yet? Owned items always show; otherwise gate
        items that 'require' a milestone (owl/monkey need a fully grown tree)."""
        if self.settings.is_unlocked(item["id"]):
            return True
        if item.get("requires") == "tree_full":
            return self.settings.get_tree_stage() >= self.settings.TREE_STAGES
        return True

    def _populate_grid(self):
        """Lay out only the tiles in the active category; an empty category shows
        the COMING SOON plate instead."""
        for t in self.tiles:
            self.grid.removeWidget(t)
            t.hide()
        matching = [t for t in self.tiles
                    if t.item.get("category") == self._category
                    and not t.item.get("hidden")
                    and self._item_available(t.item)]
        cols = self.GRID_COLS
        for i, t in enumerate(matching):
            self.grid.addWidget(t, i // cols, i % cols,
                                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            t.show()
        self.grid.setColumnStretch(cols, 1)
        self.grid_host.setVisible(bool(matching))
        self._coming_soon.setVisible(not matching)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # Inset the top-bar widgets (banner/balance/categories) to the stage so
        # they stay with the centred scene instead of the window corners.
        sx, _ = self._stage()
        self._root.setContentsMargins(sx + 16, 14, sx + 16, 14)
        self._position_shop_window()

    # ---- animation -----------------------------------------------------------
    def showEvent(self, e):
        super().showEvent(e)
        self._set_dialogue(self.DEFAULT_DIALOGUE)
        self._timer.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._timer.stop()

    def _tick(self):
        self._phase += 1
        page_chars = self._page_chars()
        if self._reveal < page_chars:
            self._reveal = min(page_chars, self._reveal + 2)
        bright = random.random() > 0.12
        if bright != self._neon_bright:
            self._set_banner_bright(bright)
        self.update()

    def mousePressEvent(self, e):
        # Click the bubble to fast-forward the typewriter, then to page through
        # the rest of Woogy's comment.
        if self._dialogue_rect().contains(e.position().toPoint()):
            if self._reveal < self._page_chars():
                self._reveal = self._page_chars()
            elif self._has_more_pages():
                self._page += 1
                self._reveal = 0
            self.update()
        super().mousePressEvent(e)

    # ---- purchase / equip ----------------------------------------------------
    def handle_tile_action(self, item):
        from techdeck.core.audio_manager import get_audio_manager, SOUND_UI_SELECT
        get_audio_manager().play(SOUND_UI_SELECT)
        s = self.settings
        if not s.is_unlocked(item["id"]):
            if not self._item_available(item):
                PixelDialog.show_message(
                    self, "Not yet",
                    f"{item['name']} shows up once your tree is fully grown.")
                return
            if not s.spend_tickets(item["cost"]):
                PixelDialog.show_message(
                    self, "Not enough tickets",
                    f"{item['name']} costs {item['cost']} tickets. You have "
                    f"{s.get_tickets()}. Run more apps to earn more!")
                return
            s.unlock_item(item["id"])
            for extra in item.get("bundle", []):   # e.g. Sun also unlocks the Moon
                s.unlock_item(extra)
            grab = self.GRAB_DESCRIPTIONS.get(item["kind"], self.GRAB_DEFAULT).format(
                name=item["name"])
            if item["kind"] == "spinner":
                s.set_equipped_spinner(item["id"])
                instr = "It's equipped! Pop it with /fidget, or switch in My Stuff."
            elif item["kind"] == "background":
                s.set_equipped_background(item["sprite"])
                instr = ("It's now your My House wallpaper! Re-click any owned "
                         "background here to switch.")
            elif item["kind"] == "tree":
                s.plant_tree()
                instr = ("It's planted! Your tree grows a little with every plugin "
                         "run - give it about a month to reach full size.")
            elif item["kind"] == "furniture":
                instr = "It's added to your collection - see it in My House."
            elif item["kind"] == "friends":
                instr = "He's moved into your yard - say hi over in My House!"
            elif item["kind"] == "game":
                instr = ("Find it in your Library (Games) and add it to a kit "
                         "to play.")
            elif item["kind"] == "gadget":
                instr = ("Open My Stuff and hit SET UP to choose which apps "
                         "open their pick-a-file-or-folder prompt through it.")
            else:
                instr = "Enjoy!"
            PixelDialog.show_message(self, "Sold!", f"{grab} {instr}")
            # Once the SOLD! box is dismissed, Woogy pipes up in his word bubble
            # with a comment for this item (paginated + typed from the top).
            self._set_dialogue(
                self.WOOGY_COMMENTS.get(item["id"], self.GENERIC_COMMENT))
        elif item["kind"] == "spinner":
            s.set_equipped_spinner(item["id"])
        elif item["kind"] == "background":
            s.set_equipped_background(item["sprite"])
        self.refresh()

    # ---- the pixel-art scene -------------------------------------------------
    def paintEvent(self, _evt):
        p = QPainter(self)
        h = self.height()
        sx, sw = self._stage()
        # Wall colour fills the whole window; the scene art is confined to the
        # centred stage so wide windows letterbox instead of stretching.
        p.fillRect(self.rect(), QColor(EMP["wall"]))
        if self._bg is not None:
            p.drawPixmap(QRect(sx, 0, sw, h), self._bg)
        self._draw_cabinet(p, sx, sw, h)
        if self._woogy is not None:
            wpm = self._scaled_woogy(h)
            ww, wh = wpm.width(), wpm.height()
            y = h - int(h * 0.30) - wh + 30
            p.drawPixmap(sx + (sw - ww) // 2, max(y, int(h * 0.32)), wpm)
        if self._counter is not None:
            ch = int(h * 0.30)
            p.drawPixmap(QRect(sx, h - ch, sw, ch), self._counter)
        _draw_bubble(p, self.banner.geometry(), self._bubbles["banner"],
                     shadow=EMP["shadow"])
        _marquee(p, self.banner.geometry(), self._phase)
        _draw_bubble(p, self.balance_lbl.geometry(), self._bubbles["balance"],
                     shadow=EMP["shadow"])
        self._draw_dialogue(p)
        p.end()

    def _scaled_woogy(self, h):
        """Woogy scaled proportionally to the scene height (cached per height) so
        he keeps his designed size relative to the scene at any window size."""
        target = max(120, int(0.31 * h))
        if getattr(self, "_woogy_h", None) != target:
            self._woogy_scaled = self._woogy.scaledToHeight(
                target, Qt.TransformationMode.FastTransformation)
            self._woogy_h = target
        return self._woogy_scaled

    # Native cabinet metrics (cells) — kept in sync with the .tdart art built by
    # tools/generate_arcade_cabinet.py (W x H = 48 x 76).
    _CAB_W, _CAB_H = 48, 76
    _SCREEN = (13, 21, 22, 20)        # x, y, w, h of the animated screen face
    _MARQUEE_BULBS = (range(8, 41, 4), 3)   # bulb x-cells, row

    def _draw_cabinet(self, p, sx, sw, h):
        pix = self._cabinet
        if pix is None:
            return
        scale = max(2, round(0.40 * h / self._CAB_H))
        cw, ch = self._CAB_W * scale, self._CAB_H * scale
        cx = sx + sw - cw - 24
        cy = max((h - int(h * 0.30)) - ch + 10 * scale, int(0.08 * h))
        p.drawPixmap(QRect(cx, cy, cw, ch), pix)
        scol, srow, scells_w, scells_h = self._SCREEN
        sx, sy = cx + scol * scale, cy + srow * scale
        sw, sh = scells_w * scale, scells_h * scale
        p.fillRect(sx, sy, sw, sh, QColor(EMP["screen"]))
        bars = ["#37c9da", "#cf3597", "#3b34c0", "#e8841f"]
        bh = max(1, sh // 4)
        for i in range(4):
            c = QColor(bars[(self._phase + i) % 4])
            c.setAlpha(150)
            p.fillRect(sx, sy + i * bh, sw, bh, c)
        by = sy + (self._phase * scale) % max(1, sh)
        p.fillRect(sx, by, sw, max(1, scale), QColor("#f0f0ff"))
        bulb_xs, bulb_row = self._MARQUEE_BULBS
        for j, mx in enumerate(bulb_xs):
            on = (self._phase + j) % 3 != 0
            p.fillRect(cx + mx * scale, cy + bulb_row * scale, scale, scale,
                       QColor("#7ef9ff" if on else "#1a4a52"))

    def _draw_dialogue(self, p):
        rect = self._dialogue_rect()
        # UFO50-style: black box, thick white rounded border, soft drop shadow.
        _draw_bubble(p, rect, self._bubbles["dialogue"], shadow=EMP["shadow"])
        # Reveal the current page's lines char-by-char (typewriter).
        lines = self._page_lines()
        r = self._reveal
        shown = []
        for ln in lines:
            shown.append(ln[:max(0, min(len(ln), r))])
            r -= len(ln)
        fully = self._reveal >= self._page_chars()
        has_more = self._has_more_pages()
        # When there's more to read, mark it with "..." and the blink-y down arrow.
        if fully and has_more and shown:
            shown[-1] = shown[-1] + "..."
        text_pm = _sf().render_lines(shown or [""], 3, EMP["dialogue_text"])
        p.drawPixmap(rect.x() + 14, rect.y() + 12, text_pm)
        if fully and has_more and (self._phase // 3) % 2 == 0:
            ax, ay = rect.center().x(), rect.bottom() - 12
            tri = QPolygon([QPoint(ax - 5, ay), QPoint(ax + 5, ay), QPoint(ax, ay + 6)])
            p.setBrush(QColor(EMP["neon_on"]))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPolygon(tri)
