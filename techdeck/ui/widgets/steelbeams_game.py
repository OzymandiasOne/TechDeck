"""
ASA: American Steel & Aluminum — Incremental Strategy
Run the yard. Form the Tech Team. Take over the universe.
Inspired by Universal Paperclips by Frank Lantz.
"""
from __future__ import annotations
import random
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QFrame, QTabWidget, QScrollArea,
)
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont


_STYLE = """
QWidget { background-color: #141414; color: #cccccc;
          font-family: Consolas, monospace; font-size: 10pt; }
QPushButton { background-color: #222222; color: #bbbbbb; border: 1px solid #383838;
              border-radius: 2px; padding: 5px 10px;
              font-family: Consolas, monospace; font-size: 9pt; text-align: left; }
QPushButton:hover   { background-color: #2e2e2e; border-color: #555; }
QPushButton:pressed { background-color: #3a3a3a; }
QPushButton:disabled { color: #404040; border-color: #1e1e1e; background-color: #181818; }
QPushButton#fab  { background-color: #1b2e1b; color: #7ec87e; border-color: #3a5a3a;
                   font-size: 11pt; font-weight: bold; text-align: center; }
QPushButton#fab:hover { background-color: #223822; }
QPushButton#fab:disabled { background-color: #181e18; color: #3a4e3a; }
QPushButton#afab { background-color: #1a2838; color: #78b0d0; border-color: #2a4a6a;
                   font-size: 11pt; font-weight: bold; text-align: center; }
QPushButton#afab:hover { background-color: #203040; }
QPushButton#afab:disabled { background-color: #161e28; color: #3a4e5a; }
QPushButton#proj { background-color: #1e1e2e; color: #aaaacc; border-color: #383858;
                   text-align: left; }
QPushButton#proj:hover { background-color: #262636; }
QPushButton#proj:disabled { color: #404050; border-color: #202030; }
QTabWidget::pane { border: 1px solid #2a2a2a; }
QTabBar::tab { background: #1a1a1a; color: #777; padding: 6px 12px;
               border: 1px solid #2a2a2a; font-family: Consolas; font-size: 9pt; }
QTabBar::tab:selected { background: #242424; color: #cccccc;
                        border-bottom: 2px solid #5a9a5a; }
QTabBar::tab:hover { background: #222; color: #aaa; }
QTextEdit { background-color: #0e0e0e; color: #888; border: 1px solid #252525; }
QScrollArea { border: none; background: transparent; }
"""


PROJECTS = [
    dict(id="form_tech_team", name="Form the Tech Team",
         desc="Hire ASA's first dedicated tech staff. Unlocks computing.",
         cost=100,    requires=set(),                  unlock="tech_formed", effect=None),
    dict(id="aframe_proto",   name="A-Frame Prototype",
         desc="Engineer A-Frame structures for solar farms. New product line.",
         cost=500,    requires={"form_tech_team"},      unlock="aframe",      effect=None),
    dict(id="solar_v1",       name="Solar Panel Integration",
         desc="Mount panels on ASA A-Frames. A-Frame demand x2.",
         cost=1000,   requires={"aframe_proto"},        unlock=None,          effect="afd_x2"),
    dict(id="solar_v2",       name="High-Efficiency Panels",
         desc="Premium solar cells. A-Frame price +75%.",
         cost=3000,   requires={"solar_v1"},            unlock=None,          effect="afp_75"),
    dict(id="solar_v3",       name="Perovskite Solar Array",
         desc="Cutting-edge cells. A-Frame demand x3, price x2.",
         cost=8000,   requires={"solar_v2"},            unlock=None,          effect="af_v3"),
    dict(id="algo_trading",   name="Algorithmic Trading",
         desc="Use compute power to play the open market.",
         cost=2000,   requires={"form_tech_team"},      unlock="market",      effect=None),
    dict(id="drone_fleet",    name="Drone Fleet Initiative",
         desc="Industrial drones for manufacturing and delivery.",
         cost=5000,   requires={"algo_trading"},        unlock="drones",      effect=None),
    dict(id="viral_mkt",      name="Viral Marketing Engine",
         desc="Saturate global demand. All demand x3.",
         cost=8000,   requires={"drone_fleet"},         unlock=None,          effect="viral"),
    dict(id="space_div",      name="ASA Space Division",
         desc="Orbital manufacturing. The sky is not the limit.",
         cost=20000,  requires={"drone_fleet"},         unlock="space",       effect=None),
    dict(id="quantum",        name="Quantum Computing Array",
         desc="Exponential ops generation. Ops x10.",
         cost=50000,  requires={"space_div"},           unlock=None,          effect="quantum"),
    dict(id="universal",      name="Universal Expansion Protocol",
         desc="Convert all matter in the universe to ASA product.",
         cost=100000, requires={"quantum"},             unlock="endgame",     effect=None),
]


class SteelBeamsGame(QWidget):

    # Phase 1
    STEEL_PER_TUBE  = 0.1
    START_STEEL     = 5.0
    LOT_TONS        = 100.0
    LOT_COST        = 500.0
    MIN_PRICE       = 5.0
    MAX_PRICE       = 200.0
    DEFAULT_PRICE   = 45.0
    BASE_DEMAND     = 1.5
    FAB_BASE_COST   = 400.0
    FAB_COST_MULT   = 1.18
    MKT_BASE_COST   = 300.0
    MKT_COST_MULT   = 2.0
    FASTER_COST     = 2_000.0
    BULK_COST       = 8_000.0
    PRECISION_COST  = 20_000.0
    # Phase 3
    STEEL_PER_AF    = 0.5
    AF_MIN_PRICE    = 50.0
    AF_MAX_PRICE    = 1_000.0
    AF_DEFAULT_PRICE= 200.0
    AF_BASE_DEMAND  = 0.4
    AF_FAB_BASE     = 800.0
    AF_FAB_MULT     = 1.20
    # Phase 4
    STOCK_START     = 100.0
    STOCK_LOT_SM    = 10
    STOCK_LOT_LG    = 100
    # Phase 5
    MFG_DRONE_COST  = 5_000.0
    DEL_DRONE_COST  = 3_000.0
    MAX_DRONES      = 20
    # Phase 6
    SOLAR_COL_COST  = 50_000.0
    SPACE_FAB_COST  = 200_000.0
    HARVESTER_COST  = 1_000_000.0

    TICK_MS = 100
    TICK_DT = 0.1

    def __init__(self):
        super().__init__(None, Qt.WindowType.Window)
        self.setWindowTitle("ASA: American Steel & Aluminum")
        self.setMinimumSize(740, 680)
        self.resize(800, 760)
        self.setStyleSheet(_STYLE)

        # Phase 1
        self.tubes          = 0.0
        self.steel          = self.START_STEEL
        self.money          = 0.0
        self.total_money    = 0.0
        self.total_made     = 0
        self.total_sold     = 0
        self.price          = self.DEFAULT_PRICE
        self.auto_fabs      = 0
        self.fab_mult       = 1.0
        self.mkt_level      = 0
        self.mkt_mult       = 1.0
        self.gp_mult        = 1.0   # global production multiplier
        self.gd_mult        = 1.0   # global demand multiplier
        self.faster_done    = False
        self.bulk_done      = False
        self.precision_done = False

        # Phase 2 – Tech Team
        self.tech_unlocked  = False
        self.tech_formed    = False
        self.rep_total      = 0
        self.developers     = 1
        self.servers        = 1
        self.ops            = 0.0
        self.ops_mult       = 1.0
        self.completed_projects = set()
        self._proj_tick     = 0

        # Phase 3 – A-Frames
        self.af_unlocked    = False
        self.aframes        = 0.0
        self.af_made        = 0
        self.af_sold        = 0
        self.af_price       = self.AF_DEFAULT_PRICE
        self.af_fabs        = 0
        self.af_d_mult      = 1.0
        self.af_p_mult      = 1.0

        # Phase 4 – Market
        self.market_unlocked = False
        self.stock_price    = self.STOCK_START
        self.stock_prev     = self.STOCK_START
        self.stock_shares   = 0
        self.stock_basis    = 0.0
        self._stock_tick    = 0

        # Phase 5 – Drones
        self.drones_unlocked = False
        self.mfg_drones     = 0
        self.del_drones     = 0

        # Phase 6 – Space
        self.space_unlocked = False
        self.solar_cols     = 0
        self.space_fabs     = 0
        self.harvesters     = 0
        self.endgame        = False

        self._flags         = set()
        self._tick_count    = 0
        self._tick_errors   = 0

        self._build_ui()
        self._update_ui()

        self._timer = QTimer(self)
        self._timer.setInterval(self.TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        self._log("ASA founded. Five tons of scrap steel in the corner of the yard.")
        self._log("Fabricate to begin.")

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(6)

        title = QLabel("ASA: AMERICAN STEEL & ALUMINUM")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Consolas", 13, QFont.Weight.Bold))
        root.addWidget(title)

        # Persistent stats bar
        self._stats_bar = QLabel("")
        self._stats_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stats_bar.setFont(QFont("Consolas", 9))
        self._stats_bar.setStyleSheet("color: #888888;")
        root.addWidget(self._stats_bar)
        root.addWidget(self._hr())

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, stretch=1)

        # Build all tab widgets now; add them to tabs as phases unlock
        self._yard_tab   = self._make_yard_tab()
        self._tech_tab   = self._make_tech_tab()
        self._aframe_tab = self._make_aframe_tab()
        self._market_tab = self._make_market_tab()
        self._drones_tab = self._make_drones_tab()
        self._space_tab  = self._make_space_tab()

        self.tabs.addTab(self._yard_tab, "The Yard")

        root.addWidget(self._hr())
        log_hdr = QLabel("LOG")
        log_hdr.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        root.addWidget(log_hdr)
        self._log_box = QTextEdit()
        self._log_box.setReadOnly(True)
        self._log_box.setFont(QFont("Consolas", 9))
        self._log_box.setFixedHeight(80)
        root.addWidget(self._log_box)

    def _make_yard_tab(self) -> QWidget:
        w = QWidget()
        root = QHBoxLayout(w)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(12)

        # Left: stats + price
        left = QVBoxLayout()
        left.setSpacing(4)
        left.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._y_tubes  = self._ml("Steel Tubes:  0")
        self._btn_fab  = QPushButton("FABRICATE TUBE")
        self._btn_fab.setObjectName("fab")
        self._btn_fab.setFixedHeight(48)
        self._btn_fab.clicked.connect(self._fabricate)
        left.addWidget(self._y_tubes)
        left.addWidget(self._btn_fab)
        left.addWidget(self._hr())
        self._y_stock  = self._ml("Steel Stock:  5.0 tons")
        self._y_money  = self._ml("Funds:        $0.00")
        self._y_made   = self._ml("Total Made:   0")
        self._y_sold   = self._ml("Total Sold:   0")
        for w2 in (self._y_stock, self._y_money, self._y_made, self._y_sold):
            left.addWidget(w2)
        left.addWidget(self._hr())
        pr = QHBoxLayout()
        self._y_price = self._ml(f"Price: ${self.DEFAULT_PRICE:.2f}")
        bdn = QPushButton("-"); bdn.setFixedSize(26, 26); bdn.clicked.connect(self._price_dn)
        bup = QPushButton("+"); bup.setFixedSize(26, 26); bup.clicked.connect(self._price_up)
        pr.addWidget(self._y_price); pr.addWidget(bdn); pr.addWidget(bup); pr.addStretch()
        left.addLayout(pr)
        self._y_demand  = self._ml("Demand:   0.00 / sec")
        self._y_revenue = self._ml("Revenue:  $0.00 / sec")
        left.addWidget(self._y_demand); left.addWidget(self._y_revenue)
        left.addStretch()
        root.addLayout(left, stretch=1)

        # Right: upgrades
        right = QVBoxLayout()
        right.setSpacing(5)
        right.setAlignment(Qt.AlignmentFlag.AlignTop)
        right.addWidget(self._sec("PRODUCTION"))
        self._btn_steel  = self._opbtn(); self._btn_steel.clicked.connect(self._buy_steel)
        self._btn_afab   = self._opbtn(); self._btn_afab.clicked.connect(self._buy_auto_fab)
        self._btn_mkt    = self._opbtn(); self._btn_mkt.clicked.connect(self._buy_marketing)
        self._btn_faster = self._opbtn(); self._btn_faster.clicked.connect(self._buy_faster)
        self._btn_bulk   = self._opbtn(); self._btn_bulk.clicked.connect(self._buy_bulk)
        self._btn_prec   = self._opbtn(); self._btn_prec.clicked.connect(self._buy_precision)
        for b in (self._btn_steel, self._btn_afab, self._btn_mkt,
                  self._btn_faster, self._btn_bulk, self._btn_prec):
            right.addWidget(b)
        right.addWidget(self._hr())
        self._y_fab_status = self._ml("Auto-Fabs: 0    Output: 0.0 / sec")
        right.addWidget(self._y_fab_status)
        right.addStretch()
        root.addLayout(right, stretch=1)
        return w

    def _make_tech_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        top = QHBoxLayout()
        self._t_rep  = self._ml("Reputation: 0 pts available")
        self._t_ops  = self._ml("Ops: 0 / 0   |   Ops/sec: 0.0")
        top.addWidget(self._t_rep); top.addStretch(); top.addWidget(self._t_ops)
        root.addLayout(top)

        hire_row = QHBoxLayout()
        self._btn_hire_dev = self._opbtn(); self._btn_hire_dev.clicked.connect(self._hire_dev)
        self._btn_hire_srv = self._opbtn(); self._btn_hire_srv.clicked.connect(self._hire_srv)
        self._t_devs = self._ml("Developers: 1")
        self._t_srvs = self._ml("Servers: 1")
        hire_row.addWidget(self._btn_hire_dev); hire_row.addWidget(self._t_devs)
        hire_row.addSpacing(16)
        hire_row.addWidget(self._btn_hire_srv); hire_row.addWidget(self._t_srvs)
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
        self._af_count   = self._ml("A-Frames:     0")
        self._btn_af_fab = QPushButton("FABRICATE A-FRAME")
        self._btn_af_fab.setObjectName("afab")
        self._btn_af_fab.setFixedHeight(48)
        self._btn_af_fab.clicked.connect(self._fabricate_af)
        left.addWidget(self._af_count)
        left.addWidget(self._btn_af_fab)
        left.addWidget(self._hr())
        self._af_made    = self._ml("Total Made:   0")
        self._af_sold    = self._ml("Total Sold:   0")
        left.addWidget(self._af_made); left.addWidget(self._af_sold)
        left.addWidget(self._hr())
        pr = QHBoxLayout()
        self._af_price_lbl = self._ml(f"Price: ${self.AF_DEFAULT_PRICE:.2f}")
        bdn = QPushButton("-"); bdn.setFixedSize(26, 26); bdn.clicked.connect(self._af_price_dn)
        bup = QPushButton("+"); bup.setFixedSize(26, 26); bup.clicked.connect(self._af_price_up)
        pr.addWidget(self._af_price_lbl); pr.addWidget(bdn); pr.addWidget(bup); pr.addStretch()
        left.addLayout(pr)
        # _lbl suffix matters: plain `self._af_demand` would shadow the
        # _af_demand() METHOD with a QLabel — the first tick after A-Frames
        # unlock then raises "'QLabel' object is not callable" forever and the
        # game visibly freezes (bit us in v0.8.6).
        self._af_demand_lbl  = self._ml("Demand:   0.00 / sec")
        self._af_revenue = self._ml("Revenue:  $0.00 / sec")
        left.addWidget(self._af_demand_lbl); left.addWidget(self._af_revenue)
        left.addStretch()
        root.addLayout(left, stretch=1)

        right = QVBoxLayout()
        right.setSpacing(5)
        right.setAlignment(Qt.AlignmentFlag.AlignTop)
        right.addWidget(self._sec("A-FRAME PRODUCTION"))
        self._btn_af_auto = self._opbtn(); self._btn_af_auto.clicked.connect(self._buy_af_fab)
        right.addWidget(self._btn_af_auto)
        right.addWidget(self._hr())
        self._af_fab_status = self._ml("A-Frame Fabs: 0    Output: 0.0 / sec")
        right.addWidget(self._af_fab_status)
        right.addStretch()
        root.addLayout(right, stretch=1)
        return w

    def _make_market_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        root.addWidget(self._sec("ASA STOCK EXCHANGE"))
        self._mkt_price   = self._ml("ASA Stock:  $100.00  (--)")
        self._mkt_price.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        root.addWidget(self._mkt_price)

        self._mkt_hold    = self._ml("Holdings:   0 shares  =  $0.00")
        self._mkt_pl      = self._ml("Cost Basis: $0.00   P/L: $0.00")
        root.addWidget(self._mkt_hold)
        root.addWidget(self._mkt_pl)
        root.addWidget(self._hr())

        btn_row1 = QHBoxLayout()
        self._btn_buy10  = self._opbtn(); self._btn_buy10.clicked.connect(lambda: self._buy_stock(10))
        self._btn_sell10 = self._opbtn(); self._btn_sell10.clicked.connect(lambda: self._sell_stock(10))
        btn_row1.addWidget(self._btn_buy10); btn_row1.addWidget(self._btn_sell10)
        root.addLayout(btn_row1)

        btn_row2 = QHBoxLayout()
        self._btn_buy100  = self._opbtn(); self._btn_buy100.clicked.connect(lambda: self._buy_stock(100))
        self._btn_sell100 = self._opbtn(); self._btn_sell100.clicked.connect(lambda: self._sell_stock(100))
        btn_row2.addWidget(self._btn_buy100); btn_row2.addWidget(self._btn_sell100)
        root.addLayout(btn_row2)
        root.addStretch()
        return w

    def _make_drones_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        root.addWidget(self._sec("DRONE FLEET"))
        self._btn_mfg_drone = self._opbtn(); self._btn_mfg_drone.clicked.connect(self._buy_mfg_drone)
        self._btn_del_drone = self._opbtn(); self._btn_del_drone.clicked.connect(self._buy_del_drone)
        root.addWidget(self._btn_mfg_drone)
        root.addWidget(self._btn_del_drone)
        root.addWidget(self._hr())
        self._drone_status = self._ml("Manufacturing: +0%   Delivery: +0%")
        root.addWidget(self._drone_status)
        root.addStretch()
        return w

    def _make_space_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        root.addWidget(self._sec("ASA SPACE DIVISION"))
        self._btn_solar_col  = self._opbtn(); self._btn_solar_col.clicked.connect(self._buy_solar_col)
        self._btn_space_fab  = self._opbtn(); self._btn_space_fab.clicked.connect(self._buy_space_fab)
        self._btn_harvester  = self._opbtn(); self._btn_harvester.clicked.connect(self._buy_harvester)
        root.addWidget(self._btn_solar_col)
        root.addWidget(self._btn_space_fab)
        root.addWidget(self._btn_harvester)
        root.addWidget(self._hr())
        self._space_status = self._ml("Orbital income: $0/sec    Space output: 0/sec")
        root.addWidget(self._space_status)
        self._end_label = QLabel("")
        self._end_label.setWordWrap(True)
        self._end_label.setStyleSheet("color: #c0c080; font-size: 10pt;")
        root.addWidget(self._end_label)
        root.addStretch()
        return w

    # ── Game logic ─────────────────────────────────────────────────────────

    def _tube_demand(self) -> float:
        frac = max(0.0, 1.0 - (self.price - self.MIN_PRICE) / (self.MAX_PRICE - self.MIN_PRICE))
        return self.BASE_DEMAND * self.mkt_mult * self.gd_mult * frac

    def _af_demand(self) -> float:
        frac = max(0.0, 1.0 - (self.af_price - self.AF_MIN_PRICE) / (self.AF_MAX_PRICE - self.AF_MIN_PRICE))
        return self.AF_BASE_DEMAND * self.af_d_mult * self.gd_mult * frac

    def _fab_cost(self) -> float:
        return self.FAB_BASE_COST * (self.FAB_COST_MULT ** self.auto_fabs)

    def _mkt_cost(self) -> float:
        return self.MKT_BASE_COST * (self.MKT_COST_MULT ** self.mkt_level)

    def _steel_cost(self) -> float:
        return (self.LOT_COST / 2) if self.bulk_done else self.LOT_COST

    def _af_fab_cost(self) -> float:
        return self.AF_FAB_BASE * (self.AF_FAB_MULT ** self.af_fabs)

    @property
    def _ops_cap(self) -> float:
        return self.servers * 1000.0

    @property
    def _trust_avail(self) -> int:
        FREE = 2
        return self.rep_total - (self.developers + self.servers - FREE)

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
                    self._log(f"[!] Game error (reported, attempting to continue): {last}")
                except Exception:
                    pass

    def _tick_inner(self):
        dt = self.TICK_DT
        self._tick_count += 1

        # Auto-fab tubes
        if self.auto_fabs > 0:
            want = self.auto_fabs * self.fab_mult * self.STEEL_PER_TUBE * dt
            actual = min(want, self.steel)
            made = (actual / self.STEEL_PER_TUBE) * self.gp_mult
            self.steel -= actual
            self.tubes += made
            self.total_made += int(made)

        # Auto-fab A-frames
        if self.af_unlocked and self.af_fabs > 0:
            want = self.af_fabs * self.STEEL_PER_AF * dt
            actual = min(want, self.steel)
            made = (actual / self.STEEL_PER_AF) * self.gp_mult
            self.steel -= actual
            self.aframes += made
            self.af_made += int(made)

        # Space production (no steel required)
        if self.space_unlocked:
            sp = (self.space_fabs * 10 + self.harvesters * 100) * dt * self.gp_mult
            sa = (self.space_fabs * 2  + self.harvesters * 20)  * dt * self.gp_mult
            pi = (self.solar_cols * 500) * dt
            self.tubes  += sp; self.total_made += int(sp)
            self.aframes += sa; self.af_made   += int(sa)
            self.money  += pi; self.total_money += pi

        # Sell tubes
        td = self._tube_demand()
        sold_t = min(self.tubes, td * dt)
        if sold_t > 0:
            rev = sold_t * self.price
            self.tubes -= sold_t
            self.money += rev
            self.total_money += rev
            self.total_sold += int(sold_t)

        # Sell A-frames
        if self.af_unlocked:
            ad = self._af_demand()
            sold_a = min(self.aframes, ad * dt)
            if sold_a > 0:
                rev = sold_a * self.af_price
                self.aframes -= sold_a
                self.money += rev
                self.total_money += rev
                self.af_sold += int(sold_a)

        # Ops accumulation
        if self.tech_unlocked:
            gain = self.developers * self.ops_mult * dt
            self.ops = min(self.ops + gain, self._ops_cap)

        # Stock price drift (every 5 ticks)
        if self.market_unlocked:
            self._stock_tick += 1
            if self._stock_tick >= 5:
                self._stock_tick = 0
                self.stock_prev = self.stock_price
                change = random.gauss(0.001, 0.025)
                self.stock_price = max(1.0, min(50_000.0, self.stock_price * (1 + change)))

        self._check_milestones()
        self._update_ui()

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
            self._log(f"Need ${cost:,.0f}."); return
        self.money -= cost
        self.steel += self.LOT_TONS
        self._log(f"Purchased {self.LOT_TONS:.0f} tons of steel.")

    def _buy_auto_fab(self):
        cost = self._fab_cost()
        if self.money < cost:
            self._log(f"Need ${cost:,.0f}."); return
        self.money -= cost
        self.auto_fabs += 1
        self._log(f"Auto-Fab #{self.auto_fabs} online.")

    def _buy_marketing(self):
        cost = self._mkt_cost()
        if self.money < cost:
            self._log(f"Need ${cost:,.0f}."); return
        self.money -= cost
        self.mkt_level += 1
        self.mkt_mult *= 1.5
        self._log(f"Marketing Level {self.mkt_level}. Demand x1.5.")

    def _buy_faster(self):
        if self.faster_done: return
        if self.money < self.FASTER_COST:
            self._log(f"Need ${self.FASTER_COST:,.0f}."); return
        self.money -= self.FASTER_COST
        self.faster_done = True
        self.fab_mult *= 2.0
        self._log("Faster Fabs installed. Output doubled.")

    def _buy_bulk(self):
        if self.bulk_done: return
        if self.money < self.BULK_COST:
            self._log(f"Need ${self.BULK_COST:,.0f}."); return
        self.money -= self.BULK_COST
        self.bulk_done = True
        self._log("Bulk steel contract active. Steel 50% off.")

    def _buy_precision(self):
        if self.precision_done: return
        if self.money < self.PRECISION_COST:
            self._log(f"Need ${self.PRECISION_COST:,.0f}."); return
        self.money -= self.PRECISION_COST
        self.precision_done = True
        self.fab_mult *= 2.0
        self._log("Precision Mill online. Output doubled again.")

    def _hire_dev(self):
        if self._trust_avail < 1:
            self._log("Not enough reputation."); return
        self.developers += 1
        self._log(f"Developer hired. Team: {self.developers} devs, {self.servers} servers.")

    def _hire_srv(self):
        if self._trust_avail < 1:
            self._log("Not enough reputation."); return
        self.servers += 1
        self._log(f"Server added. Memory capacity: {self._ops_cap:,.0f} ops.")

    def _complete_project(self, pid: str):
        proj = next((p for p in PROJECTS if p["id"] == pid), None)
        if proj is None or pid in self.completed_projects:
            return
        if not proj["requires"].issubset(self.completed_projects):
            self._log("Requirements not met."); return
        if self.ops < proj["cost"]:
            self._log(f"Need {proj['cost']:,} ops."); return
        self.ops -= proj["cost"]
        self.completed_projects.add(pid)
        self._log(f"Project complete: {proj['name']}")

        unlock = proj.get("unlock")
        effect = proj.get("effect")

        if unlock == "tech_formed":
            self.tech_formed = True
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
        elif unlock == "endgame":
            self.endgame = True
            self.gp_mult *= 100.0
            self._end_label.setText(
                "The protocol is running. ASA fabricators have been deployed across the solar system. "
                "All available matter is being converted to ASA product."
            )
            self._log("Universal Expansion Protocol initiated. The universe belongs to ASA.")

        if effect == "afd_x2":
            self.af_d_mult *= 2.0
            self._log("A-Frame demand doubled.")
        elif effect == "afp_75":
            self.af_p_mult *= 1.75
            self.af_price = min(self.AF_MAX_PRICE, self.af_price * 1.75)
            self._log("A-Frame price +75%.")
        elif effect == "af_v3":
            self.af_d_mult *= 3.0
            self.af_p_mult *= 2.0
            self.af_price = min(self.AF_MAX_PRICE, self.af_price * 2.0)
            self._log("Perovskite array online. A-Frame demand x3, price x2.")
        elif effect == "viral":
            self.gd_mult *= 3.0
            self._log("Viral campaign running. Global demand x3.")
        elif effect == "quantum":
            self.ops_mult *= 10.0
            self._log("Quantum array online. Ops generation x10.")

    def _buy_af_fab(self):
        cost = self._af_fab_cost()
        if self.money < cost:
            self._log(f"Need ${cost:,.0f}."); return
        self.money -= cost
        self.af_fabs += 1
        self._log(f"A-Frame Fabricator #{self.af_fabs} online.")

    def _buy_stock(self, n: int):
        cost = n * self.stock_price
        if self.money < cost:
            self._log(f"Need ${cost:,.2f}."); return
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
            self._log(f"Need ${self.MFG_DRONE_COST:,.0f}."); return
        self.money -= self.MFG_DRONE_COST
        self.mfg_drones += 1
        self.gp_mult = 1.0 + self.mfg_drones * 0.05 + self.del_drones * 0
        self._log(f"Manufacturing Drone #{self.mfg_drones} deployed. Production +{self.mfg_drones*5}%.")

    def _buy_del_drone(self):
        if self.del_drones >= self.MAX_DRONES:
            self._log("Max delivery drones reached."); return
        if self.money < self.DEL_DRONE_COST:
            self._log(f"Need ${self.DEL_DRONE_COST:,.0f}."); return
        self.money -= self.DEL_DRONE_COST
        self.del_drones += 1
        self.gd_mult = max(self.gd_mult, 1.0 + self.del_drones * 0.05)
        self._log(f"Delivery Drone #{self.del_drones} deployed. Demand +{self.del_drones*5}%.")

    def _buy_solar_col(self):
        if self.money < self.SOLAR_COL_COST:
            self._log(f"Need ${self.SOLAR_COL_COST:,.0f}."); return
        self.money -= self.SOLAR_COL_COST
        self.solar_cols += 1
        self._log(f"Solar Collector #{self.solar_cols} in orbit. +$500/sec passive.")

    def _buy_space_fab(self):
        if self.money < self.SPACE_FAB_COST:
            self._log(f"Need ${self.SPACE_FAB_COST:,.0f}."); return
        self.money -= self.SPACE_FAB_COST
        self.space_fabs += 1
        self._log(f"Space Fabricator #{self.space_fabs} deployed. +10 tubes/sec +2 A-frames/sec.")

    def _buy_harvester(self):
        if self.money < self.HARVESTER_COST:
            self._log(f"Need ${self.HARVESTER_COST:,.0f}."); return
        self.money -= self.HARVESTER_COST
        self.harvesters += 1
        self._log(f"Universal Harvester #{self.harvesters} online. +100 tubes/sec +20 A-frames/sec.")

    def _price_up(self): self.price = min(self.MAX_PRICE, self.price + 1.0)
    def _price_dn(self): self.price = max(self.MIN_PRICE, self.price - 1.0)
    def _af_price_up(self): self.af_price = min(self.AF_MAX_PRICE, self.af_price + 5.0)
    def _af_price_dn(self): self.af_price = max(self.AF_MIN_PRICE, self.af_price - 5.0)

    # ── Milestones ─────────────────────────────────────────────────────────

    def _check_milestones(self):
        def fire(key, cond, rep, msg):
            if key not in self._flags and cond:
                self._flags.add(key)
                self.rep_total += rep
                self._log(msg)

        fire("m1",   self.total_made >= 1,           0, "First tube off the line.")
        fire("m10",  self.total_made >= 10,           0, "Getting into a rhythm.")
        fire("m100", self.total_made >= 100,          0, "Production is steady.")
        fire("m1k",  self.total_made >= 1_000,        1, "The mill hums. (+1 rep)")
        fire("m10k", self.total_made >= 10_000,       1, "The yard never sleeps. (+1 rep)")
        fire("m100k",self.total_made >= 100_000,      2, "Supply chain fully operational. (+2 rep)")
        fire("m1m",  self.total_made >= 1_000_000,    3, "ASA dominates the steel market. (+3 rep)")
        fire("s1",   self.total_sold >= 1,            0, "Sold. Money in the account.")
        fire("s100", self.total_sold >= 100,          1, "Repeat customers. (+1 rep)")
        fire("s1k",  self.total_sold >= 1_000,        1, "You're a real supplier now. (+1 rep)")
        fire("s10k", self.total_sold >= 10_000,       2, "Major supplier. (+2 rep)")
        fire("f1",   self.auto_fabs >= 1,             0, "Machine's running. Step back.")
        fire("f5",   self.auto_fabs >= 5,             1, "The floor is automated. (+1 rep)")
        fire("mn1k", self.total_money >= 1_000,       0, "Four figures. Not bad.")
        fire("mn10k",self.total_money >= 10_000,      1, "Five figures. (+1 rep)")
        fire("mn100k",self.total_money >= 100_000,    2, "Six figures. The CFO called. (+2 rep)")
        fire("mn1m", self.total_money >= 1_000_000,   3, "A million dollars. (+3 rep)")
        fire("mn10m",self.total_money >= 10_000_000,  3, "ASA is a major corporation. (+3 rep)")

        if not self.tech_unlocked and self.total_money >= 5_000:
            self.tech_unlocked = True
            self.tabs.addTab(self._tech_tab, "Tech Team")
            self._log("Tech Team formation is available. Check the Tech Team tab.")

        if self.af_unlocked:
            fire("af100", self.af_made >= 100,        1, "A-Frame production running. (+1 rep)")
            fire("af1k",  self.af_made >= 1_000,      2, "Solar division recognized. (+2 rep)")

        if self.endgame and self.total_made >= 1_000_000_000:
            if "universe_done" not in self._flags:
                self._flags.add("universe_done")
                self._end_label.setText(
                    "The last atom has been converted. Every molecule of matter in the observable universe "
                    "is now ASA product. Production: infinite. Revenue: immeasurable. "
                    "ASA controls everything."
                )
                self._log("The universe belongs to ASA. Final score: " + f"{self.total_made:,} units produced.")

    # ── UI updates ─────────────────────────────────────────────────────────

    def _update_ui(self):
        # Stats bar
        parts = [f"Tubes: {int(self.tubes):,}", f"Funds: ${self.money:,.0f}",
                 f"Made: {self.total_made:,}"]
        if self.af_unlocked:
            parts.insert(1, f"A-Frames: {int(self.aframes):,}")
        if self.tech_unlocked:
            parts.append(f"Ops: {self.ops:.0f}/{self._ops_cap:.0f}")
        self._stats_bar.setText("  |  ".join(parts))

        cw = self.tabs.currentWidget()
        if cw is self._yard_tab:      self._update_yard()
        elif cw is self._tech_tab:    self._update_tech()
        elif cw is self._aframe_tab:  self._update_aframe()
        elif cw is self._market_tab:  self._update_market()
        elif cw is self._drones_tab:  self._update_drones()
        elif cw is self._space_tab:   self._update_space()

    def _update_yard(self):
        td = self._tube_demand()
        out = self.auto_fabs * self.fab_mult * self.gp_mult
        self._y_tubes.setText(  f"Steel Tubes:  {int(self.tubes):,}")
        self._y_stock.setText(  f"Steel Stock:  {self.steel:.1f} tons")
        self._y_money.setText(  f"Funds:        ${self.money:,.2f}")
        self._y_made.setText(   f"Total Made:   {self.total_made:,}")
        self._y_sold.setText(   f"Total Sold:   {self.total_sold:,}")
        self._y_price.setText(  f"Price: ${self.price:.2f}")
        self._y_demand.setText( f"Demand:   {td:.2f} / sec")
        self._y_revenue.setText(f"Revenue:  ${td * self.price:.2f} / sec")
        self._y_fab_status.setText(
            f"Auto-Fabs: {self.auto_fabs}    Output: {out:.1f} / sec"
        )
        self._btn_fab.setEnabled(self.steel >= self.STEEL_PER_TUBE)
        sc = self._steel_cost()
        self._btn_steel.setText(f"Buy Steel  ${sc:,.0f}  (+{self.LOT_TONS:.0f} tons)")
        self._btn_steel.setEnabled(self.money >= sc)
        fc = self._fab_cost()
        self._btn_afab.setText(f"Auto-Fabricator  ${fc:,.0f}  (+{self.fab_mult:.1f}/sec)")
        self._btn_afab.setEnabled(self.money >= fc)
        mc = self._mkt_cost()
        self._btn_mkt.setText(f"Marketing Lv{self.mkt_level+1}  ${mc:,.0f}  (x1.5 demand)")
        self._btn_mkt.setEnabled(self.money >= mc)
        if self.faster_done:
            self._btn_faster.setText("Faster Fabs  [installed]")
        else:
            self._btn_faster.setText(f"Faster Fabs  ${self.FASTER_COST:,.0f}  (x2 speed)")
        self._btn_faster.setEnabled(not self.faster_done and self.money >= self.FASTER_COST)
        if self.bulk_done:
            self._btn_bulk.setText("Bulk Contract  [active]")
        else:
            self._btn_bulk.setText(f"Bulk Contract  ${self.BULK_COST:,.0f}  (steel 50% off)")
        self._btn_bulk.setEnabled(not self.bulk_done and self.money >= self.BULK_COST)
        if self.precision_done:
            self._btn_prec.setText("Precision Mill  [online]")
        else:
            self._btn_prec.setText(f"Precision Mill  ${self.PRECISION_COST:,.0f}  (x2 speed)")
        self._btn_prec.setEnabled(not self.precision_done and self.money >= self.PRECISION_COST)

    def _update_tech(self):
        avail = self._trust_avail
        self._t_rep.setText(f"Reputation: {avail} pts available  ({self.rep_total} total)")
        ops_ps = self.developers * self.ops_mult
        self._t_ops.setText(f"Ops: {self.ops:.0f} / {self._ops_cap:.0f}   |   Ops/sec: {ops_ps:.1f}")
        self._t_devs.setText(f"Developers: {self.developers}")
        self._t_srvs.setText(f"Servers: {self.servers}")
        self._btn_hire_dev.setText(f"Hire Developer  (1 rep)  +{self.ops_mult:.0f} ops/sec")
        self._btn_hire_dev.setEnabled(avail >= 1)
        self._btn_hire_srv.setText(f"Buy Server  (1 rep)  +1,000 memory")
        self._btn_hire_srv.setEnabled(avail >= 1)
        if self._tick_count % 10 == 0:
            self._rebuild_projects()

    def _rebuild_projects(self):
        while self._proj_layout.count():
            item = self._proj_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        any_shown = False
        for proj in PROJECTS:
            pid = proj["id"]
            if pid in self.completed_projects:
                continue
            if not proj["requires"].issubset(self.completed_projects):
                continue
            cost = proj["cost"]
            btn = QPushButton(f"{proj['name']}   [{cost:,} ops]\n  {proj['desc']}")
            btn.setObjectName("proj")
            btn.setFixedHeight(44)
            btn.setEnabled(self.ops >= cost)
            btn.clicked.connect(lambda checked=False, p=pid: self._complete_project(p))
            self._proj_layout.addWidget(btn)
            any_shown = True
        if not any_shown:
            lbl = QLabel("  All available projects complete.")
            lbl.setStyleSheet("color: #555;")
            self._proj_layout.addWidget(lbl)
        self._proj_layout.addStretch()

    def _update_aframe(self):
        ad = self._af_demand()
        af_out = self.af_fabs * self.gp_mult
        self._af_count.setText(  f"A-Frames:     {int(self.aframes):,}")
        self._af_made.setText(   f"Total Made:   {self.af_made:,}")
        self._af_sold.setText(   f"Total Sold:   {self.af_sold:,}")
        self._af_price_lbl.setText(f"Price: ${self.af_price:.2f}")
        self._af_demand_lbl.setText(f"Demand:   {ad:.2f} / sec")
        self._af_revenue.setText(f"Revenue:  ${ad * self.af_price:.2f} / sec")
        self._af_fab_status.setText(
            f"A-Frame Fabs: {self.af_fabs}    Output: {af_out:.1f} / sec"
        )
        self._btn_af_fab.setEnabled(self.steel >= self.STEEL_PER_AF)
        fc = self._af_fab_cost()
        self._btn_af_auto.setText(f"A-Frame Fabricator  ${fc:,.0f}  (+{self.gp_mult:.1f}/sec)")
        self._btn_af_auto.setEnabled(self.money >= fc)

    def _update_market(self):
        chg = (self.stock_price - self.stock_prev) / max(1.0, self.stock_prev) * 100
        chg_str = f"{chg:+.2f}%"
        self._mkt_price.setText(f"ASA Stock:  ${self.stock_price:.2f}  ({chg_str})")
        self._mkt_price.setStyleSheet(
            "color: #7ec87e; font-size: 12pt; font-weight: bold;" if chg >= 0
            else "color: #c87e7e; font-size: 12pt; font-weight: bold;"
        )
        val = self.stock_shares * self.stock_price
        self._mkt_hold.setText(f"Holdings:   {self.stock_shares} shares  =  ${val:,.2f}")
        pl = val - self.stock_basis
        self._mkt_pl.setText(f"Cost Basis: ${self.stock_basis:,.2f}   P/L: ${pl:+,.2f}")
        self._btn_buy10.setText(f"Buy 10 shares  (${10*self.stock_price:,.2f})")
        self._btn_buy10.setEnabled(self.money >= 10 * self.stock_price)
        self._btn_sell10.setText(f"Sell 10 shares  (${10*self.stock_price:,.2f})")
        self._btn_sell10.setEnabled(self.stock_shares >= 10)
        self._btn_buy100.setText(f"Buy 100 shares  (${100*self.stock_price:,.2f})")
        self._btn_buy100.setEnabled(self.money >= 100 * self.stock_price)
        self._btn_sell100.setText(f"Sell 100 shares  (${100*self.stock_price:,.2f})")
        self._btn_sell100.setEnabled(self.stock_shares >= 100)

    def _update_drones(self):
        self._btn_mfg_drone.setText(
            f"Manufacturing Drone  ${self.MFG_DRONE_COST:,.0f}  "
            f"({self.mfg_drones}/{self.MAX_DRONES})  +5% production"
        )
        self._btn_mfg_drone.setEnabled(
            self.mfg_drones < self.MAX_DRONES and self.money >= self.MFG_DRONE_COST
        )
        self._btn_del_drone.setText(
            f"Delivery Drone  ${self.DEL_DRONE_COST:,.0f}  "
            f"({self.del_drones}/{self.MAX_DRONES})  +5% demand"
        )
        self._btn_del_drone.setEnabled(
            self.del_drones < self.MAX_DRONES and self.money >= self.DEL_DRONE_COST
        )
        self._drone_status.setText(
            f"Manufacturing: +{self.mfg_drones*5}%   Delivery: +{self.del_drones*5}%"
        )

    def _update_space(self):
        orbital_inc = self.solar_cols * 500
        space_out = self.space_fabs * 10 + self.harvesters * 100
        self._btn_solar_col.setText(
            f"Solar Collector  ${self.SOLAR_COL_COST:,.0f}  "
            f"({self.solar_cols})  +$500/sec"
        )
        self._btn_solar_col.setEnabled(self.money >= self.SOLAR_COL_COST)
        self._btn_space_fab.setText(
            f"Space Fabricator  ${self.SPACE_FAB_COST:,.0f}  "
            f"({self.space_fabs})  +10 tubes/sec  +2 A-frames/sec"
        )
        self._btn_space_fab.setEnabled(self.money >= self.SPACE_FAB_COST)
        self._btn_harvester.setText(
            f"Universal Harvester  ${self.HARVESTER_COST:,.0f}  "
            f"({self.harvesters})  +100 tubes/sec  +20 A-frames/sec"
        )
        self._btn_harvester.setEnabled(self.money >= self.HARVESTER_COST)
        self._space_status.setText(
            f"Orbital income: ${orbital_inc:,}/sec    Space output: {space_out:,}/sec"
        )

    # ── Helpers ────────────────────────────────────────────────────────────

    def _log(self, msg: str):
        self._log_box.append(f"> {msg}")
        sb = self._log_box.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _ml(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(QFont("Consolas", 10))
        return lbl

    def _sec(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        return lbl

    def _hr(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet("color: #2a2a2a;")
        return f

    def _opbtn(self) -> QPushButton:
        b = QPushButton()
        b.setFixedHeight(36)
        return b

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)
