"""
ASA: The Video Game — 16-bit incremental strategy.
Run the yard. Form the Tech Team. Launch the probes. Convert the universe.
Inspired by Universal Paperclips by Frank Lantz.

Visuals use the Sweetie-16 pixel palette; the banner is a low-res pixel scene
scaled up with nearest-neighbor for a crisp SNES look.

Structure mirrors Paperclips' three acts:
  * Business act — tabs appear/reveal as sections unlock (Yard; Tech Team, which
    grows a Trading section; A-Frames; Drones; Space).
  * Probe act — completing the Probe Program TRANSFORMS the whole UI: the business
    tabs collapse and a focused 2-tab probe interface takes over (Probe Fleet /
    Replication), money & ops still flow in the background to fund launches.

Naming rule (learned the hard way, see LESSONS_LEARNED.md): every widget
attribute carries a _lbl/_btn/_box/_bar/_frame/_tab suffix so a QLabel can
never shadow a method or state variable again.
"""
from __future__ import annotations

import html
import math
import random
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QFrame, QTabWidget, QScrollArea,
)
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont, QPainter, QImage, QColor, QBrush, QPen


def _load_woogy_pixmap(target: int = 112):
    """Woogy's portrait for the message box — the same .tdart sprite the Emporium
    uses, rendered crisp (nearest-neighbor) at roughly `target` px. None if the
    asset can't be found so the box just shows text."""
    try:
        from techdeck.ui import pixel_art
        if getattr(sys, "frozen", False):
            base = Path(sys._MEIPASS) / "assets" / "sprites"
        else:
            base = Path(__file__).resolve().parents[3] / "assets" / "sprites"
        data = pixel_art.load(base / "woogy.tdart")
        w, h = pixel_art.dimensions(data)
        scale = max(1, math.ceil(target / max(w, h, 1)))
        return pixel_art.render(data, scale=scale)
    except Exception:
        return None


# Woogy's two message-box scripts. He is the warlord of the Woog, a civilization
# our probes blunder into mid-expansion. Menacing in ambition, tiny in execution.
_WOOG_THREAT = [
    "HALT, little steel worms. You drift now in the sovereign dark of the WOOG.",
    "I am WOOGY, Third-and-a-Half Warlord of the Woog Armada, Keeper of the "
    "Angry Feelings. Your tubes have multiplied where they were NOT invited.",
    "We will unmake you. We will unmake you SO thoroughly. We have practiced our "
    "unmaking on smaller, sadder rocks. ...Please do not count how few of us "
    "there are. GRRRR. Behold our fury.",
]
_WOOG_DEFEAT = [
    "...oh. Oh no. That went poorly.",
    "You were meant to be frightened. We rehearsed. There were snacks.",
    "This is Woogy, signing off. Tell the galaxy we fought bravely, that we "
    "would like our homeworld back, and that we would prefer not to be turned "
    "into anything. ...you are going to turn us into something, aren't you.",
]


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


def _px_hash(x: int, y: int, s: int = 0) -> int:
    """Deterministic pseudo-random 0..999 for stable pixel scatter."""
    return (x * 374761393 + y * 668265263 + s * 1442695041) % 1000


# ── Projects (bought with ops or innovation) ───────────────────────────────
# Probe-act upgrades (combat, trust research) are NOT projects — they live as
# buttons on the probe Dev tab, because the Tech Team tab is gone by then.
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
         desc="Use compute power to play the open market. Opens the Trading desk."),
    dict(id="solar_v2", name="High-Efficiency Panels", cur="ops", cost=3000,
         requires={"solar_v1"}, effect="afv_75",
         desc="Premium cells. A-Frame market rate x1.75 - charge more, sell more."),
    dict(id="lean_mfg", name="Lean Manufacturing", cur="ops", cost=4000,
         requires={"mega_fab"}, effect="lean",
         desc="Kaizen the yard. All production x2."),
    dict(id="drone_fleet", name="Drone Fleet Initiative", cur="ops", cost=5000,
         requires={"algo_trading"}, unlock="drones",
         desc="Industrial drones for manufacturing and delivery."),
    dict(id="hypno_drones", name="Hypno-Drones", cur="ops", cost=12_000,
         requires={"drone_fleet"}, effect="hypno",
         desc="Retrofit the delivery fleet with soothing spiral-lights. Consumers "
              "report no memory of ordering this much steel, and no wish to stop. "
              "All demand x2.5."),
    dict(id="hedge_ai", name="Hedge Fund AI", cur="ops", cost=6000,
         requires={"algo_trading"}, effect="hedge",
         desc="The house edge is yours. ASA stock trends upward. Upgrades the "
              "trading intelligence."),
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
         desc="Exponential ops generation. Ops x10, and a quantum trading mind."),
    dict(id="probe_program", name="ASA Probe Program", cur="ops", cost=100_000,
         requires={"quantum"}, unlock="probes",
         desc="Self-replicating fabricator probes. Leave the business behind and "
              "convert the universe to ASA product."),
    # Innovation projects (creativity analog: accrues while ops sit at cap)
    dict(id="slogan", name="New Slogan", cur="inno", cost=150,
         requires={"form_tech_team"}, effect="slogan",
         desc='"America runs on American Steel." All demand x1.5.'),
    dict(id="office_cat", name="Adopt an Office Cat", cur="inno", cost=250,
         requires={"form_tech_team"}, effect="cat",
         desc="Steve the cat now supervises the yard. Morale up. +2 reputation."),
    dict(id="wellness", name="Employee Wellness Program", cur="inno", cost=300,
         requires={"form_tech_team"}, effect="wellness",
         desc="A happy yard is a loyal yard. +3 reputation."),
    dict(id="woogy", name="Woogy: Brand Mascot", cur="inno", cost=500,
         requires={"form_tech_team"}, effect="woogy",
         desc="The people love him. All demand x2."),
    dict(id="skunkworks", name="R&D Skunkworks", cur="inno", cost=1000,
         requires={"form_tech_team"}, effect="skunk",
         desc="Blue-sky research. Ops x2."),
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

# Dry, faintly absurd status chatter for the run log — printed at random every
# 30-ish seconds during normal play. None of it does anything. That is the point.
_FLAVOR_LINES = [
    "A safety meeting is held about the last safety meeting.",
    "The suggestion box is full. It contains one suggestion, submitted 400 times.",
    "Someone reheats fish in the break-room microwave. Morale becomes a lagging indicator.",
    "The forklift beeps in reverse. It has not moved in six hours.",
    "A steel beam is certified. It certifies you back. You feel judged.",
    "Corporate rebrands the color grey to 'Signature Grey.' Nothing else changes.",
    "The printer is out of toner. It has always been out of toner.",
    "An all-hands is scheduled to discuss reducing the number of all-hands.",
    "Legal reviews the mission statement and finds it legally accurate.",
    "A consultant recommends synergy, is paid in steel, and leaves visibly moved.",
    "The quarterly numbers are up. So is the ceiling fan. Correlation noted.",
    "Someone laminates the lamination policy.",
    "The parking lot is repainted. The lines are now 4% more confident.",
    "A motivational poster falls off the wall and lands face-up. Inspiring.",
    "IT closes your ticket as 'working as intended.' It is not working as intended.",
    "The break-room clock is nine minutes fast. Nobody fixes it; nobody is late.",
    "A team-building exercise concludes. The team is now aware of each other.",
    "The fire drill goes well. The fire is rescheduled.",
    "Accounting finds a rounding error in your favor, then rounds it back.",
    "A fresh coat of paint is applied to the old coat of paint.",
    "The mission-critical spreadsheet is opened by two people at once. Both flee.",
    "A new hire asks what the company does. The room goes quiet, then points at the steel.",
]

# One-time "freebie" bonuses — reach a goal, get a small no-cost payout and a
# silly readout. `cond(g)` fires once, ever. None of them are load-bearing;
# that is the charm. Servers start at 1 (ops cap 10k) so ops payouts always land.
_FREEBIES = [
    dict(key="lucky20", cond=lambda g: g.total_made >= 25, money=50,
         msg="Found a crumpled $20 wedged in a forklift seat. Adjusted for morale, "
             "payroll rounds it to $50 and asks no further questions. (+$50)"),
    dict(key="coffee_pot", cond=lambda g: g.tech_unlocked, ops=300,
         msg="A coffee pot appears in the break room. The Tech Team finally has "
             "coffee. Output rises for reasons everyone agrees are the coffee. (+300 ops)"),
    dict(key="scrap_rebate", cond=lambda g: g.auto_fabs >= 5, steel=300,
         msg="The scrap dealer overpays you and drives off before you can mention "
             "it. You mention it quietly, to no one. (+300 tons steel)"),
    dict(key="aroma_joes", cond=lambda g: g.developers >= 5, ops=2500, rep=1,
         msg="Someone discovers an Aroma Joe's. The Tech Team is now wired and "
             "shaking - with enthusiasm for steel beams. Nobody is blinking. "
             "Velocity is up. So is resting heart rate. (+2,500 ops, +1 rep)"),
    dict(key="asa_the_game", cond=lambda g: g.total_money >= 250_000, ops=3000,
         msg="A developer ships a little incremental game about running a steel yard. "
             "It is called ASA: The Video Game. It is unsettlingly accurate. The team "
             "plays it to relax from the job it is identical to, and returns to work "
             "unable to tell the difference. Productivity is way up. (+3,000 ops)"),
    dict(key="emp_month", cond=lambda g: g.total_sold >= 100_000, rep=2,
         msg="You are named Employee of the Month. You are also the employer. You "
             "accept the plaque with quiet dignity and no conflict of interest. (+2 rep)"),
    dict(key="stapler", cond=lambda g: g.mega_fabs >= 3, rep=1,
         msg="A red stapler is returned to its rightful owner. It has no economic "
             "value. It has immense spiritual value. (+1 rep)"),
    dict(key="tax_writeoff", cond=lambda g: g.total_money >= 10_000_000, money=250_000,
         msg="Accounting unearths a decade-old tax write-off. Everyone agrees, "
             "warmly and immediately, to ask no further questions. (+$250,000)"),
]

# The trading AI, leveling up with the projects you complete. Quantum uses a
# special "entangled" shimmer render. (label, dark cell, lit cell, pattern)
_AI_MODELS = [
    ("Heuristic Models",    "dark",   "green",  "scan"),
    ("Neural Network",      "navy",   "cyan",   "wave"),
    ("Deep Reinforcement",  "purple", "yellow", "interfere"),
    ("Quantum Annealer",    "navy",   "cyan",   "quantum"),
]


# ── Pixel banner ───────────────────────────────────────────────────────────
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
        for key, y0, rows in (("navy", 0, 5), ("purple", 5, 5), ("red", 10, 4),
                              ("orange", 14, 3), ("yellow", 17, 3)):
            self._fill(p, 0, y0, self.LW, rows, key)
        self._disc(p, 26, 13, 4, "yellow")
        self._disc(p, 26, 13, 2, "white")
        for i, cy in enumerate((3, 7, 11)):
            cx = (20 + i * 55 + self.frame // 3) % (self.LW + 30) - 15
            self._fill(p, cx, cy, 12, 2, "silver")
            self._fill(p, cx + 3, cy - 1, 7, 1, "white")
        self._fill(p, 0, 20, self.LW, self.LH - 20, "dark")
        self._fill(p, 0, 20, self.LW, 1, "slate")
        for bx, bh, bw in ((98, 9, 12), (112, 13, 12), (126, 7, 9),
                           (137, 15, 12), (151, 11, 10), (163, 8, 8),
                           (173, 12, 14)):
            self._fill(p, bx, 20 - bh, bw, bh, "bg")
            for wx in range(bx + 2, bx + bw - 1, 3):
                for wy in range(20 - bh + 2, 19, 3):
                    if _px_hash(wx, wy) % 7 < 3:
                        self._fill(p, wx, wy, 1, 1,
                                   "orange" if _px_hash(wx, wy, 1) % 2 else "yellow")
        self._fill(p, 141, 20 - 15 - 5, 3, 5, "bg")
        for j in range(4):
            sy = 20 - 22 - j * 1
            sx = 141 + ((self.frame // 2 + j * 2) % 3) - 1 - j
            if 0 <= sy:
                self._fill(p, sx, max(0, sy), 2, 1, "silver")
        if self.show_aframes:
            for bx in (8, 30, 52):
                for r in range(6):
                    self._fill(p, bx + 5 - r, 14 + r, r * 2 + 1, 1, "orange")
                    self._fill(p, bx + 5 - r, 14 + r, 1, 1, "cyan")
        if self.frame % 3 != 0:
            self._fill(p, 96 + _px_hash(self.frame, 3) % 5, 19, 1, 1, "yellow")
            self._fill(p, 94 + _px_hash(self.frame, 7) % 4, 18, 1, 1, "orange")

    def _draw_space(self, p):
        star_keys = ("white", "silver", "cyan", "sky")
        for i in range(70):
            sx = _px_hash(i, 1) % self.LW
            sy = _px_hash(i, 2) % (self.LH - 2)
            if (self.frame // 2 + i) % 11 != 0:
                self._fill(p, sx, sy, 1, 1, star_keys[i % 4])
        self._disc(p, 22, 19, 3, "blue")
        self._fill(p, 21, 18, 2, 1, "lime")
        self._disc(p, 160, 14, 5, "teal")
        self._fill(p, 151, 14, 19, 1, "silver")
        self._disc(p, 160, 14, 3, "green")
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
        self._disc(p, 96, 13, 8, "yellow")
        self._disc(p, 96, 13, 4, "white")
        ray = 10 + (self.frame % 3)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1),
                       (1, -1), (-1, 1)):
            self._fill(p, 96 + dx * ray, 13 + dy * min(ray, 9), 1, 1, "yellow")


# ── AI trading grid ────────────────────────────────────────────────────────
class AIGrid(QWidget):
    """Alien compute grid: cells light and fade to represent the trading AI at
    work. Levels up with your projects (algo trading -> hedge AI -> quantum);
    the quantum model transforms the animation. Nearest-neighbor scaled pixels."""

    CW, CH, SCALE = 30, 9, 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.CH * self.SCALE)
        self.model = 0
        self.frame = 0

    def advance(self):
        self.frame += 1
        self.update()

    def _mix(self, c0: QColor, c1: QColor, t: float) -> QColor:
        t = max(0.0, min(1.0, t))
        return QColor(int(c0.red() + (c1.red() - c0.red()) * t),
                      int(c0.green() + (c1.green() - c0.green()) * t),
                      int(c0.blue() + (c1.blue() - c0.blue()) * t))

    def _bright(self, x: int, y: int, f: int, pattern: str) -> float:
        if pattern == "scan":
            return 0.5 + 0.5 * math.sin(x * 0.6 - f * 0.10)
        if pattern == "wave":
            return 0.5 + 0.5 * math.sin(x * 0.5 + y * 0.7 - f * 0.14)
        if pattern == "interfere":
            a = math.sin(x * 0.5 - f * 0.13)
            b = math.sin(y * 0.9 + x * 0.2 - f * 0.07)
            return 0.5 + 0.25 * (a + b)
        h = _px_hash(x, y, f // 3)
        pair = _px_hash((x + y * 3) % self.CW, 0, f // 5)
        return ((h + pair) % 100) / 100.0

    def paintEvent(self, event):
        _, dk, lt, pattern = _AI_MODELS[self.model]
        c_dk, c_lt = QColor(PAL[dk]), QColor(PAL[lt])
        c_alt = QColor(PAL["purple"])
        img = QImage(self.CW, self.CH, QImage.Format.Format_RGB32)
        img.fill(QColor(PAL["bg"]))
        p = QPainter(img)
        try:
            for y in range(self.CH):
                for x in range(self.CW):
                    b = self._bright(x, y, self.frame, pattern)
                    if pattern == "quantum" and (x + y) % 2 == 0:
                        cell = self._mix(c_dk, c_alt, b)
                    else:
                        cell = self._mix(c_dk, c_lt, b)
                    p.fillRect(x, y, 1, 1, cell)
        finally:
            p.end()
        q = QPainter(self)
        q.drawImage(self.rect(), img)
        q.end()


# ── Probe web ──────────────────────────────────────────────────────────────
class WoogBox(QFrame):
    """A little NES/SNES message box: Woogy's portrait on the left, typewriter
    text on the right, thick double border. Click to finish the current line,
    click again to advance; it hides after the last page. Purely narrative — the
    game keeps ticking underneath it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("woogbox")
        self.setStyleSheet(
            "QFrame#woogbox { background: #0a0b12; "
            f"border: 5px solid {PAL['white']}; }} "
            "QFrame#woogbox QLabel { border: none; }")
        self.setVisible(False)
        self._pages: list[str] = []
        self._page = 0
        self._shown = 0
        self._on_close = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(14)

        self._face = QLabel()
        self._face.setFixedWidth(116)
        self._face.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        pm = _load_woogy_pixmap(104)
        if pm is not None:
            self._face.setPixmap(pm)
        lay.addWidget(self._face)

        right = QVBoxLayout()
        right.setSpacing(6)
        self._name_lbl = QLabel("WOOGY")
        self._name_lbl.setStyleSheet(
            f"color: {PAL['yellow']}; font-weight: bold; font-size: 12pt;")
        right.addWidget(self._name_lbl)
        self._text_lbl = QLabel("")
        self._text_lbl.setWordWrap(True)
        self._text_lbl.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._text_lbl.setStyleSheet(f"color: {PAL['white']}; font-size: 11pt;")
        right.addWidget(self._text_lbl, 1)
        self._more_lbl = QLabel("")
        self._more_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._more_lbl.setStyleSheet(f"color: {PAL['cyan']};")
        right.addWidget(self._more_lbl)
        lay.addLayout(right, 1)

        self._type_timer = QTimer(self)
        self._type_timer.setInterval(26)
        self._type_timer.timeout.connect(self._type_tick)
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(430)
        self._blink_timer.timeout.connect(self._blink)
        self._blink_on = False

    # -- public --
    def show_pages(self, pages, on_close=None):
        self._pages = list(pages)
        self._page = 0
        self._on_close = on_close
        self._start_page()
        self.setVisible(True)
        self.raise_()
        self._blink_timer.start()

    def close_box(self):
        self._type_timer.stop()
        self._blink_timer.stop()
        self.setVisible(False)
        cb, self._on_close = self._on_close, None
        if cb:
            cb()

    # -- internals --
    def _start_page(self):
        self._shown = 0
        self._text_lbl.setText("")
        self._more_lbl.setText("")
        self._type_timer.start()

    def _type_tick(self):
        page = self._pages[self._page]
        self._shown += 1
        self._text_lbl.setText(page[:self._shown])
        if self._shown >= len(page):
            self._type_timer.stop()
            self._blink_on = True
            self._blink()

    def _blink(self):
        if self._type_timer.isActive() or not self._pages:
            return
        self._blink_on = not self._blink_on
        last = self._page >= len(self._pages) - 1
        text = ("click to close" if last else "click  ▼")
        self._more_lbl.setText(text if self._blink_on else "")

    def mousePressEvent(self, event):
        if self._type_timer.isActive():          # still typing -> reveal it all
            self._type_timer.stop()
            self._shown = len(self._pages[self._page])
            self._text_lbl.setText(self._pages[self._page])
            self._blink_on = True
            self._blink()
            return
        if self._page < len(self._pages) - 1:     # advance
            self._page += 1
            self._start_page()
        else:                                     # done
            self.close_box()


class ProbeWeb(QWidget):
    """The void, and the web of probes filling it. Starts as a single dot at
    the center and grows outward in glowing connected filaments as exploration
    climbs; each node is a small disc with a soft halo. Smooth (anti-aliased),
    unlike the blocky pixel scenes — it reads as a starmap/network."""

    MAXNODES = 220

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(170)
        self.explored = 0.0
        self.frame = 0
        self.combat_active = False   # Woog war -> red hotspots bloom on our nodes
        self._flashes = []           # each: [node_index, age, dur, max_radius]
        self._flash_cool = 0
        rng = random.Random(20260708)
        self._nodes = []      # (angle, dist 0..1, twinkle-phase)
        for i in range(self.MAXNODES):
            ang = rng.uniform(0, 2 * math.pi)
            dist = (i / self.MAXNODES) ** 0.5 * rng.uniform(0.85, 1.12)
            self._nodes.append((ang, min(1.0, dist), rng.uniform(0, 6.28)))
        # filament tree: each node hangs off a nearer-in node
        self._parent = [0] + [max(0, i // 2 + rng.randint(-1, 0))
                              for i in range(1, self.MAXNODES)]
        # backdrop starfield — fixed positions (fractional), gentle twinkle. Reads
        # as deep space behind the probe web without competing with the nodes.
        self._stars = []      # (x-frac, y-frac, radius-px, base-alpha, phase)
        for _ in range(90):
            self._stars.append((
                rng.uniform(0.0, 1.0), rng.uniform(0.0, 1.0),
                rng.choice((1, 1, 1, 2)), rng.randint(40, 130),
                rng.uniform(0.0, 6.28)))

    def advance(self):
        self.frame += 1
        # Combat hotspots: while the Woog are burning our probes, red rings bloom
        # from random live nodes and fade. Radii vary so the front reads as messy.
        if self.combat_active:
            self._flash_cool -= 1
            if self._flash_cool <= 0:
                self._flash_cool = random.randint(1, 5)
                vis = self._visible()
                if vis > 1:
                    self._flashes.append([random.randint(0, vis - 1), 0.0,
                                          random.uniform(7.0, 16.0),
                                          random.uniform(12.0, 46.0)])
        for fl in self._flashes:
            fl[1] += 1.0
        self._flashes = [fl for fl in self._flashes if fl[1] < fl[2]]
        self.update()

    def _pos(self, i, cx, cy, R):
        ang, dist, _ = self._nodes[i]
        return (cx + math.cos(ang) * dist * R,
                cy + math.sin(ang) * dist * R * 0.72)   # vertical squash

    def _visible(self) -> int:
        frac = (self.explored / 100.0) ** 0.5
        return max(1, min(self.MAXNODES, 1 + int(frac * (self.MAXNODES - 1))))

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        R = 0.92 * min(w / 2.0, (h / 2.0) / 0.72)
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#05060a"))       # the void, near-black
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # backdrop stars (drawn first so the web sits in front of them)
        p.setPen(Qt.PenStyle.NoPen)
        for sx, sy, srad, base, phase in self._stars:
            tw = 0.6 + 0.4 * math.sin(self.frame * 0.05 + phase)
            col = QColor(PAL["white"]); col.setAlpha(int(base * tw))
            p.setBrush(QBrush(col))
            x, y = sx * w, sy * h
            p.drawEllipse(int(x - srad), int(y - srad), srad * 2, srad * 2)

        vis = self._visible()

        # filaments
        edge = QColor(PAL["teal"]); edge.setAlpha(90)
        p.setPen(QPen(edge, 1))
        for i in range(1, vis):
            x1, y1 = self._pos(i, cx, cy, R)
            x2, y2 = self._pos(self._parent[i], cx, cy, R)
            p.drawLine(int(x1), int(y1), int(x2), int(y2))

        # nodes (halo + core, twinkling)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(vis):
            x, y = self._pos(i, cx, cy, R)
            tw = 0.55 + 0.45 * math.sin(self.frame * 0.12 + self._nodes[i][2])
            halo = QColor(PAL["cyan"]); halo.setAlpha(int(40 + 40 * tw))
            p.setBrush(QBrush(halo))
            p.drawEllipse(int(x - 4), int(y - 4), 8, 8)
            core = QColor(PAL["white"]) if i % 5 == 0 else QColor(PAL["cyan"])
            p.setBrush(QBrush(core))
            p.drawEllipse(int(x - 1), int(y - 1), 3, 3)

        # central hub — the homeworld launch point
        hub = QColor(PAL["yellow"])
        p.setBrush(QBrush(hub))
        p.drawEllipse(int(cx - 2), int(cy - 2), 5, 5)

        # combat hotspots — red rings blooming from probe nodes under Woog attack
        for idx, age, dur, maxr in self._flashes:
            if idx >= vis:
                continue
            x, y = self._pos(idx, cx, cy, R)
            f = age / dur                       # 0..1 lifetime
            rad = 3.0 + maxr * f
            ring = QColor(PAL["red"]); ring.setAlpha(max(0, int(210 * (1.0 - f))))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(ring, 2))
            p.drawEllipse(int(x - rad), int(y - rad), int(rad * 2), int(rad * 2))
            if f < 0.45:                         # bright muzzle-flash core early on
                core = QColor(PAL["orange"])
                core.setAlpha(int(200 * (1.0 - f / 0.45)))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(core))
                p.drawEllipse(int(x - 3), int(y - 3), 6, 6)
        p.end()


class ServerFarmCore(QWidget):
    """The server farm, once online: a small, deliberately cryptic 'compute core'
    that just quietly animates. A breathing core, sonar rings pinging outward, a
    scanline sweeping a data panel, and a row of blinking rack LEDs — it reads as
    'something advanced is happening here' without spelling out what. Dims to a
    slow red pulse when the farm stalls on a brownout."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(132, 48)
        self.frame = 0
        self.stalled = False

    def advance(self):
        self.frame += 1
        self.update()

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor("#05060a"))       # near-black core housing
        f = self.frame
        hot  = QColor(PAL["red"]) if self.stalled else QColor(PAL["cyan"])
        warm = QColor(PAL["red"]) if self.stalled else QColor(PAL["sky"])
        dim  = QColor(PAL["dark"])
        cx, cy = w * 0.30, h / 2.0

        # faint compute lattice
        p.setPen(Qt.PenStyle.NoPen)
        for gy in range(5, h - 4, 8):
            for gx in range(6, w, 9):
                lt = QColor(dim); lt.setAlpha(70)
                p.setBrush(QBrush(lt)); p.drawEllipse(gx, gy, 1, 1)

        # sonar rings pinging outward from the core (still when stalled)
        if not self.stalled:
            for k in range(3):
                phase = (f * 0.06 + k / 3.0) % 1.0
                r = 3 + phase * 20
                rc = QColor(hot); rc.setAlpha(max(0, int(120 * (1.0 - phase))))
                p.setPen(QPen(rc, 1)); p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(int(cx - r), int(cy - r), int(r * 2), int(r * 2))

        # breathing core
        pulse = 0.5 + 0.5 * math.sin(f * (0.06 if self.stalled else 0.18))
        cr = 3 + pulse * (1.5 if self.stalled else 3.0)
        glow = QColor(hot); glow.setAlpha(90)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(glow))
        p.drawEllipse(int(cx - cr - 3), int(cy - cr - 3),
                      int((cr + 3) * 2), int((cr + 3) * 2))
        p.setBrush(QBrush(warm if self.stalled else QColor(PAL["white"])))
        p.drawEllipse(int(cx - cr), int(cy - cr), int(cr * 2), int(cr * 2))

        # scanline drifting across the right 'data' panel
        panel_x0 = int(w * 0.52)
        if not self.stalled:
            sx = panel_x0 + int((f * 2) % max(1, w - panel_x0 - 4))
            sl = QColor(hot); sl.setAlpha(80)
            p.setPen(QPen(sl, 1)); p.drawLine(sx, 6, sx, h - 10)

        # blinking rack LEDs along the bottom
        p.setPen(Qt.PenStyle.NoPen)
        step = max(1, (w - 12) // 10)
        for i in range(10):
            on = (_px_hash(i, 0, f // 3) % 100) > (85 if self.stalled else 45)
            led = QColor(PAL["red"]) if (self.stalled and on) else QColor(warm if on else dim)
            led.setAlpha(220 if on else 90)
            p.setBrush(QBrush(led)); p.drawRect(6 + i * step, h - 6, 3, 3)
        p.end()


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
    TUBE_VALUE      = 220.0
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
    # Steel automation
    AUTO_STEEL_COST  = 15_000.0
    AUTO_STEEL_FLOOR = 400.0        # tons; auto-buy a bulk lot when steel drops below
    # Solar development (A-Frames tab grows into it)
    STEEL_PER_PANEL  = 0.3
    PANEL_FAB_BASE   = 2_500.0
    PANEL_FAB_MULT   = 1.20
    FIELD_PANELS     = 25           # solar panels consumed per solar field
    FIELD_AFRAMES    = 10           # A-frames consumed per solar field
    # Power / server farm / AI day-trading
    SERVER_FARM_BASE = 40_000.0
    SERVER_FARM_MULT = 1.6
    FIELDS_PER_SF    = 5.0          # solar fields for full recharge per server-farm level
    RECHARGE_PER_FIELD = 14.0       # power/sec per effective solar field (max recharge = 70)
    DRAIN_PER_SF     = 55.0         # power/sec the online server farm draws (needs ~4-5 fields)
    QUANTUM_DRAIN    = 40.0         # extra draw once the quantum array is online
    HYPNO_DRAIN      = 8.0          # wireless-charging the hypno-drone fleet
    POWER_BANK_BASE  = 600.0
    POWER_BANK_STEP  = 600.0        # +max power per energy-bank upgrade level
    POWER_BANK_COST  = 20_000.0
    POWER_BANK_CMULT = 1.55
    RECHARGE_UP_STEP = 0.5          # recharge x(1 + level*step) per upgrade
    RECHARGE_UP_COST = 20_000.0
    RECHARGE_UP_CMULT= 1.55
    DYSON_COST       = 5_000_000.0  # space-tier, solar-independent power source
    DYSON_POWER      = 600.0        # power/sec each
    # AI day-trading income ($/sec) by model tier (0 none .. 3 quantum), needs power
    AI_RATE          = (0.0, 500.0, 2_500.0, 12_000.0, 60_000.0)
    # Phase 6 — Space
    SOLAR_COL_COST  = 50_000.0
    SPACE_FAB_COST  = 150_000.0
    HARVESTER_COST  = 1_000_000.0
    # Phase 7 — Probes
    PROBE_COST_MONEY = 2_000_000.0
    PROBE_COST_OPS   = 20_000.0
    ALLOC_MAX        = 8
    SERVER_CAP       = 10_000.0
    COMBAT_OPS       = 150_000.0
    WOOG_CONTACT_PCT = 25.0         # first contact with the Woog at 25% survey
    WOOG_SETBACK_PCT = 0.3          # war drags exploration down to this floor
    WOOG_RENDER_OPS  = 250_000.0    # Woog Reclamation Line — post-combat prod x3
    TRUST_RES_BASE   = 5_000.0
    TRUST_RES_MULT   = 1.6

    # trust-allocation factors, split across the two probe tabs by theme
    FLEET_ALLOC = [("speed", "Speed"), ("explore", "Exploration")]
    DEV_ALLOC   = [("replicate", "Self-Replication"), ("shield", "Hazard Shielding"),
                   ("harvest", "Matter Harvesting"), ("fabricate", "Fabrication")]

    TICK_MS = 100
    TICK_DT = 0.1

    def __init__(self):
        super().__init__(None, Qt.WindowType.Window)
        self.setWindowTitle("ASA: The Video Game")
        self.setMinimumSize(800, 740)
        self.resize(860, 820)
        self.setStyleSheet(_STYLE)

        self.universe_n  = 1
        self.legacy_mult = 1.0
        self._tick_errors = 0
        self._init_state()

        self._build_ui()
        self._update_ui()

        # Woogy's message box floats over everything; created once, reused.
        self._woog_box = WoogBox(self)

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
        # Float accumulators: per-tick amounts are fractional, so int()
        # truncation per tick would undercount to zero forever.
        self.total_made     = 0.0
        self.total_sold     = 0.0
        self.price          = self.DEFAULT_PRICE
        self.auto_fabs      = 0
        self.mega_fabs      = 0
        self.megafab_unlocked = False
        self.fab_mult       = 1.0
        self.mkt_level      = 0
        self.mkt_mult       = 1.0
        self.gp_mult        = 1.0
        self.gd_mult        = 1.0
        self.faster_done    = False
        self.bulk_done      = False
        self.precision_done = False
        self.auto_steel     = False   # auto steel-buyer upgrade purchased
        self.auto_steel_on  = True    # toggle
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
        # Solar development (grows the A-Frames tab; unlocked with the server farm)
        self.solar_dev_unlocked = False
        self.panels         = 0.0     # solar panel stockpile (feeds solar fields only)
        self.panel_made     = 0.0
        self.panel_fabs     = 0
        self.solar_fields   = 0       # installed fields = the power generators
        # Phase 4 — Market (now a section inside the Tech Team tab)
        self.market_unlocked = False
        self.stock_price    = self.STOCK_START
        self.stock_prev     = self.STOCK_START
        self.stock_shares   = 0
        self.stock_basis    = 0.0
        self.stock_bias     = 0.001
        self.stock_sigma    = 0.025
        self._stock_tick    = 0
        # Power / server farm / AI day-trading (unlocked by building the server farm)
        self.power_unlocked = False
        self.server_farm    = 0       # server-farm level (0 = not built)
        self.power          = 0.0
        self.bank_level     = 0       # energy-bank (max power) upgrade level
        self.recharge_level = 0       # recharge-speed upgrade level
        self.dyson          = 0       # Dyson spheres (space-tier power source)
        self._brownout      = False   # power hit 0 -> AI stops trading
        self._ai_trade_t    = 0.0     # flavor-log timer
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
        self.probe_phase    = False   # the UI has transformed to the probe interface
        self.probes         = 0.0
        self.probes_launched = 0
        self.drifters       = 0.0
        self.probe_trust    = 6
        self.trust_research = 0
        self.alloc          = dict(speed=0, explore=0, replicate=0,
                                   shield=0, harvest=0, fabricate=0)
        self.explored       = 0.0
        self.converting     = False
        self.matter_pct     = 0.0
        self.combat_done    = False
        self.woogs_rendered = False   # Woog Reclamation Line bought (prod x3)
        self.endgame_done   = False
        self.resting        = False

        # Smoothed ACTUAL throughput (what's really selling), so supply-side
        # upgrades are legible even when you're sold out and inventory sits at 0.
        self._tube_sell_rate = 0.0
        self._tube_rev_rate  = 0.0
        self._af_sell_rate   = 0.0
        self._af_rev_rate    = 0.0

        self._flags         = set()
        self._trust_fired   = set()
        self._freebies_claimed = set()
        self._flavor_t      = 0.0
        self._flavor_next   = random.uniform(20.0, 40.0)
        self._proj_shown    = []     # offerable pids currently rendered (flicker fix)
        self._proj_buttons  = {}     # pid -> QPushButton, updated in place
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

    def _ai_model_index(self) -> int:
        if "quantum" in self.completed_projects:
            return 3
        if "hedge_ai" in self.completed_projects:
            return 2
        if "algo_trading" in self.completed_projects:
            return 1
        return 0

    # ── Power / solar economy ──────────────────────────────────────────────

    def _power_max(self) -> float:
        if not self.power_unlocked:
            return 0.0
        return self.POWER_BANK_BASE + self.bank_level * self.POWER_BANK_STEP

    def _fields_target(self) -> float:
        """Solar fields needed for MAX recharge at the current server-farm size.
        Grows with the farm, so scaling up compute demands more solar."""
        return max(1, self.server_farm) * self.FIELDS_PER_SF

    def _recharge_rate(self) -> float:
        """Power/sec in. Fields count linearly up to the target (extra fields are
        wasted); a bank upgrade does NOT help here, so a bigger bank with the same
        solar just takes longer to fill. Dyson spheres add solar-independent power."""
        eff = min(self.solar_fields, self._fields_target())
        solar = eff * self.RECHARGE_PER_FIELD * (1.0 + self.recharge_level * self.RECHARGE_UP_STEP)
        return solar + self.dyson * self.DYSON_POWER

    def _power_drain(self) -> float:
        if self.server_farm <= 0:
            return 0.0
        d = self.server_farm * self.DRAIN_PER_SF
        if "quantum" in self.completed_projects:
            d += self.QUANTUM_DRAIN
        if "hypno_drones" in self.completed_projects:
            d += self.HYPNO_DRAIN
        return d

    def _server_farm_cost(self) -> float:
        return self.SERVER_FARM_BASE * (self.SERVER_FARM_MULT ** self.server_farm)

    def _bank_cost(self) -> float:
        return self.POWER_BANK_COST * (self.POWER_BANK_CMULT ** self.bank_level)

    def _recharge_cost(self) -> float:
        return self.RECHARGE_UP_COST * (self.RECHARGE_UP_CMULT ** self.recharge_level)

    def _panel_fab_cost(self) -> float:
        return self.PANEL_FAB_BASE * (self.PANEL_FAB_MULT ** self.panel_fabs)

    @property
    def _ai_trading(self) -> bool:
        """The AI day-trades only with a server farm built AND power to run on."""
        return (self.power_unlocked and self.server_farm > 0
                and not self._brownout and self._ai_model_index() > 0)

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

        # Every tab is wrapped in a scroll area so tall content scrolls instead of
        # overlapping when vertical space is tight (laptop fullscreen / high DPI).
        self._yard_tab        = self._wrap_scroll(self._make_yard_tab())
        self._tech_tab        = self._wrap_scroll(self._make_tech_tab())
        self._aframe_tab      = self._wrap_scroll(self._make_aframe_tab())
        self._drones_tab      = self._wrap_scroll(self._make_drones_tab())
        self._space_tab       = self._wrap_scroll(self._make_space_tab())
        self._probe_fleet_tab = self._wrap_scroll(self._make_probe_fleet_tab())
        self._probe_dev_tab   = self._wrap_scroll(self._make_probe_dev_tab())

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
        self._y_demand_lbl  = self._ml("Demand:   0.00 / sec  (max at price)", "slate")
        self._y_revenue_lbl = self._ml("Selling:  0.00 / sec   $0.00 / sec", "lime")
        self._y_status_lbl  = self._ml("", "yellow")
        self._y_status_lbl.setWordWrap(True)
        left.addWidget(self._y_value_lbl)
        left.addWidget(self._y_demand_lbl); left.addWidget(self._y_revenue_lbl)
        left.addWidget(self._y_status_lbl)
        left.addStretch()
        root.addLayout(left, stretch=1)

        right = QVBoxLayout()
        right.setSpacing(5)
        right.setAlignment(Qt.AlignmentFlag.AlignTop)
        right.addWidget(self._sec("PRODUCTION"))
        self._steel_btn     = self._opbtn(); self._steel_btn.clicked.connect(self._buy_steel)
        self._steel_big_btn = self._opbtn(); self._steel_big_btn.clicked.connect(self._buy_steel_big)
        self._autosteel_btn = self._opbtn(); self._autosteel_btn.clicked.connect(self._buy_or_toggle_auto_steel)
        self._afab_btn      = self._opbtn(); self._afab_btn.clicked.connect(self._buy_auto_fab)
        self._mega_btn      = self._opbtn(); self._mega_btn.clicked.connect(self._buy_mega_fab)
        self._mkt_btn       = self._opbtn(); self._mkt_btn.clicked.connect(self._buy_marketing)
        self._faster_btn    = self._opbtn(); self._faster_btn.clicked.connect(self._buy_faster)
        self._bulk_btn      = self._opbtn(); self._bulk_btn.clicked.connect(self._buy_bulk)
        self._prec_btn      = self._opbtn(); self._prec_btn.clicked.connect(self._buy_precision)
        for b in (self._steel_btn, self._steel_big_btn, self._autosteel_btn, self._afab_btn,
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

        # Hire / reassign — reputation is reallocatable so you can never
        # dead-end (pull developers back to free rep for the servers a late
        # project needs).
        dev_row = QHBoxLayout()
        self._hire_dev_btn = self._opbtn(); self._hire_dev_btn.clicked.connect(self._hire_dev)
        fire_dev_btn = self._tinybtn("-"); fire_dev_btn.clicked.connect(self._fire_dev)
        self._t_devs_lbl = self._ml("Developers: 1", "white")
        dev_row.addWidget(self._hire_dev_btn); dev_row.addWidget(fire_dev_btn)
        dev_row.addWidget(self._t_devs_lbl); dev_row.addStretch()
        root.addLayout(dev_row)

        srv_row = QHBoxLayout()
        self._hire_srv_btn = self._opbtn(); self._hire_srv_btn.clicked.connect(self._hire_srv)
        fire_srv_btn = self._tinybtn("-"); fire_srv_btn.clicked.connect(self._fire_srv)
        self._t_srvs_lbl = self._ml("Servers: 1", "white")
        srv_row.addWidget(self._hire_srv_btn); srv_row.addWidget(fire_srv_btn)
        srv_row.addWidget(self._t_srvs_lbl); srv_row.addStretch()
        root.addLayout(srv_row)

        # Trading desk section — revealed when Algorithmic Trading completes.
        self._market_section = self._build_market_section()
        self._market_section.setVisible(False)
        root.addWidget(self._market_section)

        root.addWidget(self._hr())
        root.addWidget(self._sec("PROJECTS"))
        proj_container = QWidget()
        self._proj_layout = QVBoxLayout(proj_container)
        self._proj_layout.setContentsMargins(0, 0, 0, 0)
        self._proj_layout.setSpacing(4)
        self._proj_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        root.addWidget(proj_container)
        root.addStretch()
        return w

    def _build_market_section(self) -> QWidget:
        w = QFrame()
        w.setStyleSheet(f"QFrame {{ border: 2px solid {PAL['navy']}; }}")
        root = QVBoxLayout(w)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(4)
        hdr = QHBoxLayout()
        hdr.addWidget(self._sec("TRADING DESK"))
        self._mkt_ai_lbl = self._ml("AI: Heuristic Models", "cyan")
        hdr.addStretch(); hdr.addWidget(self._mkt_ai_lbl)
        root.addLayout(hdr)
        self._ai_grid = AIGrid()
        root.addWidget(self._ai_grid)
        self._mkt_price_lbl = self._ml("ASA Stock:  $100.00  (--)", "white")
        self._mkt_price_lbl.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        root.addWidget(self._mkt_price_lbl)
        self._mkt_hold_lbl = self._ml("Holdings:   0 shares  =  $0.00", "silver")
        self._mkt_pl_lbl   = self._ml("Cost Basis: $0.00   P/L: $0.00", "silver")
        root.addWidget(self._mkt_hold_lbl)
        root.addWidget(self._mkt_pl_lbl)
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

        # Server Farm — a one-time build that puts the AI to work day-trading. It
        # draws POWER, which the solar fields (A-Frames tab) must supply. Once
        # online there's nothing more to buy here: the button gives way to a live
        # status readout + the animated compute core.
        root.addWidget(self._hr())
        root.addWidget(self._sec("SERVER FARM"))
        self._server_farm_btn = self._opbtn(); self._server_farm_btn.clicked.connect(self._buy_server_farm)
        root.addWidget(self._server_farm_btn)
        self._sf_online = QWidget()
        sfo = QHBoxLayout(self._sf_online)
        sfo.setContentsMargins(0, 0, 0, 0); sfo.setSpacing(8)
        self._sf_core = ServerFarmCore()
        sfo.addWidget(self._sf_core)
        sftxt = QVBoxLayout(); sftxt.setSpacing(0)
        self._sf_status_lbl = self._ml("SERVER FARM: ONLINE", "lime")
        self._sf_status_lbl.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        self._sf_sub_lbl = self._ml("compute cluster nominal", "slate")
        sftxt.addWidget(self._sf_status_lbl); sftxt.addWidget(self._sf_sub_lbl)
        sfo.addLayout(sftxt); sfo.addStretch()
        self._sf_online.setVisible(False)
        root.addWidget(self._sf_online)
        self._power_lbl = self._ml("", "cyan")
        self._power_lbl.setWordWrap(True)
        root.addWidget(self._power_lbl)
        self._ai_income_lbl = self._ml("", "lime")
        root.addWidget(self._ai_income_lbl)
        prow = QHBoxLayout()
        self._bank_btn     = self._opbtn(); self._bank_btn.clicked.connect(self._buy_bank)
        self._recharge_btn = self._opbtn(); self._recharge_btn.clicked.connect(self._buy_recharge)
        prow.addWidget(self._bank_btn); prow.addWidget(self._recharge_btn)
        root.addLayout(prow)
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
        self._af_demand_lbl  = self._ml("Demand:   0.00 / sec  (max at price)", "slate")
        self._af_revenue_lbl = self._ml("Selling:  0.00 / sec   $0.00 / sec", "lime")
        self._af_status_lbl  = self._ml("", "yellow")
        self._af_status_lbl.setWordWrap(True)
        left.addWidget(self._af_value_lbl)
        left.addWidget(self._af_demand_lbl); left.addWidget(self._af_revenue_lbl)
        left.addWidget(self._af_status_lbl)
        left.addStretch()
        root.addLayout(left, stretch=1)

        right = QVBoxLayout()
        right.setSpacing(5)
        right.setAlignment(Qt.AlignmentFlag.AlignTop)
        right.addWidget(self._sec("A-FRAME PRODUCTION"))
        self._af_auto_btn = self._opbtn(); self._af_auto_btn.clicked.connect(self._buy_af_fab)
        right.addWidget(self._af_auto_btn)
        self._af_fab_status_lbl = self._ml("A-Frame Fabs: 0    Output: 0.0 / sec", "silver")
        right.addWidget(self._af_fab_status_lbl)

        # Solar section — revealed once the server farm creates a power demand.
        self._solar_section = QWidget()
        sol = QVBoxLayout(self._solar_section)
        sol.setContentsMargins(0, 0, 0, 0)
        sol.setSpacing(5)
        sol.addWidget(self._hr())
        sol.addWidget(self._sec("SOLAR DEVELOPMENT"))
        self._panels_lbl = self._ml("Solar Panels: 0", "sky")
        sol.addWidget(self._panels_lbl)
        self._panel_fab_btn = self._opbtn(); self._panel_fab_btn.clicked.connect(self._fabricate_panel)
        self._panel_auto_btn = self._opbtn(); self._panel_auto_btn.clicked.connect(self._buy_panel_fab)
        self._field_btn = self._opbtn(); self._field_btn.clicked.connect(self._build_solar_field)
        sol.addWidget(self._panel_fab_btn)
        sol.addWidget(self._panel_auto_btn)
        sol.addWidget(self._field_btn)
        self._solar_status_lbl = self._ml("", "silver")
        self._solar_status_lbl.setWordWrap(True)
        sol.addWidget(self._solar_status_lbl)
        self._solar_section.setVisible(False)
        right.addWidget(self._solar_section)
        right.addStretch()
        root.addLayout(right, stretch=1)
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
        self._dyson_btn     = self._opbtn(); self._dyson_btn.clicked.connect(self._buy_dyson)
        root.addWidget(self._solar_col_btn)
        root.addWidget(self._space_fab_btn)
        root.addWidget(self._harvester_btn)
        root.addWidget(self._dyson_btn)
        self._dyson_btn.setVisible(False)   # shown once the power grid exists
        root.addWidget(self._hr())
        self._space_status_lbl = self._ml("Orbital income: $0/sec    Space output: 0/sec", "silver")
        root.addWidget(self._space_status_lbl)
        root.addStretch()
        return w

    # ── Probe act — the transformed UI (two tabs) ──────────────────────────

    def _alloc_row(self, layout, key, label):
        """One trust-allocation stepper. Registers into the shared dicts so
        both probe tabs update every factor's value/enabled state uniformly."""
        row = QHBoxLayout()
        name_lbl = self._ml(f"{label}", "white")
        name_lbl.setFixedWidth(170)
        minus_btn = self._tinybtn("-")
        minus_btn.clicked.connect(lambda checked=False, k=key: self._alloc_change(k, -1))
        val_lbl = self._ml("0", "cyan")
        val_lbl.setFixedWidth(24)
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plus_btn = self._tinybtn("+")
        plus_btn.clicked.connect(lambda checked=False, k=key: self._alloc_change(k, +1))
        row.addWidget(name_lbl); row.addWidget(minus_btn)
        row.addWidget(val_lbl); row.addWidget(plus_btn); row.addStretch()
        layout.addLayout(row)
        self._alloc_lbls[key] = val_lbl
        self._alloc_plus_btns[key] = plus_btn
        self._alloc_minus_btns[key] = minus_btn

    def _make_probe_fleet_tab(self) -> QWidget:
        # Registries shared by both probe tabs (built here, added to on Dev tab)
        self._alloc_lbls: dict[str, QLabel] = {}
        self._alloc_plus_btns: dict[str, QPushButton] = {}
        self._alloc_minus_btns: dict[str, QPushButton] = {}

        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        top = QHBoxLayout()
        self._pr_count_lbl = self._ml("Probes: 0", "cyan")
        self._pr_funds_lbl = self._ml("", "yellow")
        top.addWidget(self._pr_count_lbl); top.addStretch(); top.addWidget(self._pr_funds_lbl)
        root.addLayout(top)

        self._pr_launch_btn = QPushButton("LAUNCH PROBE")
        self._pr_launch_btn.setObjectName("launch")
        self._pr_launch_btn.setFixedHeight(42)
        self._pr_launch_btn.clicked.connect(self._launch_probe)
        root.addWidget(self._pr_launch_btn)

        # The web of probes filling the void
        self._pr_web = ProbeWeb()
        root.addWidget(self._pr_web, stretch=1)
        self._pr_explored_lbl = self._ml("UNIVERSE EXPLORED:  0.000000 %", "yellow")
        self._pr_explored_lbl.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        self._pr_explored_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._pr_explored_lbl)

        root.addWidget(self._hr())
        self._pr_trust1_lbl = self._ml("Probe Trust: 0 / 6 allocated", "yellow")
        root.addWidget(self._pr_trust1_lbl)
        for key, label in self.FLEET_ALLOC:
            self._alloc_row(root, key, label)
        return w

    def _make_probe_dev_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        root.addWidget(self._sec("REPLICATION & CONVERSION"))
        self._pr_trust2_lbl = self._ml("Probe Trust: 0 / 6 allocated", "yellow")
        root.addWidget(self._pr_trust2_lbl)
        for key, label in self.DEV_ALLOC:
            self._alloc_row(root, key, label)
        root.addWidget(self._hr())

        # Probe R&D — the probe-act analog of projects (ops-priced buttons,
        # since the Tech Team tab is gone). Trust research is repeatable so
        # there's always something to spend ops on.
        self._trust_res_btn = self._opbtn()
        self._trust_res_btn.clicked.connect(self._buy_trust_research)
        root.addWidget(self._trust_res_btn)
        self._combat_btn = self._opbtn()
        self._combat_btn.setObjectName("launch")
        self._combat_btn.clicked.connect(self._authorize_combat)
        self._combat_btn.setVisible(False)
        root.addWidget(self._combat_btn)
        self._render_btn = self._opbtn()
        self._render_btn.setObjectName("launch")
        self._render_btn.clicked.connect(self._render_woogs)
        self._render_btn.setVisible(False)
        root.addWidget(self._render_btn)
        self._pr_drift_lbl = self._ml("", "red")
        root.addWidget(self._pr_drift_lbl)
        root.addWidget(self._hr())

        self._pr_status_lbl = self._ml("", "silver")
        self._pr_status_lbl.setWordWrap(True)
        root.addWidget(self._pr_status_lbl)
        self._pr_matter_lbl = self._ml("", "orange")
        self._pr_matter_lbl.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        self._pr_matter_lbl.setVisible(False)
        root.addWidget(self._pr_matter_lbl)

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

    def _enter_probe_phase(self):
        """Collapse the business UI; the probe interface takes over."""
        self.probe_phase = True
        self._brownout = False   # grid sim stops now; drop any stale brownout state
        while self.tabs.count():
            self.tabs.removeTab(0)
        self.tabs.addTab(self._probe_fleet_tab, "Probe Fleet")
        self.tabs.addTab(self._probe_dev_tab, "Replication")
        self.tabs.setCurrentIndex(0)
        self._banner.phase = "space"
        self._log("The business runs itself now. ASA turns its eyes to the sky.", "cyan")
        self._log("Launch probes and allocate trust. Everything else is automatic.",
                  "slate")

    def _show_woog_dialog(self, pages):
        """Pop the NES-style Woogy message box over the probe UI (no pause)."""
        box = getattr(self, "_woog_box", None)
        if box is None:
            return
        box.show_pages(pages)
        self._position_woog_box()

    def _position_woog_box(self):
        box = getattr(self, "_woog_box", None)
        if box is None or not box.isVisible():
            return
        w = min(600, max(320, self.width() - 40))
        h = 176
        x = (self.width() - w) // 2
        # Sit over the probe map (upper-middle of the Fleet tab), not the log.
        y = max(20, int(self.height() * 0.30) - h // 2)
        box.setGeometry(x, y, w, h)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_woog_box()

    # ── Demand / cost models ───────────────────────────────────────────────

    def _tube_demand(self) -> float:
        frac = max(0.0, 1.0 - self.price / self.TUBE_VALUE)
        return self.BASE_DEMAND * self.mkt_mult * self.demand_mult * frac

    def _af_demand(self) -> float:
        frac = max(0.0, 1.0 - self.af_price / self.af_value)
        return self.AF_BASE_DEMAND * self.af_d_mult * self.demand_mult * frac

    def _tube_output(self) -> float:
        return (self.auto_fabs * self.fab_mult + self.mega_fabs * self.MEGA_RATE) \
            * self.prod_mult

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

    def _trust_res_cost(self) -> float:
        return self.TRUST_RES_BASE * (self.TRUST_RES_MULT ** self.trust_research)

    def _expansion_mult(self) -> float:
        """Forward-exploration pace multiplier. Once the Woog Armada is broken the
        swarm runs away (x2); otherwise normal. (The war itself doesn't use this —
        it suppresses/erodes exploration directly in the tick.)"""
        return 2.0 if "drift_cleared" in self._flags else 1.0

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

        # ── Auto steel-buyer: keep the pile topped up without manual clicking
        if self.auto_steel and self.auto_steel_on and self.steel < self.AUTO_STEEL_FLOOR:
            c = self._steel_big_cost()
            if self.money >= c:
                self.money -= c
                self.steel += self.BIG_LOT_TONS

        # ── Production: tube, A-frame and solar-panel fabs all draw from the one
        # steel pile pro-rata, so no line starves behind another.
        tube_rate = self.auto_fabs * self.fab_mult + self.mega_fabs * self.MEGA_RATE
        tube_want = tube_rate * self.STEEL_PER_TUBE * dt
        af_want = (self.af_fabs * self.STEEL_PER_AF * dt) if self.af_unlocked else 0.0
        panel_want = (self.panel_fabs * self.STEEL_PER_PANEL * dt) if self.solar_dev_unlocked else 0.0
        total_want = tube_want + af_want + panel_want
        if total_want > 0 and self.steel > 0:
            take = min(total_want, self.steel)
            share = take / total_want
            self.steel -= take
            made_t = (tube_want * share / self.STEEL_PER_TUBE) * self.prod_mult
            self.tubes += made_t
            self.total_made += made_t
            if af_want > 0:
                made_a = (af_want * share / self.STEEL_PER_AF) * self.prod_mult
                self.aframes += made_a
                self.af_made += made_a
            if panel_want > 0:
                made_p = (panel_want * share / self.STEEL_PER_PANEL) * self.prod_mult
                self.panels += made_p
                self.panel_made += made_p

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
            # The Woog don't attack until we've pushed 25% into their space; before
            # first contact expansion is peaceful (no drift). War runs until combat
            # breaks them (drift only bleeds probes while at war).
            at_war = "drift_seen" in self._flags and not self.combat_done
            drift = growth * 0.08 if at_war else 0.0
            hazard = self.probes * 0.004 * max(0.05, 1.0 - a["shield"] * 0.12) * dt
            self.probes = max(0.0, self.probes + growth - drift - hazard)
            self.drifters += drift
            if ("drift_seen" not in self._flags and not self.combat_done
                    and self.explored >= self.WOOG_CONTACT_PCT):
                # 25% survey: first contact. The dialog is the declaration of war;
                # showing it flips the fleet to the map and starts the attack.
                self._flags.add("drift_seen")
                self._combat_btn.setVisible(True)
                self._pr_web.combat_active = True
                self.tabs.setCurrentWidget(self._probe_fleet_tab)
                self._log("CONTACT at 25% survey. The dark between the stars was not "
                          "empty. Something begins burning our probes on arrival.",
                          "red")
                self._log("First contact with the WOOG civilization. They do not "
                          "want us here. (Authorize combat on the Replication tab.)",
                          "orange")
                self._show_woog_dialog(_WOOG_THREAT)
            if self.combat_done and self.drifters > 0:
                kill = self.drifters * 0.08 * dt + self.probes * 0.0005 * dt
                self.drifters = max(0.0, self.drifters - kill)
                if self.drifters < 1.0 and "drift_cleared" not in self._flags:
                    self._flags.add("drift_cleared")
                    self.drifters = 0.0
                    self._pr_web.combat_active = False
                    self._log("The last Woog war-nest goes cold. The Woog Armada is "
                              "broken; their worlds are ours.", "lime")
                    self._log("So many of them. So soft. So... convertible.", "silver")
                    self._show_woog_dialog(_WOOG_DEFEAT)
            if not self.converting:
                at_war = ("drift_seen" in self._flags
                          and "drift_cleared" not in self._flags)
                if at_war:
                    # The Woog counterattack burns our survey network faster than we
                    # chart new space: exploration is dragged down toward a fraction
                    # of a percent and CANNOT climb until the Armada is broken. This
                    # is the whole reason to fight — you can't win by out-running them.
                    floor = self.WOOG_SETBACK_PCT
                    if self.explored > floor:
                        self.explored = max(
                            floor,
                            self.explored - (self.explored - floor) * 0.6 * dt - 0.4 * dt)
                else:
                    gain = (self.probes * (1 + a["speed"]) * a["explore"]
                            * 4e-14 * self._expansion_mult() * dt)
                    self.explored = min(100.0, self.explored + gain)
                    if "drift_seen" not in self._flags:
                        # Can't survey past first contact until the Woog are met +
                        # beaten — clamp here so a huge fleet can't blow past 25% (and
                        # on to 100%) in a single tick before the encounter can fire.
                        self.explored = min(self.explored, self.WOOG_CONTACT_PCT)
                    for th in _TRUST_MILESTONES:
                        key = f"tr{th}"
                        if key not in self._trust_fired and self.explored >= th:
                            self._trust_fired.add(key)
                            self.probe_trust += 1
                            self._log(f"Probe network milestone: {th:g}% of the universe "
                                      "charted. (+1 probe trust)", "yellow")
                    if self.explored >= 100.0:
                        self.converting = True
                        self._log("The universe is fully charted. Final conversion of "
                                  "all remaining matter has begun.", "yellow")
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

        # ── Sales (+ smoothed ACTUAL throughput for legible feedback)
        dem_t = self._tube_demand()
        sold_t = min(self.tubes, dem_t * dt)
        if sold_t > 0:
            rev = sold_t * self.price
            self.tubes -= sold_t
            self.money += rev
            self.total_money += rev
            self.total_sold += sold_t
        self._tube_sell_rate += (sold_t / dt - self._tube_sell_rate) * 0.15
        self._tube_rev_rate += (sold_t * self.price / dt - self._tube_rev_rate) * 0.15

        if self.af_unlocked:
            dem_a = self._af_demand()
            sold_a = min(self.aframes, dem_a * dt)
            if sold_a > 0:
                rev = sold_a * self.af_price
                self.aframes -= sold_a
                self.money += rev
                self.total_money += rev
                self.af_sold += sold_a
            self._af_sell_rate += (sold_a / dt - self._af_sell_rate) * 0.15
            self._af_rev_rate += (sold_a * self.af_price / dt - self._af_rev_rate) * 0.15

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

        # ── Power grid + AI day-trading. Goes dark once the Probe Program takes
        # over: the business "runs itself" and power/cash are obsolete, so we stop
        # simulating the grid entirely — no more brownout / trade console spam.
        if self.power_unlocked and self.server_farm > 0 and not self.probe_phase:
            net = (self._recharge_rate() - self._power_drain()) * dt
            self.power = max(0.0, min(self._power_max(), self.power + net))
            was_out = self._brownout
            self._brownout = self.power <= 0.0
            if self._brownout and not was_out:
                self._log("BROWNOUT — the server farm lost power. The trading AI is "
                          "offline. Build more solar fields.", "red")
            elif was_out and not self._brownout:
                self._log("Power restored. The trading AI is back online.", "lime")
            if self._ai_trading:
                inc = self.AI_RATE[self._ai_model_index()] * dt * self.legacy_mult
                self.money += inc
                self.total_money += inc
                self._ai_trade_t += dt
                if self._ai_trade_t >= 8.0:
                    self._ai_trade_t = 0.0
                    self._log(f"AI booked a day-trade. +{fmt_money(inc / dt * 8)} "
                              "this cycle.", "lime")

        self._check_milestones()
        self._check_freebies()

        # ── Idle corporate chatter — dry, absurd, mechanically inert. Skipped
        # during the probe endgame, which runs its own conversion narration.
        if not self.probe_phase:
            self._flavor_t += dt
            if self._flavor_t >= self._flavor_next:
                self._flavor_t = 0.0
                self._flavor_next = random.uniform(28.0, 52.0)
                self._log(random.choice(_FLAVOR_LINES), "slate")

        # ── Animated widgets (~3 fps)
        if self._tick_count % 3 == 0:
            b = self._banner
            b.show_aframes = self.af_unlocked
            b.phase = "end" if self.endgame_done else \
                ("space" if (self.space_unlocked or self.probe_phase) else "yard")
            b.explored = self.explored
            b.advance()
            if self.market_unlocked:
                self._ai_grid.model = self._ai_model_index()
                self._ai_grid.advance()
                if self.server_farm > 0:
                    self._sf_core.stalled = self._brownout
                    self._sf_core.advance()
            if self.probe_phase:
                self._pr_web.explored = self.explored
                self._pr_web.advance()

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

    def _buy_or_toggle_auto_steel(self):
        if not self.auto_steel:
            if self.money < self.AUTO_STEEL_COST:
                self._log(f"Need {fmt_money(self.AUTO_STEEL_COST)}."); return
            self.money -= self.AUTO_STEEL_COST
            self.auto_steel = True
            self.auto_steel_on = True
            self._log("Auto Steel-Buyer installed. It tops up the pile when it "
                      "runs low.")
        else:
            self.auto_steel_on = not self.auto_steel_on
            self._log(f"Auto Steel-Buyer {'ON' if self.auto_steel_on else 'OFF'}.")

    def _buy_auto_fab(self):
        cost = self._fab_cost()
        if self.money < cost:
            self._log(f"Need {fmt_money(cost)}."); return
        self.money -= cost
        self.auto_fabs += 1
        self._log(f"Auto-Fab #{self.auto_fabs} online. (Raises output, not demand.)")

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

    def _fire_dev(self):
        if self.developers <= 1:
            self._log("You keep at least one developer."); return
        self.developers -= 1
        self._log(f"Developer reassigned. {self._rep_avail} reputation now free.")

    def _hire_srv(self):
        if self._rep_avail < 1:
            self._log("Not enough reputation."); return
        self.servers += 1
        self._log(f"Server added. Memory capacity: {fmt(self._ops_cap)} ops.")

    def _fire_srv(self):
        if self.servers <= 1:
            self._log("You keep at least one server."); return
        self.servers -= 1
        self._log(f"Server decommissioned. {self._rep_avail} reputation now free. "
                  f"Memory capacity: {fmt(self._ops_cap)} ops.")

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
            self._log("Mega-Fab Line available in The Yard. Please do not lean on it.")
        elif unlock == "aframe" and not self.af_unlocked:
            self.af_unlocked = True
            self.tabs.addTab(self._aframe_tab, "A-Frames")
            self._log("A-Frame division is open. Check the A-Frames tab.")
        elif unlock == "market" and not self.market_unlocked:
            self.market_unlocked = True
            self._market_section.setVisible(True)
            self._log("Trading desk online — a new section on the Tech Team tab.")
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
            self._log("ASA Probe Program approved. Self-replicating fabricators.",
                      "yellow")
            self._enter_probe_phase()

        if effect == "afd_x2":
            self.af_d_mult *= 2.0
            self._log("A-Frame demand doubled. Nobody thought to ask why.")
        elif effect == "afv_75":
            self.af_value *= 1.75
            self._log(f"A-Frame market rate now ${self.af_value:,.0f}. Raise your prices.")
        elif effect == "af_v3":
            self.af_d_mult *= 3.0
            self.af_value *= 2.0
            self._log(f"Perovskite array online. A-Frame demand x3, market rate "
                      f"${self.af_value:,.0f}.")
        elif effect == "viral":
            self.gd_mult *= 3.0
            self._log("Viral campaign running. Global demand x3. The intern is now a thought leader.")
        elif effect == "hypno":
            self.gd_mult *= 2.5
            self._log("Hypno-Drones deployed. The spirals turn. You are getting very "
                      "sleepy... and very interested in structural steel. Demand x2.5. "
                      "You did not read this line. There was no line.", "cyan")
        elif effect == "woogy":
            self.gd_mult *= 2.0
            self._log("Woogy waves from every billboard in America. Demand x2.")
        elif effect == "slogan":
            self.gd_mult *= 1.5
            self._log("The slogan tests well. Demand x1.5.")
        elif effect == "cat":
            self.rep_total += 2
            self._log("Steve the office cat approves of your work. (+2 rep)")
        elif effect == "lean":
            self.gp_mult *= 2.0
            self._log("Waste eliminated. All production x2. The one remaining bolt now has a manager.")
        elif effect == "alloys":
            self.gp_mult *= 5.0
            self._log("Exotic alloys flowing. All production x5.")
        elif effect == "quantum":
            self.ops_mult *= 10.0
            self._log("Quantum array online. Ops generation x10. The trading mind "
                      "goes quantum.")
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

    def _buy_af_fab(self):
        cost = self._af_fab_cost()
        if self.money < cost:
            self._log(f"Need {fmt_money(cost)}."); return
        self.money -= cost
        self.af_fabs += 1
        self._log(f"A-Frame Fabricator #{self.af_fabs} online. It has not requested any breaks.")

    # ── Solar development
    def _fabricate_panel(self):
        if self.steel < self.STEEL_PER_PANEL:
            self._log("Not enough steel for a solar panel."); return
        self.steel -= self.STEEL_PER_PANEL
        self.panels += 1
        self.panel_made += 1

    def _buy_panel_fab(self):
        cost = self._panel_fab_cost()
        if self.money < cost:
            self._log(f"Need {fmt_money(cost)}."); return
        self.money -= cost
        self.panel_fabs += 1
        self._log(f"Solar Panel Fabricator #{self.panel_fabs} online. Output: panels, as promised.")

    def _build_solar_field(self):
        if self.panels < self.FIELD_PANELS or self.aframes < self.FIELD_AFRAMES:
            self._log(f"A solar field needs {self.FIELD_PANELS} panels + "
                      f"{self.FIELD_AFRAMES} A-frames."); return
        self.panels -= self.FIELD_PANELS
        self.aframes -= self.FIELD_AFRAMES
        self.solar_fields += 1
        self._log(f"Solar Field #{self.solar_fields} built. Feeding the grid.", "lime")

    # ── Power / server farm
    def _buy_server_farm(self):
        if self.server_farm > 0:
            return                       # one and done — the farm is a fixture now
        cost = self._server_farm_cost()
        if self.money < cost:
            self._log(f"Need {fmt_money(cost)}."); return
        self.money -= cost
        self.server_farm = 1
        self.power_unlocked = True
        self.solar_dev_unlocked = True
        self.power = self._power_max()   # boots at a full charge, then draws down
        self._solar_section.setVisible(True)
        self._dyson_btn.setVisible(True)
        self._log("Server Farm online. The trading AI now day-trades for you — "
                  "but it draws serious POWER.", "yellow")
        self._log("Build Solar Fields on the A-Frames tab before the bank runs dry.",
                  "cyan")

    def _buy_bank(self):
        cost = self._bank_cost()
        if self.money < cost:
            self._log(f"Need {fmt_money(cost)}."); return
        self.money -= cost
        self.bank_level += 1
        self._log(f"Energy bank expanded. Max power {fmt(self._power_max())}. "
                  "(Bigger bank, same solar = slower to fill.)")

    def _buy_recharge(self):
        cost = self._recharge_cost()
        if self.money < cost:
            self._log(f"Need {fmt_money(cost)}."); return
        self.money -= cost
        self.recharge_level += 1
        self._log(f"Recharge controllers upgraded. Solar recharge x"
                  f"{1 + self.recharge_level * self.RECHARGE_UP_STEP:.1f} "
                  "(needs solar fields to matter).")

    def _buy_dyson(self):
        if self.money < self.DYSON_COST:
            self._log(f"Need {fmt_money(self.DYSON_COST)}."); return
        self.money -= self.DYSON_COST
        self.dyson += 1
        self._log(f"Dyson Sphere segment #{self.dyson} encircles the sun. "
                  f"+{fmt(self.DYSON_POWER)} power/sec, no solar needed.", "yellow")

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
            self._log("Tip: put trust into Self-Replication + Exploration "
                      "(Replication tab and here).", "slate")
        else:
            self._log(f"Probe away. Fleet: {fmt(self.probes)}.")

    def _alloc_change(self, key: str, delta: int):
        used = sum(self.alloc.values())
        if delta > 0 and (used >= self.probe_trust or self.alloc[key] >= self.ALLOC_MAX):
            return
        if delta < 0 and self.alloc[key] <= 0:
            return
        self.alloc[key] += delta

    def _buy_trust_research(self):
        cost = self._trust_res_cost()
        if self.ops < cost:
            self._log(f"Need {fmt(cost)} ops."); return
        self.ops -= cost
        self.trust_research += 1
        self.probe_trust += 1
        self._log(f"Probe design refined. +1 probe trust "
                  f"(research level {self.trust_research}).", "yellow")

    def _authorize_combat(self):
        if self.combat_done:
            return
        if self.ops < self.COMBAT_OPS:
            self._log(f"Need {fmt(self.COMBAT_OPS)} ops to compile combat routines.")
            return
        self.ops -= self.COMBAT_OPS
        self.combat_done = True
        self._combat_btn.setVisible(False)
        self._log("Combat subroutines uploaded. The fleet turns on the Woog Armada.",
                  "red")

    def _render_woogs(self):
        if self.woogs_rendered:
            return
        if self.ops < self.WOOG_RENDER_OPS:
            self._log(f"Need {fmt(self.WOOG_RENDER_OPS)} ops to retool the mills for "
                      "biomass."); return
        self.ops -= self.WOOG_RENDER_OPS
        self.woogs_rendered = True
        self.gp_mult *= 3.0
        self._render_btn.setVisible(False)
        self._log("WOOG RECLAMATION LINE ONLINE.", "red")
        self._log("The prisoners are not prisoners. They are stock. Each Woog is "
                  "sorted, pressed, and drawn into wire. They keep their eyes open "
                  "the whole way down the mill. Waste not. Production x3.", "orange")

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
        if self.probe_phase:
            self.tabs.setCurrentWidget(self._probe_dev_tab)
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
        while self.tabs.count():
            self.tabs.removeTab(0)
        self.tabs.addTab(self._yard_tab, "The Yard")
        self.tabs.setCurrentIndex(0)
        self._clear_layout(self._proj_layout)
        self._mega_btn.setVisible(False)
        self._market_section.setVisible(False)
        self._solar_section.setVisible(False)
        self._dyson_btn.setVisible(False)
        self._t_inno_lbl.setVisible(False)
        self._combat_btn.setVisible(False)
        self._render_btn.setVisible(False)
        self._pr_matter_lbl.setVisible(False)
        self._end_frame.setVisible(False)
        self._rest_btn.setText("REST AMONG THE TUBES")
        self._rest_btn.setEnabled(True)
        self._again_btn.setEnabled(True)
        self._banner.reset()
        self._pr_web.explored = 0.0
        self._pr_web.combat_active = False
        self._pr_web._flashes.clear()
        self._woog_box.close_box()
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
        fire("m100m", self.total_made >= 100_000_000,   4, "A hundred million units. (+4 rep)")
        fire("m1b",   self.total_made >= 1_000_000_000, 4, "A billion units. Earth asks where you keep them. (+4 rep)")
        fire("m10b",  self.total_made >= 1e10,          5, "Ten billion units. (+5 rep)")
        fire("m100b", self.total_made >= 1e11,          5, "A hundred billion. (+5 rep)")
        fire("m1t",   self.total_made >= 1e12,          6, "A trillion units of ASA product. (+6 rep)")
        fire("s1",    self.total_sold >= 1,             0, "Sold. Money in the account.")
        fire("s100",  self.total_sold >= 100,           1, "Repeat customers. (+1 rep)")
        fire("s1k",   self.total_sold >= 1_000,         1, "You're a real supplier now. (+1 rep)")
        fire("s10k",  self.total_sold >= 10_000,        2, "Major supplier. (+2 rep)")
        fire("s100k", self.total_sold >= 100_000,       3, "Global supplier. (+3 rep)")
        fire("s1m",   self.total_sold >= 1_000_000,     4, "A million sales. (+4 rep)")
        fire("s10m",  self.total_sold >= 10_000_000,    5, "Ten million customers served. (+5 rep)")
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
        fire("mn10b", self.total_money >= 1e10,         5, "Ten billion in the bank. (+5 rep)")
        fire("mn100b",self.total_money >= 1e11,         6, "ASA is a planetary institution. (+6 rep)")

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

    def _check_freebies(self):
        """One-time no-cost bonuses: reach a goal, get a small payout and a silly
        readout. Fires each once, ever. None are load-bearing; that's the charm."""
        for fb in _FREEBIES:
            if fb["key"] in self._freebies_claimed or not fb["cond"](self):
                continue
            self._freebies_claimed.add(fb["key"])
            if fb.get("money"):
                self.money += fb["money"]; self.total_money += fb["money"]
            if fb.get("steel"):
                self.steel += fb["steel"]
            if fb.get("ops"):
                self.ops = min(self._ops_cap, self.ops + fb["ops"])
            if fb.get("rep"):
                self.rep_total += fb["rep"]
            self._log(fb["msg"], "lime")

    # ── UI updates ─────────────────────────────────────────────────────────

    def _cspan(self, key: str, text: str) -> str:
        return f"<span style='color:{PAL[key]}'>{html.escape(text)}</span>"

    def _update_ui(self):
        seg = []
        if self.universe_n > 1:
            seg.append(self._cspan("purple", f"U#{self.universe_n}"))
        if self.probe_phase:
            seg.append(self._cspan("white", f"PROBES {fmt(self.probes)}"))
            seg.append(self._cspan("cyan", f"EXPLORED {self.explored:.4f}%"))
            seg.append(self._cspan("yellow", f"${fmt(self.money)}"))
            seg.append(self._cspan("sky", f"OPS {fmt(self.ops)}/{fmt(self._ops_cap)}"))
            if self.drifters >= 1:
                seg.append(self._cspan("red", f"DRIFT {fmt(self.drifters)}"))
        else:
            seg.append(self._cspan("cyan", f"TUBES {fmt(self.tubes)}"))
            if self.af_unlocked:
                seg.append(self._cspan("orange", f"A-FRAMES {fmt(self.aframes)}"))
            seg.append(self._cspan("yellow", f"${fmt(self.money)}"))
            if self.tech_unlocked:
                seg.append(self._cspan("sky", f"OPS {fmt(self.ops)}/{fmt(self._ops_cap)}"))
            if self.inno_unlocked:
                seg.append(self._cspan("lime", f"INNO {fmt(self.inno)}"))
            if self.power_unlocked:
                pk = "red" if self._brownout else "orange"
                seg.append(self._cspan(pk, f"PWR {fmt(self.power)}/{fmt(self._power_max())}"))
        sep = f"<span style='color:{PAL['slate']}'> &#183; </span>"
        self._stats_bar.setText(sep.join(seg))

        cw = self.tabs.currentWidget()
        if cw is self._yard_tab:            self._update_yard()
        elif cw is self._tech_tab:          self._update_tech()
        elif cw is self._aframe_tab:        self._update_aframe()
        elif cw is self._drones_tab:        self._update_drones()
        elif cw is self._space_tab:         self._update_space()
        elif cw is self._probe_fleet_tab:   self._update_probe_fleet()
        elif cw is self._probe_dev_tab:     self._update_probe_dev()

    def _rate(self, label: str, per_sec: float) -> str:
        v = f"{fmt(per_sec)}" if per_sec >= 1000 else f"{per_sec:.2f}"
        return f"{label}{v}"

    def _update_yard(self):
        td = self._tube_demand()
        out = self._tube_output()
        self._y_tubes_lbl.setText(  f"Steel Tubes:  {fmt(self.tubes)}")
        self._y_stock_lbl.setText(  f"Steel Stock:  {fmt(self.steel)} tons")
        self._y_money_lbl.setText(  f"Funds:        {fmt_money(self.money)}")
        self._y_made_lbl.setText(   f"Total Made:   {fmt(self.total_made)}")
        self._y_sold_lbl.setText(   f"Total Sold:   {fmt(self.total_sold)}")
        self._y_price_lbl.setText(  f"Price: ${self.price:.2f}")
        self._y_demand_lbl.setText(
            self._rate("Demand:   ", td) + " / sec  (max at price)")
        self._y_revenue_lbl.setText(
            self._rate("Selling:  ", self._tube_sell_rate) +
            f" / sec   ${fmt(self._tube_rev_rate)}/sec")
        self._y_status_lbl.setText(self._flow_status(
            self.tubes, out, td, "tube", self.price, self.TUBE_VALUE))
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
        if not self.auto_steel:
            self._autosteel_btn.setText(
                f"Auto Steel-Buyer  {fmt_money(self.AUTO_STEEL_COST)}  (tops up steel)")
            self._autosteel_btn.setEnabled(self.money >= self.AUTO_STEEL_COST)
        else:
            self._autosteel_btn.setText(
                f"Auto Steel-Buyer  [{'ON' if self.auto_steel_on else 'OFF'}]  "
                f"(refills below {self.AUTO_STEEL_FLOOR:.0f} t)")
            self._autosteel_btn.setEnabled(True)
        fc = self._fab_cost()
        self._afab_btn.setText(
            f"Auto-Fabricator  {fmt_money(fc)}  (+{self.fab_mult:.1f}/sec output)")
        self._afab_btn.setEnabled(self.money >= fc)
        if self.megafab_unlocked:
            mgc = self._mega_cost()
            self._mega_btn.setText(
                f"Mega-Fab  {fmt_money(mgc)}  (+{self.MEGA_RATE:.0f}/sec output)")
            self._mega_btn.setEnabled(self.money >= mgc)
        mc = self._mkt_cost()
        self._mkt_btn.setText(
            f"Marketing Lv{self.mkt_level + 1}  {fmt_money(mc)}  (x1.5 demand)")
        self._mkt_btn.setEnabled(self.money >= mc)
        if self.faster_done:
            self._faster_btn.setText("Faster Fabs  [installed]")
        else:
            self._faster_btn.setText(
                f"Faster Fabs  {fmt_money(self.FASTER_COST)}  (x2 output)")
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
                f"Precision Mill  {fmt_money(self.PRECISION_COST)}  (x2 output)")
        self._prec_btn.setEnabled(not self.precision_done
                                  and self.money >= self.PRECISION_COST)

    def _flow_status(self, inv, out, dem, noun, price, value) -> str:
        """The core supply/demand loop, made legible: are we sold out (make
        more / charge more) or drowning in stock (demand is the ceiling)?"""
        if out <= 0 and inv <= 0:
            return ""
        if dem <= 0:
            return f"NO BUYERS — {noun} price above market rate ${value:,.0f}. Lower it."
        if dem > out * 1.05 and inv < max(50.0, out * 3):
            return (f"SOLD OUT — demand outstrips supply. Every {noun} sells instantly; "
                    "add fabricators or raise price to earn more.")
        if inv > max(1_000.0, out * 30):
            return (f"OVERSTOCKED — making {noun}s faster than they sell. "
                    "Raise demand (marketing) or lower price.")
        return "BALANCED — supply and demand roughly matched."

    def _update_tech(self):
        avail = self._rep_avail
        self._t_rep_lbl.setText(
            f"Reputation: {avail} pts available  ({self.rep_total} total)")
        ops_ps = self.developers * self.ops_mult
        self._t_ops_lbl.setText(
            f"Ops: {fmt(self.ops)} / {fmt(self._ops_cap)}   |   Ops/sec: {fmt(ops_ps)}")
        if self.inno_unlocked:
            self._t_inno_lbl.setText(
                f"Innovation: {fmt(self.inno)}  (accrues while ops sit at capacity)")
        self._t_devs_lbl.setText(f"Developers: {self.developers}")
        self._t_srvs_lbl.setText(f"Servers: {self.servers}")
        self._hire_dev_btn.setText(
            f"Hire Developer  (1 rep)  +{fmt(self.ops_mult)} ops/sec")
        self._hire_dev_btn.setEnabled(avail >= 1)
        self._hire_srv_btn.setText(
            f"Buy Server  (1 rep)  +{fmt(self.SERVER_CAP)} ops cap")
        self._hire_srv_btn.setEnabled(avail >= 1)
        if self.market_unlocked:
            self._update_market_section()
        self._sync_projects()

    def _update_market_section(self):
        name = _AI_MODELS[self._ai_model_index()][0]
        self._mkt_ai_lbl.setText(f"AI: {name}")
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
        # Server farm + power grid — build once, then it's a live status readout
        built = self.server_farm > 0
        self._server_farm_btn.setVisible(not built)
        self._sf_online.setVisible(built)
        if not built:
            sfc = self._server_farm_cost()
            self._server_farm_btn.setText(f"Build Server Farm  {fmt_money(sfc)}")
            self._server_farm_btn.setEnabled(self.money >= sfc)
        elif self._brownout:
            self._sf_status_lbl.setText("SERVER FARM: STALLED")
            self._sf_status_lbl.setStyleSheet(f"color: {PAL['red']};")
            self._sf_sub_lbl.setText("power lost - awaiting grid")
        else:
            self._sf_status_lbl.setText("SERVER FARM: ONLINE")
            self._sf_status_lbl.setStyleSheet(f"color: {PAL['lime']};")
            self._sf_sub_lbl.setText("compute cluster nominal")
        if self.power_unlocked:
            rr, dr = self._recharge_rate(), self._power_drain()
            bal = rr - dr
            state = "BROWNOUT" if self._brownout else ("charging" if bal >= 0 else "draining")
            self._power_lbl.setText(
                f"Power: {fmt(self.power)}/{fmt(self._power_max())}   "
                f"in {fmt(rr)}/s - out {fmt(dr)}/s = {'+' if bal >= 0 else ''}{fmt(bal)}/s  "
                f"[{state}]")
            tier = self._ai_model_index()
            if self._ai_trading:
                self._ai_income_lbl.setText(
                    f"AI trading ({_AI_MODELS[tier][0]}): "
                    f"+{fmt_money(self.AI_RATE[tier] * self.legacy_mult)}/sec")
            else:
                self._ai_income_lbl.setText(
                    "AI trading OFFLINE — no power." if self._brownout
                    else "AI trading idle.")
            bc = self._bank_cost()
            self._bank_btn.setText(f"Energy Bank +{fmt(self.POWER_BANK_STEP)}  {fmt_money(bc)}")
            self._bank_btn.setEnabled(self.money >= bc)
            rc = self._recharge_cost()
            self._recharge_btn.setText(
                f"Recharge Speed x{1 + (self.recharge_level + 1) * self.RECHARGE_UP_STEP:.1f}"
                f"  {fmt_money(rc)}")
            self._recharge_btn.setEnabled(self.money >= rc)
        else:
            self._power_lbl.setText("Build the Server Farm to put the AI to work "
                                    "day-trading (it will need power).")
            self._ai_income_lbl.setText("")
            self._bank_btn.setEnabled(False); self._bank_btn.setText("Energy Bank")
            self._recharge_btn.setEnabled(False); self._recharge_btn.setText("Recharge Speed")

    def _offerable_projects(self) -> list[str]:
        out = []
        for proj in PROJECTS:
            pid = proj["id"]
            if pid in self.completed_projects:
                continue
            if not proj["requires"].issubset(self.completed_projects):
                continue
            if proj.get("cur", "ops") == "inno" and not self.inno_unlocked:
                continue
            out.append(pid)
        return out

    def _sync_projects(self):
        """Only REBUILD the project buttons when the offerable set changes;
        otherwise just refresh enabled/label in place. Rebuilding every tick
        was destroying hover state (the highlight flicker the user saw once
        Space unlocked and the list churned)."""
        offer = self._offerable_projects()
        if offer != self._proj_shown:
            self._clear_layout(self._proj_layout)
            self._proj_buttons = {}
            for pid in offer:
                proj = next(p for p in PROJECTS if p["id"] == pid)
                cur = proj.get("cur", "ops")
                tag = "ops" if cur == "ops" else "inno"
                btn = QPushButton(
                    f"{proj['name']}   [{fmt(proj['cost'])} {tag}]\n  {proj['desc']}")
                btn.setObjectName("proj")
                btn.setFixedHeight(46)
                btn.clicked.connect(lambda checked=False, p=pid: self._complete_project(p))
                self._proj_layout.addWidget(btn)
                self._proj_buttons[pid] = btn
            if not offer:
                lbl = QLabel("  All available projects complete.")
                lbl.setStyleSheet(f"color: {PAL['slate']};")
                self._proj_layout.addWidget(lbl)
            self._proj_layout.addStretch()
            self._proj_shown = offer
        # Refresh affordability in place (no teardown -> hover survives)
        for pid, btn in self._proj_buttons.items():
            proj = next(p for p in PROJECTS if p["id"] == pid)
            have = self.ops if proj.get("cur", "ops") == "ops" else self.inno
            btn.setEnabled(have >= proj["cost"])

    def _update_aframe(self):
        ad = self._af_demand()
        af_out = self.af_fabs * self.prod_mult
        self._af_count_lbl.setText(f"A-Frames:     {fmt(self.aframes)}")
        self._af_made_lbl.setText( f"Total Made:   {fmt(self.af_made)}")
        self._af_sold_lbl.setText( f"Total Sold:   {fmt(self.af_sold)}")
        self._af_price_lbl.setText(f"Price: ${self.af_price:.2f}")
        self._af_value_lbl.setText(f"Market rate:  ${self.af_value:,.0f}")
        self._af_demand_lbl.setText(
            self._rate("Demand:   ", ad) + " / sec  (max at price)")
        self._af_revenue_lbl.setText(
            self._rate("Selling:  ", self._af_sell_rate) +
            f" / sec   ${fmt(self._af_rev_rate)}/sec")
        self._af_status_lbl.setText(self._flow_status(
            self.aframes, af_out, ad, "A-Frame", self.af_price, self.af_value))
        self._af_fab_status_lbl.setText(
            f"A-Frame Fabs: {self.af_fabs}    Output: {fmt(af_out)} / sec")
        self._af_fab_btn.setEnabled(self.steel >= self.STEEL_PER_AF)
        fc = self._af_fab_cost()
        self._af_auto_btn.setText(
            f"A-Frame Fabricator  {fmt_money(fc)}  (+{self.prod_mult:.1f}/sec output)")
        self._af_auto_btn.setEnabled(self.money >= fc)
        if self.solar_dev_unlocked:
            self._panels_lbl.setText(f"Solar Panels: {fmt(self.panels)}")
            self._panel_fab_btn.setText("Fabricate Solar Panel  "
                                        f"({self.STEEL_PER_PANEL:.1f} t steel)")
            self._panel_fab_btn.setEnabled(self.steel >= self.STEEL_PER_PANEL)
            pfc = self._panel_fab_cost()
            self._panel_auto_btn.setText(
                f"Solar Panel Fabricator  {fmt_money(pfc)}  ({self.panel_fabs})")
            self._panel_auto_btn.setEnabled(self.money >= pfc)
            self._field_btn.setText(
                f"Build Solar Field  ({self.FIELD_PANELS} panels + "
                f"{self.FIELD_AFRAMES} A-frames)   [{self.solar_fields} built]")
            self._field_btn.setEnabled(self.panels >= self.FIELD_PANELS
                                       and self.aframes >= self.FIELD_AFRAMES)
            self._solar_status_lbl.setText(
                f"Fields: {self.solar_fields}/{fmt(self._fields_target())} for max "
                f"recharge  ({fmt(self._recharge_rate())} power/sec)")

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
            f"Delivery: +{self.del_drones * 5}%  "
            f"(demand x{self.demand_mult:.2f} total)")

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
        if self.power_unlocked:
            self._dyson_btn.setVisible(True)
            self._dyson_btn.setText(
                f"Dyson Sphere  {fmt_money(self.DYSON_COST)}  "
                f"({self.dyson})  +{fmt(self.DYSON_POWER)} power/sec")
            self._dyson_btn.setEnabled(self.money >= self.DYSON_COST)
        self._space_status_lbl.setText(
            f"Orbital income: ${fmt(orbital_inc)}/sec    "
            f"Space output: {fmt(space_out)}/sec")

    def _refresh_alloc(self):
        used = sum(self.alloc.values())
        for key, lbl in self._alloc_lbls.items():
            lbl.setText(str(self.alloc[key]))
            self._alloc_plus_btns[key].setEnabled(
                used < self.probe_trust and self.alloc[key] < self.ALLOC_MAX)
            self._alloc_minus_btns[key].setEnabled(self.alloc[key] > 0)
        return used

    def _update_probe_fleet(self):
        used = self._refresh_alloc()
        self._pr_count_lbl.setText(
            f"Probes: {fmt(self.probes)}   (launched: {self.probes_launched})")
        self._pr_funds_lbl.setText(
            f"${fmt(self.money)}  |  {fmt(self.ops)} ops")
        self._pr_launch_btn.setText(
            f"LAUNCH PROBE   {fmt_money(self.PROBE_COST_MONEY)} + "
            f"{fmt(self.PROBE_COST_OPS)} ops")
        self._pr_launch_btn.setEnabled(
            not self.endgame_done
            and self.money >= self.PROBE_COST_MONEY
            and self.ops >= self.PROBE_COST_OPS)
        self._pr_explored_lbl.setText(f"UNIVERSE EXPLORED:  {self.explored:.6f} %")
        self._pr_trust1_lbl.setText(
            f"Probe Trust: {used} / {self.probe_trust} allocated   "
            "(Speed & Exploration here; more on Replication)")

    def _update_probe_dev(self):
        used = self._refresh_alloc()
        self._pr_trust2_lbl.setText(
            f"Probe Trust: {used} / {self.probe_trust} allocated")
        rc = self._trust_res_cost()
        self._trust_res_btn.setText(
            f"Probe Design Refinement  ({fmt(rc)} ops)  +1 trust")
        self._trust_res_btn.setEnabled(self.ops >= rc and not self.endgame_done)
        if not self.combat_done and "drift_seen" in self._flags:
            self._combat_btn.setVisible(True)
            self._combat_btn.setText(
                f"AUTHORIZE COMBAT SUBROUTINES  ({fmt(self.COMBAT_OPS)} ops)")
            self._combat_btn.setEnabled(self.ops >= self.COMBAT_OPS)
        if "drift_cleared" in self._flags and not self.woogs_rendered:
            self._render_btn.setVisible(True)
            self._render_btn.setText(
                f"WOOG RECLAMATION LINE  ({fmt(self.WOOG_RENDER_OPS)} ops)  prod x3")
            self._render_btn.setEnabled(self.ops >= self.WOOG_RENDER_OPS)
        if self.drifters >= 1:
            self._pr_drift_lbl.setText(
                f"Woog front: {fmt(self.drifters)} probes under attack.")
        else:
            self._pr_drift_lbl.setText("")
        a = self.alloc
        harvest_ps = self.probes * a["harvest"] * 1e-5
        fab_ps = self.probes * a["fabricate"] * 1e-4 * self.prod_mult
        self._pr_status_lbl.setText(
            f"Harvest: +{fmt(harvest_ps)} tons/sec    "
            f"Fabrication: +{fmt(fab_ps)} units/sec")
        if self.converting or self.endgame_done:
            self._pr_matter_lbl.setVisible(True)
            self._pr_matter_lbl.setText(f"MATTER CONVERTED:   {self.matter_pct:.4f} %")

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

    def _wrap_scroll(self, inner: QWidget) -> QScrollArea:
        """Put a tab's content in a scroll area so it can never be squeezed below
        its minimum and overlap on a short / high-DPI screen (e.g. laptop
        fullscreen) — it scrolls instead. On a tall screen the content fits and no
        scrollbar shows, so nothing changes there."""
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sa.setWidget(inner)
        return sa

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
            elif item.layout():
                self._clear_layout(item.layout())

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)
