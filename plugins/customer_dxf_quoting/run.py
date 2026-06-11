"""
Customer DXF Quoting plugin for TechDeck.

Opens a customer DXF flat pattern in an interactive viewer: geometry rendered
with layer colors, a table of every entity's length, per-layer subtotals, and a
grand total of linear inches for quoting. Lines can be reassigned to a different
layer (CUT / BEND_UP / BEND_DOWN / BOUNDING_BOX) when the customer's file is
mis-layered. BOUNDING_BOX and IGNORE layers never count toward the total.

The DXF parser is self-contained (stdlib only) so the frozen build needs no new
hiddenimports. ASCII DXF only; supports LINE, ARC, CIRCLE, LWPOLYLINE, POLYLINE.
"""

import math
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QCheckBox,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QGraphicsView,
    QGraphicsScene, QGraphicsPathItem, QGraphicsSimpleTextItem, QGraphicsItem,
    QSplitter, QFileDialog, QMessageBox, QGroupBox, QAbstractItemView
)
from PySide6.QtCore import Qt, QRect, QRectF, QTimer, QItemSelectionModel
from PySide6.QtGui import QPen, QBrush, QColor, QPainter, QPainterPath, QPixmap, QIcon

from techdeck.core.plugin_window import PluginWindow

# Module-level reference prevents the window from being garbage collected when run() returns
_window = None

SUPPORTED_TYPES = {"LINE", "ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE"}

# AutoCAD Color Index -> hex, for the indexes that show up in practice.
# (Full 255-entry ACI table is overkill; unknown indexes fall back to light gray.)
ACI_COLORS = {
    1: "#FF4444", 2: "#FFFF55", 3: "#55FF55", 4: "#55FFFF", 5: "#5577FF",
    6: "#FF55FF", 7: "#F0F0F0", 8: "#9A9A9A", 9: "#C8C8C8",
    250: "#3C3C3C", 251: "#5B5B5B", 252: "#848484", 253: "#ADADAD",
    254: "#D6D6D6", 255: "#FFFFFF",
}

# Layers offered for (re)assignment, and their colors when the file doesn't define them
STANDARD_LAYERS = ["CUT", "BEND_UP", "BEND_DOWN", "BOUNDING_BOX"]
DEFAULT_LAYER_COLORS = {
    "CUT": ACI_COLORS[1], "BEND_UP": ACI_COLORS[4], "BEND_DOWN": ACI_COLORS[6],
    "BOUNDING_BOX": ACI_COLORS[9], "ETCH": ACI_COLORS[2], "FORM": ACI_COLORS[3],
    "IGNORE": ACI_COLORS[8],
}

# Layers that are reference-only: never included in the linear-inch total
NEVER_COUNT = {"BOUNDING_BOX", "BOUNDING BOX", "IGNORE"}


def aci_to_hex(index):
    return ACI_COLORS.get(index, "#DDDDDD")


# ---------------------------------------------------------------------------
# DXF parsing
# ---------------------------------------------------------------------------

def _read_pairs(path):
    """Read an ASCII DXF into a list of (group_code, value) pairs."""
    data = Path(path).read_bytes()
    if data.startswith(b"AutoCAD Binary DXF"):
        raise ValueError("Binary DXF files are not supported - re-export as ASCII DXF.")
    text = None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("Could not decode file - is this a DXF?")

    lines = text.splitlines()
    pairs = []
    it = iter(lines)
    for code_line in it:
        try:
            value = next(it)
        except StopIteration:
            break
        try:
            code = int(code_line.strip())
        except ValueError:
            raise ValueError("Malformed DXF (expected a numeric group code, "
                             f"got {code_line.strip()!r}).")
        pairs.append((code, value.strip()))
    if not pairs:
        raise ValueError("File is empty.")
    return pairs


def _arc_points(cx, cy, r, a0, sweep, n=None):
    """Sample an arc into a polyline for display."""
    if n is None:
        n = max(8, int(abs(sweep) / math.tau * 64) + 1)
    return [(cx + r * math.cos(a0 + sweep * t / n),
             cy + r * math.sin(a0 + sweep * t / n)) for t in range(n + 1)]


def _bulge_segment(p1, p2, bulge):
    """Polyline segment with DXF bulge -> (display points, true arc length)."""
    x1, y1 = p1
    x2, y2 = p2
    dx, dy = x2 - x1, y2 - y1
    chord = math.hypot(dx, dy)
    if abs(bulge) < 1e-12 or chord < 1e-12:
        return [p1, p2], chord
    theta = 4.0 * math.atan(bulge)              # signed included angle (CCW positive)
    radius = chord * (1.0 + bulge * bulge) / (4.0 * abs(bulge))
    # Signed distance from chord midpoint to arc center, along the left normal
    h = chord * (1.0 - bulge * bulge) / (4.0 * bulge)
    mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    nx, ny = -dy / chord, dx / chord
    cx, cy = mx + nx * h, my + ny * h
    a0 = math.atan2(y1 - cy, x1 - cx)
    return _arc_points(cx, cy, radius, a0, theta), radius * abs(theta)


def _collect_until_next_entity(pairs, j):
    """Gather (code, value) groups from j until the next 0 group."""
    groups = []
    n = len(pairs)
    while j < n and pairs[j][0] != 0:
        groups.append(pairs[j])
        j += 1
    return groups, j


def _build_line(groups):
    g = dict()
    for code, val in groups:
        if code in (8, 10, 20, 11, 21):
            g[code] = val
    try:
        p1 = (float(g[10]), float(g[20]))
        p2 = (float(g[11]), float(g[21]))
    except KeyError:
        return None
    return {"type": "LINE", "layer": g.get(8, "0"),
            "points": [p1, p2], "length": math.dist(p1, p2)}


def _build_arc(groups, full_circle=False):
    g = {}
    for code, val in groups:
        if code in (8, 10, 20, 40, 50, 51):
            g[code] = val
    try:
        cx, cy, r = float(g[10]), float(g[20]), float(g[40])
    except KeyError:
        return None
    if full_circle:
        a0, sweep = 0.0, math.tau
        etype = "CIRCLE"
    else:
        a0 = math.radians(float(g.get(50, 0.0)))
        a1 = math.radians(float(g.get(51, 360.0)))
        sweep = (a1 - a0) % math.tau or math.tau
        etype = "ARC"
    return {"type": etype, "layer": g.get(8, "0"),
            "points": _arc_points(cx, cy, r, a0, sweep), "length": r * sweep}


def _build_lwpolyline(groups):
    layer, flags = "0", 0
    verts = []  # each: [x, y, bulge]
    for code, val in groups:
        if code == 8:
            layer = val
        elif code == 70:
            flags = int(val)
        elif code == 10:
            verts.append([float(val), None, 0.0])
        elif code == 20 and verts:
            verts[-1][1] = float(val)
        elif code == 42 and verts:
            verts[-1][2] = float(val)
    return _polyline_entity("LWPOLYLINE", layer, verts, closed=bool(flags & 1))


def _build_polyline(pairs, j):
    """Heavy POLYLINE: consume VERTEX entities through SEQEND. Returns (entity, next_j)."""
    groups, j = _collect_until_next_entity(pairs, j)
    layer, flags = "0", 0
    for code, val in groups:
        if code == 8:
            layer = val
        elif code == 70:
            flags = int(val)
    verts = []
    n = len(pairs)
    while j < n:
        code, val = pairs[j]
        if code == 0 and val == "VERTEX":
            vgroups, j = _collect_until_next_entity(pairs, j + 1)
            v = [None, None, 0.0]
            vflags = 0
            for c, vv in vgroups:
                if c == 10:
                    v[0] = float(vv)
                elif c == 20:
                    v[1] = float(vv)
                elif c == 42:
                    v[2] = float(vv)
                elif c == 70:
                    vflags = int(vv)
            # Skip spline frame control points (flag bit 16)
            if v[0] is not None and v[1] is not None and not (vflags & 16):
                verts.append(v)
        elif code == 0 and val == "SEQEND":
            _, j = _collect_until_next_entity(pairs, j + 1)
            break
        else:
            j += 1
    return _polyline_entity("POLYLINE", layer, verts, closed=bool(flags & 1)), j


def _polyline_entity(etype, layer, verts, closed):
    verts = [v for v in verts if v[1] is not None]
    if len(verts) < 2:
        return None
    points, total = [], 0.0
    seg_pairs = list(zip(verts, verts[1:]))
    if closed:
        seg_pairs.append((verts[-1], verts[0]))
    for v1, v2 in seg_pairs:
        seg_pts, seg_len = _bulge_segment((v1[0], v1[1]), (v2[0], v2[1]), v1[2])
        points.extend(seg_pts if not points else seg_pts[1:])
        total += seg_len
    return {"type": etype, "layer": layer, "points": points, "length": total}


def parse_dxf(path):
    """
    Parse an ASCII DXF.

    Returns (entities, layer_colors, skipped, insunits):
      entities     - list of {type, layer, points [(x,y)...], length}
      layer_colors - {layer_name: hex_color}
      skipped      - {entity_type: count} of unsupported entity types
      insunits     - $INSUNITS header value or None
    """
    pairs = _read_pairs(path)
    n = len(pairs)
    entities, layer_colors, skipped = [], {}, {}
    insunits = None
    section = None
    i = 0
    while i < n:
        code, val = pairs[i]
        if code == 0 and val == "SECTION" and i + 1 < n and pairs[i + 1][0] == 2:
            section = pairs[i + 1][1]
            i += 2
            continue
        if code == 0 and val == "ENDSEC":
            section = None
            i += 1
            continue

        if section == "HEADER" and code == 9 and val == "$INSUNITS":
            if i + 1 < n and pairs[i + 1][0] == 70:
                insunits = int(pairs[i + 1][1])
            i += 1
            continue

        if section == "TABLES" and code == 0 and val == "LAYER":
            groups, i = _collect_until_next_entity(pairs, i + 1)
            name, color = None, 7
            for c, v in groups:
                if c == 2:
                    name = v
                elif c == 62:
                    color = abs(int(v))  # negative = layer off; color is abs value
            if name is not None:
                layer_colors[name] = aci_to_hex(color)
            continue

        if section == "ENTITIES" and code == 0:
            if val == "LINE":
                groups, i = _collect_until_next_entity(pairs, i + 1)
                ent = _build_line(groups)
            elif val == "ARC":
                groups, i = _collect_until_next_entity(pairs, i + 1)
                ent = _build_arc(groups)
            elif val == "CIRCLE":
                groups, i = _collect_until_next_entity(pairs, i + 1)
                ent = _build_arc(groups, full_circle=True)
            elif val == "LWPOLYLINE":
                groups, i = _collect_until_next_entity(pairs, i + 1)
                ent = _build_lwpolyline(groups)
            elif val == "POLYLINE":
                ent, i = _build_polyline(pairs, i + 1)
            else:
                skipped[val] = skipped.get(val, 0) + 1
                i += 1
                continue
            if ent is not None:
                entities.append(ent)
            continue

        i += 1

    return entities, layer_colors, skipped, insunits


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

class DxfView(QGraphicsView):
    """Graphics view with wheel zoom, middle/right-drag pan, left-click select
    (Ctrl+click adds to / removes from the selection)."""

    def __init__(self, on_pick, parent=None):
        super().__init__(parent)
        self._on_pick = on_pick
        self._pan_origin = None
        self.setRenderHint(QPainter.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QColor("#14141c"))
        self.setDragMode(QGraphicsView.NoDrag)
        # No visible scrollbars: pan is drag-based (the hidden bars still hold
        # the scroll range, so the drag-pan handlers keep working) and edge
        # dimension labels no longer butt up against a scrollbar.
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def wheelEvent(self, event):
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.scale(factor, factor)

    def mousePressEvent(self, event):
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._pan_origin = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
            return
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint()
            # 9x9 px pick box so hairline geometry is clickable
            picked = self.items(QRect(pos.x() - 4, pos.y() - 4, 9, 9))
            for item in picked:
                if isinstance(item, QGraphicsPathItem) and item.data(0) is not None:
                    self._on_pick(item.data(0), event.modifiers())
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_origin is not None:
            delta = event.position().toPoint() - self._pan_origin
            self._pan_origin = event.position().toPoint()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._pan_origin is not None and event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._pan_origin = None
            self.setCursor(Qt.ArrowCursor)
            return
        super().mouseReleaseEvent(event)


class QuotingWindow(PluginWindow):

    HIDDEN_BY_DEFAULT = {"BOUNDING_BOX", "BOUNDING BOX", "IGNORE"}

    @classmethod
    def _hidden_by_default(cls, layer):
        name = layer.upper()
        return name in cls.HIDDEN_BY_DEFAULT or name.startswith("BEND")

    def __init__(self, log=print):
        super().__init__("customer_dxf_quoting", "Customer DXF Quoting")
        self.resize(1320, 840)
        self._log = log
        self.entities = []
        self.layer_colors = {}
        self.items = []        # QGraphicsPathItem per entity
        self.labels = []       # QGraphicsSimpleTextItem per entity
        self.layer_checks = {}
        self._geom_rect = QRectF()
        self._build_ui()

    # ----- UI construction -------------------------------------------------

    def _build_ui(self):
        container = QWidget()
        root = QVBoxLayout(container)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        toolbar = QHBoxLayout()
        self.btn_open = QPushButton("Open DXF...")
        self.btn_open.clicked.connect(self.open_file_dialog)
        self.btn_fit = QPushButton("Fit View")
        self.btn_fit.clicked.connect(self.fit_view)
        self.chk_labels = QCheckBox("Show length labels")
        self.chk_labels.setChecked(True)
        self.chk_labels.toggled.connect(self._update_label_visibility)
        self.lbl_file = QLabel("No file loaded")
        toolbar.addWidget(self.btn_open)
        toolbar.addWidget(self.btn_fit)
        toolbar.addSpacing(12)
        toolbar.addWidget(self.chk_labels)
        toolbar.addStretch(1)
        toolbar.addWidget(self.lbl_file)
        root.addLayout(toolbar)

        splitter = QSplitter(Qt.Horizontal)

        self.scene = QGraphicsScene()
        self.view = DxfView(on_pick=self._on_view_pick)
        self.view.setScene(self.scene)
        splitter.addWidget(self.view)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        self.layers_group = QGroupBox("Layers (checked = shown + counted)")
        self.layers_layout = QVBoxLayout(self.layers_group)
        self.layers_layout.setSpacing(2)
        right_layout.addWidget(self.layers_group)

        assign_row = QHBoxLayout()
        assign_row.addWidget(QLabel("Assign selected lines to:"))
        self.cmb_assign = QComboBox()
        self.cmb_assign.addItems(STANDARD_LAYERS)
        # Auto-apply: picking a layer assigns the selected lines immediately —
        # no Apply click. `activated` only fires on USER interaction (including
        # re-picking the same entry), never on programmatic combo refreshes.
        self.cmb_assign.activated.connect(self._assign_selected)
        assign_row.addWidget(self.cmb_assign, 1)
        right_layout.addLayout(assign_row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["#", "Layer", "Type", "Length (in)"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._sync_highlights)
        self.table.cellClicked.connect(self._center_on_row)
        right_layout.addWidget(self.table, 1)

        totals = QGroupBox("Totals")
        totals_layout = QVBoxLayout(totals)
        self.lbl_total = QLabel("Total linear inches: -")
        self.lbl_total.setStyleSheet("font-size: 15px; font-weight: bold;")
        self.lbl_skipped = QLabel("")
        totals_layout.addWidget(self.lbl_total)
        totals_layout.addWidget(self.lbl_skipped)
        right_layout.addWidget(totals)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([800, 500])
        root.addWidget(splitter, 1)

        self.set_content(container)

    # ----- file loading -----------------------------------------------------

    def open_file_dialog(self):
        start_dir = str(Path.home() / "Downloads")
        path, _ = QFileDialog.getOpenFileName(
            self, "Open DXF", start_dir, "DXF files (*.dxf);;All files (*.*)")
        if path:
            self.load_dxf(path)

    def load_dxf(self, path):
        try:
            entities, layer_colors, skipped, insunits = parse_dxf(path)
        except Exception as e:
            QMessageBox.critical(self, "Customer DXF Quoting", f"Could not read DXF:\n{e}")
            self._log(f"Failed to read {path}: {e}")
            return
        if not entities:
            QMessageBox.warning(self, "Customer DXF Quoting",
                                "No measurable geometry (LINE/ARC/CIRCLE/POLYLINE) found.")
            return

        self.entities = entities
        self.layer_colors = layer_colors

        self.lbl_file.setText(Path(path).name)
        self._populate_scene()
        self._populate_layer_checks()
        self._refresh_assign_combo()
        self._populate_table()
        self._apply_layer_visibility()
        self.refresh_totals()
        # Defer the fit until the splitter/layout has settled at its real size,
        # otherwise the drawing lands off-center in a half-laid-out view
        QTimer.singleShot(0, self.fit_view)

        if skipped:
            detail = ", ".join(f"{t} x{c}" for t, c in sorted(skipped.items()))
            self.lbl_skipped.setText(f"Skipped (unsupported): {detail}")
            self._log(f"Skipped unsupported entities: {detail}")
        else:
            self.lbl_skipped.setText("")
        if insunits not in (None, 0, 1):
            self._log(f"NOTE: DXF $INSUNITS={insunits} (not inches) - "
                      "totals are in drawing units.")
        self._log_summary(path)

    def _log_summary(self, path):
        self._log(f"Loaded {Path(path).name}: {len(self.entities)} entities")
        for layer in self._layers_in_order():
            ents = [e for e in self.entities if e["layer"] == layer]
            total = sum(e["length"] for e in ents)
            suffix = "  [not counted]" if layer.upper() in NEVER_COUNT else ""
            self._log(f"  {layer}: {total:.4f} in ({len(ents)} entities){suffix}")

    # ----- scene / table / layer panel construction -------------------------

    def _layers_in_order(self):
        seen = []
        for e in self.entities:
            if e["layer"] not in seen:
                seen.append(e["layer"])
        return seen

    def _layer_color(self, layer):
        return self.layer_colors.get(layer) or DEFAULT_LAYER_COLORS.get(layer.upper(), "#DDDDDD")

    def _entity_tooltip(self, idx):
        e = self.entities[idx]
        return (f"#{idx + 1}  {e['type']} on {e['layer']}\n"
                f"Length: {e['length']:.4f} in")

    def _populate_scene(self):
        self.scene.clear()
        self.items = []
        self.labels = []
        xs, ys = [], []
        for idx, e in enumerate(self.entities):
            color = QColor(self._layer_color(e["layer"]))
            path = QPainterPath()
            pts = e["points"]
            # Negate Y: DXF is y-up, Qt scenes are y-down
            path.moveTo(pts[0][0], -pts[0][1])
            for x, y in pts[1:]:
                path.lineTo(x, -y)
            xs.extend(p[0] for p in pts)
            ys.extend(-p[1] for p in pts)
            item = QGraphicsPathItem(path)
            pen = QPen(color)
            pen.setCosmetic(True)
            pen.setWidthF(1.4)
            item.setPen(pen)
            item.setData(0, idx)
            item.setToolTip(self._entity_tooltip(idx))
            self.scene.addItem(item)
            self.items.append(item)

            mid = pts[len(pts) // 2]
            label = QGraphicsSimpleTextItem(f"{e['length']:.3f}\"")
            label.setBrush(QBrush(color))
            label.setFlag(QGraphicsItem.ItemIgnoresTransformations)
            label.setPos(mid[0], -mid[1])
            label.setZValue(10)
            self.scene.addItem(label)
            self.labels.append(label)

        # Fit on the geometry only - the fixed-size text labels report inflated
        # scene bounds (ItemIgnoresTransformations), which skewed fitInView
        self._geom_rect = QRectF()
        if xs:
            self._geom_rect = QRectF(min(xs), min(ys),
                                     (max(xs) - min(xs)) or 1.0,
                                     (max(ys) - min(ys)) or 1.0)
            # Pin the scene rect symmetrically around the part. Without this
            # the label items inflate sceneRect asymmetrically (down/right),
            # so fitInView's centering scroll could not reach center and the
            # part sat high in the viewport. The 1x padding each side leaves
            # room to drag-pan when zoomed in.
            pad_x = max(self._geom_rect.width(), 1.0)
            pad_y = max(self._geom_rect.height(), 1.0)
            self.scene.setSceneRect(
                self._geom_rect.adjusted(-pad_x, -pad_y, pad_x, pad_y))

    def _populate_layer_checks(self, preserve=None):
        preserve = preserve or {}
        while self.layers_layout.count():
            item = self.layers_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.layer_checks = {}
        for layer in self._layers_in_order():
            ents = [e for e in self.entities if e["layer"] == layer]
            total = sum(e["length"] for e in ents)
            text = f"{layer}   -   {total:.4f} in   ({len(ents)})"
            if layer.upper() in NEVER_COUNT:
                text += "   [never counted]"
            chk = QCheckBox(text)
            chip = QPixmap(12, 12)
            chip.fill(QColor(self._layer_color(layer)))
            chk.setIcon(QIcon(chip))
            chk.setChecked(preserve.get(layer, not self._hidden_by_default(layer)))
            chk.toggled.connect(self._on_layer_toggled)
            self.layers_layout.addWidget(chk)
            self.layer_checks[layer] = chk

    def _refresh_assign_combo(self):
        current = self.cmb_assign.currentText()
        layers = list(STANDARD_LAYERS)
        layers += [l for l in self._layers_in_order() if l not in layers]
        self.cmb_assign.blockSignals(True)
        self.cmb_assign.clear()
        self.cmb_assign.addItems(layers)
        if current in layers:
            self.cmb_assign.setCurrentText(current)
        self.cmb_assign.blockSignals(False)

    def _populate_table(self):
        self.table.clearSelection()
        self.table.setRowCount(len(self.entities))
        for idx, e in enumerate(self.entities):
            cells = [str(idx + 1), e["layer"], e["type"], f"{e['length']:.4f}"]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col in (0, 3):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(idx, col, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)

    # ----- interactivity ----------------------------------------------------

    def _selected_rows(self):
        return {ix.row() for ix in self.table.selectionModel().selectedRows()}

    def _on_view_pick(self, idx, modifiers):
        if modifiers & Qt.ControlModifier:
            model_index = self.table.model().index(idx, 0)
            self.table.selectionModel().select(
                model_index, QItemSelectionModel.Toggle | QItemSelectionModel.Rows)
        else:
            self.table.selectRow(idx)
        self.table.scrollToItem(self.table.item(idx, 0))

    def _center_on_row(self, row, _col=0):
        if 0 <= row < len(self.items):
            self.view.centerOn(self.items[row])

    def _sync_highlights(self):
        selected = self._selected_rows()
        for idx, item in enumerate(self.items):
            pen = item.pen()
            if idx in selected:
                pen.setColor(QColor("#FFFFFF"))
                pen.setWidthF(3.5)
            else:
                pen.setColor(QColor(self._layer_color(self.entities[idx]["layer"])))
                pen.setWidthF(1.4)
            item.setPen(pen)

    def _assign_selected(self, _index=None):
        rows = sorted(self._selected_rows())
        if not rows:
            # Combo navigation with nothing selected is a no-op (auto-apply
            # fires on every pick) — a modal here would nag, so just log a hint.
            self._log("No lines selected — click a line in the view or table, "
                      "then pick a layer to reassign it.")
            return
        layer = self.cmb_assign.currentText()
        if layer not in self.layer_colors:
            self.layer_colors[layer] = DEFAULT_LAYER_COLORS.get(layer.upper(), "#DDDDDD")
        color = QColor(self._layer_color(layer))
        states = {l: c.isChecked() for l, c in self.layer_checks.items()}
        states.setdefault(layer, True)  # make a newly used layer visible so the change shows
        for r in rows:
            self.entities[r]["layer"] = layer
            self.labels[r].setBrush(QBrush(color))
            self.items[r].setToolTip(self._entity_tooltip(r))
            self.table.item(r, 1).setText(layer)
        self._populate_layer_checks(preserve=states)
        self._refresh_assign_combo()
        self._apply_layer_visibility()
        self._sync_highlights()
        self.refresh_totals()
        self._log(f"Assigned {len(rows)} line(s) to {layer}")

    def _included_layers(self):
        return {layer for layer, chk in self.layer_checks.items()
                if chk.isChecked() and layer.upper() not in NEVER_COUNT}

    def _on_layer_toggled(self, _checked):
        self._apply_layer_visibility()
        self.refresh_totals()

    def _apply_layer_visibility(self):
        labels_on = self.chk_labels.isChecked()
        dim = QBrush(QColor("#777777"))
        for idx, e in enumerate(self.entities):
            chk = self.layer_checks.get(e["layer"])
            visible = chk.isChecked() if chk else True
            counted = visible and e["layer"].upper() not in NEVER_COUNT
            self.items[idx].setVisible(visible)
            self.labels[idx].setVisible(visible and labels_on)
            for col in range(self.table.columnCount()):
                cell = self.table.item(idx, col)
                if cell:
                    cell.setData(Qt.ForegroundRole, None if counted else dim)

    def _update_label_visibility(self, _checked=None):
        self._apply_layer_visibility()

    def refresh_totals(self):
        included = self._included_layers()
        ents = [e for e in self.entities if e["layer"] in included]
        total = sum(e["length"] for e in ents)
        self.lbl_total.setText(f"Total linear inches: {total:.4f} in"
                               f"   ({len(ents)} entities)")

    def fit_view(self):
        if not self._geom_rect.isNull():
            # 12% breathing room so edge dimension labels (fixed-size text
            # hanging outside the geometry) stay clear of the view edges.
            margin_x = self._geom_rect.width() * 0.12
            margin_y = self._geom_rect.height() * 0.12
            self.view.fitInView(self._geom_rect.adjusted(-margin_x, -margin_y,
                                                         margin_x, margin_y),
                                Qt.KeepAspectRatio)


# ---------------------------------------------------------------------------
# Plugin entrypoint
# ---------------------------------------------------------------------------

def run(params: dict, progress_callback, cancel_event):
    global _window
    log = params.get("log", print)
    settings = params.get("settings", {})

    log("Opening Customer DXF Quoting...")
    progress_callback(10)

    _window = QuotingWindow(log=log)
    _window.show()

    default = (settings.get("default_dxf") or "").strip()
    if default and Path(default).is_file():
        _window.load_dxf(default)
    else:
        _window.open_file_dialog()

    progress_callback(100)
    log("Customer DXF Quoting window opened.")
