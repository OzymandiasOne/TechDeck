"""
Achievements — claimable milestones that pay out tickets.

Same fixed arcade palette + UFO50 sprite font + 9-slice word-bubble chrome as the
Emporium and My Stuff, so the My Account tabs read as one world. The catalog and
all progress/claim logic live in techdeck.core.achievements; this is purely the
view: a sticky header (title + live ticket balance) over a scrolling column of
achievement cards, each with a progress bar and a CLAIM button.
"""

from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QFrame, QScrollArea,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QPoint, QRect
from PySide6.QtGui import QPainter, QColor, QIcon, QImage, QPixmap

from techdeck.ui.sprite_font import font as _sf
from techdeck.ui.arcade_chrome import (
    EMP, _draw_bubble, _load_art, _trim_v, _tile_ring, _garden_dir,
)
from techdeck.ui.pages.mystuff_page import _wall_tile, _WALL_BASE
from techdeck.core import achievements as ACH
from techdeck.core.audio_manager import get_audio_manager, SOUND_UI_CLAIM


# There is only one trophy sprite, so the three difficulty tiers are made by
# recolouring it: each opaque pixel is tinted while keeping its original
# brightness, so the highlights/shadows (and black outline) survive.
_TROPHY_TINTS = {"bronze": (205, 127, 50), "silver": (200, 200, 210), "gold": (255, 205, 60)}
_trophy_cache = {}


def _trophy_icon(difficulty, size):
    key = (difficulty, size)
    if key in _trophy_cache:
        return _trophy_cache[key]
    img = QImage(str(_garden_dir() / "sPet_ItemTrophy_0.png"))
    if img.isNull():
        _trophy_cache[key] = None
        return None
    img = img.convertToFormat(QImage.Format.Format_ARGB32)
    tr, tg, tb = _TROPHY_TINTS.get(difficulty, _TROPHY_TINTS["bronze"])
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha() == 0:
                continue
            b = (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()) / 255.0
            b = b ** 0.75            # lift the midtones so it doesn't read too dark
            img.setPixelColor(x, y, QColor(int(tr * b), int(tg * b), int(tb * b), c.alpha()))
    pm = QPixmap.fromImage(img).scaledToHeight(size, Qt.TransformationMode.FastTransformation)
    _trophy_cache[key] = pm
    return pm


class _AchHeader(QWidget):
    """Sticky, full-width header: the ACHIEVEMENTS box on the left and the live
    ticket balance on the right, painted over a continuation of the page wall so
    cards cleanly slide under it as the list scrolls."""

    def __init__(self, page, title_pm):
        super().__init__(page)
        self.page = page
        self._title = title_pm
        self.box_w = title_pm.width() + 44
        self.box_h = title_pm.height() + 22

    def paintEvent(self, _e):
        p = QPainter(self)
        wall = self.page._wall
        if wall is not None:
            p.drawTiledPixmap(self.rect(), wall,
                              QPoint(self.x() % wall.width(), self.y() % wall.height()))
        else:
            p.fillRect(self.rect(), QColor(_WALL_BASE))
        # Title box (left)
        box = QRect(16, 0, self.box_w, self.box_h)
        _draw_bubble(p, box.adjusted(0, 0, -1, -1),
                     self.page._bubbles["banner"], shadow=EMP["shadow"])
        p.drawPixmap(box.x() + (self.box_w - self._title.width()) // 2,
                     box.y() + (self.box_h - self._title.height()) // 2, self._title)
        # Live ticket balance (right)
        bal = _sf().render(f"{self.page.settings.get_tickets()} TICKETS", 2, EMP["ticket"])
        bw = bal.width() + 36
        bbox = QRect(self.width() - bw - 16, (self.box_h - (bal.height() + 18)) // 2,
                     bw, bal.height() + 18)
        _draw_bubble(p, bbox, self.page._bubbles["balance"], shadow=EMP["shadow"])
        p.drawPixmap(bbox.x() + (bbox.width() - bal.width()) // 2,
                     bbox.y() + (bbox.height() - bal.height()) // 2, bal)
        p.end()


class AchievementCard(QFrame):
    """One achievement: title + description + progress bar, with a CLAIM button
    that lights up once the target is met and dims to CLAIMED after."""

    H = 112
    BTN_AREA = 168   # right-hand strip reserved for the claim button

    def __init__(self, ach, page):
        super().__init__()
        self.ach = ach
        self.page = page
        self.setFixedHeight(self.H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("AchievementCard { background: transparent; }")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 22, 10)
        lay.addStretch(1)
        self.btn = QPushButton()
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.setFixedHeight(34)
        # No keyboard focus: claiming disables the button, and a focused-then-
        # disabled child makes the QScrollArea chase the next focusable card.
        self.btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn.clicked.connect(self._on_claim)
        lay.addWidget(self.btn, 0, Qt.AlignmentFlag.AlignVCenter)

        self._cur = 0
        self._tgt = ach.target
        self._claimed = False
        self.refresh()

    # ---- button helpers (mirror the Emporium/My Stuff look) ------------------
    def _btn_qss(self, bg, edge):
        return (f"QPushButton {{ background:{bg}; border:2px solid {edge}; "
                f"border-radius:5px; padding:3px 12px; }}"
                f"QPushButton:disabled {{ background:{bg}; border-color:{edge}; }}")

    def _set_btn(self, label, bg, edge, enabled):
        pm = _sf().render(label, 2, EMP["btn_text"])
        self.btn.setText("")
        self.btn.setIcon(QIcon(pm))
        self.btn.setIconSize(pm.size())
        self.btn.setEnabled(enabled)
        self.btn.setStyleSheet(self._btn_qss(bg, edge))

    def refresh(self):
        s = self.page.settings
        self._cur, self._tgt = ACH.progress(self.ach, s)
        self._claimed = s.is_achievement_claimed(self.ach.id)
        if self._claimed:
            self._set_btn("CLAIMED", EMP["owned"], EMP["owned"], False)
        elif ACH.is_complete(self.ach, s):
            self._set_btn(f"CLAIM +{self.ach.reward}", EMP["buy"], EMP["buy_lit_edge"], True)
        else:
            self._set_btn(f"+{self.ach.reward}", EMP["buy_dim"], EMP["buy_dim_edge"], False)
        self.update()

    def _on_claim(self):
        self.page.claim(self.ach)

    def paintEvent(self, _e):
        p = QPainter(self)
        rect = self.rect().adjusted(0, 0, -5, -5)
        _draw_bubble(p, rect, self.page._bubbles["tile"], shadow=EMP["shadow"])
        ring = EMP["ticket"] if self._claimed else EMP["ring"]
        _tile_ring(p, rect, ring)

        # Difficulty trophy on the left (bronze/silver/gold = how hard it is).
        troph = _trophy_icon(self.ach.difficulty, 56)
        icon_x = rect.x() + 16
        tw = 0
        if troph is not None:
            p.drawPixmap(icon_x, rect.y() + (rect.height() - troph.height()) // 2, troph)
            tw = troph.width()

        x = icon_x + tw + 16
        text_w = rect.width() - self.BTN_AREA - tw - 16
        # Title (top-left of the text area)
        title_pm = _sf().render(self.ach.title.upper(), 3, EMP["tile_text"])
        p.drawPixmap(x, rect.y() + 12, title_pm)
        # Progress count (top-right of the text area)
        count_pm = _sf().render(f"{self._cur} / {self._tgt}", 2,
                                EMP["ticket"] if self._cur >= self._tgt else EMP["tile_dim"])
        p.drawPixmap(x + text_w - count_pm.width() - 8, rect.y() + 16, count_pm)
        # Description
        desc_pm = _sf().render_wrapped(self.ach.desc.upper(), 2, EMP["tile_dim"],
                                       max_width=text_w - 24)
        p.drawPixmap(x, rect.y() + 12 + title_pm.height() + 8, desc_pm)

        # Progress bar along the bottom of the text area
        bar_w = text_w - 20
        bar = QRect(x, rect.bottom() - 22, max(0, bar_w), 12)
        p.fillRect(bar, QColor(EMP["tile_bg"]))
        frac = (self._cur / self._tgt) if self._tgt else 0.0
        fill_col = EMP["equip"] if self._cur >= self._tgt else EMP["frame_a"]
        if frac > 0:
            p.fillRect(QRect(bar.x(), bar.y(), int(bar.width() * min(1.0, frac)), bar.height()),
                       QColor(fill_col))
        p.setPen(QColor(EMP["ring"]))
        p.drawRect(bar)
        p.end()


class AchievementsPage(QWidget):
    """Scrolling column of achievement cards under a sticky title/balance header."""

    def __init__(self, settings, parent=None, on_claim=None):
        super().__init__(parent)
        self.settings = settings
        self._on_claim_cb = on_claim          # let the host refresh sibling tabs
        self._wall = _wall_tile()
        self._bubbles = {"tile": _load_art("bubble_tile.tdart"),
                         "banner": _load_art("bubble_banner.tdart"),
                         "balance": _load_art("bubble_balance.tdart")}
        self._title = _trim_v(_sf().render("ACHIEVEMENTS", 4, EMP["neon_on"]))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 14, 0, 0)
        root.setSpacing(0)

        self.header = _AchHeader(self, self._title)
        self._banner_h = self.header.box_h

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.scroll.viewport().setStyleSheet("background: transparent;")
        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._vbox = QVBoxLayout(self._content)
        self._vbox.setContentsMargins(20, self._banner_h + 18, 20, 16)
        self._vbox.setSpacing(12)
        self.scroll.setWidget(self._content)
        root.addWidget(self.scroll, 1)

        self.cards = []
        self._build()

    def _build(self):
        while self._vbox.count():
            item = self._vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.cards = []
        for ach in ACH.ACHIEVEMENTS:
            card = AchievementCard(ach, self)
            self.cards.append(card)
            self._vbox.addWidget(card)
        self._vbox.addStretch(1)

    def refresh(self):
        # Progress can advance between visits (runs, purchases), so re-stat each card.
        for c in self.cards:
            c.refresh()
        self.header.update()

    def claim(self, ach):
        got = ACH.claim(ach, self.settings)
        if got:
            get_audio_manager().play(SOUND_UI_CLAIM)
            self.refresh()
            if self._on_claim_cb:
                self._on_claim_cb()
        return got

    def resizeEvent(self, e):
        super().resizeEvent(e)
        sb_w = self.scroll.verticalScrollBar().sizeHint().width()
        self.header.setGeometry(0, 14, max(self.header.box_w + 16, self.width() - sb_w),
                                self.header.box_h)
        self.header.raise_()

    def paintEvent(self, _evt):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(_WALL_BASE))
        if self._wall is not None:
            p.drawTiledPixmap(self.rect(), self._wall)
        p.end()
