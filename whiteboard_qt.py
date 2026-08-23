#!/usr/bin/env python3
"""Interactive Whiteboard Pro â€” Qt edition (Session 1).

Modern shell + GPU canvas. Compatible with legacy .wbd documents for the
supported object subset (pen/highlighter/line/arrow/rect/oval/text).
"""
from __future__ import annotations

import json
import math
import sys
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import Qt, QPointF, QRectF, QLineF, QMarginsF
from PySide6.QtGui import (QAction, QBrush, QColor, QFont, QPainter, QPainterPath,
                           QPen, QImage, QIcon, QKeySequence, QGuiApplication)
from PySide6.QtWidgets import (QApplication, QColorDialog, QComboBox, QFileDialog,
                               QFrame, QGraphicsEllipseItem, QGraphicsItem,
                               QGraphicsLineItem, QGraphicsPathItem,
                               QGraphicsRectItem, QGraphicsScene,
                               QGraphicsTextItem, QGraphicsView,
                               QHBoxLayout, QLabel, QInputDialog, QListWidget,
                               QMainWindow, QMessageBox, QPushButton, QSizePolicy,
                               QSlider, QVBoxLayout, QWidget, QGridLayout,
                               QDialog, QLineEdit, QSpinBox, QCheckBox,
                               QDialogButtonBox, QVBoxLayout as VBox)

APP_ID = "InteractiveWhiteboard"
DOC_VERSION = 1


def QDate_str() -> str:
    from datetime import date
    return date.today().isoformat()


try:
    from whiteboard import PEN_PRESETS  # reuse presets
except Exception:
    PEN_PRESETS = {
        "fine":   {"label": "Fine",   "size": 3,  "pressure": 35, "flow": 100, "sensitivity": 25},
        "brush":  {"label": "Brush",  "size": 9,  "pressure": 80, "flow": 92,  "sensitivity": 70},
        "marker": {"label": "Marker", "size": 15, "pressure": 15, "flow": 60,  "sensitivity": 10},
    }

QSS = """
* { font-family: 'Segoe UI', 'Arial', 'Noto Sans', sans-serif; font-size: 13px; }
QMainWindow, QWidget#sidebar { background: #1e2530; }
QWidget#canvasHost { background: #2b3442; }
QToolBar { background: #1e2530; border: none; padding: 4px 6px; spacing: 2px; }
QToolBar QToolButton { background: transparent; color: #cfd8dc; border: none;
    border-radius: 6px; padding: 6px 9px; }
QToolBar QToolButton:hover { background: #31405a; color: white; }
QToolBar QToolButton:pressed, QToolBar QToolButton:checked { background: #2196f3; color: white; }
QLabel { color: #b0bec5; background: transparent; }
QPushButton { background: #31405a; color: #eceff1; border: none; border-radius: 6px;
    padding: 7px 10px; }
QPushButton:hover { background: #3c5077; }
QPushButton#accent { background: #2196f3; color: white; }
QPushButton#accent:hover { background: #42a5f5; }
QPushButton:checked { background: #2196f3; color: white; }
QSlider::groove:horizontal { height: 4px; background: #3c5077; border-radius: 2px; }
QSlider::handle:horizontal { width: 14px; margin: -6px 0; background: #2196f3; border-radius: 7px; }
QStatusBar { background: #171c25; color: #90a4ae; }
QToolTip { background: #11151c; color: white; border: none; padding: 4px; }
"""


def _qcolor(hex_str: str, alpha: int = 255) -> QColor:
    c = QColor(hex_str)
    c.setAlpha(alpha)
    return c


class StrokeItem(QGraphicsPathItem):
    def kind(self):
        return self.data(0).get("type")


class BoardView(QGraphicsView):
    """Infinite canvas: wheel = zoom at cursor, middle-drag = pan."""

    def __init__(self, scene, win):
        super().__init__(scene)
        self.win = win
        self.setRenderHints(QPainter.RenderHint.Antialiasing |
                            QPainter.RenderHint.TextAntialiasing |
                            QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setBackgroundBrush(QColor("#ffffff"))
        self.setMouseTracking(True)
        self._panning = False
        self._pan_start = QPointF()
        self._creating = None          # temp QGraphicsItem while drawing shapes
        self._start_pt = QPointF()
        self._erasing = False

    # ------------------------------------------------------------- helpers
    def _tool(self):
        return self.win.tool

    def _pen(self, color, width, alpha=255):
        pen = QPen(_qcolor(color, alpha))
        pen.setWidthF(max(0.5, width))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    # ------------------------------------------------------------- zoom/pan
    def wheelEvent(self, e):
        factor = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        factor = max(1 / 20, min(40, factor))
        self.scale(factor, factor)
        self.win.update_zoom_label()
        e.accept()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = e.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            e.accept()
            return
        tool = self._tool()
        if tool == "select":
            super().mousePressEvent(e)          # native move / selection
            return
        if e.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(e)
            return
        sp = self.mapToScene(e.position().toPoint())
        if tool == "eraser":
            self.win.push_undo()
            self._erasing = True
            self._erase_at(sp)
            e.accept()
            return
        if tool in ("pen", "highlighter"):
            self.win.push_undo()
            spec = PEN_PRESETS.get(self.win.active_preset, {})
            width = float(self.win.size_value)
            item = StrokeItem()
            path = QPainterPath(sp)
            item.setPath(path)
            alpha = 255 if tool == "pen" else 90
            item.setPen(self._pen(self.win.color, width, alpha))
            item.setZValue(5 if tool == "highlighter" else 10)
            item.setData(0, {"type": tool, "points": [[sp.x(), sp.y()], [sp.x(), sp.y()]],
                             "width": width, "color": self.win.color,
                             "alpha": alpha, "layer": self.win.current_layer})
            self.scene().addItem(item)
            self._creating = item
            e.accept()
            return
        # shapes
        self.win.push_undo()
        self._start_pt = sp
        if tool == "line":
            it = QGraphicsLineItem(QLineF(sp, sp))
            it.setPen(self._pen(self.win.color, self.win.size_value))
            payload = {"type": "line", "p1": [sp.x(), sp.y()], "p2": [sp.x(), sp.y()],
                       "color": self.win.color, "width": self.win.size_value, "layer": self.win.current_layer}
        elif tool == "arrow":
            it = StrokeItem()
            it.setPath(self._arrow_path(sp, sp))
            it.setPen(self._pen(self.win.color, self.win.size_value))
            it.setBrush(QBrush(_qcolor(self.win.color)))
            payload = {"type": "arrow", "p1": [sp.x(), sp.y()], "p2": [sp.x(), sp.y()],
                       "head": [], "color": self.win.color,
                       "width": self.win.size_value, "layer": self.win.current_layer}
        elif tool == "rect":
            it = QGraphicsRectItem(QRectF(sp, sp))
            it.setPen(self._pen(self.win.color, self.win.size_value))
            payload = {"type": "rect", "x1": sp.x(), "y1": sp.y(), "x2": sp.x(), "y2": sp.y(),
                       "color": self.win.color, "width": self.win.size_value,
                       "fill": None, "layer": self.win.current_layer}
        elif tool == "ellipse":
            it = QGraphicsEllipseItem(QRectF(sp, sp))
            it.setPen(self._pen(self.win.color, self.win.size_value))
            payload = {"type": "oval", "x1": sp.x(), "y1": sp.y(), "x2": sp.x(), "y2": sp.y(),
                       "color": self.win.color, "width": self.win.size_value,
                       "fill": None, "layer": self.win.current_layer}
        else:
            super().mousePressEvent(e)
            return
        it.setData(0, payload)
        it.setZValue(10)
        self.scene().addItem(it)
        self._creating = it
        e.accept()

    def mouseMoveEvent(self, e):
        if self._panning:
            delta = e.position() - self._pan_start
            self._pan_start = e.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))
            e.accept()
            return
        sp = self.mapToScene(e.position().toPoint())
        tool = self._tool()
        if self._erasing:
            self._erase_at(sp)
            e.accept()
            return
        if self._creating is not None and tool in ("pen", "highlighter"):
            path = self._creating.path()
            path.lineTo(sp)
            self._creating.setPath(path)
            pl = self._creating.data(0)
            pl["points"].append([sp.x(), sp.y()])
            e.accept()
            return
        if self._creating is not None and tool == "line":
            it = self._creating
            it.setLine(QLineF(self._start_pt, sp))
            it.data(0)["p2"] = [sp.x(), sp.y()]
            e.accept()
            return
        if self._creating is not None and tool == "arrow":
            it = self._creating
            it.setPath(self._arrow_path(self._start_pt, sp))
            pl = it.data(0)
            pl["p2"] = [sp.x(), sp.y()]
            pl["head"] = [[p.x(), p.y()] for p in self._arrow_head(self._start_pt, sp)]
            e.accept()
            return
        if self._creating is not None and tool in ("rect", "ellipse"):
            r = QRectF(self._start_pt, sp).normalized()
            self._creating.setRect(r)
            pl = self._creating.data(0)
            pl["x1"], pl["y1"], pl["x2"], pl["y2"] = r.left(), r.top(), r.right(), r.bottom()
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._panning:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            e.accept()
            return
        if self._erasing:
            self._erasing = False
            e.accept()
            return
        if self._creating is not None:
            item, self._creating = self._creating, None
            pl = item.data(0)
            if pl["type"] in ("line", "arrow"):
                a, b = QPointF(*pl["p1"]), QPointF(*pl["p2"])
                if QLineF(a, b).length() < 3:
                    self.scene().removeItem(item)
                    self.win.pop_undo()
                    e.accept()
                    return
            if pl["type"] in ("rect", "oval"):
                r = item.rect()
                if r.width() < 3 and r.height() < 3:
                    self.scene().removeItem(item)
                    self.win.pop_undo()
                    e.accept()
                    return
            if pl["type"] in ("pen", "highlighter") and len(pl["points"]) < 3:
                self.scene().removeItem(item)
                self.win.pop_undo()
                e.accept()
                return
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        if self._tool() == "text":
            sp = self.mapToScene(e.position().toPoint())
            self.win.add_text_at(sp)
            e.accept()
            return
        super().mouseDoubleClickEvent(e)

    # ------------------------------------------------------------- shapes utils
    def _arrow_head(self, a: QPointF, b: QPointF):
        dx, dy = b.x() - a.x(), b.y() - a.y()
        r = math.hypot(dx, dy)
        if r < 1e-6:
            return []
        ux, uy = dx / r, dy / r
        hl = min(22.0, r * 0.35)
        hw = hl * 0.5
        back = QPointF(b.x() - ux * hl, b.y() - uy * hl)
        perp = QPointF(-uy, ux)
        return [back + perp * hw, b, back - perp * hw]

    def _arrow_path(self, a: QPointF, b: QPointF) -> QPainterPath:
        path = QPainterPath(a)
        path.lineTo(b)
        head = self._arrow_head(a, b)
        if head:
            poly = QPainterPath(head[0])
            for p in head[1:]:
                poly.lineTo(p)
            poly.closeSubpath()
            path = path.united(poly)
        return path

    def _erase_at(self, sp: QPointF):
        for it in self.scene().items(sp, Qt.ItemSelectionMode.IntersectsItemShape,
                                     Qt.SortOrder.DescendingOrder):
            if isinstance(it, QGraphicsTextItem):
                continue
            if it.data(0):
                self.scene().removeItem(it)

    # ------------------------------------------------------------- grid
    def drawBackground(self, painter: QPainter, rect: QRectF):
        painter.fillRect(rect, QColor("#ffffff"))
        step = 24.0
        zoom = self.transform().m11()
        while step * zoom < 10:
            step *= 2
        pen = QPen(QColor(210, 216, 224))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        x0 = math.floor(rect.left() / step) * step
        y0 = math.floor(rect.top() / step) * step
        r = 1.1
        for x in [x0 + i * step for i in range(int(rect.width() / step) + 2)]:
            for y in [y0 + j * step for j in range(int(rect.height() / step) + 2)]:
                painter.drawEllipse(QPointF(x, y), r, r)


def payload_to_item(pl: dict):
    t = pl.get("type")
    color = pl.get("color", "#000000")
    width = float(pl.get("width", 3))
    if t in ("pen", "highlighter"):
        it = StrokeItem()
        path = QPainterPath()
        pts = pl.get("points", [])
        if pts:
            path.moveTo(QPointF(pts[0][0], pts[0][1]))
            for p in pts[1:]:
                path.lineTo(QPointF(p[0], p[1]))
        it.setPath(path)
        it.setPen(QPen(QBrush(_qcolor(color, pl.get("alpha", 255))), width,
                       Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                       Qt.PenJoinStyle.RoundJoin))
    elif t == "line":
        it = QGraphicsLineItem(QLineF(QPointF(*pl["p1"]), QPointF(*pl["p2"])))
        it.setPen(QPen(QColor(color), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    elif t == "arrow":
        it = StrokeItem()
        a, b = QPointF(*pl["p1"]), QPointF(*pl["p2"])
        it.setPath(QPainterPath(a))
        head = [[b.x(), b.y()]]
        it.setData(0, {})
        path = QPainterPath(a)
        path.lineTo(b)
        hl = min(22.0, max(3.0, QLineF(a, b).length() * 0.35))
        ux, uy = 0, 0
        r = math.hypot(b.x() - a.x(), b.y() - a.y())
        if r > 1e-6:
            ux, uy = (b.x() - a.x()) / r, (b.y() - a.y()) / r
        back = QPointF(b.x() - ux * hl, b.y() - uy * hl)
        perp = QPointF(-uy, ux)
        poly = QPainterPath(back + perp * (hl * 0.5))
        poly.lineTo(b)
        poly.lineTo(back - perp * (hl * 0.5))
        poly.closeSubpath()
        it.setPath(path.united(poly))
        it.setPen(QPen(QColor(color), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        it.setBrush(QBrush(QColor(color)))
        pl = dict(pl)
        pl.setdefault("head", head)
    elif t == "rect":
        it = QGraphicsRectItem(QRectF(QPointF(pl["x1"], pl["y1"]), QPointF(pl["x2"], pl["y2"])))
        it.setPen(QPen(QColor(color), width))
        if pl.get("fill"):
            it.setBrush(QBrush(QColor(pl["fill"])))
    elif t == "oval":
        it = QGraphicsEllipseItem(QRectF(QPointF(pl["x1"], pl["y1"]), QPointF(pl["x2"], pl["y2"])))
        it.setPen(QPen(QColor(color), width))
        if pl.get("fill"):
            it.setBrush(QBrush(QColor(pl["fill"])))
    elif t == "text":
        it = QGraphicsTextItem(pl.get("text", ""))
        it.setDefaultTextColor(QColor(color))
        f = QFont("Segoe UI", int(pl.get("size", 18)))
        it.setFont(f)
        it.setPos(QPointF(*pl.get("pos", [0, 0])))
    else:
        return None
    it.setData(0, deepcopy(pl))
    it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
    it.setZValue(5 if t == "highlighter" else 10)
    return it


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Interactive Whiteboard Pro")
        self.resize(1500, 950)
        self.color = "#111111"
        self.size_value = 4.0
        self.tool = "pen"
        self.active_preset = "fine"
        self.undo_stack: list = []
        self.redo_stack: list = []
        self.current_file: str | None = None
        self.layers = [{"name": "Layer 1", "visible": True}]
        self.current_layer = 0
        self.pages: list[list[dict]] = [[]]
        self.page_idx = 0

        self.scene = QGraphicsScene(-100000, -100000, 200000, 200000)
        self.view = BoardView(self.scene, self)

        self._build_toolbar()
        side = self._build_sidebar()
        central = QWidget()
        central.setObjectName("canvasHost")
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(side)
        lay.addWidget(self.view, 1)
        self.setCentralWidget(central)
        self.statusBar().showMessage("Ready — Qt edition")
        self.apply_preset("fine")
        self._refresh_layer_combo()

    # ------------------------------------------------------------ toolbar
    def _act(self, text, shortcut, fn, checkable=False):
        a = QAction(text, self)
        a.setShortcut(QKeySequence(shortcut))
        a.triggered.connect(fn)
        a.setCheckable(checkable)
        self.addAction(a)
        return a

    def _build_toolbar(self):
        tb = self.addToolBar("main")
        tb.setMovable(False)
        self._act("New", "Ctrl+N", self.new_board)
        self._act("Open", "Ctrl+O", self.open_doc)
        self._act("Save", "Ctrl+S", self.save_doc)
        self._act("Export PNG", "Ctrl+E", self.export_png)
        tb.addSeparator()
        self._act("Undo", "Ctrl+Z", self.undo)
        self._act("Redo", "Ctrl+Y", self.redo)
        tb.addSeparator()
        for key, spec in PEN_PRESETS.items():
            b = QPushButton(spec["label"])
            b.setCheckable(True)
            b.setObjectName("accent")
            b.clicked.connect(lambda _=False, k=key: self.apply_preset(k))
            self._preset_buttons = getattr(self, "_preset_buttons", {})
            self._preset_buttons[key] = b
            tb.addWidget(b)
        tb.addSeparator()
        self.color_btn = QPushButton("â– ")
        self.color_btn.setFixedWidth(38)
        self.color_btn.setStyleSheet(f"background:{self.color}; color:white; font-weight:bold;")
        self.color_btn.clicked.connect(self.pick_color)
        tb.addWidget(self.color_btn)
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(1, 40)
        self.size_slider.setValue(4)
        self.size_slider.setFixedWidth(110)
        self.size_slider.valueChanged.connect(self._on_size)
        tb.addWidget(self.size_slider)
        tb.addSeparator()
        self._act("Zoom Out", "Ctrl+-", lambda: self._zoom(1 / 1.2))
        self.zoom_label = QLabel("100%")
        tb.addWidget(self.zoom_label)
        self._act("Zoom In", "Ctrl+=", lambda: self._zoom(1.2))
        self._act("Fit", "Ctrl+0", self.fit_content)
        tb.addSeparator()
        self._act("Clear", "Ctrl+Del", self.clear_board)
        self._act("Delete selection", "Del", self.delete_selected)
        tb.addSeparator()
        b_prev = QPushButton("◀")
        b_prev.setFixedWidth(30)
        b_prev.clicked.connect(self.prev_page)
        tb.addWidget(b_prev)
        self.page_label = QLabel("Page 1/1")
        tb.addWidget(self.page_label)
        b_next = QPushButton("▶")
        b_next.setFixedWidth(30)
        b_next.clicked.connect(self.next_page)
        tb.addWidget(b_next)
        b_add = QPushButton("＋Page")
        b_add.clicked.connect(self.add_page)
        tb.addWidget(b_add)
        b_delp = QPushButton("✕")
        b_delp.setFixedWidth(30)
        b_delp.setToolTip("Delete page")
        b_delp.clicked.connect(self.delete_page)
        tb.addWidget(b_delp)
        tb.addSeparator()
        for text, fn in [("🧪 Chem", self.open_chem_library),
                         ("⚡ Physics", self.open_physics_library),
                         ("📝 Worksheet", self.open_worksheet_maker)]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            tb.addWidget(b)

    def delete_selected(self):
        sel = [it for it in self.scene.selectedItems() if it.data(0)]
        if not sel:
            return
        self.push_undo()
        for it in sel:
            self.scene.removeItem(it)
        self.statusBar().showMessage(f"Deleted {len(sel)} object(s)")

    # ------------------------------------------------------------ pages
    def _sync_page_store(self):
        self.pages[self.page_idx] = self._payloads()

    def add_page(self):
        self._sync_page_store()
        self.pages.insert(self.page_idx + 1, [])
        self._load_page(self.page_idx + 1)

    def delete_page(self):
        if len(self.pages) <= 1:
            QMessageBox.information(self, "Pages", "At least one page is required.")
            return
        del self.pages[self.page_idx]
        self._load_page(min(self.page_idx, len(self.pages) - 1))

    def prev_page(self):
        if self.page_idx > 0:
            self._load_page(self.page_idx - 1)

    def next_page(self):
        if self.page_idx < len(self.pages) - 1:
            self._load_page(self.page_idx + 1)

    def _load_page(self, idx: int):
        self.pages[self.page_idx] = self._payloads()
        self.page_idx = idx
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._restore(self.pages[idx])
        self.page_label.setText(f"Page {idx + 1}/{len(self.pages)}")
        self._apply_layer_visibility()

    # ------------------------------------------------------------ layers
    def _refresh_layer_combo(self):
        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()
        for i, lyr in enumerate(self.layers):
            mark = "" if lyr["visible"] else "  (hidden)"
            self.layer_combo.addItem(f"{lyr['name']}{mark}", i)
        self.layer_combo.setCurrentIndex(self.current_layer)
        self.layer_combo.blockSignals(False)

    def _on_layer_change(self, idx: int):
        self.current_layer = max(0, idx)

    def add_layer(self):
        self.layers.append({"name": f"Layer {len(self.layers) + 1}", "visible": True})
        self.current_layer = len(self.layers) - 1
        self._refresh_layer_combo()

    def toggle_layer_visible(self):
        lyr = self.layers[self.current_layer]
        lyr["visible"] = not lyr["visible"]
        self._refresh_layer_combo()
        self._apply_layer_visibility()

    def _apply_layer_visibility(self):
        for it in self.scene.items():
            pl = it.data(0)
            if not pl:
                continue
            l_idx = int(pl.get("layer", 0))
            if 0 <= l_idx < len(self.layers):
                it.setVisible(self.layers[l_idx]["visible"])

    # ------------------------------------------------------------ libraries
    def _open_equation_library(self, title: str, categories: dict):
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        v = QVBoxLayout(dlg)
        combo = QComboBox()
        combo.addItems(list(categories.keys()))
        v.addWidget(combo)
        lst = QListWidget()
        lst.setFont(QFont("Consolas", 12))

        def refresh():
            lst.clear()
            for e in categories.get(combo.currentText(), []):
                lst.addItem(e if isinstance(e, str) else e[0])
        combo.currentTextChanged.connect(refresh)
        refresh()
        v.addWidget(lst, 1)
        row = QHBoxLayout()
        ins = QPushButton("Insert on board")
        ins.setObjectName("accent")
        close = QPushButton("Close")
        row.addWidget(ins)
        row.addStretch(1)
        row.addWidget(close)
        v.addLayout(row)

        def do_insert():
            sel = lst.currentItem()
            if not sel:
                return
            self.push_undo()
            it = payload_to_item({"type": "text", "pos": [0, 0], "text": sel.text(),
                                  "size": 22, "color": self.color, "layer": self.current_layer})
            it.setPos(self.view.mapToScene(self.view.viewport().rect().center()))
            self.scene.addItem(it)
            dlg.accept()
        ins.clicked.connect(do_insert)
        lst.itemDoubleClicked.connect(lambda _: do_insert())
        close.clicked.connect(dlg.reject)
        dlg.resize(520, 480)
        dlg.exec()

    def open_chem_library(self):
        import whiteboard as legacy
        self._open_equation_library("Chemistry Library", legacy.CHEMISTRY_EQUATIONS)

    def open_physics_library(self):
        import whiteboard as legacy
        cats = {k: list(v) for k, v in legacy.PHYSICS_EQUATIONS.items()}
        self._open_equation_library("Physics Formulas", cats)

    # ------------------------------------------------------------ worksheet maker
    def open_worksheet_maker(self):
        import whiteboard as legacy
        dlg = QDialog(self)
        dlg.setWindowTitle("Worksheet Maker")
        v = QVBoxLayout(dlg)
        row0 = QHBoxLayout()
        row0.addWidget(QLabel("Language"))
        lang = QComboBox()
        lang.addItems(["العربية", "English"])
        row0.addWidget(lang, 1)
        v.addLayout(row0)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Title"))
        title = QLineEdit()
        row1.addWidget(title, 1)
        v.addLayout(row1)
        row2 = QHBoxLayout()
        self._ws_fields = {}
        for key, lbl in [("school", "School"), ("teacher", "Teacher"),
                         ("klass", "Class"), ("date", "Date")]:
            self._ws_fields[key] = QLineEdit()
            self._ws_fields[key].setPlaceholderText(lbl)
            row2.addWidget(self._ws_fields[key])
        self._ws_fields["date"].setText(QDate_str())
        v.addLayout(row2)
        v.addWidget(QLabel("Topics (ctrl-click for multiple):"))
        topics = QListWidget()
        topics.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        topics.addItems(list(legacy.WORKSHEET_TOPICS.keys()))
        for i in range(min(3, topics.count())):
            topics.item(i).setSelected(True)
        v.addWidget(topics, 1)
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Per topic"))
        count = QSpinBox()
        count.setRange(1, 10)
        count.setValue(2)
        row3.addWidget(count)
        row3.addWidget(QLabel("Level"))
        level = QSpinBox()
        level.setRange(1, 5)
        level.setValue(2)
        row3.addWidget(level)
        row3.addWidget(QLabel("Seed"))
        seed = QLineEdit()
        seed.setPlaceholderText("auto")
        row3.addWidget(seed, 1)
        v.addLayout(row3)
        btns = QDialogButtonBox()
        b_ins = btns.addButton("Insert on board", QDialogButtonBox.ButtonRole.AcceptRole)
        b_pdf = btns.addButton("Export PDF…", QDialogButtonBox.ButtonRole.ApplyRole)
        btns.addButton(QDialogButtonBox.StandardButton.Cancel)
        v.addWidget(btns)

        def collect():
            sel = [i.text() for i in topics.selectedItems()]
            if not sel:
                QMessageBox.warning(dlg, "Worksheet", "Select at least one topic.")
                return None
            seed_t = seed.text().strip()
            if seed_t:
                try:
                    import random as _r
                    _r.seed(int(seed_t))
                except ValueError:
                    import random as _r
                    _r.seed(seed_t)
                meta_seed = seed_t
            else:
                import random as _r
                meta_seed = str(_r.randrange(10 ** 8))
                _r.seed(int(meta_seed))
            lang_code = "ar" if lang.currentText().startswith("العربية") else "en"
            meta = {"lang": lang_code,
                    "title": title.text().strip() or legacy.WORKSHEET_LANGS[lang_code]["title"],
                    "school": self._ws_fields["school"].text().strip(),
                    "teacher": self._ws_fields["teacher"].text().strip(),
                    "klass": self._ws_fields["klass"].text().strip(),
                    "date": self._ws_fields["date"].text().strip(),
                    "seed": meta_seed}
            qs = legacy.generate_verified_questions(sel, count.value(), level.value(),
                                                    lang=lang_code)
            return meta, qs

        def do_insert():
            got = collect()
            if not got:
                return
            meta, qs = got
            self.push_undo()
            x, y = 40.0, 40.0
            header = meta["title"]
            bits = [meta.get("school"), meta.get("teacher"),
                    (meta["klass"] and f"{meta['klass']}") or "",
                    meta.get("date")]
            header += "\n" + "  |  ".join([b for b in bits if b])
            for text, size in [(header, 24)] + [
                    (f"{i}. {q}\n{'.' * 46}", 16) for i, (_t, q, _a) in enumerate(qs, 1)]:
                it = payload_to_item({"type": "text", "pos": [x, y], "text": text,
                                      "size": size, "color": self.color,
                                      "layer": self.current_layer})
                self.scene.addItem(it)
                y += (text.count("\n") + 2.2) * size
            key_txt = [f"{i}. {a}" for i, (_t, _q, a) in enumerate(qs, 1)]
            it = payload_to_item({"type": "text", "pos": [x, y + 40],
                                  "text": f"—— {legacy.WORKSHEET_LANGS[meta['lang']]['answer_key']} ——\n" + "\n".join(key_txt),
                                  "size": 13, "color": self.color,
                                  "layer": self.current_layer})
            self.scene.addItem(it)
            self.statusBar().showMessage(f"Worksheet inserted ({len(qs)} questions)")
            dlg.accept()

        def do_pdf():
            got = collect()
            if not got:
                return
            meta, qs = got
            path, _f = QFileDialog.getSaveFileName(dlg, "Export worksheet PDF",
                                                   "worksheet.pdf", "PDF (*.pdf)")
            if not path:
                return
            try:
                host = type("_PDFHost", (), {
                    "_worksheet_pdf_fonts": legacy.WhiteboardApp._worksheet_pdf_fonts,
                })()
                legacy.WhiteboardApp._write_worksheet_pdf(host, path, meta, qs)
                QMessageBox.information(dlg, "Worksheet", f"Saved:\n{path}")
            except Exception as exc:
                QMessageBox.critical(dlg, "Worksheet", f"Failed:\n{exc}")
        b_ins.clicked.connect(do_insert)
        b_pdf.clicked.connect(do_pdf)
        btns.rejected.connect(dlg.reject)
        dlg.resize(640, 620)
        dlg.exec()

    # ------------------------------------------------------------ sidebar
    def _build_sidebar(self):
        side = QWidget(objectName="sidebar")
        side.setFixedWidth(168)
        v = QVBoxLayout(side)
        v.setContentsMargins(10, 12, 10, 10)
        v.setSpacing(6)
        title = QLabel("TOOLS")
        title.setStyleSheet("color:#78909c; letter-spacing:2px; font-size:11px;")
        v.addWidget(title)
        grid = QGridLayout()
        grid.setSpacing(6)
        tools = [
            ("Select", "⬚", "select"), ("Pen", "✏", "pen"),
            ("Marker", "🖍", "highlighter"), ("Eraser", "⌫", "eraser"),
            ("Line", "╱", "line"), ("Arrow", "➤", "arrow"),
            ("Rect", "▭", "rect"), ("Ellipse", "◯", "ellipse"),
            ("Text", "T", "text"),
        ]
        self.tool_buttons = {}
        for i, (name, glyph, key) in enumerate(tools):
            b = QPushButton(f"{glyph}\n{name}")
            b.setCheckable(True)
            b.setFixedHeight(56)
            b.clicked.connect(lambda _=False, k=key: self.set_tool(k))
            grid.addWidget(b, i // 2, i % 2)
            self.tool_buttons[key] = b
        v.addLayout(grid)
        v.addStretch(1)

        lrow = QHBoxLayout()
        lrow.addWidget(QLabel("Layer"))
        self.layer_combo = QComboBox()
        self.layer_combo.currentIndexChanged.connect(self._on_layer_change)
        lrow.addWidget(self.layer_combo, 1)
        b_add_l = QPushButton("+")
        b_add_l.setFixedWidth(26)
        b_add_l.clicked.connect(self.add_layer)
        lrow.addWidget(b_add_l)
        b_eye = QPushButton("👁")
        b_eye.setFixedWidth(30)
        b_eye.setToolTip("Toggle layer visibility")
        b_eye.clicked.connect(self.toggle_layer_visible)
        lrow.addWidget(b_eye)
        v.addLayout(lrow)

        hint = QLabel("Wheel: zoom\nMiddle-drag: pan\nDouble-click: text\nDel: remove")
        hint.setStyleSheet("color:#607d8b; font-size:11px;")
        v.addWidget(hint)
        self.set_tool("pen")
        return side

    # ------------------------------------------------------------ actions
    def set_tool(self, key):
        self.tool = key
        for k, b in self.tool_buttons.items():
            b.setChecked(k == key)
        self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag if key == "select"
                              else QGraphicsView.DragMode.NoDrag)
        self.statusBar().showMessage(f"Tool: {key}")

    def apply_preset(self, key):
        spec = PEN_PRESETS[key]
        self.active_preset = key
        self.size_value = float(spec["size"])
        self.size_slider.setValue(spec["size"])
        for k, b in self._preset_buttons.items():
            b.setChecked(k == key)
        self.set_tool("pen")

    def _on_size(self, v):
        self.size_value = float(v)

    def pick_color(self):
        c = QColorDialog.getColor(QColor(self.color), self, "Choose color")
        if c.isValid():
            self.color = c.name()
            self.color_btn.setStyleSheet(
                f"background:{self.color}; color:white; font-weight:bold;")

    def add_text_at(self, sp: QPointF):
        text, ok = QInputDialog.getMultiLineText(self, "Text", "Enter text:")
        if not ok or not text.strip():
            return
        self.push_undo()
        it = payload_to_item({"type": "text", "pos": [sp.x(), sp.y()], "text": text,
                              "size": 20, "color": self.color, "layer": self.win.current_layer})
        self.scene().addItem(it)

    def _zoom(self, f):
        self.view.scale(f, f)
        self.update_zoom_label()

    def update_zoom_label(self):
        self.zoom_label.setText(f"{int(self.view.transform().m11() * 100)}%")

    def fit_content(self):
        r = self.scene.itemsBoundingRect()
        if r.isEmpty():
            self.view.resetTransform()
        else:
            self.view.fitInView(r.marginsAdded(QMarginsF(60, 60, 60, 60)),
                                Qt.AspectRatioMode.KeepAspectRatio)
        self.update_zoom_label()

    def clear_board(self):
        self.push_undo()
        self.scene.clear()
        self.statusBar().showMessage("Board cleared â€” Ctrl+Z to undo")

    # ------------------------------------------------------------ undo
    def _payloads(self):
        return [deepcopy(it.data(0)) for it in self.scene.items()
                if it.data(0) and not isinstance(it, QGraphicsTextItem) or
                (isinstance(it, QGraphicsTextItem) and it.data(0))]

    def push_undo(self):
        self.undo_stack.append(deepcopy(self._payloads()))
        if len(self.undo_stack) > 60:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def pop_undo(self):
        if self.undo_stack:
            self.undo_stack.pop()

    def _restore(self, payloads):
        self.scene.clear()
        for pl in payloads:
            it = payload_to_item(pl)
            if it:
                self.scene.addItem(it)
        self._apply_layer_visibility()

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append(self._payloads())
        self._restore(self.undo_stack.pop())

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(self._payloads())
        self._restore(self.redo_stack.pop())

    # ------------------------------------------------------------ document
    def new_board(self):
        if self.scene.items() and not self._confirm_discard():
            return
        self.scene.clear()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.current_file = None

    def _confirm_discard(self):
        return QMessageBox.question(self, "Discard?", "Clear the board without saving?") == \
            QMessageBox.StandardButton.Yes

    def save_doc(self):
        path = self.current_file or "board.wbd"
        path, _ = QFileDialog.getSaveFileName(self, "Save document", path,
                                              "Whiteboard document (*.wbd)")
        if not path:
            return
        data = {"app": APP_ID, "version": DOC_VERSION, "theme": "dark",
                "fg_color": self.color, "current_page": 0,
                "layers": [{"name": "Layer 1", "visible": True}],
                "current_layer": 0,
                "pages": [{"bg_kind": "dots", "bg_image": None,
                           "objects": self._payloads()}]}
        Path(path).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.current_file = path
        self.statusBar().showMessage(f"Saved: {path}")

    def open_doc(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open document", "",
                                              "Whiteboard document (*.wbd)")
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            page = data.get("pages", [{}])[0]
            raw_layers = data.get("layers")
            if isinstance(raw_layers, list) and raw_layers:
                self.layers = [{"name": str(l.get("name", f"Layer {i + 1}")),
                                "visible": bool(l.get("visible", True))}
                               for i, l in enumerate(raw_layers) if isinstance(l, dict)]
            self._refresh_layer_combo()
            self._restore(page.get("objects", []))
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.current_file = path
            self.statusBar().showMessage(f"Opened: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Could not open:\n{exc}")

    def export_png(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export PNG", "board.png", "PNG (*.png)")
        if not path:
            return
        r = self.scene.itemsBoundingRect().marginsAdded(QRectF(40, 40, 40, 40))
        img = QImage(int(r.width() * 2), int(r.height() * 2),
                     QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.white)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.scene.render(p, QRectF(img.rect()), r)
        p.end()
        img.save(path)
        self.statusBar().showMessage(f"Exported: {path}")


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    win = MainWindow()
    ico = Path(__file__).resolve().parent / "icon.ico"
    if ico.exists():
        win.setWindowIcon(QIcon(str(ico)))
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()


