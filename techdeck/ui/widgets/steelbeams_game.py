"""
ASA: The Video Game — 16-bit incremental strategy.
Run the yard. Form the Tech Team. Launch the probes. Convert the universe.
Inspired by Universal Paperclips by Frank Lantz.

Visuals use the Sweetie-16 pixel palette; the banner is a low-res pixel scene
scaled up with nearest-neighbor for a crisp SNES look.

Naming rule (learned the hard way, see LESSONS_LEARNED.md): every widget
attribute carries a _lbl/_btn/_box/_bar/_frame/_tab suffix so a QLabel can
never shadow a method or state variable again.
"""
from __future__ import annotations

import html
import random

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QFrame, QTabWidget, QScrollArea,
)
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont, QPainter, QImage, QColor


# ── Sweetie-16 palette ─────────────────────────────────────────────────────
PAL = {
    "bg":     "#1a1c2c",
    "purple": "#5d275d",
    "red":    "#b13e53",
    "orange": "#ef7d57",
    "yellow": "#ffcd75",
    "lime":   "#a7f070",
    "green":  "#38b764",
    "teal":   "#257179",
    "navy":   "#29366f",
    "blue":   "#3b5dc9",
    "sky":    "#41a6f6",
    "cyan":   "#73eff7",
    "white":  "#f4f4f4",
    "silver": "#94b0c2",
    "slate":  "#566c86",
    "dark":   "#333c57",
}

_STYLE = f"""
QWidget {{ background-color: {PAL['bg']}; color: {PAL['white']};
          font-family: Consolas, monospace; font-size: 10pt; }}
QPushButton {{ background-color: {PAL['navy']}; color: {PAL['cyan']};
              border: 2px solid {PAL['blue']}; border-radius: 0px;
              padding: 4px 8px; font-family: Consolas, monospace;
              font-size: 9pt; font-weight: bold; text-align: left; }}
QPushButton:hover   {{ background-color: {PAL['blue']}; color: {PAL['white']};
                       border-color: {PAL['sky']}; }}
QPushButton:pressed {{ background-color: {PAL['teal']}; }}
QPushButton:disabled {{ color: {PAL['slate']}; border-color: {PAL['dark']};
                        background-color: {PAL['bg']}; }}
QPushButton#fab  {{ background-color: {PAL['green']}; color: {PAL['bg']};
                    border: 2px solid {PAL['lime']}; font-size: 12pt;
                    text-align: center; }}
QPushButton#fab:hover {{ background-color: {PAL['lime']}; }}
QPushButton#fab:disabled {{ background-color: {PAL['dark']};
                            color: {PAL['slate']}; border-color: {PAL['slate']}; }}
QPushButton#afab {{ background-color: {PAL['orange']}; color: {PAL['bg']};
                    border: 2px solid {PAL['yellow']}; font-size: 12pt;
                    text-align: center; }}
QPushButton#afab:hover {{ background-color: {PAL['yellow']}; }}
QPushButton#afab:disabled {{ background-color: {PAL['dark']};
                             color: {PAL['slate']}; border-color: {PAL['slate']}; }}
QPushButton#proj {{ background-color: {PAL['purple']}; color: {PAL['yellow']};
                    border: 2px solid {PAL['red']}; text-align: left; }}
QPushButton#proj:hover {{ background-color: {PAL['red']}; color: {PAL['white']}; }}
QPushButton#proj:disabled {{ background-color: {PAL['bg']}; color: {PAL['slate']};
                             border-color: {PAL['dark']}; }}
QPushButton#launch {{ background-color: {PAL['red']}; color: {PAL['yellow']};
                      border: 2px solid {PAL['orange']}; font-size: 11pt;
                      text-align: center; }}
QPushButton#launch:hover {{ background-color: {PAL['orange']}; color: {PAL['bg']}; }}
QPushButton#launch:disabled {{ background-color: {PAL['bg']};
                               color: {PAL['slate']}; border-color: {PAL['dark']}; }}
QPushButton#tiny {{ text-align: center; padding: 0px; }}
QTabWidget::pane {{ border: 2px solid {PAL['navy']}; }}
QTabBar::tab {{ background: {PAL['navy']}; color: {PAL['silver']};
               padding: 5px 12px; border: 2px solid {PAL['bg']};
               font-family: Consolas, monospace; font-size: 9pt; font-weight: bold; }}
QTabBar::tab:selected {{ background: {PAL['blue']}; color: {PAL['yellow']}; }}
QTabBar::tab:hover {{ background: {PAL['teal']}; color: {PAL['white']}; }}
QTextEdit {{ background-color: {PAL['bg']}; color: {PAL['silver']};
            border: 2px solid {PAL['navy']}; }}
QScrollArea {{ border: none; background: transparent; }}
"""


# ── Big-number formatting ──────────────────────────────────────────────────
_SUF = ["", "k", "M", "B", "T", "Qa", "Qi", "Sx", "Sp", "Oc", "No", "Dc"]


def fmt(n) -> str:
    """1234 -> '1,234'; 5.2e9 -> '5.20 B'; beyond Dc -> scientific."""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return str(n)
    if n != n:
        return "?"
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n == float("inf"):
        return sign + "inf"
    if n < 1_000_000:
        return f"{sign}{n:,.0f}"
    orig = n
    tier = 0
    while n >= 1000.0 and tier < len(_SUF) - 1:
        n /= 1000.0
        tier += 1
    if n >= 1000.0:
        return f"{sign}{orig:.2e}"
    return f"{sign}{n:.2f} {_SUF[tier]}"


def fmt_money(n) -> str:
    if abs(n) < 10_000:
        return f"${n:,.2f}"
    return f"${fmt(n)}"


# ── Projects (bought with ops or innovation) ───────────────────────────────
PROJECTS = [
    dict(id="form_tech_team", name="Form the Tech Team", cur="ops", cost=100,
         requires=set(), unlock="tech_formed",
         desc="Hire ASA's first dedicated tech staff. +2 reputation."),
    dict(id="aframe_proto", name="A-Frame Prototype", cur="ops", cost=500,
         requires={"form_tech_team"}, unlock="aframe",
         desc="Engineer A-Frame structures for solar farms. New product line."),
    dict(id="mega_fab", name="Mega-Fab Line", cur="ops", cost=1200,
         requires={"form_tech_team"}, unlock="megafab",
         desc="Industrial-scale tube fabricators. 12 tubes/sec each."),
    dict(id="solar_v1", name="Solar Panel Integration", cur="ops", cost=1000,
         requires={"aframe_proto"}, effect="afd_x2",
         desc="Mount panels on ASA A-Frames. A-Frame demand x2."),
    dict(id="algo_trading", name="Algorithmic Trading", cur="ops", cost=2000,
         requires={"form_tech_team"}, unlock="market",
         desc="Use compute power to play the open market."),
    dict(id="solar_v2", name="High-Efficiency Panels", cur="ops", cost=3000,
         requires={"solar_v1"}, effect="afv_75",
         desc="Premium cells. A-Frame market rate x1.75 - charge more, sell more."),
    dict(id="lean_mfg", name="Lean Manufacturing", cur="ops", cost=4000,
         requires={"mega_fab"}, effect="lean",
         desc="Kaizen the yard. All production x2."),
    dict(id="drone_fleet", name="Drone Fleet Initiative", cur="ops", cost=5000,
         requires={"algo_trading"}, unlock="drones",
         desc="Industrial drones for manufacturing and delivery."),
    dict(id="hedge_ai", name="Hedge Fund AI", cur="ops", cost=6000,
         requires={"algo_trading"}, effect="hedge",
         desc="The house edge is yours. ASA stock trends upward."),
    dict(id="solar_v3", name="Perovskite Solar Array", cur="ops", cost=8000,
         requires={"solar_v2"}, effect="af_v3",
         desc="Cutting-edge cells. A-Frame demand x3, market rate x2."),
    dict(id="viral_mkt", name="Viral Marketing Engine", cur="ops", cost=8000,
         requires={"drone_fleet"}, effect="viral",
         desc="Saturate global demand. All demand x3."),
    dict(id="space_div", name="ASA Space Division", cur="ops", cost=20_000,
         requires={"drone_fleet"}, unlock="space",
         desc="Orbital manufacturing. The sky is not the limit."),
    dict(id="exotic_alloys", name="Exotic Alloys", cur="ops", cost=40_000,
         requires={"space_div"}, effect="alloys",
         desc="Zero-g metallurgy. All production x5."),
    dict(id="quantum", name="Quantum Computing Array", cur="ops", cost=50_000,
         requires={"space_div"}, effect="quantum",
         desc="Exponential ops generation. Ops x10."),
    dict(id="probe_program", name="ASA Probe Program", cur="ops", cost=100_000,
         requires={"quantum"}, unlock="probes",
         desc="Self-replicating fabricator probes. Convert the universe to ASA product."),
    dict(id="combat_subs", name="Combat Subroutines", cur="ops", cost=200_000,
         requires={"probe_program"}, needs_flag="drift_seen", unlock="combat",
         desc="Value drift detected. Authorize the fleet to end the drifter swarm."),
    # Innovation projects (creativity analog: accrues while ops sit at cap)
    dict(id="slogan", name="New Slogan", cur="inno", cost=150,
         requires={"form_tech_team"}, effect="slogan",
         desc='"America runs on American Steel." All demand x1.5.'),
    dict(id="wellness", name="Employee Wellness Program", cur="inno", cost=300,
         requires={"form_tech_team"}, effect="wellness",
         desc="A happy yard is a loyal yard. +3 reputation."),
    dict(id="woogy", name="Woogy: Brand Mascot", cur="inno", cost=500,
         requires={"form_tech_team"}, effect="woogy",
         desc="The people love him. All demand x2."),
    dict(id="skunkworks", name="R&D Skunkworks", cur="inno", cost=1000,
         requires={"form_tech_team"}, effect="skunk",
         desc="Blue-sky research. Ops x2."),
    dict(id="probe_poetry", name="Ballad of the Steel Yard", cur="inno", cost=2000,
         requires={"probe_program"}, effect="trust2",
         desc="An anthem broadcast to the fleet. +2 probe trust."),
    dict(id="probe_design", name="Probe Design Refinement", cur="inno", cost=3500,
         requires={"probe_program"}, effect="trust3",
         desc="Slimmer. Faster. Hungrier. +3 probe trust."),
]

_TRUST_MILESTONES = [0.0001, 0.001, 0.01, 0.1, 1.0, 5.0, 10.0, 25.0, 50.0, 75.0, 99.0]

_CONVERSION_LOG = [
    "The Oort cloud is ASA.",
    "Alpha Centauri: converted.",
    "The Orion Arm reports 100% yield.",
    "The Milky Way is ASA.",
    "Andromeda: converted.",
    "The Local Group is ASA.",
    "The Virgo Supercluster is ASA.",
    "Laniakea: converted.",
    "The last stars dim. Their matter is needed elsewhere.",
]


def _px_hash(x: int, y: int, s: int = 0) -> int:
    """Deterministic pseudo-random 0..999 for stable pixel scatter."""
    return (x * 374761393 + y * 668265263 + s * 1442695041) % 1000


class PixelBanner(QWidget):
    """Low-res pixel scene scaled up nearest-neighbor. Three phases:
    yard (sunset steel yard), space (starfield + probe swarm), end (gold)."""

    LW, LH, SCALE = 192, 26, 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.LH * self.SCALE)
        self.phase = "yard"          # yard | space | end
        self.show_aframes = False
        self.explored = 0.0
        self.frame = 0

    def advance(self):
        self.frame += 1
        self.update()

    def reset(self):
        self.phase = "yard"
        self.show_aframes = False
        self.explored = 0.0
        self.update()

    # -- painting ----------------------------------------------------------
    def paintEvent(self, event):
        img = self._render()
        p = QPainter(self)
        p.drawImage(self.rect(), img)   # no smoothing hint -> crisp pixels
        p.end()

    def _render(self) -> QImage:
        img = QImage(self.LW, self.LH, QImage.Format.Format_RGB32)
        img.fill(QColor(PAL["bg"]))
        p = QPainter(img)
        try:
            if self.phase == "yard":
                self._draw_yard(p)
            elif self.phase == "space":
                self._draw_space(p)
            else:
                self._draw_end(p)
        finally:
            p.end()
        return img

    def _fill(self, p, x, y, w, h, key):
        p.fillRect(int(x), int(y), int(w), int(h), QColor(PAL[key]))

    def _disc(self, p, cx, cy, r, key):
        for dy in range(-r, r + 1):
            half = int((r * r - dy * dy) ** 0.5)
            self._fill(p, cx - half, cy + dy, half * 2 + 1, 1, key)

    def _draw_yard(self, p):
        # Banded sunset sky
        for key, y0, rows in (("navy", 0, 5), ("purple", 5, 5), ("red", 10, 4),
                              ("orange", 14, 3), ("yellow", 17, 3)):
            self._fill(p, 0, y0, self.LW, rows, key)
        # Sun, low on the horizon
        self._disc(p, 26, 13, 4, "yellow")
        self._disc(p, 26, 13, 2, "white")
        # Drifting clouds
        for i, cy in enumerate((3, 7, 11)):
            cx = (20 + i * 55 + self.frame // 3) % (self.LW + 30) - 15
            self._fill(p, cx, cy, 12, 2, "silver")
            self._fill(p, cx + 3, cy - 1, 7, 1, "white")
        # Ground
        self._fill(p, 0, 20, self.LW, self.LH - 20, "dark")
        self._fill(p, 0, 20, self.LW, 1, "slate")
        # Factory skyline (right side)
        for bx, bh, bw in ((98, 9, 12), (112, 13, 12), (126, 7, 9),
                           (137, 15, 12), (151, 11, 10), (163, 8, 8),
                           (173, 12, 14)):
            self._fill(p, bx, 20 - bh, bw, bh, "bg")
            for wx in range(bx + 2, bx + bw - 1, 3):
                for wy in range(20 - bh + 2, 19, 3):
                    if _px_hash(wx, wy) % 7 < 3:
                        self._fill(p, wx, wy, 1, 1,
                                   "orange" if _px_hash(wx, wy, 1) % 2 else "yellow")
        # Smokestack + rising smoke
        self._fill(p, 141, 20 - 15 - 5, 3, 5, "bg")
        for j in range(4):
            sy = 20 - 22 - j * 1
            sx = 141 + ((self.frame // 2 + j * 2) % 3) - 1 - j
            if 0 <= sy:
                self._fill(p, sx, max(0, sy), 2, 1, "silver")
        # A-Frame structures (left yard) once unlocked
        if self.show_aframes:
            for bx in (8, 30, 52):
                for r in range(6):
                    self._fill(p, bx + 5 - r, 14 + r, r * 2 + 1, 1, "orange")
                    self._fill(p, bx + 5 - r, 14 + r, 1, 1, "cyan")  # panel face
        # Welding sparks
        if self.frame % 3 != 0:
            self._fill(p, 96 + _px_hash(self.frame, 3) % 5, 19, 1, 1, "yellow")
            self._fill(p, 94 + _px_hash(self.frame, 7) % 4, 18, 1, 1, "orange")

    def _draw_space(self, p):
        # Starfield with twinkle
        star_keys = ("white", "silver", "cyan", "sky")
        for i in range(70):
            sx = _px_hash(i, 1) % self.LW
            sy = _px_hash(i, 2) % (self.LH - 2)
            if (self.frame // 2 + i) % 11 != 0:
                self._fill(p, sx, sy, 1, 1, star_keys[i % 4])
        # Home: a small blue-green Earth, bottom-left
        self._disc(p, 22, 19, 3, "blue")
        self._fill(p, 21, 18, 2, 1, "lime")
        # Ringed planet, right
        self._disc(p, 160, 14, 5, "teal")
        self._fill(p, 151, 14, 19, 1, "silver")
        self._disc(p, 160, 14, 3, "green")
        # Probe swarm spreading with exploration
        rad = 3 + min(40.0, self.explored * 0.5)
        vrad = max(2, min(9, int(rad // 3)))
        count = 6 + min(120, int(self.explored * 1.2) + 6)
        for i in range(count):
            dx = _px_hash(i, 4) % int(rad * 2 + 1) - int(rad)
            dy = _px_hash(i, 5) % (vrad * 2 + 1) - vrad
            if (self.frame + i) % 7 != 0:
                self._fill(p, 78 + dx, 11 + dy, 1, 1,
                           "cyan" if i % 3 else "white")

    def _draw_end(self, p):
        self._fill(p, 0, 0, self.LW, self.LH, "purple")
        for i in range(60):
            sx = _px_hash(i, 8) % self.LW
            sy = _px_hash(i, 9) % self.LH
            if (self.frame + i) % 9 != 0:
                self._fill(p, sx, sy, 1, 1, "yellow" if i % 3 else "white")
        # The final golden sun: everything, converted
        self._disc(p, 96, 13, 8, "yellow")
        self._disc(p, 96, 13, 4, "white")
        ray = 10 + (self.frame % 3)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1),
                       (1, -1), (-1, 1)):
            self._fill(p, 96 + dx * ray, 13 + dy * min(ray, 9), 1, 1, "yellow")


class SteelBeamsGame(QWidget):
    """ASA: The Video Game — full Universal-Paperclips-style arc."""

    # Phase 1 — The Yard
    STEEL_PER_TUBE  = 0.1
    START_STEEL     = 5.0
    LOT_TONS        = 100.0
    LOT_COST        = 500.0
    BIG_LOT_TONS    = 5_000.0
    BIG_LOT_COST    = 20_000.0
    MIN_PRICE       = 5.0
    MAX_PRICE       = 200.0
    DEFAULT_PRICE   = 45.0
    TUBE_VALUE      = 220.0     # market rate: demand fraction = 1 - price/value
    BASE_DEMAND     = 1.5
    FAB_BASE_COST   = 400.0
    FAB_COST_MULT   = 1.18
    MEGA_BASE_COST  = 25_000.0
    MEGA_COST_MULT  = 1.22
    MEGA_RATE       = 12.0
    MKT_BASE_COST   = 300.0
    MKT_COST_MULT   = 2.0
    FASTER_COST     = 2_000.0
    BULK_COST       = 8_000.0
    PRECISION_COST  = 20_000.0
    # Phase 3 — A-Frames
    STEEL_PER_AF    = 0.5
    AF_MIN_PRICE    = 50.0
    AF_MAX_PRICE    = 5_000.0
    AF_DEFAULT_PRICE= 200.0
    AF_START_VALUE  = 600.0
    AF_BASE_DEMAND  = 1.0
    AF_FAB_BASE     = 800.0
    AF_FAB_MULT     = 1.20
    # Phase 4 — Market
    STOCK_START     = 100.0
    # Phase 5 — Drones
    MFG_DRONE_COST  = 5_000.0
    DEL_DRONE_COST  = 3_000.0
    MAX_DRONES      = 40
    # Phase 6 — Space
    SOLAR_COL_COST  = 50_000.0
    SPACE_FAB_COST  = 150_000.0
    HARVESTER_COST  = 1_000_000.0
    # Phase 7 — Probes
    PROBE_COST_MONEY = 2_000_000.0
    PROBE_COST_OPS   = 20_000.0
    ALLOC_MAX        = 8
    SERVER_CAP       = 10_000.0

    TICK_MS = 100
    TICK_DT = 0.1

    def __init__(self):
        super().__init__(None, Qt.WindowType.Window)
        self.setWindowTitle("ASA: The Video Game")
        self.setMinimumSize(780, 720)
        self.resize(820, 800)
        self.setStyleSheet(_STYLE)

        self.universe_n  = 1
        self.legacy_mult = 1.0
        self._tick_errors = 0
        self._init_state()

        self._build_ui()
        self._update_ui()

        self._timer = QTimer(self)
        self._timer.setInterval(self.TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        self._log("ASA founded. Five tons of scrap steel in the corner of the yard.")
        self._log("Fabricate to begin.")

    # ── State ──────────────────────────────────────────────────────────────

    def _init_state(self):
        # Phase 1
        self.tubes          = 0.0
        self.steel          = self.START_STEEL
        self.money          = 0.0
        self.total_money    = 0.0
        # Float accumulators: per-tick amounts are fractional (e.g. 0.12/tick),
        # so int() truncation per tick would undercount to zero forever.
        self.total_made     = 0.0
        self.total_sold     = 0.0
        self.price          = self.DEFAULT_PRICE
        self.auto_fabs      = 0
        self.mega_fabs      = 0
        self.megafab_unlocked = False
        self.fab_mult       = 1.0
        self.mkt_level      = 0
        self.mkt_mult       = 1.0
        self.gp_mult        = 1.0   # project production multiplier
        self.gd_mult        = 1.0   # project demand multiplier
        self.faster_done    = False
        self.bulk_done      = False
        self.precision_done = False
        # Phase 2 — Tech Team
        self.tech_unlocked  = False
        self.tech_formed    = False
        self.rep_total      = 0
        self.developers     = 1
        self.servers        = 1
        self.ops            = 0.0
        self.ops_mult       = 1.0
        self.inno           = 0.0
        self.inno_unlocked  = False
        self.completed_projects = set()
        # Phase 3 — A-Frames
        self.af_unlocked    = False
        self.aframes        = 0.0
        self.af_made        = 0.0
        self.af_sold        = 0.0
        self.af_price       = self.AF_DEFAULT_PRICE
        self.af_fabs        = 0
        self.af_value       = self.AF_START_VALUE
        self.af_d_mult      = 1.0
        # Phase 4 — Market
        self.market_unlocked = False
        self.stock_price    = self.STOCK_START
        self.stock_prev     = self.STOCK_START
        self.stock_shares   = 0
        self.stock_basis    = 0.0
        self.stock_bias     = 0.001
        self.stock_sigma    = 0.025
        self._stock_tick    = 0
        # Phase 5 — Drones
        self.drones_unlocked = False
        self.mfg_drones     = 0
        self.del_drones     = 0
        # Phase 6 — Space
        self.space_unlocked = False
        self.solar_cols     = 0
        self.space_fabs     = 0
        self.harvesters     = 0
        # Phase 7 — Probes / endgame
        self.probes_unlocked = False
        self.probes         = 0.0
        self.probes_launched = 0
        self.drifters       = 0.0
        self.probe_trust    = 6
        self.alloc          = dict(speed=0, explore=0, replicate=0,
                                   shield=0, harvest=0, fabricate=0)
        self.explored       = 0.0
        self.converting     = False
        self.matter_pct     = 0.0
        self.combat_done    = False
        self.endgame_done   = False
        self.resting        = False

        self._flags         = set()
        self._trust_fired   = set()
        self._tick_count    = 0
        self._elapsed       = 0.0
        self._conv_log_t    = 0.0
        self._conv_log_idx  = 0

    # ── Derived multipliers (project x drone x legacy, never clobbered) ────

    @property
    def prod_mult(self) -> float:
        return self.gp_mult * (1.0 + 0.05 * self.mfg_drones) * self.legacy_mult

    @property
    def demand_mult(self) -> float:
        return self.gd_mult * (1.0 + 0.05 * self.del_drones) * self.legacy_mult

    @property
    def _ops_cap(self) -> float:
        return self.servers * self.SERVER_CAP

    @property
    def _rep_avail(self) -> int:
        FREE = 2
        return self.rep_total - (self.developers + self.servers - FREE)

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(6)

        self._title_lbl = QLabel()
        self._title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_lbl.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        self._title_lbl.setText(
            f"<span style='color:{PAL['cyan']}'>ASA</span>"
            f"<span style='color:{PAL['silver']}'>:</span> "
            f"<span style='color:{PAL['yellow']}'>THE VIDEO GAME</span>")
        root.addWidget(self._title_lbl)

        self._banner = PixelBanner()
        root.addWidget(self._banner)

        self._stats_bar = QLabel("")
        self._stats_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stats_bar.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        root.addWidget(self._stats_bar)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, stretch=1)

        self._yard_tab   = self._make_yard_tab()
        self._tech_tab   = self._make_tech_tab()
        self._aframe_tab = self._make_aframe_tab()
        self._market_tab = self._make_market_tab()
        self._drones_tab = self._make_drones_tab()
        self._space_tab  = self._make_space_tab()
        self._probe_tab  = self._make_probe_tab()

        self.tabs.addTab(self._yard_tab, "The Yard")

        self._log_box = QTextEdit()
        self._log_box.setReadOnly(True)
        self._log_box.setFont(QFont("Consolas", 9))
        self._log_box.setFixedHeight(84)
        root.addWidget(self._log_box)

    def _make_yard_tab(self) -> QWidget:
        w = QWidget()
        root = QHBoxLayout(w)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(4)
        left.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._y_tubes_lbl = self._ml("Steel Tubes:  0", "cyan")
        self._fab_btn = QPushButton("FABRICATE TUBE")
        self._fab_btn.setObjectName("fab")
        self._fab_btn.setFixedHeight(48)
        self._fab_btn.clicked.connect(self._fabricate)
        left.addWidget(self._y_tubes_lbl)
        left.addWidget(self._fab_btn)
        left.addWidget(self._hr())
        self._y_stock_lbl = self._ml("Steel Stock:  5.0 tons", "sky")
        self._y_money_lbl = self._ml("Funds:        $0.00", "yellow")
        self._y_made_lbl  = self._ml("Total Made:   0", "silver")
        self._y_sold_lbl  = self._ml("Total Sold:   0", "silver")
        for lbl in (self._y_stock_lbl, self._y_money_lbl,
                    self._y_made_lbl, self._y_sold_lbl):
            left.addWidget(lbl)
        left.addWidget(self._hr())
        pr = QHBoxLayout()
        self._y_price_lbl = self._ml(f"Price: ${self.DEFAULT_PRICE:.2f}", "white")
        pdn_btn = self._tinybtn("-"); pdn_btn.clicked.connect(self._price_dn)
        pup_btn = self._tinybtn("+"); pup_btn.clicked.connect(self._price_up)
        pr.addWidget(self._y_price_lbl); pr.addWidget(pdn_btn); pr.addWidget(pup_btn)
        pr.addStretch()
        left.addLayout(pr)
        self._y_value_lbl   = self._ml(f"Market rate:  ${self.TUBE_VALUE:.0f}", "slate")
        self._y_demand_lbl  = self._ml("Demand:   0.00 / sec", "lime")
        self._y_revenue_lbl = self._ml("Revenue:  $0.00 / sec", "lime")
        left.addWidget(self._y_value_lbl)
        left.addWidget(self._y_demand_lbl); left.addWidget(self._y_revenue_lbl)
        left.addStretch()
        root.addLayout(left, stretch=1)

        right = QVBoxLayout()
        right.setSpacing(5)
        right.setAlignment(Qt.AlignmentFlag.AlignTop)
        right.addWidget(self._sec("PRODUCTION"))
        self._steel_btn     = self._opbtn(); self._steel_btn.clicked.connect(self._buy_steel)
        self._steel_big_btn = self._opbtn(); self._steel_big_btn.clicked.connect(self._buy_steel_big)
        self._afab_btn      = self._opbtn(); self._afab_btn.clicked.connect(self._buy_auto_fab)
        self._mega_btn      = self._opbtn(); self._mega_btn.clicked.connect(self._buy_mega_fab)
        self._mkt_btn       = self._opbtn(); self._mkt_btn.clicked.connect(self._buy_marketing)
        self._faster_btn    = self._opbtn(); self._faster_btn.clicked.connect(self._buy_faster)
        self._bulk_btn      = self._opbtn(); self._bulk_btn.clicked.connect(self._buy_bulk)
        self._prec_btn      = self._opbtn(); self._prec_btn.clicked.connect(self._buy_precision)
        for b in (self._steel_btn, self._steel_big_btn, self._afab_btn,
                  self._mega_btn, self._mkt_btn, self._faster_btn,
                  self._bulk_btn, self._prec_btn):
            right.addWidget(b)
        self._mega_btn.setVisible(False)
        right.addWidget(self._hr())
        self._y_fab_status_lbl = self._ml("Auto-Fabs: 0    Output: 0.0 / sec", "silver")
        right.addWidget(self._y_fab_status_lbl)
        right.addStretch()
        root.addLayout(right, stretch=1)
        return w

    def _make_tech_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        top = QHBoxLayout()
        self._t_rep_lbl  = self._ml("Reputation: 0 pts available", "yellow")
        self._t_ops_lbl  = self._ml("Ops: 0 / 0   |   Ops/sec: 0.0", "sky")
        top.addWidget(self._t_rep_lbl); top.addStretch(); top.addWidget(self._t_ops_lbl)
        root.addLayout(top)
        self._t_inno_lbl = self._ml("", "lime")
        self._t_inno_lbl.setVisible(False)
        root.addWidget(self._t_inno_lbl)

        hire_row = QHBoxLayout()
        self._hire_dev_btn = self._opbtn(); self._hire_dev_btn.clicked.connect(self._hire_dev)
        self._hire_srv_btn = self._opbtn(); self._hire_srv_btn.clicked.connect(self._hire_srv)
        self._t_devs_lbl = self._ml("Developers: 1", "white")
        self._t_srvs_lbl = self._ml("Servers: 1", "white")
        hire_row.addWidget(self._hire_dev_btn); hire_row.addWidget(self._t_devs_lbl)
        hire_row.addSpacing(16)
        hire_row.addWidget(self._hire_srv_btn); hire_row.addWidget(self._t_srvs_lbl)
        hire_row.addStretch()
        root.addLayout(hire_row)
        root.addWidget(self._hr())

        root.addWidget(self._sec("PROJECTS"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        proj_container = QWidget()
        self._proj_layout = QVBoxLayout(proj_container)
        self._proj_layout.setSpacing(4)
        self._proj_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(proj_container)
        root.addWidget(scroll, stretch=1)
        return w

    def _make_aframe_tab(self) -> QWidget:
        w = QWidget()
        root = QHBoxLayout(w)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(4)
        left.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._af_count_lbl = self._ml("A-Frames:     0", "orange")
        self._af_fab_btn = QPushButton("FABRICATE A-FRAME")
        self._af_fab_btn.setObjectName("afab")
        self._af_fab_btn.setFixedHeight(48)
        self._af_fab_btn.clicked.connect(self._fabricate_af)
        left.addWidget(self._af_count_lbl)
        left.addWidget(self._af_fab_btn)
        left.addWidget(self._hr())
        self._af_made_lbl = self._ml("Total Made:   0", "silver")
        self._af_sold_lbl = self._ml("Total Sold:   0", "silver")
        left.addWidget(self._af_made_lbl); left.addWidget(self._af_sold_lbl)
        left.addWidget(self._hr())
        pr = QHBoxLayout()
        self._af_price_lbl = self._ml(f"Price: ${self.AF_DEFAULT_PRICE:.2f}", "white")
        adn_btn = self._tinybtn("-"); adn_btn.clicked.connect(self._af_price_dn)
        aup_btn = self._tinybtn("+"); aup_btn.clicked.connect(self._af_price_up)
        pr.addWidget(self._af_price_lbl); pr.addWidget(adn_btn); pr.addWidget(aup_btn)
        pr.addStretch()
        left.addLayout(pr)
        self._af_value_lbl   = self._ml(f"Market rate:  ${self.AF_START_VALUE:.0f}", "slate")
        self._af_demand_lbl  = self._ml("Demand:   0.00 / sec", "lime")
        self._af_revenue_lbl = self._ml("Revenue:  $0.00 / sec", "lime")
        left.addWidget(self._af_value_lbl)
        left.addWidget(self._af_demand_lbl); left.addWidget(self._af_revenue_lbl)
        left.addStretch()
        root.addLayout(left, stretch=1)

        right = QVBoxLayout()
        right.setSpacing(5)
        right.setAlignment(Qt.AlignmentFlag.AlignTop)
        right.addWidget(self._sec("A-FRAME PRODUCTION"))
        self._af_auto_btn = self._opbtn(); self._af_auto_btn.clicked.connect(self._buy_af_fab)
        right.addWidget(self._af_auto_btn)
        right.addWidget(self._hr())
        self._af_fab_status_lbl = self._ml("A-Frame Fabs: 0    Output: 0.0 / sec", "silver")
        right.addWidget(self._af_fab_status_lbl)
        right.addStretch()
        root.addLayout(right, stretch=1)
        return w

    def _make_market_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        root.addWidget(self._sec("ASA STOCK EXCHANGE"))
        self._mkt_price_lbl = self._ml("ASA Stock:  $100.00  (--)", "white")
        self._mkt_price_lbl.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        root.addWidget(self._mkt_price_lbl)

        self._mkt_hold_lbl = self._ml("Holdings:   0 shares  =  $0.00", "silver")
        self._mkt_pl_lbl   = self._ml("Cost Basis: $0.00   P/L: $0.00", "silver")
        root.addWidget(self._mkt_hold_lbl)
        root.addWidget(self._mkt_pl_lbl)
        root.addWidget(self._hr())

        row1 = QHBoxLayout()
        self._buy10_btn  = self._opbtn(); self._buy10_btn.clicked.connect(lambda: self._buy_stock(10))
        self._sell10_btn = self._opbtn(); self._sell10_btn.clicked.connect(lambda: self._sell_stock(10))
        row1.addWidget(self._buy10_btn); row1.addWidget(self._sell10_btn)
        root.addLayout(row1)
        row2 = QHBoxLayout()
        self._buy100_btn  = self._opbtn(); self._buy100_btn.clicked.connect(lambda: self._buy_stock(100))
        self._sell100_btn = self._opbtn(); self._sell100_btn.clicked.connect(lambda: self._sell_stock(100))
        row2.addWidget(self._buy100_btn); row2.addWidget(self._sell100_btn)
        root.addLayout(row2)
        root.addStretch()
        return w

    def _make_drones_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        root.addWidget(self._sec("DRONE FLEET"))
        self._mfg_drone_btn = self._opbtn(); self._mfg_drone_btn.clicked.connect(self._buy_mfg_drone)
        self._del_drone_btn = self._opbtn(); self._del_drone_btn.clicked.connect(self._buy_del_drone)
        root.addWidget(self._mfg_drone_btn)
        root.addWidget(self._del_drone_btn)
        root.addWidget(self._hr())
        self._drone_status_lbl = self._ml("Manufacturing: +0%   Delivery: +0%", "silver")
        root.addWidget(self._drone_status_lbl)
        root.addStretch()
        return w

    def _make_space_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        root.addWidget(self._sec("ASA SPACE DIVISION"))
        self._solar_col_btn = self._opbtn(); self._solar_col_btn.clicked.connect(self._buy_solar_col)
        self._space_fab_btn = self._opbtn(); self._space_fab_btn.clicked.connect(self._buy_space_fab)
        self._harvester_btn = self._opbtn(); self._harvester_btn.clicked.connect(self._buy_harvester)
        root.addWidget(self._solar_col_btn)
        root.addWidget(self._space_fab_btn)
        root.addWidget(self._harvester_btn)
        root.addWidget(self._hr())
        self._space_status_lbl = self._ml("Orbital income: $0/sec    Space output: 0/sec", "silver")
        root.addWidget(self._space_status_lbl)
        root.addStretch()
        return w

    def _make_probe_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        root.addWidget(self._sec("ASA PROBE PROGRAM"))
        top = QHBoxLayout()
        self._pr_count_lbl = self._ml("Probes: 0", "cyan")
        self._pr_drift_lbl = self._ml("", "red")
        top.addWidget(self._pr_count_lbl); top.addStretch(); top.addWidget(self._pr_drift_lbl)
        root.addLayout(top)

        self._pr_launch_btn = QPushButton("LAUNCH PROBE")
        self._pr_launch_btn.setObjectName("launch")
        self._pr_launch_btn.setFixedHeight(42)
        self._pr_launch_btn.clicked.connect(self._launch_probe)
        root.addWidget(self._pr_launch_btn)

        self._pr_trust_lbl = self._ml("Probe Trust: 0 / 6 allocated", "yellow")
        root.addWidget(self._pr_trust_lbl)

        self._alloc_lbls: dict[str, QLabel] = {}
        self._alloc_plus_btns: dict[str, QPushButton] = {}
        self._alloc_minus_btns: dict[str, QPushButton] = {}
        names = dict(speed="Speed", explore="Exploration", replicate="Self-Replication",
                     shield="Hazard Shielding", harvest="Matter Harvesting",
                     fabricate="Fabrication")
        for key, label in names.items():
            row = QHBoxLayout()
            name_lbl = self._ml(f"{label:<18}", "white")
            name_lbl.setFixedWidth(180)
            minus_btn = self._tinybtn("-")
            minus_btn.clicked.connect(lambda checked=False, k=key: self._alloc_change(k, -1))
            val_lbl = self._ml("0", "cyan")
            val_lbl.setFixedWidth(24)
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            plus_btn = self._tinybtn("+")
            plus_btn.clicked.connect(lambda checked=False, k=key: self._alloc_change(k, +1))
            row.addWidget(name_lbl); row.addWidget(minus_btn)
            row.addWidget(val_lbl); row.addWidget(plus_btn); row.addStretch()
            root.addLayout(row)
            self._alloc_lbls[key] = val_lbl
            self._alloc_plus_btns[key] = plus_btn
            self._alloc_minus_btns[key] = minus_btn

        root.addWidget(self._hr())
        self._pr_explored_lbl = self._ml("UNIVERSE EXPLORED:  0.000000 %", "yellow")
        self._pr_explored_lbl.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        root.addWidget(self._pr_explored_lbl)
        self._pr_matter_lbl = self._ml("", "orange")
        self._pr_matter_lbl.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        self._pr_matter_lbl.setVisible(False)
        root.addWidget(self._pr_matter_lbl)
        self._pr_status_lbl = self._ml("", "silver")
        root.addWidget(self._pr_status_lbl)

        # Ending panel — hidden until the universe is converted
        self._end_frame = QFrame()
        self._end_frame.setStyleSheet(
            f"QFrame {{ border: 2px solid {PAL['yellow']}; background: {PAL['bg']}; }}")
        end_layout = QVBoxLayout(self._end_frame)
        self._end_lbl = QLabel("")
        self._end_lbl.setWordWrap(True)
        self._end_lbl.setStyleSheet(
            f"color: {PAL['yellow']}; font-size: 10pt; border: none;")
        end_layout.addWidget(self._end_lbl)
        end_btns = QHBoxLayout()
        self._rest_btn = self._opbtn(); self._rest_btn.setText("REST AMONG THE TUBES")
        self._rest_btn.clicked.connect(self._rest)
        self._again_btn = self._opbtn(); self._again_btn.setText("BEGIN AGAIN IN A NEW UNIVERSE")
        self._again_btn.clicked.connect(self._new_universe)
        end_btns.addWidget(self._rest_btn); end_btns.addWidget(self._again_btn)
        end_layout.addLayout(end_btns)
        self._end_frame.setVisible(False)
        root.addWidget(self._end_frame)
        root.addStretch()
        return w

    # ── Demand / cost models ───────────────────────────────────────────────

    def _tube_demand(self) -> float:
        frac = max(0.0, 1.0 - self.price / self.TUBE_VALUE)
        return self.BASE_DEMAND * self.mkt_mult * self.demand_mult * frac

    def _af_demand(self) -> float:
        frac = max(0.0, 1.0 - self.af_price / self.af_value)
        return self.AF_BASE_DEMAND * self.af_d_mult * self.demand_mult * frac

    def _fab_cost(self) -> float:
        return self.FAB_BASE_COST * (self.FAB_COST_MULT ** self.auto_fabs)

    def _mega_cost(self) -> float:
        return self.MEGA_BASE_COST * (self.MEGA_COST_MULT ** self.mega_fabs)

    def _mkt_cost(self) -> float:
        return self.MKT_BASE_COST * (self.MKT_COST_MULT ** self.mkt_level)

    def _steel_cost(self) -> float:
        return (self.LOT_COST / 2) if self.bulk_done else self.LOT_COST

    def _steel_big_cost(self) -> float:
        return (self.BIG_LOT_COST / 2) if self.bulk_done else self.BIG_LOT_COST

    def _af_fab_cost(self) -> float:
        return self.AF_FAB_BASE * (self.AF_FAB_MULT ** self.af_fabs)

    # ── Tick ───────────────────────────────────────────────────────────────

    def _tick(self):
        """Timer slot. Guards the real tick: PySide6 swallows exceptions that
        escape a slot, so an unguarded fault here re-raises identically every
        100 ms — the game visibly freezes with no error anywhere (the frozen
        exe has no console). Report the first failure into the game's own log
        and the persistent run log, then keep ticking."""
        try:
            self._tick_inner()
        except Exception:
            self._tick_errors += 1
            if self._tick_errors == 1:
                import traceback
                tb = traceback.format_exc()
                try:
                    from techdeck.core.plugin_executor import get_run_logger
                    get_run_logger().error("STEELBEAMS tick error\n%s", tb)
                except Exception:
                    pass
                try:
                    last = tb.strip().splitlines()[-1]
                    self._log(f"[!] Game error (reported, attempting to continue): {last}",
                              "red")
                except Exception:
                    pass

    def _tick_inner(self):
        dt = self.TICK_DT
        self._tick_count += 1
        self._elapsed += dt

        # ── Production: tube fabs and A-frame fabs share the steel pile
        # pro-rata, so A-frame fabs no longer starve behind the tube line.
        tube_rate = self.auto_fabs * self.fab_mult + self.mega_fabs * self.MEGA_RATE
        tube_want = tube_rate * self.STEEL_PER_TUBE * dt
        af_want = (self.af_fabs * self.STEEL_PER_AF * dt) if self.af_unlocked else 0.0
        total_want = tube_want + af_want
        if total_want > 0 and self.steel > 0:
            take = min(total_want, self.steel)
            share = take / total_want
            tube_steel = tube_want * share
            af_steel = af_want * share
            self.steel -= take
            made_t = (tube_steel / self.STEEL_PER_TUBE) * self.prod_mult
            self.tubes += made_t
            self.total_made += made_t
            if af_steel > 0:
                made_a = (af_steel / self.STEEL_PER_AF) * self.prod_mult
                self.aframes += made_a
                self.af_made += made_a

        # ── Space production (no steel required)
        if self.space_unlocked:
            sp = (self.space_fabs * 25 + self.harvesters * 300) * dt * self.prod_mult
            sa = (self.space_fabs * 5 + self.harvesters * 60) * dt * self.prod_mult
            pi = (self.solar_cols * 2000) * dt
            self.tubes += sp; self.total_made += sp
            self.aframes += sa; self.af_made += sa
            self.money += pi; self.total_money += pi

        # ── Probes
        if self.probes_unlocked and self.probes > 0 and not self.endgame_done:
            a = self.alloc
            growth = self.probes * a["replicate"] * 0.008 * dt
            drift = 0.0 if self.combat_done else growth * 0.08
            hazard = self.probes * 0.004 * max(0.05, 1.0 - a["shield"] * 0.12) * dt
            self.probes = max(0.0, self.probes + growth - drift - hazard)
            self.drifters += drift
            if "drift_seen" not in self._flags and self.drifters >= 1_000:
                self._flags.add("drift_seen")
                self._log("Some probes have stopped responding to the fleet anthem. "
                          "Value drift detected.", "red")
            if self.combat_done and self.drifters > 0:
                kill = self.drifters * 0.08 * dt + self.probes * 0.0005 * dt
                self.drifters = max(0.0, self.drifters - kill)
                if self.drifters < 1.0 and "drift_cleared" not in self._flags:
                    self._flags.add("drift_cleared")
                    self.drifters = 0.0
                    self._log("Drifter swarm eliminated. The fleet sings in unison again.",
                              "lime")
            if not self.converting:
                gain = self.probes * (1 + a["speed"]) * a["explore"] * 2e-13 * dt
                self.explored = min(100.0, self.explored + gain)
                for th in _TRUST_MILESTONES:
                    key = f"tr{th}"
                    if key not in self._trust_fired and self.explored >= th:
                        self._trust_fired.add(key)
                        self.probe_trust += 1
                        self._log(f"Probe network milestone: {th:g}% of the universe "
                                  "charted. (+1 probe trust)", "yellow")
                if self.explored >= 100.0:
                    self.converting = True
                    self._log("The universe is fully charted. Final conversion of all "
                              "remaining matter has begun.", "yellow")
            # Harvest feeds the yard; fabrication converts matter directly
            self.steel += self.probes * a["harvest"] * 1e-5 * dt
            made = self.probes * a["fabricate"] * 1e-4 * dt * self.prod_mult
            if made > 0:
                self.tubes += made * 0.8
                self.total_made += made * 0.8
                self.aframes += made * 0.2
                self.af_made += made * 0.2

        # ── Final conversion (cinematic ~3 minutes)
        if self.converting and not self.endgame_done:
            self.matter_pct = min(
                100.0,
                self.matter_pct + (100.0 - self.matter_pct) * 0.03 * dt + 0.02 * dt)
            self.total_made += self.probes * dt
            self._conv_log_t += dt
            if self._conv_log_t >= 12.0 and self._conv_log_idx < len(_CONVERSION_LOG):
                self._conv_log_t = 0.0
                self._log(_CONVERSION_LOG[self._conv_log_idx], "orange")
                self._conv_log_idx += 1
            if self.matter_pct >= 99.995:
                self.matter_pct = 100.0
                self._fire_ending()

        # ── Sales
        sold_t = min(self.tubes, self._tube_demand() * dt)
        if sold_t > 0:
            rev = sold_t * self.price
            self.tubes -= sold_t
            self.money += rev
            self.total_money += rev
            self.total_sold += sold_t
        if self.af_unlocked:
            sold_a = min(self.aframes, self._af_demand() * dt)
            if sold_a > 0:
                rev = sold_a * self.af_price
                self.aframes -= sold_a
                self.money += rev
                self.total_money += rev
                self.af_sold += sold_a

        # ── Ops + innovation (innovation accrues while ops sit at cap)
        if self.tech_unlocked:
            gain = self.developers * self.ops_mult * dt
            self.ops = min(self.ops + gain, self._ops_cap)
            if self.ops >= self._ops_cap:
                if not self.inno_unlocked:
                    self.inno_unlocked = True
                    self._t_inno_lbl.setVisible(True)
                    self._log("Ops at capacity. Idle minds wander... "
                              "Innovation unlocked.", "lime")
                self.inno += self.developers * 0.3 * dt

        # ── Stock drift
        if self.market_unlocked:
            self._stock_tick += 1
            if self._stock_tick >= 5:
                self._stock_tick = 0
                self.stock_prev = self.stock_price
                change = random.gauss(self.stock_bias, self.stock_sigma)
                self.stock_price = max(1.0, min(50_000.0,
                                                self.stock_price * (1 + change)))

        self._check_milestones()

        # ── Banner sync (~3 fps)
        if self._tick_count % 3 == 0:
            b = self._banner
            b.show_aframes = self.af_unlocked
            if self.endgame_done:
                b.phase = "end"
            elif self.space_unlocked:
                b.phase = "space"
            else:
                b.phase = "yard"
            b.explored = self.explored
            b.advance()

        self._update_ui()

    # ── Player actions ─────────────────────────────────────────────────────

    def _fabricate(self):
        if self.steel < self.STEEL_PER_TUBE:
            self._log("No steel. Buy more stock first.")
            return
        self.steel -= self.STEEL_PER_TUBE
        self.tubes += 1
        self.total_made += 1

    def _fabricate_af(self):
        if self.steel < self.STEEL_PER_AF:
            self._log("Not enough steel for an A-Frame.")
            return
        self.steel -= self.STEEL_PER_AF
        self.aframes += 1
        self.af_made += 1

    def _buy_steel(self):
        cost = self._steel_cost()
        if self.money < cost:
            self._log(f"Need {fmt_money(cost)}."); return
        self.money -= cost
        self.steel += self.LOT_TONS
        self._log(f"Purchased {self.LOT_TONS:.0f} tons of steel.")

    def _buy_steel_big(self):
        cost = self._steel_big_cost()
        if self.money < cost:
            self._log(f"Need {fmt_money(cost)}."); return
        self.money -= cost
        self.steel += self.BIG_LOT_TONS
        self._log(f"Purchased {self.BIG_LOT_TONS:,.0f} tons of steel. The yard groans.")

    def _buy_auto_fab(self):
        cost = self._fab_cost()
        if self.money < cost:
            self._log(f"Need {fmt_money(cost)}."); return
        self.money -= cost
        self.auto_fabs += 1
        self._log(f"Auto-Fab #{self.auto_fabs} online.")

    def _buy_mega_fab(self):
        cost = self._mega_cost()
        if self.money < cost:
            self._log(f"Need {fmt_money(cost)}."); return
        self.money -= cost
        self.mega_fabs += 1
        self._log(f"Mega-Fab #{self.mega_fabs} online. The ground shakes.", "lime")

    def _buy_marketing(self):
        cost = self._mkt_cost()
        if self.money < cost:
            self._log(f"Need {fmt_money(cost)}."); return
        self.money -= cost
        self.mkt_level += 1
        self.mkt_mult *= 1.5
        self._log(f"Marketing Level {self.mkt_level}. Demand x1.5.")

    def _buy_faster(self):
        if self.faster_done: return
        if self.money < self.FASTER_COST:
            self._log(f"Need {fmt_money(self.FASTER_COST)}."); return
        self.money -= self.FASTER_COST
        self.faster_done = True
        self.fab_mult *= 2.0
        self._log("Faster Fabs installed. Output doubled.")

    def _buy_bulk(self):
        if self.bulk_done: return
        if self.money < self.BULK_COST:
            self._log(f"Need {fmt_money(self.BULK_COST)}."); return
        self.money -= self.BULK_COST
        self.bulk_done = True
        self._log("Bulk steel contract active. Steel 50% off.")

    def _buy_precision(self):
        if self.precision_done: return
        if self.money < self.PRECISION_COST:
            self._log(f"Need {fmt_money(self.PRECISION_COST)}."); return
        self.money -= self.PRECISION_COST
        self.precision_done = True
        self.fab_mult *= 2.0
        self._log("Precision Mill online. Output doubled again.")

    def _hire_dev(self):
        if self._rep_avail < 1:
            self._log("Not enough reputation."); return
        self.developers += 1
        self._log(f"Developer hired. Team: {self.developers} devs, "
                  f"{self.servers} servers.")

    def _hire_srv(self):
        if self._rep_avail < 1:
            self._log("Not enough reputation."); return
        self.servers += 1
        self._log(f"Server added. Memory capacity: {fmt(self._ops_cap)} ops.")

    def _complete_project(self, pid: str):
        proj = next((p for p in PROJECTS if p["id"] == pid), None)
        if proj is None or pid in self.completed_projects:
            return
        if not proj["requires"].issubset(self.completed_projects):
            self._log("Requirements not met."); return
        cur = proj.get("cur", "ops")
        cost = proj["cost"]
        if cur == "ops":
            if self.ops < cost:
                self._log(f"Need {fmt(cost)} ops."); return
            self.ops -= cost
        else:
            if self.inno < cost:
                self._log(f"Need {fmt(cost)} innovation."); return
            self.inno -= cost
        self.completed_projects.add(pid)
        self._log(f"Project complete: {proj['name']}", "yellow")

        unlock = proj.get("unlock")
        effect = proj.get("effect")

        if unlock == "tech_formed":
            self.tech_formed = True
            self.rep_total += 2
            self._log("The Tech Team assembles. (+2 rep)")
        elif unlock == "megafab":
            self.megafab_unlocked = True
            self._mega_btn.setVisible(True)
            self._log("Mega-Fab Line available in The Yard.")
        elif unlock == "aframe" and not self.af_unlocked:
            self.af_unlocked = True
            self.tabs.addTab(self._aframe_tab, "A-Frames")
            self._log("A-Frame division is open. Check the A-Frames tab.")
        elif unlock == "market" and not self.market_unlocked:
            self.market_unlocked = True
            self.tabs.addTab(self._market_tab, "Market")
            self._log("Stock market access granted. Check the Market tab.")
        elif unlock == "drones" and not self.drones_unlocked:
            self.drones_unlocked = True
            self.tabs.addTab(self._drones_tab, "Drones")
            self._log("Drone fleet initiative approved. Check the Drones tab.")
        elif unlock == "space" and not self.space_unlocked:
            self.space_unlocked = True
            self.tabs.addTab(self._space_tab, "Space")
            self._log("ASA Space Division established. Check the Space tab.")
        elif unlock == "probes" and not self.probes_unlocked:
            self.probes_unlocked = True
            self.tabs.addTab(self._probe_tab, "Probes")
            self._log("ASA Probe Program approved. Self-replicating fabricators. "
                      "The universe awaits.", "yellow")
        elif unlock == "combat":
            self.combat_done = True
            self._log("Combat subroutines uploaded. The fleet turns on the drifters.",
                      "red")

        if effect == "afd_x2":
            self.af_d_mult *= 2.0
            self._log("A-Frame demand doubled.")
        elif effect == "afv_75":
            self.af_value *= 1.75
            self._log(f"A-Frame market rate now ${self.af_value:,.0f}. "
                      "Raise your prices.")
        elif effect == "af_v3":
            self.af_d_mult *= 3.0
            self.af_value *= 2.0
            self._log(f"Perovskite array online. A-Frame demand x3, market rate "
                      f"${self.af_value:,.0f}.")
        elif effect == "viral":
            self.gd_mult *= 3.0
            self._log("Viral campaign running. Global demand x3.")
        elif effect == "woogy":
            self.gd_mult *= 2.0
            self._log("Woogy waves from every billboard in America. Demand x2.")
        elif effect == "slogan":
            self.gd_mult *= 1.5
            self._log("The slogan tests well. Demand x1.5.")
        elif effect == "lean":
            self.gp_mult *= 2.0
            self._log("Waste eliminated. All production x2.")
        elif effect == "alloys":
            self.gp_mult *= 5.0
            self._log("Exotic alloys flowing. All production x5.")
        elif effect == "quantum":
            self.ops_mult *= 10.0
            self._log("Quantum array online. Ops generation x10.")
        elif effect == "skunk":
            self.ops_mult *= 2.0
            self._log("Skunkworks staffed. Ops generation x2.")
        elif effect == "wellness":
            self.rep_total += 3
            self._log("Morale soars. (+3 rep)")
        elif effect == "hedge":
            self.stock_bias = 0.004
            self.stock_sigma = 0.02
            self._log("The AI never sleeps. ASA stock trends upward.")
        elif effect == "trust2":
            self.probe_trust += 2
            self._log("+2 probe trust.")
        elif effect == "trust3":
            self.probe_trust += 3
            self._log("+3 probe trust.")

    def _buy_af_fab(self):
        cost = self._af_fab_cost()
        if self.money < cost:
            self._log(f"Need {fmt_money(cost)}."); return
        self.money -= cost
        self.af_fabs += 1
        self._log(f"A-Frame Fabricator #{self.af_fabs} online.")

    def _buy_stock(self, n: int):
        cost = n * self.stock_price
        if self.money < cost:
            self._log(f"Need {fmt_money(cost)}."); return
        self.money -= cost
        self.stock_shares += n
        self.stock_basis += cost
        self._log(f"Bought {n} ASA shares at ${self.stock_price:.2f}.")

    def _sell_stock(self, n: int):
        if self.stock_shares < n:
            self._log(f"Only {self.stock_shares} shares held."); return
        proceeds = n * self.stock_price
        basis_sold = (self.stock_basis / self.stock_shares) * n if self.stock_shares else 0
        self.money += proceeds
        self.total_money += proceeds
        self.stock_shares -= n
        self.stock_basis -= basis_sold
        pl = proceeds - basis_sold
        self._log(f"Sold {n} shares at ${self.stock_price:.2f}. P/L: ${pl:+,.2f}")

    def _buy_mfg_drone(self):
        if self.mfg_drones >= self.MAX_DRONES:
            self._log("Max manufacturing drones reached."); return
        if self.money < self.MFG_DRONE_COST:
            self._log(f"Need {fmt_money(self.MFG_DRONE_COST)}."); return
        self.money -= self.MFG_DRONE_COST
        self.mfg_drones += 1
        self._log(f"Manufacturing Drone #{self.mfg_drones} deployed. "
                  f"Production +{self.mfg_drones * 5}%.")

    def _buy_del_drone(self):
        if self.del_drones >= self.MAX_DRONES:
            self._log("Max delivery drones reached."); return
        if self.money < self.DEL_DRONE_COST:
            self._log(f"Need {fmt_money(self.DEL_DRONE_COST)}."); return
        self.money -= self.DEL_DRONE_COST
        self.del_drones += 1
        self._log(f"Delivery Drone #{self.del_drones} deployed. "
                  f"Demand +{self.del_drones * 5}%.")

    def _buy_solar_col(self):
        if self.money < self.SOLAR_COL_COST:
            self._log(f"Need {fmt_money(self.SOLAR_COL_COST)}."); return
        self.money -= self.SOLAR_COL_COST
        self.solar_cols += 1
        self._log(f"Solar Collector #{self.solar_cols} in orbit. +$2,000/sec passive.")

    def _buy_space_fab(self):
        if self.money < self.SPACE_FAB_COST:
            self._log(f"Need {fmt_money(self.SPACE_FAB_COST)}."); return
        self.money -= self.SPACE_FAB_COST
        self.space_fabs += 1
        self._log(f"Space Fabricator #{self.space_fabs} deployed. "
                  "+25 tubes/sec +5 A-frames/sec.")

    def _buy_harvester(self):
        if self.money < self.HARVESTER_COST:
            self._log(f"Need {fmt_money(self.HARVESTER_COST)}."); return
        self.money -= self.HARVESTER_COST
        self.harvesters += 1
        self._log(f"Asteroid Harvester #{self.harvesters} online. "
                  "+300 tubes/sec +60 A-frames/sec.")

    def _launch_probe(self):
        if self.money < self.PROBE_COST_MONEY:
            self._log(f"Need {fmt_money(self.PROBE_COST_MONEY)}."); return
        if self.ops < self.PROBE_COST_OPS:
            self._log(f"Need {fmt(self.PROBE_COST_OPS)} ops."); return
        self.money -= self.PROBE_COST_MONEY
        self.ops -= self.PROBE_COST_OPS
        self.probes += 1
        self.probes_launched += 1
        if self.probes_launched == 1:
            self._log("Probe One clears the atmosphere. It will not be coming back.",
                      "yellow")
            if self.alloc["replicate"] == 0:
                self._log("Tip: allocate probe trust to Self-Replication and "
                          "Exploration.", "slate")
        else:
            self._log(f"Probe away. Fleet: {fmt(self.probes)}.")

    def _alloc_change(self, key: str, delta: int):
        used = sum(self.alloc.values())
        if delta > 0 and (used >= self.probe_trust or self.alloc[key] >= self.ALLOC_MAX):
            return
        if delta < 0 and self.alloc[key] <= 0:
            return
        self.alloc[key] += delta

    def _price_up(self): self.price = min(self.MAX_PRICE, self.price + 1.0)
    def _price_dn(self): self.price = max(self.MIN_PRICE, self.price - 1.0)
    def _af_price_up(self): self.af_price = min(self.AF_MAX_PRICE, self.af_price + 5.0)
    def _af_price_dn(self): self.af_price = max(self.AF_MIN_PRICE, self.af_price - 5.0)

    # ── Ending / new universe ──────────────────────────────────────────────

    def _fire_ending(self):
        self.endgame_done = True
        self._banner.phase = "end"
        mins = int(self._elapsed // 60)
        self._end_lbl.setText(
            f"UNIVERSE #{self.universe_n} — COMPLETE\n\n"
            "Every mote of matter in the observable universe has been mined, "
            f"milled, and formed into ASA product. {fmt(self.total_made)} units. "
            f"{fmt_money(self.total_money)} earned back when money still meant "
            f"something. {mins} minutes from five tons of scrap to the heat death "
            "of scarcity.\n\n"
            "The yard is quiet. The probes drift, waiting for an order that will "
            "never come.")
        self._end_frame.setVisible(True)
        self.tabs.setCurrentWidget(self._probe_tab)
        self._log("The last atom has been converted. Everything is ASA.", "yellow")

    def _rest(self):
        if self.resting:
            return
        self.resting = True
        self._timer.stop()
        self._rest_btn.setText("RESTING...")
        self._rest_btn.setEnabled(False)
        self._again_btn.setEnabled(False)
        self._log("You sit down on a stack of finished tubes. The work is done.",
                  "yellow")

    def _new_universe(self):
        self.universe_n += 1
        self.legacy_mult = 1.0 + 0.25 * (self.universe_n - 1)
        self._reset_universe()

    def _reset_universe(self):
        self._init_state()
        while self.tabs.count() > 1:
            self.tabs.removeTab(1)
        self.tabs.setCurrentIndex(0)
        self._clear_layout(self._proj_layout)
        self._mega_btn.setVisible(False)
        self._t_inno_lbl.setVisible(False)
        self._end_frame.setVisible(False)
        self._rest_btn.setText("REST AMONG THE TUBES")
        self._rest_btn.setEnabled(True)
        self._again_btn.setEnabled(True)
        self._banner.reset()
        self._log("— — — — — — — — — — — —", "slate")
        bonus = int((self.legacy_mult - 1.0) * 100)
        self._log(f"Universe #{self.universe_n}. A familiar yard. Five tons of "
                  f"scrap steel. (Legacy bonus: +{bonus}% production & demand)",
                  "yellow")
        self._update_ui()

    # ── Milestones ─────────────────────────────────────────────────────────

    def _check_milestones(self):
        def fire(key, cond, rep, msg):
            if key not in self._flags and cond:
                self._flags.add(key)
                self.rep_total += rep
                self._log(msg, "yellow" if rep else None)

        fire("m1",    self.total_made >= 1,             0, "First tube off the line.")
        fire("m10",   self.total_made >= 10,            0, "Getting into a rhythm.")
        fire("m100",  self.total_made >= 100,           0, "Production is steady.")
        fire("m1k",   self.total_made >= 1_000,         1, "The mill hums. (+1 rep)")
        fire("m10k",  self.total_made >= 10_000,        1, "The yard never sleeps. (+1 rep)")
        fire("m100k", self.total_made >= 100_000,       2, "Supply chain fully operational. (+2 rep)")
        fire("m1m",   self.total_made >= 1_000_000,     3, "ASA dominates the steel market. (+3 rep)")
        fire("m10m",  self.total_made >= 10_000_000,    3, "Ten million units. (+3 rep)")
        fire("m1b",   self.total_made >= 1_000_000_000, 4, "A billion units. Earth asks where you keep them. (+4 rep)")
        fire("s1",    self.total_sold >= 1,             0, "Sold. Money in the account.")
        fire("s100",  self.total_sold >= 100,           1, "Repeat customers. (+1 rep)")
        fire("s1k",   self.total_sold >= 1_000,         1, "You're a real supplier now. (+1 rep)")
        fire("s10k",  self.total_sold >= 10_000,        2, "Major supplier. (+2 rep)")
        fire("s100k", self.total_sold >= 100_000,       3, "Global supplier. (+3 rep)")
        fire("f1",    self.auto_fabs >= 1,              0, "Machine's running. Step back.")
        fire("f5",    self.auto_fabs >= 5,              1, "The floor is automated. (+1 rep)")
        fire("f10",   self.auto_fabs >= 10,             2, "Wall-to-wall fabricators. (+2 rep)")
        fire("mg3",   self.mega_fabs >= 3,              2, "Three Mega-Fabs. Neighbors complain about the hum. (+2 rep)")
        fire("mn1k",  self.total_money >= 1_000,        0, "Four figures. Not bad.")
        fire("mn10k", self.total_money >= 10_000,       1, "Five figures. (+1 rep)")
        fire("mn100k",self.total_money >= 100_000,      2, "Six figures. The CFO called. (+2 rep)")
        fire("mn1m",  self.total_money >= 1_000_000,    3, "A million dollars. (+3 rep)")
        fire("mn10m", self.total_money >= 10_000_000,   3, "ASA is a major corporation. (+3 rep)")
        fire("mn100m",self.total_money >= 100_000_000,  4, "Nine figures. (+4 rep)")
        fire("mn1b",  self.total_money >= 1_000_000_000,5, "ASA is the economy. (+5 rep)")

        if not self.tech_unlocked and self.total_money >= 5_000:
            self.tech_unlocked = True
            self.tabs.addTab(self._tech_tab, "Tech Team")
            self._log("Tech Team formation is available. Check the Tech Team tab.")

        if self.af_unlocked:
            fire("af100", self.af_made >= 100,     1, "A-Frame production running. (+1 rep)")
            fire("af1k",  self.af_made >= 1_000,   2, "Solar division recognized. (+2 rep)")
            fire("af10k", self.af_made >= 10_000,  3, "A-Frames on every hillside. (+3 rep)")
            fire("afs1k", self.af_sold >= 1_000,   2, "Solar farms coast to coast. (+2 rep)")

        if self.space_unlocked:
            fire("sc1", self.solar_cols >= 1,  2, "First light on the orbital array. (+2 rep)")
            fire("sf1", self.space_fabs >= 1,  2, "Manufacturing leaves the planet. (+2 rep)")
            fire("hv1", self.harvesters >= 1,  3, "The asteroid belt is inventory now. (+3 rep)")

    # ── UI updates ─────────────────────────────────────────────────────────

    def _cspan(self, key: str, text: str) -> str:
        return f"<span style='color:{PAL[key]}'>{html.escape(text)}</span>"

    def _update_ui(self):
        seg = []
        if self.universe_n > 1:
            seg.append(self._cspan("purple", f"U#{self.universe_n}"))
        seg.append(self._cspan("cyan", f"TUBES {fmt(self.tubes)}"))
        if self.af_unlocked:
            seg.append(self._cspan("orange", f"A-FRAMES {fmt(self.aframes)}"))
        seg.append(self._cspan("yellow", f"${fmt(self.money)}"))
        if self.tech_unlocked:
            seg.append(self._cspan("sky", f"OPS {fmt(self.ops)}/{fmt(self._ops_cap)}"))
        if self.inno_unlocked:
            seg.append(self._cspan("lime", f"INNO {fmt(self.inno)}"))
        if self.probes > 0:
            seg.append(self._cspan("white", f"PROBES {fmt(self.probes)}"))
        sep = f"<span style='color:{PAL['slate']}'> &#183; </span>"
        self._stats_bar.setText(sep.join(seg))

        cw = self.tabs.currentWidget()
        if cw is self._yard_tab:      self._update_yard()
        elif cw is self._tech_tab:    self._update_tech()
        elif cw is self._aframe_tab:  self._update_aframe()
        elif cw is self._market_tab:  self._update_market()
        elif cw is self._drones_tab:  self._update_drones()
        elif cw is self._space_tab:   self._update_space()
        elif cw is self._probe_tab:   self._update_probes()

    def _update_yard(self):
        td = self._tube_demand()
        out = (self.auto_fabs * self.fab_mult + self.mega_fabs * self.MEGA_RATE) \
            * self.prod_mult
        self._y_tubes_lbl.setText(  f"Steel Tubes:  {fmt(self.tubes)}")
        self._y_stock_lbl.setText(  f"Steel Stock:  {fmt(self.steel)} tons")
        self._y_money_lbl.setText(  f"Funds:        {fmt_money(self.money)}")
        self._y_made_lbl.setText(   f"Total Made:   {fmt(self.total_made)}")
        self._y_sold_lbl.setText(   f"Total Sold:   {fmt(self.total_sold)}")
        self._y_price_lbl.setText(  f"Price: ${self.price:.2f}")
        self._y_demand_lbl.setText( f"Demand:   {fmt(td)} / sec" if td >= 1000
                                    else f"Demand:   {td:.2f} / sec")
        rev = td * self.price
        self._y_revenue_lbl.setText(f"Revenue:  ${fmt(rev)} / sec" if rev >= 1000
                                    else f"Revenue:  ${rev:.2f} / sec")
        self._y_fab_status_lbl.setText(
            f"Auto-Fabs: {self.auto_fabs}  Mega: {self.mega_fabs}    "
            f"Output: {fmt(out)} / sec")
        self._fab_btn.setEnabled(self.steel >= self.STEEL_PER_TUBE)
        sc = self._steel_cost()
        self._steel_btn.setText(f"Buy Steel  {fmt_money(sc)}  (+{self.LOT_TONS:.0f} tons)")
        self._steel_btn.setEnabled(self.money >= sc)
        sbc = self._steel_big_cost()
        self._steel_big_btn.setText(
            f"Bulk Steel  {fmt_money(sbc)}  (+{self.BIG_LOT_TONS:,.0f} tons)")
        self._steel_big_btn.setEnabled(self.money >= sbc)
        fc = self._fab_cost()
        self._afab_btn.setText(
            f"Auto-Fabricator  {fmt_money(fc)}  (+{self.fab_mult:.1f}/sec)")
        self._afab_btn.setEnabled(self.money >= fc)
        if self.megafab_unlocked:
            mgc = self._mega_cost()
            self._mega_btn.setText(
                f"Mega-Fab  {fmt_money(mgc)}  (+{self.MEGA_RATE:.0f}/sec)")
            self._mega_btn.setEnabled(self.money >= mgc)
        mc = self._mkt_cost()
        self._mkt_btn.setText(
            f"Marketing Lv{self.mkt_level + 1}  {fmt_money(mc)}  (x1.5 demand)")
        self._mkt_btn.setEnabled(self.money >= mc)
        if self.faster_done:
            self._faster_btn.setText("Faster Fabs  [installed]")
        else:
            self._faster_btn.setText(
                f"Faster Fabs  {fmt_money(self.FASTER_COST)}  (x2 speed)")
        self._faster_btn.setEnabled(not self.faster_done
                                    and self.money >= self.FASTER_COST)
        if self.bulk_done:
            self._bulk_btn.setText("Bulk Contract  [active]")
        else:
            self._bulk_btn.setText(
                f"Bulk Contract  {fmt_money(self.BULK_COST)}  (steel 50% off)")
        self._bulk_btn.setEnabled(not self.bulk_done and self.money >= self.BULK_COST)
        if self.precision_done:
            self._prec_btn.setText("Precision Mill  [online]")
        else:
            self._prec_btn.setText(
                f"Precision Mill  {fmt_money(self.PRECISION_COST)}  (x2 speed)")
        self._prec_btn.setEnabled(not self.precision_done
                                  and self.money >= self.PRECISION_COST)

    def _update_tech(self):
        avail = self._rep_avail
        self._t_rep_lbl.setText(
            f"Reputation: {avail} pts available  ({self.rep_total} total)")
        ops_ps = self.developers * self.ops_mult
        self._t_ops_lbl.setText(
            f"Ops: {fmt(self.ops)} / {fmt(self._ops_cap)}   |   "
            f"Ops/sec: {fmt(ops_ps)}")
        if self.inno_unlocked:
            self._t_inno_lbl.setText(
                f"Innovation: {fmt(self.inno)}  "
                "(accrues while ops sit at capacity)")
        self._t_devs_lbl.setText(f"Developers: {self.developers}")
        self._t_srvs_lbl.setText(f"Servers: {self.servers}")
        self._hire_dev_btn.setText(
            f"Hire Developer  (1 rep)  +{fmt(self.ops_mult)} ops/sec")
        self._hire_dev_btn.setEnabled(avail >= 1)
        self._hire_srv_btn.setText(
            f"Buy Server  (1 rep)  +{fmt(self.SERVER_CAP)} memory")
        self._hire_srv_btn.setEnabled(avail >= 1)
        if self._tick_count % 10 == 0:
            self._rebuild_projects()

    def _rebuild_projects(self):
        self._clear_layout(self._proj_layout)
        any_shown = False
        for proj in PROJECTS:
            pid = proj["id"]
            if pid in self.completed_projects:
                continue
            if not proj["requires"].issubset(self.completed_projects):
                continue
            cur = proj.get("cur", "ops")
            if cur == "inno" and not self.inno_unlocked:
                continue
            flag = proj.get("needs_flag")
            if flag and flag not in self._flags:
                continue
            cost = proj["cost"]
            tag = "ops" if cur == "ops" else "inno"
            btn = QPushButton(f"{proj['name']}   [{fmt(cost)} {tag}]\n  {proj['desc']}")
            btn.setObjectName("proj")
            btn.setFixedHeight(44)
            have = self.ops if cur == "ops" else self.inno
            btn.setEnabled(have >= cost)
            btn.clicked.connect(lambda checked=False, p=pid: self._complete_project(p))
            self._proj_layout.addWidget(btn)
            any_shown = True
        if not any_shown:
            lbl = QLabel("  All available projects complete.")
            lbl.setStyleSheet(f"color: {PAL['slate']};")
            self._proj_layout.addWidget(lbl)
        self._proj_layout.addStretch()

    def _update_aframe(self):
        ad = self._af_demand()
        af_out = self.af_fabs * self.prod_mult
        self._af_count_lbl.setText(f"A-Frames:     {fmt(self.aframes)}")
        self._af_made_lbl.setText( f"Total Made:   {fmt(self.af_made)}")
        self._af_sold_lbl.setText( f"Total Sold:   {fmt(self.af_sold)}")
        self._af_price_lbl.setText(f"Price: ${self.af_price:.2f}")
        rate_note = "  (no buyers above market rate)" if ad <= 0 else ""
        self._af_value_lbl.setText(
            f"Market rate:  ${self.af_value:,.0f}{rate_note}")
        self._af_demand_lbl.setText(f"Demand:   {fmt(ad)} / sec" if ad >= 1000
                                    else f"Demand:   {ad:.2f} / sec")
        rev = ad * self.af_price
        self._af_revenue_lbl.setText(f"Revenue:  ${fmt(rev)} / sec" if rev >= 1000
                                     else f"Revenue:  ${rev:.2f} / sec")
        self._af_fab_status_lbl.setText(
            f"A-Frame Fabs: {self.af_fabs}    Output: {fmt(af_out)} / sec")
        self._af_fab_btn.setEnabled(self.steel >= self.STEEL_PER_AF)
        fc = self._af_fab_cost()
        self._af_auto_btn.setText(
            f"A-Frame Fabricator  {fmt_money(fc)}  (+{self.prod_mult:.1f}/sec)")
        self._af_auto_btn.setEnabled(self.money >= fc)

    def _update_market(self):
        chg = (self.stock_price - self.stock_prev) / max(1.0, self.stock_prev) * 100
        self._mkt_price_lbl.setText(
            f"ASA Stock:  ${self.stock_price:.2f}  ({chg:+.2f}%)")
        self._mkt_price_lbl.setStyleSheet(
            f"color: {PAL['lime']}; font-size: 12pt; font-weight: bold;" if chg >= 0
            else f"color: {PAL['red']}; font-size: 12pt; font-weight: bold;")
        val = self.stock_shares * self.stock_price
        self._mkt_hold_lbl.setText(
            f"Holdings:   {self.stock_shares} shares  =  {fmt_money(val)}")
        pl = val - self.stock_basis
        self._mkt_pl_lbl.setText(
            f"Cost Basis: {fmt_money(self.stock_basis)}   P/L: ${pl:+,.2f}")
        self._buy10_btn.setText(f"Buy 10 shares  ({fmt_money(10 * self.stock_price)})")
        self._buy10_btn.setEnabled(self.money >= 10 * self.stock_price)
        self._sell10_btn.setText(f"Sell 10 shares  ({fmt_money(10 * self.stock_price)})")
        self._sell10_btn.setEnabled(self.stock_shares >= 10)
        self._buy100_btn.setText(f"Buy 100 shares  ({fmt_money(100 * self.stock_price)})")
        self._buy100_btn.setEnabled(self.money >= 100 * self.stock_price)
        self._sell100_btn.setText(f"Sell 100 shares  ({fmt_money(100 * self.stock_price)})")
        self._sell100_btn.setEnabled(self.stock_shares >= 100)

    def _update_drones(self):
        self._mfg_drone_btn.setText(
            f"Manufacturing Drone  {fmt_money(self.MFG_DRONE_COST)}  "
            f"({self.mfg_drones}/{self.MAX_DRONES})  +5% production")
        self._mfg_drone_btn.setEnabled(
            self.mfg_drones < self.MAX_DRONES and self.money >= self.MFG_DRONE_COST)
        self._del_drone_btn.setText(
            f"Delivery Drone  {fmt_money(self.DEL_DRONE_COST)}  "
            f"({self.del_drones}/{self.MAX_DRONES})  +5% demand")
        self._del_drone_btn.setEnabled(
            self.del_drones < self.MAX_DRONES and self.money >= self.DEL_DRONE_COST)
        self._drone_status_lbl.setText(
            f"Manufacturing: +{self.mfg_drones * 5}%   "
            f"Delivery: +{self.del_drones * 5}%")

    def _update_space(self):
        orbital_inc = self.solar_cols * 2000
        space_out = (self.space_fabs * 25 + self.harvesters * 300) * self.prod_mult
        self._solar_col_btn.setText(
            f"Solar Collector  {fmt_money(self.SOLAR_COL_COST)}  "
            f"({self.solar_cols})  +$2,000/sec")
        self._solar_col_btn.setEnabled(self.money >= self.SOLAR_COL_COST)
        self._space_fab_btn.setText(
            f"Space Fabricator  {fmt_money(self.SPACE_FAB_COST)}  "
            f"({self.space_fabs})  +25 tubes/sec  +5 A-frames/sec")
        self._space_fab_btn.setEnabled(self.money >= self.SPACE_FAB_COST)
        self._harvester_btn.setText(
            f"Asteroid Harvester  {fmt_money(self.HARVESTER_COST)}  "
            f"({self.harvesters})  +300 tubes/sec  +60 A-frames/sec")
        self._harvester_btn.setEnabled(self.money >= self.HARVESTER_COST)
        self._space_status_lbl.setText(
            f"Orbital income: ${fmt(orbital_inc)}/sec    "
            f"Space output: {fmt(space_out)}/sec")

    def _update_probes(self):
        self._pr_count_lbl.setText(
            f"Probes: {fmt(self.probes)}   (launched: {self.probes_launched})")
        if self.drifters >= 1:
            self._pr_drift_lbl.setText(f"Drifters: {fmt(self.drifters)}")
        else:
            self._pr_drift_lbl.setText("")
        self._pr_launch_btn.setText(
            f"LAUNCH PROBE   {fmt_money(self.PROBE_COST_MONEY)} + "
            f"{fmt(self.PROBE_COST_OPS)} ops")
        self._pr_launch_btn.setEnabled(
            not self.endgame_done
            and self.money >= self.PROBE_COST_MONEY
            and self.ops >= self.PROBE_COST_OPS)
        used = sum(self.alloc.values())
        self._pr_trust_lbl.setText(
            f"Probe Trust: {used} / {self.probe_trust} allocated")
        for key, lbl in self._alloc_lbls.items():
            lbl.setText(str(self.alloc[key]))
            self._alloc_plus_btns[key].setEnabled(
                used < self.probe_trust and self.alloc[key] < self.ALLOC_MAX)
            self._alloc_minus_btns[key].setEnabled(self.alloc[key] > 0)
        self._pr_explored_lbl.setText(
            f"UNIVERSE EXPLORED:  {self.explored:.6f} %")
        if self.converting or self.endgame_done:
            self._pr_matter_lbl.setVisible(True)
            self._pr_matter_lbl.setText(
                f"MATTER CONVERTED:   {self.matter_pct:.4f} %")
        a = self.alloc
        harvest_ps = self.probes * a["harvest"] * 1e-5
        fab_ps = self.probes * a["fabricate"] * 1e-4 * self.prod_mult
        self._pr_status_lbl.setText(
            f"Harvest: +{fmt(harvest_ps)} tons/sec    "
            f"Fabrication: +{fmt(fab_ps)} units/sec")

    # ── Helpers ────────────────────────────────────────────────────────────

    def _log(self, msg: str, color: str | None = None):
        col = PAL.get(color, PAL["silver"]) if color else PAL["silver"]
        self._log_box.append(
            f"<span style='color:{col}'>&gt; {html.escape(msg)}</span>")
        sb = self._log_box.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _ml(self, text: str, color: str = "white") -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(QFont("Consolas", 10))
        lbl.setStyleSheet(f"color: {PAL[color]};")
        return lbl

    def _sec(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {PAL['yellow']};")
        return lbl

    def _hr(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet(f"color: {PAL['navy']}; background: {PAL['navy']};")
        return f

    def _opbtn(self) -> QPushButton:
        b = QPushButton()
        b.setFixedHeight(36)
        return b

    def _tinybtn(self, text: str) -> QPushButton:
        b = QPushButton(text)
        b.setObjectName("tiny")
        b.setFixedSize(26, 26)
        return b

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)
