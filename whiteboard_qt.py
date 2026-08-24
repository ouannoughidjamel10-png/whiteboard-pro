#!/usr/bin/env python3
"""Interactive Whiteboard Pro â€” Qt edition (Session 1).

Modern shell + GPU canvas. Compatible with legacy .wbd documents for the
supported object subset (pen/highlighter/line/arrow/rect/oval/text).
"""
from __future__ import annotations

import base64
import io
import json
import math
import sys
import time
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import Qt, QPointF, QRectF, QLineF, QMarginsF, QTimer, QBuffer, QIODevice, QMimeData, QSizeF
from PySide6.QtGui import (QAction, QBrush, QColor, QFont, QPainter, QPainterPath,
                           QPen, QImage, QIcon, QKeySequence, QPixmap, QGuiApplication,
                           QPainterPathStroker, QPolygonF, QPdfWriter, QPageSize)
from PySide6.QtWidgets import (QApplication, QColorDialog, QComboBox, QFileDialog,
                               QFrame, QGraphicsEllipseItem, QGraphicsItem,
                               QGraphicsLineItem, QGraphicsPathItem,
                               QGraphicsRectItem, QGraphicsScene,
                               QGraphicsTextItem, QGraphicsView,
                               QHBoxLayout, QLabel, QInputDialog, QListWidget,
                               QMainWindow, QMessageBox, QPushButton, QSizePolicy,
                               QSlider, QVBoxLayout, QWidget, QGridLayout,
                               QDialog, QLineEdit, QSpinBox, QCheckBox,
                               QDialogButtonBox, QVBoxLayout as VBox,
                               QGraphicsDropShadowEffect)


def QDate_str() -> str:
    from datetime import date
    return date.today().isoformat()


# ================================================================== instruments
INSTR_TYPE = "_instr"


class InstrumentItem(QGraphicsItem):
    """Base for draggable/rotatable translucent drawing instruments."""

    def __init__(self, win):
        super().__init__()
        self.win = win
        self._payload = {INSTR_TYPE: True}
        self.setZValue(500)
        sh = QGraphicsDropShadowEffect()
        sh.setBlurRadius(22)
        sh.setOffset(0, 5)
        sh.setColor(QColor(10, 25, 50, 110))
        self.setGraphicsEffect(sh)
        self._drag_off = QPointF()

    def data(self, _i):
        return {INSTR_TYPE: True}          # excluded from payloads

    def boundingRect(self):
        raise NotImplementedError

    def handles(self):
        """[(QPointF local, role:str), ...]"""
        return []

    def hit_role(self, scene_pos):
        for lp, role in self.handles():
            if QLineF(self.mapToScene(lp), scene_pos).length() < 16:
                return role
        return None

    def snap_scene(self, scene_pos):
        return None


class RulerItem(InstrumentItem):
    L, H = 460.0, 46.0

    def boundingRect(self):
        return QRectF(-18, -self.H / 2 - 18, self.L + 36, self.H + 36)

    def handles(self):
        return [(QPointF(self.L / 2 + 18, 0), "rot")]

    def paint(self, p: QPainter, *_args):
        L, H = self.L, self.H
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QRectF(-L / 2, -H / 2, L, H)
        p.setPen(QPen(QColor(21, 101, 192), 1.6))
        p.setBrush(QColor(205, 228, 245, 105))
        p.drawRoundedRect(body, 6, 6)
        p.setPen(QPen(QColor(21, 101, 192, 220), 1))
        i = 0
        x = -L / 2
        while x <= L / 2:
            ln = 12 if i % 9 == 0 else (6 if i % 3 == 0 else 3)
            p.drawLine(QPointF(x, H / 2), QPointF(x, H / 2 - ln))
            if i % 9 == 0:
                p.setPen(QPen(QColor(13, 71, 161)))
                p.drawText(QPointF(x + 2, H / 2 - 14), str(i // 9))
                p.setPen(QPen(QColor(21, 101, 192, 220), 1))
            x += 9
            i += 1
        kx = L / 2 + 18
        p.setPen(QPen(QColor("white"), 2))
        p.setBrush(QColor(33, 150, 243))
        p.drawEllipse(QPointF(kx, 0), 11, 11)
        p.setPen(QPen(QColor(13, 71, 161), 2))
        p.drawLine(QPointF(kx - 5, 0), QPointF(kx + 5, 0))

    def snap_scene(self, sp: QPointF):
        a = self.mapToScene(QPointF(-self.L / 2, self.H / 2))
        b = self.mapToScene(QPointF(self.L / 2, self.H / 2))
        vx, vy = b.x() - a.x(), b.y() - a.y()
        seg2 = vx * vx + vy * vy
        t = max(0.0, min(1.0, ((sp.x() - a.x()) * vx + (sp.y() - a.y()) * vy) / seg2))
        qx, qy = a.x() + t * vx, a.y() + t * vy
        if math.hypot(sp.x() - qx, sp.y() - qy) < 15:
            return QPointF(qx, qy)
        return None


class ProtractorItem(InstrumentItem):
    R = 150.0

    def boundingRect(self):
        return QRectF(-self.R - 16, -self.R - 16, 2 * self.R + 32, self.R + 32)

    def handles(self):
        return [(QPointF(self.R, 0), "rot")]

    def paint(self, p: QPainter, *_args):
        R = self.R
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(21, 101, 192), 1.6))
        p.setBrush(QColor(150, 200, 240, 80))
        p.drawPie(QRectF(-R, -R, 2 * R, 2 * R), 180 * 16, 180 * 16)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(21, 101, 192), 2.4))
        p.drawArc(QRectF(-R, -R, 2 * R, 2 * R), 180 * 16, 180 * 16)
        p.setPen(QPen(QColor(21, 101, 192), 2))
        p.drawLine(QPointF(-R, 0), QPointF(R, 0))
        for t in range(0, 181, 5):
            rad = math.radians(180 + t)
            ux, uy = math.cos(rad), math.sin(rad)
            ln = 13 if t % 10 == 0 else 6
            p.setPen(QPen(QColor(21, 101, 192, 220), 1))
            p.drawLine(QPointF(R * ux, R * uy), QPointF((R - ln) * ux, (R - ln) * uy))
            if t % 30 == 0:
                p.setPen(QPen(QColor(13, 71, 161)))
                p.drawText(QPointF((R - 28) * ux - 7, (R - 28) * uy + 4), str(t))
        p.setBrush(QColor(229, 57, 53))
        p.drawEllipse(QPointF(0, 0), 4, 4)
        p.setPen(QPen(QColor("white"), 2))
        p.setBrush(QColor(33, 150, 243))
        p.drawEllipse(QPointF(R, 0), 11, 11)

    def snap_scene(self, sp: QPointF):
        c = self.mapToScene(QPointF(0, 0))
        d = QLineF(c, sp).length()
        if abs(d - self.R) < 17:
            lp = self.mapFromScene(sp)
            a = math.degrees(math.atan2(lp.y(), lp.x()))
            if -180 <= a <= 0:
                rad = math.radians(a)
                return self.mapToScene(QPointF(self.R * math.cos(rad),
                                               self.R * math.sin(rad)))
        return None


class CompassItem(InstrumentItem):
    def __init__(self, win):
        super().__init__(win)
        self.angle = math.radians(-35)
        self.leg = 150.0
        self.arc_a0 = None

    def tip_local(self):
        return QPointF(self.leg * math.cos(self.angle), self.leg * math.sin(self.angle))

    def boundingRect(self):
        return QRectF(-self.leg - 30, -self.leg - 60, 2 * self.leg + 60,
                      2 * self.leg + 80)

    def handles(self):
        return [(QPointF(0, 0), "body"), (self.tip_local(), "tip")]

    def paint(self, p: QPainter, *_args):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        tip = self.tip_local()
        p.setPen(QPen(QColor(55, 60, 70), 5, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(0, 0), tip)
        p.drawLine(QPointF(0, 0), QPointF(-22, -46))
        p.setBrush(QColor(205, 205, 212))
        p.setPen(QPen(QColor(45, 50, 58), 3))
        p.drawEllipse(QPointF(0, 0), 7, 7)
        p.setBrush(QColor(33, 150, 243))
        p.setPen(QPen(QColor("white"), 2))
        p.drawEllipse(tip, 9, 9)
        if self.arc_a0 is not None:
            lw = max(2.0, float(self.win.size_value))
            p.setPen(QPen(_qcolor(self.win.color), lw, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap))
            rect = QRectF(-self.leg, -self.leg, 2 * self.leg, 2 * self.leg)
            a0 = math.degrees(self.arc_a0)
            a1 = math.degrees(self.angle)
            span = ((a1 - a0 + 540) % 360) - 180
            p.drawArc(rect, int(a0 * 16), int(span * 16))
            mid = math.radians((a0 + a0 + span) / 2)
            p.setPen(QPen(QColor(229, 57, 53)))
            p.drawText(QPointF((self.leg + 16) * math.cos(mid) - 14,
                               (self.leg + 16) * math.sin(mid) + 4),
                       f"R={self.leg / max(self.win.view.transform().m11(), 1e-6):.1f}")

    def update_tip(self, scene_pos):
        c = self.mapToScene(QPointF(0, 0))
        lp = self.mapFromScene(scene_pos)
        self.angle = math.atan2(lp.y(), lp.x())
        d = QLineF(c, scene_pos).length()
        if 30 <= d <= 340:
            self.leg = d
        if self.arc_a0 is None:
            self.arc_a0 = self.angle
        self.prepareGeometryChange()
        self.update()

    def commit(self):
        """Return a compass payload for the swept arc, or None."""
        if self.arc_a0 is None:
            return None
        span = math.degrees(((self.angle - self.arc_a0) + math.pi) % (2 * math.pi) - math.pi)
        self.arc_a0 = None
        self.update()
        if abs(span) < 2:
            return None
        c = self.mapToScene(QPointF(0, 0))
        r_world = self.leg / max(self.win.view.transform().m11(), 1e-6)
        end_local = self.tip_local()
        end = self.mapToScene(end_local)
        return {"type": "compass", "center": [c.x(), c.y()],
                "p2": [end.x(), end.y()], "radius": r_world,
                "color": self.win.color, "width": float(self.win.size_value),
                "layer": self.win.current_layer}


def _var_stroke_path(pts, widths) -> QPainterPath:
    """Filled variable-width stroke (brush feel)."""
    if len(pts) < 2:
        return QPainterPath()
    right, left = [], []
    for i, (p, w) in enumerate(zip(pts, widths)):
        if i == 0:
            dx, dy = pts[1][0] - p[0], pts[1][1] - p[1]
        else:
            dx, dy = p[0] - pts[i - 1][0], p[1] - pts[i - 1][1]
        r = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / r, dx / r
        right.append(QPointF(p[0] + nx * w, p[1] + ny * w))
        left.append(QPointF(p[0] - nx * w, p[1] - ny * w))
    path = QPainterPath(right[0])
    for pt in right[1:]:
        path.lineTo(pt)
    for pt in reversed(left):
        path.lineTo(pt)
    path.closeSubpath()
    return path


def _speed_widths(points, base, times):
    widths = []
    for i in range(len(points)):
        if i == 0:
            widths.append(base * 1.15)
            continue
        d = math.hypot(points[i][0] - points[i - 1][0],
                       points[i][1] - points[i - 1][1])
        dt = max(1e-3, times[i] - times[i - 1])
        v = min(1.0, d / dt / 2600.0)
        widths.append(max(base * 0.55, base * 1.7 * (1.12 - v)))
    return widths
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
        if tool == "laser":
            self.win.laser_press(self.mapToScene(e.position().toPoint()))
            e.accept()
            return
        if self.win.instrument_press(self.mapToScene(e.position().toPoint())):
            e.accept()
            return
        if tool not in ("select", "eraser", "text"):
            sp0 = self.mapToScene(e.position().toPoint())
            sn = self.win.snap_pen(sp0)
            if sn:
                self._snapped_press = sn
        if tool == "select":
            super().mousePressEvent(e)          # native move / selection
            return
        if e.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(e)
            return
        sp = self._snapped_press if getattr(self, "_snapped_press", None) else \
            self.mapToScene(e.position().toPoint())
        self._snapped_press = None
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
            item._payload = {"type": tool, "points": [[sp.x(), sp.y()], [sp.x(), sp.y()]],
                             "width": width, "color": self.win.color,
                             "alpha": alpha, "layer": self.win.current_layer}
            item.setData(0, True)
            if self.win.active_preset == "brush":
                t0 = time.monotonic()
                item._payload["times"] = [t0, t0]
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
        it._payload = payload
        it.setData(0, True)
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
        if self._tool() == "laser":
            self.win.laser_move(sp)
            e.accept()
            return
        if self.win.instrument_move(sp):
            e.accept()
            return
        tool = self._tool()
        if self._tool() == "pen" and self._creating is not None:
            sn = self.win.snap_pen(sp)
            if sn:
                sp = sn
        if self._erasing:
            self._erase_at(sp)
            e.accept()
            return
        if self.win.instrument_release():
            e.accept()
            return
        if self._creating is not None and tool in ("pen", "highlighter"):
            path = self._creating.path()
            path.lineTo(sp)
            self._creating.setPath(path)
            pl = self._creating._payload
            pl["points"].append([sp.x(), sp.y()])
            if "times" in pl:
                pl["times"].append(time.monotonic())
            e.accept()
            return
        if self._creating is not None and tool == "line":
            it = self._creating
            it.setLine(QLineF(self._start_pt, sp))
            it._payload["p2"] = [sp.x(), sp.y()]
            e.accept()
            return
        if self._creating is not None and tool == "arrow":
            it = self._creating
            it.setPath(self._arrow_path(self._start_pt, sp))
            pl = it._payload
            pl["p2"] = [sp.x(), sp.y()]
            pl["head"] = [[p.x(), p.y()] for p in self._arrow_head(self._start_pt, sp)]
            e.accept()
            return
        if self._creating is not None and tool in ("rect", "ellipse"):
            r = QRectF(self._start_pt, sp).normalized()
            self._creating.setRect(r)
            pl = self._creating._payload
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
            pl = item._payload
            if pl.get("type") == "pen" and pl.get("times"):
                widths = _speed_widths(pl["points"], float(pl.get("width", 4)),
                                       pl["times"])
                pl["widths"] = [round(w, 2) for w in widths]
                pl["variable"] = True
                pl.pop("times", None)
                item.setPath(_var_stroke_path(pl["points"], widths))
                item.setBrush(QBrush(_qcolor(pl["color"], pl.get("alpha", 255))))
                item.setPen(QPen(Qt.PenStyle.NoPen))
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
            if pl_of(it):
                self.scene().removeItem(it)

    # ------------------------------------------------------------- grid
    def drawBackground(self, painter: QPainter, rect: QRectF):
        dark = getattr(self.win, "dark", False)
        painter.fillRect(rect, QColor("#182720") if dark else QColor("#ffffff"))
        step = 24.0
        zoom = self.transform().m11()
        while step * zoom < 10:
            step *= 2
        pen = QPen(QColor(70, 110, 90) if dark else QColor(210, 216, 224))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        x0 = math.floor(rect.left() / step) * step
        y0 = math.floor(rect.top() / step) * step
        r = 1.1
        for x in [x0 + i * step for i in range(int(rect.width() / step) + 2)]:
            for y in [y0 + j * step for j in range(int(rect.height() / step) + 2)]:
                painter.drawEllipse(QPointF(x, y), r, r)


def pl_of(it):
    """Live payload dict for an item (PySide setData copies dicts!)."""
    return getattr(it, "_payload", None)


def payload_to_item(pl: dict):
    t = pl.get("type")
    color = pl.get("color", "#000000")
    width = float(pl.get("width", 3))
    if t in ("pen", "highlighter"):
        it = StrokeItem()
        pts = pl.get("points", [])
        if pl.get("variable") and pl.get("widths"):
            it.setPath(_var_stroke_path(pts, pl["widths"]))
            it.setBrush(QBrush(_qcolor(color, pl.get("alpha", 255))))
            it.setPen(QPen(Qt.PenStyle.NoPen))
        else:
            path = QPainterPath()
            if pts:
                path.moveTo(QPointF(pts[0][0], pts[0][1]))
                for p in pts[1:]:
                    path.lineTo(QPointF(p[0], p[1]))
            it.setPath(path)
            it.setPen(QPen(QBrush(_qcolor(color, pl.get("alpha", 255))), width,
                           Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                           Qt.PenJoinStyle.RoundJoin))
    elif t == "compass":
        it = StrokeItem()
        cx, cy = pl.get("center", [0, 0])
        r = float(pl.get("radius", 50))
        path = QPainterPath()
        path.addEllipse(QPointF(cx, cy), r, r)
        p2 = pl.get("p2", [cx + r, cy])
        path.moveTo(QPointF(cx, cy))
        path.lineTo(QPointF(p2[0], p2[1]))
        it.setPath(path)
        it.setPen(QPen(QColor(color), width, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap))
    elif t == "line":
        it = QGraphicsLineItem(QLineF(QPointF(*pl["p1"]), QPointF(*pl["p2"])))
        it.setPen(QPen(QColor(color), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    elif t == "arrow":
        it = StrokeItem()
        a, b = QPointF(*pl["p1"]), QPointF(*pl["p2"])
        it.setPath(QPainterPath(a))
        head = [[b.x(), b.y()]]
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
    elif t == "image":
        from PySide6.QtWidgets import QGraphicsPixmapItem
        img = QImage()
        img.loadFromData(base64.b64decode(pl.get("png", "")), "PNG")
        it = QGraphicsPixmapItem()
        it.setPixmap(QPixmap.fromImage(img))
        if pl.get("pos"):
            it.setPos(QPointF(*pl["pos"]))
        it.setScale(float(pl.get("scale", 1.0)))
    elif t == "text":
        it = QGraphicsTextItem(pl.get("text", ""))
        it.setDefaultTextColor(QColor(color))
        f = QFont("Segoe UI", int(pl.get("size", 18)))
        it.setFont(f)
        it.setPos(QPointF(*pl.get("pos", [0, 0])))
    else:
        return None
    it._payload = deepcopy(pl)
    it.setData(0, True)
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
        self._instr = None
        self._laser = None
        self.dark = False

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
        self._act("Flatten export", "Ctrl+E", self.export_flatten)
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
        self._act("Copy", "Ctrl+C", self.copy_selection)
        self._act("Cut", "Ctrl+X", lambda: self.copy_selection(cut=True))
        self._act("Paste", "Ctrl+V", self.paste_clipboard)
        self._act("Duplicate", "Ctrl+D", self.duplicate_selection)
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
        b_delp = QPushButton("Del")
        b_delp.setFixedWidth(30)
        b_delp.setToolTip("Delete page")
        b_delp.clicked.connect(self.delete_page)
        tb.addWidget(b_delp)
        tb.addSeparator()
        b_pdfin = QPushButton("PDF In")
        b_pdfin.setToolTip("Import PDF pages as selectable images")
        b_pdfin.clicked.connect(self.import_pdf)
        tb.addWidget(b_pdfin)
        for text, fn in [("Chem", self.open_chem_library),
                         ("Physics", self.open_physics_library),
                         ("Worksheet", self.open_worksheet_maker)]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            tb.addWidget(b)
        tb.addSeparator()
        for txt, tip, fn in [("Ruler", "Ruler", lambda: self.toggle_instrument("ruler")),
                             ("Protr", "Protractor", lambda: self.toggle_instrument("protractor")),
                             ("Compass", "Compass", lambda: self.toggle_instrument("compass")),
                             ("Dark", "Chalkboard", self.toggle_theme)]:
            b = QPushButton(txt)
            b.setFixedWidth(36)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            tb.addWidget(b)

    def delete_selected(self):
        sel = [it for it in self.scene.selectedItems() if pl_of(it)]
        if not sel:
            return
        self.push_undo()
        for it in sel:
            self.scene.removeItem(it)
        self.statusBar().showMessage(f"Deleted {len(sel)} object(s)")

    # ------------------------------------------------------------ instruments
    def instrument_press(self, sp: QPointF) -> bool:
        items = [i for i in self.scene.items() if isinstance(i, InstrumentItem)]
        for it in items:                                   # handles first
            role = it.hit_role(sp)
            if role:
                if isinstance(it, CompassItem) and role == "tip":
                    lp = it.mapFromScene(sp)
                    it.arc_a0 = math.atan2(lp.y(), lp.x())
                self._instr = (it, role, it.pos() - sp if role == "body" else None)
                return True
        for it in items:                                   # then bodies
            if it.contains(it.mapFromScene(sp)):
                self._instr = (it, "body", it.pos() - sp)
                return True
        return False

    def instrument_move(self, sp: QPointF) -> bool:
        if not self._instr:
            return False
        it, role, off = self._instr
        if role == "body":
            it.setPos(sp + off)
        elif role == "rot":
            c = it.mapToScene(QPointF(0, 0))
            ang = math.degrees(math.atan2(sp.y() - c.y(), sp.x() - c.x()))
            if isinstance(it, ProtractorItem):
                it.setRotation(ang - 180.0)
            else:
                it.setRotation(ang)
        elif role == "tip":
            it.update_tip(sp)
        return True

    def instrument_release(self) -> bool:
        if not self._instr:
            return False
        it, role, _off = self._instr
        self._instr = None
        if isinstance(it, CompassItem) and role == "tip":
            pl = it.commit()
            if pl:
                self.push_undo()
                self.scene.addItem(payload_to_item(pl))
                self.statusBar().showMessage("Arc added")
        return True

    def snap_pen(self, sp: QPointF):
        for it in self.scene.items():
            if isinstance(it, InstrumentItem):
                s = it.snap_scene(sp)
                if s is not None:
                    return s
        return None

    def toggle_instrument(self, kind: str):
        for it in list(self.scene.items()):
            if isinstance(it, InstrumentItem) and type(it).__name__.lower().startswith(kind[:4]):
                self.scene.removeItem(it)
                return
        cls = {"ruler": RulerItem, "protractor": ProtractorItem,
               "compass": CompassItem}[kind]
        c = self.view.mapToScene(self.view.viewport().rect().center())
        it = cls(self)
        it.setPos(c + QPointF(0, -30))
        self.scene.addItem(it)

    # ------------------------------------------------------------ laser
    def laser_press(self, sp: QPointF):
        it = StrokeItem()
        path = QPainterPath(sp)
        path.lineTo(sp + QPointF(0.01, 0.01))
        it.setPath(path)
        it.setPen(QPen(QColor(255, 45, 85), 6, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        it.setZValue(900)
        self.scene.addItem(it)
        self._laser = [it, time.monotonic()]
        if not hasattr(self, "_laser_timer"):
            self._laser_timer = QTimer(self)
            self._laser_timer.timeout.connect(self.laser_fade)
        self._laser_timer.start(70)

    def laser_move(self, sp: QPointF):
        if self._laser:
            it = self._laser[0]
            path = it.path()
            path.lineTo(sp)
            it.setPath(path)

    def laser_fade(self):
        if not self._laser:
            return
        it, t0 = self._laser
        el = time.monotonic() - t0
        if el > 1.5:
            self.scene.removeItem(it)
            self._laser = None
            self._laser_timer.stop()
            return
        it.setOpacity(max(0.05, 1.0 - el / 1.5))

    # ------------------------------------------------------------ theme
    def toggle_theme(self):
        self.dark = not self.dark
        if self.dark and QColor(self.color).lightness() < 120:
            self.color = "#f4f4f4"
            self.color_btn.setStyleSheet(
                f"background:{self.color}; color:#222; font-weight:bold;")
        self.view.viewport().update()
        self.statusBar().showMessage("Chalkboard mode" if self.dark else "Whiteboard mode")

    # ------------------------------------------------------------ clipboard
    CLIP_MIME = "application/x-interactive-whiteboard"

    def _selected_items(self):
        return [it for it in self.scene.selectedItems()
                if pl_of(it) and not pl_of(it).get(INSTR_TYPE)]

    def _selection_image(self, items) -> QImage:
        rect = QRectF()
        for it in items:
            rect = rect.united(it.sceneBoundingRect())
        rect = rect.marginsAdded(QMarginsF(10, 10, 10, 10))
        img = QImage(int(rect.width() * 2), int(rect.height() * 2),
                     QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        hidden = []
        for it in self.scene.items():
            if it not in items:
                hidden.append((it, it.isVisible()))
                it.setVisible(False)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.scene.render(p, QRectF(img.rect()), rect)
        p.end()
        for it, vis in hidden:
            it.setVisible(vis)
        return img

    def copy_selection(self, cut: bool = False):
        items = self._selected_items()
        if not items:
            self.statusBar().showMessage("Nothing selected")
            return
        payloads = [deepcopy(pl_of(it)) for it in items]
        img = self._selection_image(items)
        mime = QMimeData()
        mime.setData(self.CLIP_MIME,
                     bytes(json.dumps(payloads, ensure_ascii=False), "utf-8"))
        mime.setImageData(img)
        QApplication.clipboard().setMimeData(mime)
        if cut:
            self.push_undo()
            for it in items:
                self.scene.removeItem(it)
            self.statusBar().showMessage(f"Cut {len(items)} object(s)")
        else:
            self.statusBar().showMessage(f"Copied {len(items)} object(s) — paste in Word as image too")

    def paste_clipboard(self):
        cb = QApplication.clipboard()
        mime = cb.mimeData()
        pasted = 0
        if mime.hasFormat(self.CLIP_MIME):
            try:
                payloads = json.loads(bytes(mime.data(self.CLIP_MIME)).decode("utf-8"))
            except Exception:
                payloads = []
            center = self.view.mapToScene(self.view.viewport().rect().center())
            if payloads:
                min_x = min(p.get("pos", p.get("p1", [p.get("x1", 0), 0]))[0]
                            for p in payloads if isinstance(p.get("pos", p.get("p1", p.get("x1"))), list))
                min_y = min(p.get("pos", p.get("p1", [0, p.get("y1", 0)]))[1]
                            for p in payloads if isinstance(p.get("pos", p.get("p1", p.get("y1"))), list))
            else:
                min_x = min_y = 0
            dx, dy = center.x() - min_x - 60, center.y() - min_y - 60
            self.push_undo()
            for pl in payloads:
                if pl.get("type") == "text" and pl.get("pos"):
                    pl["pos"] = [pl["pos"][0] + dx, pl["pos"][1] + dy]
                elif pl.get("type") in ("line", "arrow"):
                    pl["p1"] = [pl["p1"][0] + dx, pl["p1"][1] + dy]
                    pl["p2"] = [pl["p2"][0] + dx, pl["p2"][1] + dy]
                elif "x1" in pl:
                    for k in ("x1", "x2"):
                        pl[k] += dx
                    for k in ("y1", "y2"):
                        pl[k] += dy
                elif pl.get("pos"):
                    pl["pos"] = [pl["pos"][0] + dx, pl["pos"][1] + dy]
                it = payload_to_item(pl)
                if it:
                    self.scene.addItem(it)
                    it.setSelected(True)
                    pasted += 1
            self.statusBar().showMessage(f"Pasted {pasted} object(s)")
            return
        img = cb.image()
        if not img.isNull():
            buf = QBuffer()
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            img.save(buf, "PNG")
            self.push_undo()
            center = self.view.mapToScene(self.view.viewport().rect().center())
            scale = min(1.0, 700.0 / max(1, img.width()))
            it = payload_to_item({"type": "image", "png": base64.b64encode(buf.data()).decode(),
                                  "pos": [center.x() - img.width() * scale / 2,
                                          center.y() - img.height() * scale / 2],
                                  "scale": scale, "layer": self.current_layer})
            self.scene.addItem(it)
            it.setSelected(True)
            self.statusBar().showMessage("Pasted image from clipboard")

    def duplicate_selection(self):
        self.copy_selection()
        self.paste_clipboard()

    # ------------------------------------------------------------ flatten export
    def _content_rect(self, selection_only: bool) -> QRectF:
        if selection_only:
            items = self._selected_items()
            if items:
                rect = QRectF()
                for it in items:
                    rect = rect.united(it.sceneBoundingRect())
                return rect.marginsAdded(QMarginsF(10, 10, 10, 10))
        r = self.scene.itemsBoundingRect()
        return r if not r.isNull() else QRectF(0, 0, 800, 600)

    def _render_board(self, rect: QRectF, dpi: int, alpha: bool) -> QImage:
        scale = dpi / 72.0
        img = QImage(max(1, int(rect.width() * scale)),
                     max(1, int(rect.height() * scale)),
                     QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent if alpha else Qt.GlobalColor.white)
        hidden = []
        if not alpha:
            pass
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.scene.render(p, QRectF(img.rect()), rect)
        p.end()
        for it, vis in hidden:
            it.setVisible(vis)
        return img

    def _export_pdf(self, path: str, rect: QRectF, dpi: int, vector_text: bool = True):
        writer = QPdfWriter(path)
        writer.setResolution(dpi)
        page_size = QPageSize(QSizeF(rect.width() * 72.0 / dpi,
                                     rect.height() * 72.0 / dpi),
                              QPageSize.Unit.Point, "board")
        writer.setPageSize(page_size)
        writer.setPageMargins(QMarginsF(0, 0, 0, 0))
        p = QPainter(writer)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pr = QRectF(writer.pageLayout().paintRectPixels(writer.resolution()))
        text_items = []
        if vector_text:
            text_items = [it for it in self.scene.items()
                          if isinstance(it, QGraphicsTextItem) and pl_of(it)]
            for t in text_items:
                t.setVisible(False)
        self.scene.render(p, pr, rect)
        if text_items:
            scale = pr.width() / max(1.0, rect.width())
            for t in text_items:
                pos = t.pos()
                dx = pr.left() + (pos.x() - rect.left()) * scale
                dy = pr.top() + (pos.y() - rect.top()) * scale
                f = t.font()
                px = max(6, int(round(f.pixelSize() * scale)))
                f.setPixelSize(px)
                p.setFont(f)
                p.setPen(QPen(t.defaultTextColor()))
                y = dy
                for line in t.toPlainText().split("\n"):
                    p.drawText(QPointF(dx, y + px), line)
                    y += px * 1.25
            for t in text_items:
                t.setVisible(True)
        p.end()

    def export_flatten(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Flatten transparency — Export")
        v = QVBoxLayout(dlg)

        row0 = QHBoxLayout()
        row0.addWidget(QLabel("Preset:"))
        preset = QComboBox()
        preset.addItems(["Medium resolution", "High resolution", "Print (600)", "Custom"])
        row0.addWidget(preset, 1)
        v.addLayout(row0)

        v.addWidget(QLabel("Balance  Raster ⟷ Vector"))
        bal = QSlider(Qt.Orientation.Horizontal)
        bal.setRange(0, 100)
        bal.setValue(75)
        v.addWidget(bal)

        grid = QGridLayout()
        grid.addWidget(QLabel("Line art & text:"), 0, 0)
        res_line = QSpinBox()
        res_line.setRange(36, 1200)
        res_line.setValue(300)
        grid.addWidget(res_line, 0, 1)
        grid.addWidget(QLabel("ppi"), 0, 2)
        grid.addWidget(QLabel("Gradients & effects:"), 1, 0)
        res_grad = QSpinBox()
        res_grad.setRange(36, 1200)
        res_grad.setValue(150)
        grid.addWidget(res_grad, 1, 1)
        grid.addWidget(QLabel("ppi"), 1, 2)
        v.addLayout(grid)

        cb_text = QCheckBox("Vectorize all text (PDF)")
        cb_text.setChecked(True)
        cb_stroke = QCheckBox("Vectorize all strokes (PDF)")
        cb_stroke.setChecked(True)
        cb_alpha = QCheckBox("Preserve alpha transparency (PNG)")
        cb_alpha.setChecked(True)
        sel_items = self._selected_items()
        cb_sel = QCheckBox(f"Selection only ({len(sel_items)} objects)")
        cb_sel.setChecked(bool(sel_items))
        has_src = any(p.get("src_pdf") for pg in self.pages for p in pg)
        cb_src = QCheckBox("Keep imported PDF pages as TRUE vector")
        cb_src.setEnabled(has_src)
        cb_src.setChecked(has_src)
        if not has_src:
            cb_src.setToolTip("Enabled after importing a PDF via 📄 In")
        for c in (cb_text, cb_stroke, cb_alpha, cb_sel, cb_src):
            v.addWidget(c)
        self._preview_label = QLabel()
        self._preview_label.setFixedHeight(150)
        self._preview_label.setStyleSheet("background:#3c5077; border-radius:6px;")
        v.addWidget(self._preview_label)

        row = QHBoxLayout()
        b_preview = QPushButton("Preview")
        b_word = QPushButton("Copy for Word")
        b_word.setObjectName("accent")
        b_save = QPushButton("Save…")
        b_save.setObjectName("accent")
        cancel = QPushButton("Cancel")
        for b in (b_preview, b_word, b_save):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(cancel)
        v.addLayout(row)

        def current_rect():
            return self._content_rect(cb_sel.isChecked())

        def do_preview():
            img = self._render_board(current_rect(), max(72, res_line.value() // 2),
                                     cb_alpha.isChecked())
            pm = QPixmap.fromImage(img).scaledToHeight(140,
                Qt.TransformationMode.SmoothTransformation)
            self._preview_label.setPixmap(pm)
        b_preview.clicked.connect(do_preview)

        def do_word():
            img = self._render_board(current_rect(), res_line.value(),
                                     cb_alpha.isChecked())
            mime = QMimeData()
            mime.setImageData(img)
            QApplication.clipboard().setMimeData(mime)
            self.statusBar().showMessage(
                f"Copied at {res_line.value()} ppi — paste in Word (Ctrl+V)")
            dlg.accept()
        b_word.clicked.connect(do_word)

        def do_save():
            rect = current_rect()
            if cb_src.isEnabled() and cb_src.isChecked():
                path, _f = QFileDialog.getSaveFileName(
                    dlg, "Save vector PDF (source pages kept)",
                    "board_vector.pdf", "PDF (*.pdf)")
                if not path:
                    return
                self._export_overlay_pdf(path, res_line.value())
                self.statusBar().showMessage(
                    f"Vector PDF saved — original pages untouched: {path}")
                dlg.accept()
                return
            vector_side = bal.value() >= 50
            if vector_side:
                path, _f = QFileDialog.getSaveFileName(dlg, "Save vector PDF",
                                                       "board.pdf", "PDF (*.pdf)")
                if not path:
                    return
                self._export_pdf(path, rect, res_line.value(), cb_text.isChecked())
                self.statusBar().showMessage(f"Vector PDF saved: {path}")
            else:
                path, _f = QFileDialog.getSaveFileName(dlg, "Save PNG",
                                                       "board.png", "PNG (*.png)")
                if not path:
                    return
                img = self._render_board(rect, res_line.value(), cb_alpha.isChecked())
                img.save(path)
                self.statusBar().showMessage(f"PNG saved at {res_line.value()} ppi: {path}")
            dlg.accept()
        b_save.clicked.connect(do_save)
        cancel.clicked.connect(dlg.reject)

        def preset_changed(i):
            if i == 0:
                bal.setValue(75); res_line.setValue(300); res_grad.setValue(150)
            elif i == 1:
                bal.setValue(85); res_line.setValue(450); res_grad.setValue(300)
            elif i == 2:
                bal.setValue(100); res_line.setValue(600); res_grad.setValue(600)
        preset.currentIndexChanged.connect(preset_changed)
        dlg.resize(520, 560)
        dlg.exec()

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
            pl = it._payload
            if not pl or pl.get(INSTR_TYPE):
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

    # ------------------------------------------------------------ PDF import
    @staticmethod
    def _qimage_to_png_b64(img: QImage) -> str:
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        return base64.b64encode(buf.data()).decode("ascii")

    def _render_pdf_images(self, path: str, dpi: int = 200, cap: int = 60):
        import pymupdf
        doc = pymupdf.open(path)
        zoom = dpi / 72.0
        mat = pymupdf.Matrix(zoom, zoom)
        out = []
        for i in range(min(doc.page_count, cap)):
            pix = doc[i].get_pixmap(matrix=mat, alpha=False)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                         QImage.Format.Format_RGB888).copy()
            r = doc[i].rect
            out.append((img, r.width, r.height))
        doc.close()
        return out

    def _make_image_payload(self, img: QImage, pos, src_pdf: str | None = None,
                            src_page: int | None = None,
                            page_pt: tuple | None = None) -> dict:
        pl = {"type": "image", "png": self._qimage_to_png_b64(img),
              "pos": [pos.x(), pos.y()], "scale": 1.0,
              "layer": self.current_layer}
        if src_pdf:
            pl["src_pdf"] = src_pdf
            pl["src_page"] = src_page
            pl["page_pt"] = list(page_pt or [595, 842])
        return pl

    def import_pdf(self):
        path, _f = QFileDialog.getOpenFileName(self, "Import PDF", "",
                                               "PDF files (*.pdf)")
        if not path:
            return
        dpi, ok = QInputDialog.getInt(self, "Import PDF",
                                      "Render quality (ppi):\nhigher = sharper, bigger file",
                                      200, 96, 400)
        if not ok:
            return
        try:
            rendered = self._render_pdf_images(path, dpi)
        except Exception as exc:
            QMessageBox.critical(self, "Import PDF", f"Could not render:\n{exc}")
            return
        if not rendered:
            QMessageBox.warning(self, "Import PDF", "No pages found.")
            return
        box = QMessageBox(self)
        box.setWindowTitle("Import PDF")
        box.setText(f"{len(rendered)} page(s) at {dpi} ppi. How to insert?")
        b_pages = box.addButton("One app-page each", QMessageBox.ButtonRole.AcceptRole)
        b_here = box.addButton("Current page (center)", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is b_pages:
            self.push_undo()
            new_pages = []
            for idx, (img, w_pt, h_pt) in enumerate(rendered):
                it = payload_to_item(self._make_image_payload(
                    img, QPointF(0, 0), src_pdf=path, src_page=idx,
                    page_pt=(w_pt, h_pt)))
                new_pages.append([it._payload])
            at = self.page_idx + 1
            self.pages[at:at] = new_pages
            self._load_page(at)
            self.statusBar().showMessage(
                f"Imported {len(rendered)} page(s) — source kept for vector export")
        elif clicked is b_here:
            self.push_undo()
            c = self.view.mapToScene(self.view.viewport().rect().center())
            first, w_pt, h_pt = rendered[0]
            it = payload_to_item(self._make_image_payload(
                first, QPointF(c.x() - first.width() / 2, c.y() - first.height() / 2),
                src_pdf=path, src_page=0, page_pt=(w_pt, h_pt)))
            self.scene.addItem(it)
            it.setSelected(True)
            self.statusBar().showMessage("PDF page inserted - select, copy, or flatten-export it")

    def _export_overlay_pdf(self, path: str, dpi: int):
        """Original PDF pages stay TRUE vector; annotations layered on top."""
        import pymupdf
        self._sync_page_store()
        out = pymupdf.open()
        src_docs = {}
        for page_payloads in self.pages:
            src_pl = next((p for p in page_payloads
                           if p.get("type") == "image" and p.get("src_pdf")), None)
            overlay_items = []
            if src_pl:
                sp = src_pl["src_pdf"]
                if sp not in src_docs:
                    src_docs[sp] = pymupdf.open(sp)
                sdoc = src_docs[sp]
                w_pt, h_pt = src_pl.get("page_pt", [595, 842])
                np_page = out.new_page(width=w_pt, height=h_pt)
                np_page.show_pdf_page(np_page.rect, sdoc, int(src_pl.get("src_page", 0)))
                skip_id = id(src_pl)
            else:
                w_pt = h_pt = None
                skip_id = None
            for pl in page_payloads:
                if id(pl) == skip_id:
                    continue
                it = payload_to_item(pl)
                if it:
                    self.scene.addItem(it)
                    overlay_items.append(it)
            rect = QRectF()
            for it in overlay_items:
                rect = rect.united(it.sceneBoundingRect())
            if src_pl:
                rect = QRectF(0, 0, w_pt * dpi / 72.0, h_pt * dpi / 72.0)
            if not rect.isNull() and (overlay_items or src_pl):
                if not src_pl:
                    rect = rect.marginsAdded(QMarginsF(16, 16, 16, 16))
                img = self._render_board(rect, dpi, bool(src_pl))
                buf = QBuffer()
                buf.open(QIODevice.OpenModeFlag.WriteOnly)
                img.save(buf, "PNG")
                if not src_pl:
                    np_page = out.new_page(width=rect.width() * 72.0 / dpi,
                                           height=rect.height() * 72.0 / dpi)
                np_page.insert_image(np_page.rect, stream=bytes(buf.data()))
            for it in overlay_items:
                self.scene.removeItem(it)
        for d in src_docs.values():
            d.close()
        out.save(path)
        out.close()

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
            ("Select", "", "select"), ("Pen", "", "pen"),
            ("Marker", "", "highlighter"), ("Eraser", "", "eraser"),
            ("Line", "", "line"), ("Arrow", "", "arrow"),
            ("Rect", "", "rect"), ("Ellipse", "", "ellipse"),
            ("Text", "", "text"), ("Laser", "", "laser"),
        ]
        self.tool_buttons = {}
        for i, (name, glyph, key) in enumerate(tools):
            b = QPushButton(name)
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
        b_eye = QPushButton("Eye")
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
        out = []
        for it in self.scene.items():
            pl = it._payload
            if not pl or pl.get(INSTR_TYPE):
                continue
            out.append(deepcopy(pl))
        return out

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




