"""Beyblade builder — swap the three layers to make your own.

The payoff for shipping beyblades as separate TOP / BOTTOM / CENTER sprites
instead of flattened art: a player who owns two designs can wear one's attack
ring over another's weight disk with a third's chip. This is the screen where
that happens.

Layout is deliberately console-like rather than form-like: a big live preview
with three selector rows under it, each cycled with < and > . Picking a part
re-composes the preview immediately, so the build is judged by eye, which is
the only way to judge it.

Only designs the player OWNS are offered — the parts unlock together when the
beyblade is bought.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QIcon

from techdeck.ui import beyblade, pixel_art
from techdeck.ui.arcade_chrome import EMP, _draw_bubble, _load_art
from techdeck.ui.sprite_font import font as _sf

_LABEL = {"top": "ATTACK RING", "bottom": "WEIGHT DISK", "center": "BIT CHIP"}


class BeybladeBuilder(QDialog):
    """Pick a design per layer, preview the result, equip it."""

    WIDTH = 420
    PREVIEW = 4          # px per art cell in the preview

    def __init__(self, parent, settings):
        super().__init__(parent)
        self.settings = settings
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self._bubble = _load_art("bubble_dialogue.tdart")

        self.owned = self._owned_designs()
        self.choice = beyblade.normalize_choice(
            beyblade.parse_variant(settings.get_equipped_spinner()))
        # An equipped combo can name a design that was never owned (or the
        # default fallback); snap each slot to something the player actually has
        # so the arrows never land on a part they cannot use.
        for kind in beyblade.KINDS:
            if self.choice[kind] not in self.owned:
                self.choice[kind] = self.owned[0]

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 18)
        lay.setSpacing(10)

        self._title = _sf().render("BUILD A BEYBLADE", 2, EMP["neon_on"])
        lay.addSpacing(self._title.height() + 8)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setFixedHeight(62 * self.PREVIEW + 8)
        self.preview.setStyleSheet("background: transparent; border: none;")
        lay.addWidget(self.preview)

        self._rows = {}
        # Top-down as the player pictures it, not bottom-up as it composes.
        for kind in ("top", "bottom", "center"):
            lay.addLayout(self._selector(kind))

        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(self._button("CANCEL", EMP["owned"], EMP["owned"], self.reject))
        btns.addWidget(self._button("EQUIP", EMP["equip"], "#7af0a0", self._equip))
        btns.addStretch()
        lay.addSpacing(6)
        lay.addLayout(btns)
        self.setFixedWidth(self.WIDTH)
        self._refresh()

    # ---- construction helpers ------------------------------------------------
    def _owned_designs(self) -> list:
        got = [d for d in beyblade.DESIGNS
               if any(self.settings.is_unlocked(i)
                      for i, dd in beyblade.ITEM_DESIGN.items() if dd == d)]
        return got or [beyblade.DESIGNS[0]]

    def _button(self, label, bg, edge, slot):
        b = QPushButton()
        pm = _sf().render(label, 2, EMP["btn_text"])
        b.setIcon(QIcon(pm)); b.setIconSize(pm.size()); b.setText("")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFixedHeight(30)
        b.setStyleSheet(f"QPushButton {{ background:{bg}; border:2px solid {edge}; "
                        f"border-radius:5px; padding:3px 16px; }}")
        b.clicked.connect(slot)
        return b

    def _arrow(self, glyph, kind, step):
        b = QPushButton()
        pm = _sf().render(glyph, 2, EMP["btn_text"])
        b.setIcon(QIcon(pm)); b.setIconSize(pm.size()); b.setText("")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFixedSize(30, 26)
        b.setStyleSheet(f"QPushButton {{ background:{EMP['tile_bg']}; border:2px "
                        f"solid {EMP['frame_a']}; border-radius:4px; }}")
        b.clicked.connect(lambda: self._cycle(kind, step))
        return b

    def _selector(self, kind):
        row = QHBoxLayout()
        row.setSpacing(6)
        cap = QLabel()
        cap.setPixmap(_sf().render(_LABEL[kind], 1, EMP["tile_dim"]))
        cap.setFixedWidth(max(_sf().text_width(v, 1) for v in _LABEL.values()) + 6)
        cap.setStyleSheet("background: transparent; border: none;")
        val = QLabel()
        val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val.setStyleSheet("background: transparent; border: none;")
        row.addWidget(cap)
        row.addWidget(self._arrow("<", kind, -1))
        row.addWidget(val, 1)
        row.addWidget(self._arrow(">", kind, +1))
        self._rows[kind] = val
        return row

    # ---- behaviour -----------------------------------------------------------
    def _cycle(self, kind, step):
        opts = self.owned
        i = (opts.index(self.choice[kind]) + step) % len(opts)
        self.choice[kind] = opts[i]
        self._refresh()

    def _refresh(self):
        for kind, lbl in self._rows.items():
            lbl.setPixmap(_sf().render(
                beyblade.DISPLAY.get(self.choice[kind], self.choice[kind]).upper(),
                2, EMP["tile_text"]))
        data = beyblade.compose(self.choice)
        if data is not None:
            self.preview.setPixmap(pixel_art.render(data, scale=self.PREVIEW))
        self.update()

    def _equip(self):
        variant = beyblade.variant_id(self.choice)
        self.settings.set_equipped_spinner(variant)
        # Remembered separately from the equipped slot so the My Stuff "Build
        # Your Own" tile keeps showing what they built even after they equip
        # some other spinner.
        self.settings.set_beyblade_build(variant)
        self.accept()

    def paintEvent(self, _e):
        p = QPainter(self)
        _draw_bubble(p, self.rect().adjusted(0, 0, -1, -1), self._bubble,
                     shadow=EMP["shadow"])
        p.drawPixmap((self.width() - self._title.width()) // 2, 20, self._title)
        p.end()
