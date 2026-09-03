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
                            QPainterPathStroker, QPolygonF, QPdfWriter, QPageSize,
                            QTransform, QLinearGradient, QRadialGradient, QGradient)
from PySide6.QtWidgets import (QApplication, QColorDialog, QComboBox, QFileDialog,
                               QFrame, QGraphicsEllipseItem, QGraphicsItem, QGraphicsItemGroup,
                               QGraphicsLineItem, QGraphicsPathItem,
                               QGraphicsRectItem, QGraphicsScene,
                               QGraphicsTextItem, QGraphicsView,
                               QHBoxLayout, QLabel, QInputDialog, QListWidget, QPlainTextEdit,
                               QMainWindow, QMessageBox, QPushButton, QSizePolicy,
                               QSlider, QVBoxLayout, QWidget, QGridLayout,
                               QDialog, QLineEdit, QSpinBox, QCheckBox,
                               QDialogButtonBox, QVBoxLayout as VBox,
                               QGraphicsDropShadowEffect)

try:
    import numpy as _np
except Exception:
    _np = None
try:
    import imageio as _imageio
except Exception:
    _imageio = None
try:
    import shiboken6 as _shiboken
except Exception:
    _shiboken = None


def shiboken_key(it):
    """Stable identity for a Qt item across wrapper instances."""
    if _shiboken is not None:
        try:
            return _shiboken.getCppPointer(it)
        except Exception:
            return id(it)
    return id(it)


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


def _rdp_keep_indices(points, eps: float):
    """Indices kept by Douglas-Peucker (keeps parallel arrays aligned)."""
    if len(points) < 3:
        return list(range(len(points)))

    def _seg(a, b):
        if b - a < 2:
            return [a, b]
        ax, ay = points[a]
        bx, by = points[b]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy)
        idx, dmax = a + 1, 0.0
        for i in range(a + 1, b):
            if L < 1e-9:
                d = math.hypot(points[i][0] - ax, points[i][1] - ay)
            else:
                d = abs(dy * (points[i][0] - ax) -
                        dx * (points[i][1] - ay)) / L
            if d > dmax:
                idx, dmax = i, d
        if dmax > eps:
            return _seg(a, idx)[:-1] + _seg(idx, b)
        return [a, b]

    return _seg(0, len(points) - 1)


def _rdp_simplify(points, eps: float):
    """Douglas-Peucker: drop jitter, keep shape. points=[[x,y],..] eps=scene px."""
    if len(points) < 3:
        return list(points)
    def _perp_dist(p, a, b):
        ax, ay = a[0], a[1]
        bx, by = b[0], b[1]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy)
        if L < 1e-9:
            return math.hypot(p[0] - ax, p[1] - ay)
        return abs(dy * (p[0] - ax) - dx * (p[1] - ay)) / L
    first, last = points[0], points[-1]
    idx, dmax = 0, 0.0
    for i in range(1, len(points) - 1):
        d = _perp_dist(points[i], first, last)
        if d > dmax:
            idx, dmax = i, d
    if dmax > eps:
        left = _rdp_simplify(points[:idx + 1], eps)
        right = _rdp_simplify(points[idx:], eps)
        return left[:-1] + right
    return [first, last]


def _catmull_bezier_path(points) -> QPainterPath:
    """Catmull-Rom through cubic Beziers: smooth hand-drawn curves."""
    if not points:
        return QPainterPath()
    pts = [QPointF(*p) if not isinstance(p, QPointF) else p for p in points]
    if len(pts) == 1:
        return QPainterPath(pts[0])
    path = QPainterPath(pts[0])
    n = len(pts)
    for i in range(n - 1):
        p0 = pts[i - 1] if i > 0 else pts[0]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < n else pts[n - 1]
        c1 = QPointF(p1.x() + (p2.x() - p0.x()) / 6.0,
                     p1.y() + (p2.y() - p0.y()) / 6.0)
        c2 = QPointF(p2.x() - (p3.x() - p1.x()) / 6.0,
                     p2.y() - (p3.y() - p1.y()) / 6.0)
        path.cubicTo(c1, c2, p2)
    return path


def _smooth_stroke_path(points, eps: float = 1.4) -> QPainterPath:
    """RDP simplify + Catmull-Rom smoothing for freehand strokes."""
    simplified = _rdp_simplify(points, eps)
    if len(simplified) < 3:
        path = QPainterPath(QPointF(*points[0])) if points else QPainterPath()
        for p in points[1:]:
            path.lineTo(QPointF(*p))
        return path
    return _catmull_bezier_path(simplified)


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
                               QFrame, QGraphicsEllipseItem, QGraphicsItem, QGraphicsItemGroup,
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


def latex_to_qpath(tex: str, size: float = 28.0) -> QPainterPath:
    """Render LaTeX (mathtext) as pure-vector QPainterPath (y flipped for Qt)."""
    from matplotlib.textpath import TextPath
    from matplotlib.font_manager import FontProperties
    import matplotlib.path as mpath
    fp = FontProperties(size=size)
    tp = TextPath((0, 0), f"${tex}$", prop=fp, usetex=False)
    path = QPainterPath()
    verts, codes = tp.vertices, tp.codes
    i = 0
    while i < len(codes):
        c = codes[i]
        x, y = verts[i]
        if c == mpath.Path.MOVETO:
            path.moveTo(x, -y)
            i += 1
        elif c == mpath.Path.LINETO:
            path.lineTo(x, -y)
            i += 1
        elif c == mpath.Path.CURVE3:
            x2, y2 = verts[i + 1]
            path.quadTo(x, -y, x2, -y2)
            i += 2
        elif c == mpath.Path.CURVE4:
            x2, y2 = verts[i + 1]
            x3, y3 = verts[i + 2]
            path.cubicTo(x, -y, x2, -y2, x3, -y3)
            i += 3
        elif c == mpath.Path.CLOSEPOLY:
            path.closeSubpath()
            i += 1
        else:
            i += 1
    return path


def qpath_to_svg_d(path: QPainterPath) -> str:
    """QPainterPath -> SVG path 'd' string."""
    parts = []
    i = 0
    n = path.elementCount()
    while i < n:
        e = path.elementAt(i)
        if e.isMoveTo():
            parts.append(f"M {e.x:.2f} {e.y:.2f}")
            i += 1
        elif e.isLineTo():
            parts.append(f"L {e.x:.2f} {e.y:.2f}")
            i += 1
        elif e.isCurveTo():
            if i + 2 < n:
                c2 = path.elementAt(i + 1)
                e2 = path.elementAt(i + 2)
                parts.append(f"C {e.x:.2f} {e.y:.2f} {c2.x:.2f} {c2.y:.2f} "
                             f"{e2.x:.2f} {e2.y:.2f}")
            i += 3
        else:
            i += 1
    return " ".join(parts)


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


# ================================================================== vpath (P2)
def _vp_node(p, out=None, inn=None, t="corner"):
    """Normalize a vpath node dict."""
    return {"p": [float(p[0]), float(p[1])],
            "out": ([float(out[0]), float(out[1])] if out else None),
            "in": ([float(inn[0]), float(inn[1])] if inn else None),
            "t": t if t in ("corner", "smooth", "asym") else "corner"}


def _vpath_to_qpath(nodes: list, closed: bool) -> QPainterPath:
    """Cubic path through nodes: control = p + in/out offsets (relative)."""
    if not nodes:
        return QPainterPath()
    path = QPainterPath(QPointF(*nodes[0]["p"]))
    n = len(nodes)
    for i in range(n - 1):
        a, b = nodes[i], nodes[i + 1]
        c1 = QPointF(a["p"][0] + (a["out"][0] if a["out"] else 0),
                     a["p"][1] + (a["out"][1] if a["out"] else 0))
        c2 = QPointF(b["p"][0] - (b["in"][0] if b["in"] else 0),
                     b["p"][1] - (b["in"][1] if b["in"] else 0))
        path.cubicTo(c1, c2, QPointF(*b["p"]))
    if closed and n > 1:
        a, b = nodes[-1], nodes[0]
        c1 = QPointF(a["p"][0] + (a["out"][0] if a["out"] else 0),
                     a["p"][1] + (a["out"][1] if a["out"] else 0))
        c2 = QPointF(b["p"][0] - (b["in"][0] if b["in"] else 0),
                     b["p"][1] - (b["in"][1] if b["in"] else 0))
        path.cubicTo(c1, c2, QPointF(*b["p"]))
    return path


def _vp_seg_bezier(nodes, i):
    """Absolute control points of segment i (node i -> i+1, wrap if closed)."""
    j = (i + 1) % len(nodes)
    a, b = nodes[i], nodes[j]
    p0 = QPointF(*a["p"])
    p3 = QPointF(*b["p"])
    p1 = QPointF(a["p"][0] + (a["out"][0] if a["out"] else 0),
                 a["p"][1] + (a["out"][1] if a["out"] else 0))
    p2 = QPointF(b["p"][0] - (b["in"][0] if b["in"] else 0),
                 b["p"][1] - (b["in"][1] if b["in"] else 0))
    return p0, p1, p2, p3


def _vp_point_on_seg(nodes, i, t: float) -> QPointF:
    p0, p1, p2, p3 = _vp_seg_bezier(nodes, i)
    u = 1 - t
    return QPointF(
        u * u * u * p0.x() + 3 * u * u * t * p1.x() +
        3 * u * t * t * p2.x() + t * t * t * p3.x(),
        u * u * u * p0.y() + 3 * u * u * t * p1.y() +
        3 * u * t * t * p2.y() + t * t * t * p3.y())


def _vp_split_segment(nodes: list, i: int, t: float) -> list:
    """de Casteljau split at t: SAME shape, one extra node. Returns new list."""
    j = (i + 1) % len(nodes)
    closed = _vp_is_closed(nodes, i)
    p0, p1, p2, p3 = _vp_seg_bezier(nodes, i)
    u = 1 - t
    q0 = QPointF(u * p0.x() + t * p1.x(), u * p0.y() + t * p1.y())
    q1 = QPointF(u * p1.x() + t * p2.x(), u * p1.y() + t * p2.y())
    q2 = QPointF(u * p2.x() + t * p3.x(), u * p2.y() + t * p3.y())
    r0 = QPointF(u * q0.x() + t * q1.x(), u * q0.y() + t * q1.y())
    r1 = QPointF(u * q1.x() + t * q2.x(), u * q1.y() + t * q2.y())
    s = QPointF(u * r0.x() + t * r1.x(), u * r0.y() + t * r1.y())
    new_nodes = [dict(x) for x in nodes]
    A, B = dict(nodes[i]), dict(nodes[j])
    # A.out -> q0 (relative), B.in -> q2 (relative)
    A["out"] = [q0.x() - A["p"][0], q0.y() - A["p"][1]]
    # new node: in = r0->s reversed => in offset = s - r0, out = s->r1 => r1 - s
    M = {"p": [s.x(), s.y()],
         "in": [s.x() - r0.x(), s.y() - r0.y()],
         "out": [r1.x() - s.x(), r1.y() - s.y()],
         "t": "smooth"}
    B["in"] = [q2.x() - B["p"][0], q2.y() - B["p"][1]]
    new_nodes[i] = A
    if j == 0:                      # wrap-around split on closed path
        new_nodes.append(M)
    else:
        new_nodes.insert(i + 1, M)
    return new_nodes


def _vp_is_closed(nodes, i=None) -> bool:
    """Closed when the wrap segment (last->first) exists, i.e. caller context.
    Pure helper kept for clarity: closedness is passed explicitly; this only
    validates node continuity markers (kept trivial)."""
    return False


def _vp_delete_node(nodes: list, i: int, closed: bool) -> list:
    """Remove node i; smooth the joint of its neighbours (auto handles)."""
    n = len(nodes)
    if n <= 2:
        return [dict(x) for x in nodes if x is not nodes[i]]
    new = [dict(x) for x in nodes]
    removed = new.pop(i)
    j = (i - 1) % len(new)          # node before removal point
    k = i % len(new)                # node after removal point
    # smooth transition: give j an out toward old direction of removed->k
    r_p = QPointF(*removed["p"])
    k_p = QPointF(*new[k]["p"])
    j_p = QPointF(*new[j]["p"])
    # out of j: 1/3 toward the midpoint arc — use vector j->removed->k guide
    v1 = r_p - j_p
    v2 = k_p - r_p
    out_v = (v1 * 0.4) + (v2 * 0.4)
    new[j]["out"] = [out_v.x(), out_v.y()]
    in_v = -(k_p - j_p) * 0.4
    new[k]["in"] = [in_v.x(), in_v.y()]
    new[j]["t"] = "smooth"
    new[k]["t"] = "smooth"
    return new


def _ink_to_vpath(points, closed: bool = False) -> list:
    """Ink (RDP-simplified points) -> vpath nodes via Catmull-Rom handles.
    in/out offsets = (prev/next - current)/6, exactly matching
    _catmull_bezier_path geometry."""
    nodes = []
    n = len(points)
    for i, p in enumerate(points):
        p_prev = points[i - 1] if i > 0 else points[0]
        p_next = points[i + 1] if i < n - 1 else points[n - 1]
        inn = [(p_prev[0] - p[0]) / 6.0, (p_prev[1] - p[1]) / 6.0]
        out = [(p_next[0] - p[0]) / 6.0, (p_next[1] - p[1]) / 6.0]
        t = "corner" if i in (0, n - 1) else "smooth"
        nodes.append(_vp_node(p, out, inn, t))
    return nodes


def _vp_path_bbox(nodes, closed):
    """Pure-python bbox of the cubic path (no Qt scene)."""
    xs, ys = [], []
    n = len(nodes)
    segs = range(n if closed else n - 1)
    for i in segs:
        p0, p1, p2, p3 = _vp_seg_bezier(nodes, i)
        for k in range(0, 21):
            t = k / 20.0
            xs.append(_vp_point_on_seg(nodes, i, t).x())
            ys.append(_vp_point_on_seg(nodes, i, t).y())
    return min(xs), min(ys), max(xs), max(ys)


# ================================================================== snap engine
class SnapEngine:
    """Geometry snapping: object points, 15° angles, ortho, grid, instruments.

    Pure logic (unit-testable): the view feeds scene points + modifiers and
    receives (snapped_point, kind). kind: None|"end"|"mid"|"center"|"grid"|
    "angle"|"ortho"|"instr".
    """
    TOL = 12.0        # screen px tolerance
    ANGLE_STEP = 15.0
    GRID = 24.0       # scene units (matches drawBackground step)

    def __init__(self, win):
        self.win = win

    # ------------------------------------------------- candidate object points
    def _object_points(self, exclude=None):
        """(QPointF, kind) candidates from every payload item on the board."""
        out = []
        for it in self.win.scene.items():
            if it is exclude or it.parentItem() is not None:
                continue
            pl = pl_of(it)
            if not pl or pl.get(INSTR_TYPE):
                continue
            t = pl.get("type")
            if t in ("pen", "highlighter", "polygon"):
                pts = [QPointF(*p) for p in pl.get("points", [])]
                if pts:
                    out.append((pts[0], "end"))
                    out.append((pts[-1], "end"))
                    if len(pts) > 2:
                        mid = pts[len(pts) // 2]
                        out.append((mid, "mid"))
            elif t in ("line", "arrow"):
                a, b = QPointF(*pl["p1"]), QPointF(*pl["p2"])
                out.append((a, "end"))
                out.append((b, "end"))
                out.append((QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2), "mid"))
                if t == "arrow" and pl.get("head"):
                    out.append((QPointF(*pl["head"][1]), "end"))
            elif t in ("rect", "oval"):
                x1, y1, x2, y2 = pl["x1"], pl["y1"], pl["x2"], pl["y2"]
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                if t == "rect":
                    for px, py in [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]:
                        out.append((QPointF(px, py), "end"))
                out.append((QPointF(cx, cy), "center"))
                if t == "oval":
                    out.append((QPointF(x1, cy), "end"))
                    out.append((QPointF(x2, cy), "end"))
                    out.append((QPointF(cx, y1), "end"))
                    out.append((QPointF(cx, y2), "end"))
            elif t in ("text", "image", "latex"):
                if pl.get("pos"):
                    out.append((QPointF(*pl["pos"]), "end"))
            elif t == "vpath":
                for nd in pl.get("nodes", []):
                    out.append((QPointF(*nd["p"]), "end"))
            elif t == "compass":
                c = QPointF(*pl.get("center", [0, 0]))
                out.append((c, "center"))
                out.append((QPointF(*pl.get("p2", [0, 0])), "end"))
        return out

    # ------------------------------------------------------------- main entry
    def snap(self, sp: QPointF, origin: QPointF | None = None,
             shift=False, alt=False, exclude=None, grid=False,
             tol: float | None = None) -> tuple[QPointF | None, str | None]:
        """Return (snapped point, kind). origin = last committed point for
        angle/ortho constraints (line drawing). alt disables object snap."""
        zoom = self.win.view.transform().m11() if self.win.view else 1.0
        tol = (self.TOL if tol is None else tol) / max(1e-6, zoom)
        # 1) instruments (ruler edge / protractor arc) keep highest priority
        sn = self.win.snap_pen(sp)
        if sn is not None:
            return sn, "instr"
        # 2) object points unless Alt
        if not alt:
            best, bkind = None, None
            for pt, kind in self._object_points(exclude=exclude):
                d = math.hypot(pt.x() - sp.x(), pt.y() - sp.y())
                if d <= tol and (best is None or d < math.hypot(
                        best.x() - sp.x(), best.y() - sp.y())):
                    best, bkind = pt, kind
            if best is not None:
                return best, bkind
        # 3) angle from origin (Shift) — 15° steps
        if origin is not None:
            dx, dy = sp.x() - origin.x(), sp.y() - origin.y()
            dist = math.hypot(dx, dy)
            if dist > 1e-6:
                if shift:
                    ang = math.radians(round(math.degrees(
                        math.atan2(dy, dx)) / self.ANGLE_STEP) * self.ANGLE_STEP)
                    return QPointF(origin.x() + dist * math.cos(ang),
                                  origin.y() + dist * math.sin(ang)), "angle"
                # 4) implicit ortho when very close to axes
                if abs(dx) < tol * 0.6:
                    return QPointF(origin.x(), sp.y()), "ortho"
                if abs(dy) < tol * 0.6:
                    return QPointF(sp.x(), origin.y()), "ortho"
        # 5) grid fallback
        if grid:
            g = self.GRID
            return QPointF(round(sp.x() / g) * g, round(sp.y() / g) * g), "grid"
        return None, None


class TransformBox(QGraphicsItem):
    """8 resize handles + rotation handle around the single selected item.
    Pure overlay: hit-test via handle_at(); BoardView applies the transform."""

    H = 7.0        # handle half-size (screen px, scaled by inverse zoom)

    def __init__(self, view):
        super().__init__()
        self.view = view
        self.setZValue(9000)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setAcceptHoverEvents(False)

    def boundingRect(self) -> QRectF:
        r = self.view._tbox_rect
        pad = 14.0
        return r.adjusted(-pad, -pad - 26, pad, pad + 14)

    def _rect(self) -> QRectF:
        return self.view._tbox_rect

    def _handles(self):
        """[(name, QPointF)] in scene coords: 8 boxes + rot above top-mid."""
        r = self._rect()
        cx = r.center()
        pts = [("nw", QPointF(r.left(), r.top())), ("n", QPointF(cx.x(), r.top())),
               ("ne", QPointF(r.right(), r.top())), ("e", QPointF(r.right(), cx.y())),
               ("se", QPointF(r.right(), r.bottom())), ("s", QPointF(cx.x(), r.bottom())),
               ("sw", QPointF(r.left(), r.bottom())), ("w", QPointF(r.left(), cx.y()))]
        pts.append(("rot", QPointF(cx.x(), r.top() - 22)))
        return pts

    def handle_at(self, sp: QPointF) -> str | None:
        zoom = max(1e-6, self.view.transform().m11())
        h = self.H / zoom
        for name, p in self._handles():
            if abs(sp.x() - p.x()) <= h and abs(sp.y() - p.y()) <= h:
                return name
        return None

    def paint(self, p: QPainter, _o, _w):
        zoom = max(1e-6, self.view.transform().m11())
        r = self._rect()
        pen = QPen(QColor("#1976d2"), 1.4 / zoom)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(r)
        # rotation stem
        cx = r.center().x()
        p.drawLine(QPointF(cx, r.top()), QPointF(cx, r.top() - 22))
        h = self.H / zoom
        p.setBrush(QBrush(QColor("#ffffff")))
        for name, pt in self._handles():
            p.setPen(QPen(QColor("#1565c0"), 1.2 / zoom))
            if name == "rot":
                p.drawEllipse(pt, h, h)
            else:
                p.drawRect(QRectF(pt.x() - h, pt.y() - h, 2 * h, 2 * h))


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
        self.snap_engine = SnapEngine(win)
        self._snap_marker = None       # live snap indicator item
        self._tbox = None              # TransformBox overlay when 1 selected
        self._tbox_rect = QRectF()     # current box rect (scene coords)
        self._transform_drag = None    # (mode, item, pl0, rect0, anchor, mods)
        # vpen (vector pen) session state
        self._vp_item = None           # StrokeItem being drawn (live preview)
        self._vp_last = None           # last placed node scene pos
        self._vp_drag_node = None      # (node_index, phase) while dragging handles
        # nodeedit (direct-select) state
        self._ne_item = None           # vpath item under node editing
        self._ne_sel = set()           # selected node indices
        self._ne_drag = None           # ('node'|'handle', idx, hkind, start)
        self._ne_rubber = None         # (QPointF, QPointF) rubber start/end

    # ----------------------------------------------------- snap indicator
    _SNAP_PEN = None

    def _show_snap(self, pt: QPointF | None, kind: str | None):
        """Green indicator: square=end, triangle=mid, circle=center,
        diamond=grid/angle/ortho/instr."""
        if pt is None or kind is None:
            if self._snap_marker is not None:
                self.scene().removeItem(self._snap_marker)
                self._snap_marker = None
            return
        if self._SNAP_PEN is None:
            BoardView._SNAP_PEN = QPen(QColor("#00c853"), 2.0)
        if self._snap_marker is None:
            self._snap_marker = QGraphicsPathItem()
            self._snap_marker.setPen(self._SNAP_PEN)
            self._snap_marker.setZValue(9999)
            self._snap_marker.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            self._snap_marker.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            self.scene().addItem(self._snap_marker)
        path = QPainterPath()
        r = 4.5
        if kind == "end":                       # square
            path.addRect(QRectF(pt.x() - r, pt.y() - r, 2 * r, 2 * r))
        elif kind == "mid":                     # triangle
            path.moveTo(pt.x(), pt.y() - r)
            path.lineTo(pt.x() - r, pt.y() + r)
            path.lineTo(pt.x() + r, pt.y() + r)
            path.closeSubpath()
        elif kind == "center":                  # circle + cross
            path.addEllipse(pt, r, r)
            path.moveTo(pt.x() - r * 1.8, pt.y())
            path.lineTo(pt.x() + r * 1.8, pt.y())
            path.moveTo(pt.x(), pt.y() - r * 1.8)
            path.lineTo(pt.x(), pt.y() + r * 1.8)
        else:                                   # diamond
            path.moveTo(pt.x(), pt.y() - r)
            path.lineTo(pt.x() + r, pt.y())
            path.lineTo(pt.x(), pt.y() + r)
            path.lineTo(pt.x() - r, pt.y())
            path.closeSubpath()
        self._snap_marker.setPath(path)

    # ------------------------------------------------------------- helpers
    def _tool(self):
        return self.win.tool

    def _pen(self, color, width, alpha=255):
        pen = QPen(_qcolor(color, alpha))
        pen.setWidthF(max(0.5, width))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    # ------------------------------------------------------------- vpen tool
    def _vpen_press(self, sp: QPointF, alt: bool):
        win = self.win
        # closing click on first node?
        if self._vp_item is not None:
            pl = pl_of(self._vp_item)
            nodes = pl.get("nodes") or []
            if nodes:
                zoom = max(1e-6, self.transform().m11())
                tol = 12.0 / zoom
                p0 = QPointF(*nodes[0]["p"])
                if math.hypot(sp.x() - p0.x(), sp.y() - p0.y()) <= tol:
                    pl["closed"] = True
                    self._vpen_commit()
                    return
        if self._vp_item is None:
            # snap first node
            sp2 = sp
            if win.snap_on:
                sn, kind = self.snap_engine.snap(sp)
                if sn is not None:
                    sp2, _ = sn, self._show_snap(sn, kind)
            win.push_undo()
            self._vp_item = StrokeItem()
            pl = {"type": "vpath", "closed": False,
                  "nodes": [_vp_node((sp2.x(), sp2.y()))],
                  "stroke": {"color": win.color, "width": float(win.size_value),
                             "alpha": 255},
                  "fill": None, "rot": 0.0, "layer": win.current_layer}
            self._vp_item._payload = pl
            self._vp_item.setData(0, True)
            self._vp_item.setPen(self._pen(win.color, win.size_value))
            win._add_item(self._vp_item)
            self._vp_drag_node = ["out", 0]
            self._vp_last = sp2
        else:
            # subsequent node: place, drag adjusts its OUT handle
            sn = sp
            if win.snap_on:
                sn2, kind = self.snap_engine.snap(sp)
                if sn2 is not None:
                    sn, _ = sn2, self._show_snap(sn2, kind)
            pl = pl_of(self._vp_item)
            # mirror previous out -> in (smooth chain default)
            prev = pl["nodes"][-1]
            pl["nodes"].append(_vp_node((sn.x(), sn.y()),
                                        out=None, inn=None, t="corner"))
            self._vp_drag_node = ["out", len(pl["nodes"]) - 1]
            self._vp_last = sn
            self._vpen_refresh()

    def _vpen_drag(self, sp: QPointF, alt: bool):
        if self._vp_item is None or not self._vp_drag_node:
            return
        phase, idx = self._vp_drag_node
        pl = pl_of(self._vp_item)
        nodes = pl["nodes"]
        nd = nodes[idx]
        if phase == "out":
            out = [sp.x() - nd["p"][0], sp.y() - nd["p"][1]]
            nd["out"] = out if math.hypot(*out) > 1e-6 else None
            if not alt:                       # symmetric in
                nd["in"] = [-out[0], -out[1]] if nd["out"] else None
                nd["t"] = "smooth" if nd["out"] else nd.get("t", "corner")
            else:
                nd["t"] = "asym"
            self._vpen_refresh()

    def _vpen_release(self, sp: QPointF):
        self._vp_drag_node = None
        self._show_snap(None, None)

    def _vpen_refresh(self):
        if self._vp_item is None:
            return
        pl = pl_of(self._vp_item)
        self._vp_item.setPath(_vpath_to_qpath(pl["nodes"], pl.get("closed", False)))

    def _vpen_commit(self):
        self._vpen_finish(commit=True)

    def _vpen_finish(self, commit: bool):
        item, self._vp_item = self._vp_item, None
        self._vp_drag_node = None
        self._vp_last = None
        self._show_snap(None, None)
        if item is None:
            return
        pl = pl_of(item)
        if not commit or not pl.get("nodes") or len(pl["nodes"]) < 2:
            # discard (undo the push_undo placeholder)
            self.scene().removeItem(item)
            if item in self.win._item_refs:
                self.win._item_refs.remove(item)
            self.win.pop_undo()
            return
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.win.statusBar().showMessage(
            f"Path: {len(pl['nodes'])} nodes"
            + (" (closed)" if pl.get("closed") else ""))

    # ------------------------------------------------------------- node edit
    def _ne_nodes(self):
        if self._ne_item is None:
            return None
        pl = pl_of(self._ne_item)
        return pl.get("nodes") if pl else None

    def _nodeedit_press(self, sp: QPointF, alt: bool):
        win = self.win
        # pick the vpath under cursor if not editing it yet
        if self._ne_item is None:
            cand = None
            for it in self.scene().items():
                pl = pl_of(it)
                if pl and pl.get("type") == "vpath":
                    if it.contains(it.mapFromScene(sp)) or \
                            it.shape().contains(it.mapFromScene(sp)):
                        cand = it
                        break
            if cand is None:
                return
            self._ne_item = cand
            self._ne_sel = set()
            cand.setSelected(False)
        nodes = self._ne_nodes()
        if nodes is None:
            self._ne_item = None
            return
        zoom = max(1e-6, self.transform().m11())
        tol = 10.0 / zoom
        # 1) node handles
        for i, nd in enumerate(nodes):
            if math.hypot(sp.x() - nd["p"][0], sp.y() - nd["p"][1]) <= tol:
                self._ne_sel = {i}
                self._ne_drag = ("node", i, None, QPointF(*nd["p"]))
                win.push_undo()
                self._ne_redraw()
                return
        # 2) bezier handles of selected node(s)
        for i in sorted(self._ne_sel):
            nd = nodes[i]
            for hk, key in (("in", "in"), ("out", "out")):
                if nd.get(key):
                    hx = nd["p"][0] + nd[key][0]
                    hy = nd["p"][1] + nd[key][1]
                    if math.hypot(sp.x() - hx, sp.y() - hy) <= tol:
                        self._ne_drag = ("handle", i, key, QPointF(hx, hy))
                        win.push_undo()
                        return
        # 3) segment: alt+click inserts node (de Casteljau, shape-preserving)
        if alt:
            n = len(nodes)
            closed = bool(pl_of(self._ne_item).get("closed"))
            segs = range(n if closed else n - 1)
            for i in segs:
                p0, p1, p2, p3 = _vp_seg_bezier(nodes, i)
                # near-segment test: sample
                hit, tbest, dbest = False, 0.0, 1e9
                for k in range(1, 20):
                    t = k / 20.0
                    pt = _vp_point_on_seg(nodes, i, t)
                    d = math.hypot(sp.x() - pt.x(), sp.y() - pt.y())
                    if d < dbest:
                        tbest, dbest = t, d
                if dbest <= tol * 1.4:
                    win.push_undo()
                    new_nodes = _vp_split_segment(nodes, i, tbest)
                    pl_of(self._ne_item)["nodes"] = new_nodes
                    idx = i + 1 if i + 1 < len(new_nodes) else len(new_nodes) - 1
                    self._ne_sel = {idx}
                    self._ne_redraw()
                    win.statusBar().showMessage(f"Node added at t={tbest:.2f}")
                    return
        # 4) rubber-band start
        self._ne_sel = set()
        self._ne_rubber = (sp, sp)
        self._ne_redraw()

    def _nodeedit_move(self, sp: QPointF, alt: bool):
        if self._ne_rubber is not None:
            self._ne_rubber = (self._ne_rubber[0], sp)
            self._ne_redraw()
            return
        if self._ne_drag is None:
            return
        kind, idx, hkey, start = self._ne_drag
        nodes = self._ne_nodes()
        if nodes is None or idx >= len(nodes):
            self._ne_drag = None
            return
        nd = nodes[idx]
        if kind == "node":
            dx, dy = sp.x() - start.x(), sp.y() - start.y()
            nd["p"] = [start.x() + dx, start.y() + dy]
        else:
            off = [sp.x() - nd["p"][0], sp.y() - nd["p"][1]]
            nd[hkey] = off if math.hypot(*off) > 1e-6 else None
            if not alt:
                other = "in" if hkey == "out" else "out"
                nd[other] = [-off[0], -off[1]] if nd[hkey] else None
                nd["t"] = "smooth" if nd[hkey] else nd.get("t", "corner")
            else:
                nd["t"] = "asym"
        self._vpen_refresh_path(self._ne_item)
        self._ne_redraw_handles_only()

    def _nodeedit_release(self, sp: QPointF):
        if self._ne_rubber is not None:
            a, b = self._ne_rubber
            r = QRectF(a, b).normalized()
            nodes = self._ne_nodes()
            if nodes:
                self._ne_sel = {i for i, nd in enumerate(nodes)
                                 if r.contains(QPointF(*nd["p"]))}
            self._ne_rubber = None
            self._ne_redraw()
            return
        self._ne_drag = None

    def _nodeedit_delete_selected(self):
        if self._ne_item is None or not self._ne_sel:
            return
        pl = pl_of(self._ne_item)
        nodes = pl.get("nodes") or []
        if len(nodes) - len(self._ne_sel) < 2:
            # too few remain: remove whole path
            self.scene().removeItem(self._ne_item)
            if self._ne_item in self.win._item_refs:
                self.win._item_refs.remove(self._ne_item)
            self._nodeedit_exit()
            return
        self.win.push_undo()
        closed = bool(pl.get("closed"))
        for i in sorted(self._ne_sel, reverse=True):
            nodes = _vp_delete_node(nodes, i, closed)
        pl["nodes"] = nodes
        self._ne_sel = set()
        self._vpen_refresh_path(self._ne_item)
        self._ne_redraw()
        self.win.statusBar().showMessage("Node deleted, neighbours smoothed")

    def _nodeedit_toggle_type(self, t):
        if self._ne_item is None or not self._ne_sel:
            return
        nodes = self._ne_nodes()
        self.win.push_undo()
        for i in self._ne_sel:
            nd = nodes[i]
            nd["t"] = t
            if t == "corner":
                nd["in"] = None
                nd["out"] = None
            else:
                # ensure some handles for smoothness (mirror from neighbours)
                nxt = nodes[(i + 1) % len(nodes)]["p"]
                prv = nodes[i - 1]["p"] if i > 0 else nodes[-1]["p"]
                v = [(nxt[0] - prv[0]) / 6.0, (nxt[1] - prv[1]) / 6.0]
                nd["out"] = v
                nd["in"] = [-v[0], -v[1]]
        self._vpen_refresh_path(self._ne_item)
        self._ne_redraw()
        self.win.statusBar().showMessage(f"Nodes → {t}")

    def _vpen_refresh_path(self, item):
        pl = pl_of(item)
        if pl:
            item.setPath(_vpath_to_qpath(pl.get("nodes") or [],
                                          bool(pl.get("closed"))))

    def _nodeedit_exit(self):
        self._ne_item = None
        self._ne_sel = set()
        self._ne_drag = None
        self._ne_rubber = None
        if getattr(self, "_ne_overlay", None) is not None:
            self.scene().removeItem(self._ne_overlay)
            self._ne_overlay = None

    def _ne_redraw(self):
        self._ne_redraw_handles_only()

    def _ne_redraw_handles_only(self):
        """(Re)draw node/handle overlay for _ne_item."""
        if getattr(self, "_ne_overlay", None) is None:
            self._ne_overlay = QGraphicsPathItem()
            self._ne_overlay.setZValue(9500)
            self._ne_overlay.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            self._ne_overlay.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            self.scene().addItem(self._ne_overlay)
            if self._ne_overlay not in self.win._item_refs:
                self.win._item_refs.append(self._ne_overlay)
        nodes = self._ne_nodes()
        path = QPainterPath()
        zoom = max(1e-6, self.transform().m11())
        r_node = 4.0 / zoom
        if nodes:
            for i, nd in enumerate(nodes):
                p = QPointF(*nd["p"])
                sel = i in self._ne_sel
                col = QColor("#e91e63") if sel else QColor("#1976d2")
                # nodes as squares
                path.addRect(QRectF(p.x() - r_node, p.y() - r_node,
                                    2 * r_node, 2 * r_node))
                # handles
                for key in ("in", "out"):
                    if nd.get(key):
                        h = QPointF(p.x() + nd[key][0], p.y() + nd[key][1])
                        path.moveTo(p)
                        path.lineTo(h)
                        path.addEllipse(h, r_node * 0.7, r_node * 0.7)
            if self._ne_rubber is not None:
                a, b = self._ne_rubber
                path.addRect(QRectF(a, b).normalized())
        self._ne_overlay.setPath(path)
        pen = QPen(QColor("#e91e63"), 1.2 / zoom)
        self._ne_overlay.setPen(pen)
        self._ne_overlay.setBrush(Qt.BrushStyle.NoBrush)


    # ------------------------------------------------------------- zoom/pan
    def wheelEvent(self, e):
        factor = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        cur = self.transform().m11()
        target = max(0.05, min(40.0, cur * factor))
        self.scale(target / cur, target / cur)
        self.win.update_zoom_label()
        e.accept()

    def mousePressEvent(self, e):
        self.win._commit_text_edits()          # flush in-place text edits
        if e.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = e.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            e.accept()
            return
        tool = self._tool()
        if tool == "text":
            self.win.add_text_at(self.mapToScene(e.position().toPoint()))
            e.accept()
            return
        if tool == "latex":
            sp = self.mapToScene(e.position().toPoint())
            self.win.open_equation_dialog(sp)
            e.accept()
            return
        if tool == "laser":
            self.win.laser_press(self.mapToScene(e.position().toPoint()))
            e.accept()
            return
        if tool == "vpen":
            self._vpen_press(self.mapToScene(e.position().toPoint()),
                             alt=bool(e.modifiers() & Qt.KeyboardModifier.AltModifier))
            e.accept()
            return
        if tool == "nodeedit":
            self._nodeedit_press(self.mapToScene(e.position().toPoint()),
                                 alt=bool(e.modifiers() & Qt.KeyboardModifier.AltModifier))
            e.accept()
            return
        if self.win.instrument_press(self.mapToScene(e.position().toPoint())):
            e.accept()
            return
        if tool not in ("select", "eraser", "text"):
            sp0 = self.mapToScene(e.position().toPoint())
            if self.win.snap_on:
                sn, kind = self.snap_engine.snap(
                    sp0, shift=bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier),
                    alt=bool(e.modifiers() & Qt.KeyboardModifier.AltModifier))
                if sn is not None:
                    self._snapped_press = sn
                    self._show_snap(sn, kind)
        if tool == "select":
            if self.win._tbox_press(self.mapToScene(e.position().toPoint()),
                                   shift=bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)):
                e.accept()
                return
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
            self.win._add_item(item)
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
        self.win._add_item(it)
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
        if tool == "vpen" and self._vp_item is not None:
            self._vpen_drag(sp,
                            alt=bool(e.modifiers() & Qt.KeyboardModifier.AltModifier))
            e.accept()
            return
        if tool == "nodeedit":
            self._nodeedit_move(sp,
                                alt=bool(e.modifiers() & Qt.KeyboardModifier.AltModifier))
            e.accept()
            return
        if self._transform_drag is not None:
            if self.win._tbox_move(
                    sp,
                    shift=bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier),
                    alt=bool(e.modifiers() & Qt.KeyboardModifier.AltModifier)):
                e.accept()
                return
        if self._tool() == "laser":
            self.win.laser_move(sp)
            e.accept()
            return
        if self.win.instrument_move(sp):
            e.accept()
            return
        if tool == "pen" and self._creating is not None:
            sn = self.win.snap_pen(sp)
            if sn:
                sp = sn
        # live snapping while drawing (origin = press point)
        if self._creating is not None and tool in ("line", "arrow",
                                                   "rect", "ellipse") \
                and self.win.snap_on:
            sn, kind = self.snap_engine.snap(
                sp, origin=self._start_pt,
                shift=bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier),
                alt=bool(e.modifiers() & Qt.KeyboardModifier.AltModifier))
            if sn is not None:
                sp = sn
                self._show_snap(sn, kind)
            else:
                self._show_snap(None, None)
        if self._erasing:
            self._erase_at(sp)
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
        if self.win.instrument_release():
            e.accept()
            return
        sp_rel = self.mapToScene(e.position().toPoint())
        if self._tool() == "vpen" and self._vp_item is not None:
            self._vpen_release(sp_rel)
            e.accept()
            return
        if self._tool() == "nodeedit":
            self._nodeedit_release(sp_rel)
            e.accept()
            return
        if self._transform_drag is not None:
            if self.win._tbox_release(self.mapToScene(e.position().toPoint())):
                e.accept()
                return
        if self._creating is not None:
            self._show_snap(None, None)          # clear snap indicator
            item, self._creating = self._creating, None
            pl = item._payload
            if pl.get("type") == "pen" and pl.get("times"):
                # brush: simplify point indices, keep times aligned
                pairs = list(zip(pl["points"], pl["times"]))
                if len(pairs) > 3:
                    idxs = _rdp_keep_indices(pl["points"], 1.0)
                    pairs = [pairs[i] for i in idxs]
                pl["points"] = [k[0] for k in pairs]
                pl["times"] = [k[1] for k in pairs]
                widths = _speed_widths(pl["points"], float(pl.get("width", 4)),
                                       pl["times"])
                pl["widths"] = [round(w, 2) for w in widths]
                pl["variable"] = True
                pl.pop("times", None)
                item.setPath(_var_stroke_path(pl["points"], widths))
                item.setBrush(QBrush(_qcolor(pl["color"], pl.get("alpha", 255))))
                item.setPen(QPen(Qt.PenStyle.NoPen))
            elif pl.get("type") in ("pen", "highlighter") and len(pl["points"]) >= 3:
                # regular ink: RDP + Catmull-Rom smoothing
                item.setPath(_smooth_stroke_path(pl["points"]))
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
        if self._tbox is not None:
            self.win._update_tbox()          # follow native item drags

    def mouseDoubleClickEvent(self, e):
        if self._tool() == "text":
            sp = self.mapToScene(e.position().toPoint())
            self.win.add_text_at(sp)
            e.accept()
            return
        if self._tool() == "select":
            # in-place text editing: double click a text item
            sp = self.mapToScene(e.position().toPoint())
            hit = None
            for it in self.win._item_refs:        # strong refs keep _payload
                if isinstance(it, QGraphicsTextItem) and pl_of(it):
                    if it.contains(it.mapFromScene(sp)):
                        hit = it
                        break
            if hit is not None:
                self.win.edit_text_item(hit)
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


class BoardGroup(QGraphicsItemGroup):
    """Selectable/movable group that keeps child payloads in sync on move."""

    def __init__(self):
        super().__init__()
        self._payload = {"type": "group", "items": [], "layer": 0}
        self.setData(0, True)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                      QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setZValue(10)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            new_pos = value
            dx = new_pos.x() - self.pos().x()
            dy = new_pos.y() - self.pos().y()
            if dx or dy:
                for c in self.childItems():
                    if pl_of(c):
                        translate_payload(pl_of(c), dx, dy)
        return super().itemChange(change, value)


def translate_payload(pl: dict, dx: float, dy: float) -> None:
    t = pl.get("type")
    if t in ("pen", "highlighter", "polygon"):
        for p in pl.get("points", []):
            p[0] += dx
            p[1] += dy
    elif t == "vpath":
        for nd in pl.get("nodes", []):
            nd["p"][0] += dx
            nd["p"][1] += dy
    elif t in ("text", "image", "latex"):
        if pl.get("pos"):
            pl["pos"][0] += dx
            pl["pos"][1] += dy
    elif t in ("line", "arrow"):
        for k in ("p1", "p2"):
            pl[k][0] += dx
            pl[k][1] += dy
        for p in pl.get("head", []):
            p[0] += dx
            p[1] += dy
    elif t in ("rect", "oval"):
        pl["x1"] += dx
        pl["x2"] += dx
        pl["y1"] += dy
        pl["y2"] += dy
    elif t == "compass":
        for k in ("center", "p2"):
            pl[k][0] += dx
            pl[k][1] += dy
    elif t == "group":
        for k in pl.get("items", []):
            translate_payload(k, dx, dy)


def scale_payload(pl: dict, sx: float, sy: float,
                  ox: float, oy: float) -> None:
    """Scale payload about origin (ox,oy). Stroke width follows |sx*sy|**0.5."""
    t = pl.get("type")
    if t in ("pen", "highlighter", "polygon"):
        for p in pl.get("points", []):
            p[0] = ox + (p[0] - ox) * sx
            p[1] = oy + (p[1] - oy) * sy
    elif t == "vpath":
        for nd in pl.get("nodes", []):
            nd["p"][0] = ox + (nd["p"][0] - ox) * sx
            nd["p"][1] = oy + (nd["p"][1] - oy) * sy
            for key in ("in", "out"):
                if nd.get(key):
                    nd[key][0] *= sx
                    nd[key][1] *= sy
    elif t in ("text", "image", "latex"):
        if pl.get("pos"):
            pl["pos"][0] = ox + (pl["pos"][0] - ox) * sx
            pl["pos"][1] = oy + (pl["pos"][1] - oy) * sy
        if t == "latex":
            pl["scale"] = float(pl.get("scale", 1.0)) * math.sqrt(abs(sx * sy))
        else:
            pl["size"] = float(pl.get("size", 18)) * math.sqrt(abs(sx * sy))
    elif t in ("line", "arrow"):
        for k in ("p1", "p2"):
            pl[k][0] = ox + (pl[k][0] - ox) * sx
            pl[k][1] = oy + (pl[k][1] - oy) * sy
        for p in pl.get("head", []):
            p[0] = ox + (p[0] - ox) * sx
            p[1] = oy + (p[1] - oy) * sy
    elif t in ("rect", "oval"):
        for kx, ky in (("x1", "y1"), ("x2", "y2")):
            pl[kx] = ox + (pl[kx] - ox) * sx
            pl[ky] = oy + (pl[ky] - oy) * sy
    elif t == "compass":
        for k in ("center", "p2"):
            pl[k][0] = ox + (pl[k][0] - ox) * sx
            pl[k][1] = oy + (pl[k][1] - oy) * sy
        pl["radius"] = float(pl.get("radius", 10)) * math.sqrt(abs(sx * sy))
    elif t == "group":
        for k in pl.get("items", []):
            scale_payload(k, sx, sy, ox, oy)
    if t == "vpath":
        st = pl.setdefault("stroke", {})
        st["width"] = max(0.5, float(st.get("width", pl.get("width", 2))) *
                          math.sqrt(abs(sx * sy)))
    elif t not in ("text", "latex", "image"):
        pl["width"] = max(0.5, float(pl.get("width", 2)) *
                          math.sqrt(abs(sx * sy)))


def rotate_payload(pl: dict, deg: float, ox: float, oy: float) -> None:
    """Rotate payload CCW-positive (Qt screen coords) about (ox,oy) in degrees.
    Rect/oval keep bounds but gain 'rot' (visual rotation via setRotation)."""
    t = pl.get("type")
    a = math.radians(deg)
    if t in ("rect", "oval"):
        cx = (pl["x1"] + pl["x2"]) / 2
        cy = (pl["y1"] + pl["y2"]) / 2
        nx = ox + (cx - ox) * math.cos(a) - (cy - oy) * math.sin(a)
        ny = oy + (cx - ox) * math.sin(a) + (cy - oy) * math.cos(a)
        w, h = abs(pl["x2"] - pl["x1"]), abs(pl["y2"] - pl["y1"])
        pl["x1"], pl["y1"] = nx - w / 2, ny - h / 2
        pl["x2"], pl["y2"] = nx + w / 2, ny + h / 2
        pl["rot"] = float(pl.get("rot", 0.0)) + deg
        return
    def rp(p):
        p[0], p[1] = (ox + (p[0] - ox) * math.cos(a) - (p[1] - oy) * math.sin(a),
                      oy + (p[0] - ox) * math.sin(a) + (p[1] - oy) * math.cos(a))
    if t in ("pen", "highlighter", "polygon"):
        for p in pl.get("points", []):
            rp(p)
    elif t == "vpath":
        for nd in pl.get("nodes", []):
            rp(nd["p"])
            for key in ("in", "out"):
                if nd.get(key):
                    dxh, dyh = nd[key]
                    nd[key] = [dxh * math.cos(a) - dyh * math.sin(a),
                               dxh * math.sin(a) + dyh * math.cos(a)]
    elif t in ("text", "image", "latex"):
        if pl.get("pos"):
            rp(pl["pos"])
        pl["rot"] = float(pl.get("rot", 0.0)) + deg
    elif t in ("line", "arrow"):
        for k in ("p1", "p2"):
            rp(pl[k])
        for p in pl.get("head", []):
            rp(p)
    elif t == "compass":
        for k in ("center", "p2"):
            rp(pl[k])
    elif t == "group":
        for k in pl.get("items", []):
            rotate_payload(k, deg, ox, oy)
        pl["rot"] = float(pl.get("rot", 0.0)) + deg


# ================================================================== gradients (P3)
def _norm_fill(fl):
    """Normalize a fill spec: None | str | dict(kind,stops[,angle|center,radius])."""
    if fl is None:
        return None
    if isinstance(fl, str):
        return fl
    if isinstance(fl, dict):
        stops = [(max(0.0, min(1.0, float(s[0]))),
                  str(s[1]),
                  int(s[2]) if len(s) > 2 else 255)
                 for s in fl.get("stops", [])
                 if isinstance(s, (list, tuple)) and len(s) >= 2]
        stops.sort(key=lambda s: s[0])
        if not stops:
            return None
        kind = fl.get("kind", "linear")
        out = {"kind": kind if kind in ("linear", "radial") else "linear",
               "stops": [[t, c, a] for t, c, a in stops]}
        if out["kind"] == "linear":
            out["angle"] = float(fl.get("angle", 0.0))
        else:
            out["center"] = [float(fl.get("center", [0.5, 0.5])[0]),
                             float(fl.get("center", [0.5, 0.5])[1])]
            out["radius"] = max(0.01, float(fl.get("radius", 0.5)))
        return out
    return None


def _fill_qbrush(fl, rect: QRectF) -> QBrush | None:
    """QBrush from a fill spec within the item's bounding rect.
    Gradient coords are relative (0..1) and mapped onto the rect."""
    fl = _norm_fill(fl)
    if fl is None:
        return None
    if isinstance(fl, str):
        return QBrush(QColor(fl))
    stops = [(s[0], _qcolor(s[1], s[2] if len(s) > 2 else 255))
             for s in fl["stops"]]
    if fl["kind"] == "linear":
        ang = math.radians(fl.get("angle", 0.0))
        cx, cy = rect.center().x(), rect.center().y()
        L = max(1e-6, rect.width() / 2.0)
        dx, dy = math.cos(ang) * L, math.sin(ang) * L
        g = QLinearGradient(QPointF(cx - dx, cy - dy),
                            QPointF(cx + dx, cy + dy))
    else:
        cc = fl.get("center", [0.5, 0.5])
        c = QPointF(rect.left() + cc[0] * rect.width(),
                    rect.top() + cc[1] * rect.height())
        r = fl.get("radius", 0.5) * max(rect.width(), rect.height())
        g = QRadialGradient(c, max(1e-6, r))
    for t, col in stops:
        g.setColorAt(t, col)
    return QBrush(g)


def apply_fill_to_item(it, fl) -> None:
    """Set (or clear) the item brush from a normalized fill spec."""
    fl = _norm_fill(fl)
    if fl is None:
        it.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        return
    if isinstance(fl, str):
        it.setBrush(QBrush(QColor(fl)))
        return
    it.setBrush(_fill_qbrush(fl, it.boundingRect()))


# ================================================================== boolean ops (P4)
def _qpath_to_vpath_nodes(path: QPainterPath) -> tuple:
    """Convert a QPainterPath into vpath nodes (+closed flag).
    Curve control points become smooth node handles."""
    nodes = []
    closed = False
    els = [path.elementAt(i) for i in range(path.elementCount())]
    i = 0
    pending_ctrl = None            # [c1, c2] awaiting the on-curve point
    while i < len(els):
        e = els[i]
        t = e.type
        if t == QPainterPath.ElementType.MoveToElement:
            if pending_ctrl is None:
                if nodes:
                    closed = False
                nodes.append(_vp_node((e.x, e.y)))
            else:
                nodes.append(_vp_node((e.x, e.y)))
        elif t == QPainterPath.ElementType.LineToElement:
            if pending_ctrl is not None:
                # degenerate: treat curve controls as skipped
                pending_ctrl = None
            nodes.append(_vp_node((e.x, e.y)))
        elif t == QPainterPath.ElementType.CurveToElement:
            c1 = (e.x, e.y)
            if i + 2 < len(els):
                c2 = (els[i + 1].x, els[i + 1].y)
                tgt = (els[i + 2].x, els[i + 2].y)
            else:
                c2 = tgt = c1
            # previous node gets out = c1 - prev_p
            if nodes:
                prev = nodes[-1]
                px, py = prev["p"]
                prev["out"] = [c1[0] - px, c1[1] - py]
            # new node: in = c2->p reversed, t=smooth
            nodes.append(_vp_node(tgt,
                                  out=None,
                                  inn=[tgt[0] - c2[0], tgt[1] - c2[1]],
                                  t="smooth"))
            i += 2
        i += 1
    if nodes and els and els[-1].type in (
            QPainterPath.ElementType.LineToElement,
            QPainterPath.ElementType.CurveToDataElement):
        # detect closure: last point == first
        if (abs(nodes[-1]["p"][0] - nodes[0]["p"][0]) < 1e-4 and
                abs(nodes[-1]["p"][1] - nodes[0]["p"][1]) < 1e-4):
            nodes.pop()
            closed = True
    return nodes, closed


def sync_item_payload_pos(it) -> None:
    """If the item was natively moved (pos != 0), bake the offset into its
    payload so saving/copying reflects the visual position."""
    pl = pl_of(it)
    if not pl or pl.get(INSTR_TYPE):
        return
    if it.parentItem() is not None:          # group children: group handles it
        return
    p = it.pos()
    if abs(p.x()) < 1e-9 and abs(p.y()) < 1e-9:
        return
    t = pl.get("type")
    if t in ("text", "image", "latex"):
        if pl.get("pos"):
            pl["pos"][0] += p.x()
            pl["pos"][1] += p.y()
    else:
        translate_payload(pl, p.x(), p.y())
    # re-anchor geometry: reset local geometry to the new payload values
    if hasattr(it, "setRect") and t in ("rect", "oval"):
        it.setRect(QRectF(QPointF(pl["x1"], pl["y1"]),
                          QPointF(pl["x2"], pl["y2"])))
    elif t == "line":
        it.setLine(QLineF(QPointF(*pl["p1"]), QPointF(*pl["p2"])))
    it.setPos(0, 0)


def sync_scene_payloads(win) -> None:
    """Bake native item moves into payloads (before save/copy/undo).
    Uses strong refs (_item_refs) to avoid Shiboken GC pitfalls; refs to
    items no longer in the scene are pruned."""
    live = []
    for it in list(getattr(win, "_item_refs", None) or []):
        try:
            if it.scene() is win.scene:
                live.append(it)
                sync_item_payload_pos(it)
        except RuntimeError:
            continue
    win._item_refs = live


def payload_to_qpath(pl: dict) -> QPainterPath:
    """Scene-space QPainterPath of any closed-shape payload (bool ops input)."""
    t = pl.get("type")
    if t == "vpath":
        return _vpath_to_qpath(pl.get("nodes") or [], bool(pl.get("closed")))
    if t == "rect":
        r = QRectF(QPointF(pl["x1"], pl["y1"]), QPointF(pl["x2"], pl["y2"]))
        p = QPainterPath()
        p.addRect(r)
        return p
    if t == "oval":
        r = QRectF(QPointF(pl["x1"], pl["y1"]), QPointF(pl["x2"], pl["y2"]))
        p = QPainterPath()
        p.addEllipse(r)
        return p
    if t == "polygon":
        pts = pl.get("points", [])
        p = QPainterPath()
        if pts:
            p.moveTo(QPointF(*pts[0]))
            for q in pts[1:]:
                p.lineTo(QPointF(*q))
            p.closeSubpath()
        return p
    if t in ("pen", "highlighter"):
        pts = pl.get("points", [])
        p = QPainterPath()
        if pts:
            p.moveTo(QPointF(*pts[0]))
            for q in pts[1:]:
                p.lineTo(QPointF(*q))
        return p
    return QPainterPath()


def boolean_payloads(pl_a: dict, pl_b: dict, op: str) -> dict | None:
    """Boolean combine two shape payloads ('unite'|'subtract'|'intersect')
    into a new vpath payload. Returns None for empty results."""
    pa = payload_to_qpath(pl_a)
    pb = payload_to_qpath(pl_b)
    if pa.isEmpty() or pb.isEmpty():
        return None
    if op == "unite":
        res = pa.united(pb)
    elif op == "subtract":
        res = pa.subtracted(pb)
    elif op == "intersect":
        res = pa.intersected(pb)
    else:
        return None
    if res.isEmpty():
        return None
    nodes, closed = _qpath_to_vpath_nodes(res)
    # Qt flattens curves in some boolean results: simplify dense polylines
    if len(nodes) > 60:
        pts = [nd["p"] for nd in nodes]
        bb = QRectF()
        for p in pts:
            bb = bb.united(QRectF(p[0], p[1], 0.01, 0.01))
        eps = max(0.6, min(4.0, bb.width() / 220.0))
        keep = _rdp_keep_indices(pts, eps)
        nodes = [nodes[i] for i in keep]
        for nd in nodes:
            nd["t"] = "corner"
            nd["in"] = None
            nd["out"] = None
    if len(nodes) < 2:
        return None
    st = pl_a.get("stroke") or {}
    stroke = {"color": st.get("color", pl_a.get("color", "#111111")),
              "width": float(st.get("width", pl_a.get("width", 3))),
              "alpha": int(st.get("alpha", pl_a.get("alpha", 255)))}
    fill = pl_a.get("fill")
    return {"type": "vpath", "closed": closed, "nodes": nodes,
            "stroke": stroke, "fill": deepcopy(fill) if fill else None,
            "rot": 0.0, "layer": int(pl_a.get("layer", 0))}


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
        apply_fill_to_item(it, pl.get("fill"))
    elif t == "oval":
        it = QGraphicsEllipseItem(QRectF(QPointF(pl["x1"], pl["y1"]), QPointF(pl["x2"], pl["y2"])))
        it.setPen(QPen(QColor(color), width))
        apply_fill_to_item(it, pl.get("fill"))
    elif t == "polygon":
        it = StrokeItem()
        pts = pl.get("points", [])
        if pts:
            path = QPainterPath(QPointF(pts[0][0], pts[0][1]))
            for p in pts[1:]:
                path.lineTo(QPointF(p[0], p[1]))
            path.closeSubpath()
            it.setPath(path)
        it.setPen(QPen(QColor(color), width, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap))
        apply_fill_to_item(it, pl.get("fill"))
    elif t == "vpath":
        it = StrokeItem()
        nodes = pl.get("nodes") or []
        it.setPath(_vpath_to_qpath(nodes, bool(pl.get("closed"))))
        st = pl.get("stroke") or {}
        self_store = {"color": st.get("color", color),
                      "width": float(st.get("width", width)),
                      "alpha": int(st.get("alpha", 255)),
                      "dash": st.get("dash"),
                      "join": st.get("join", "round")}
        pen = QPen(_qcolor(self_store["color"], self_store["alpha"]),
                   self_store["width"], Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.FlatCap if self_store["dash"] else Qt.PenCapStyle.RoundCap,
                   {"round": Qt.PenJoinStyle.RoundJoin,
                    "miter": Qt.PenJoinStyle.MiterJoin,
                    "bevel": Qt.PenJoinStyle.BevelJoin}.get(self_store["join"],
                                                            Qt.PenJoinStyle.RoundJoin))
        if self_store["dash"]:
            pen.setDashPattern(self_store["dash"])
        it.setPen(pen)
        fl = pl.get("fill")
        if fl:
            apply_fill_to_item(it, fl)
    elif t == "latex":
        it = StrokeItem()
        try:
            it.setPath(latex_to_qpath(pl.get("tex", ""), float(pl.get("size", 28))))
        except Exception:
            it.setPath(QPainterPath())
        it.setBrush(QBrush(QColor(color)))
        it.setPen(QPen(Qt.PenStyle.NoPen))
        if pl.get("pos"):
            it.setPos(QPointF(*pl["pos"]))
        it.setScale(float(pl.get("scale", 1.0)))
    elif t == "group":
        kids = [payload_to_item(k) for k in pl.get("items", [])]
        grp = BoardGroup()
        for k in kids:
            if k:
                k.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
                k.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
                grp.addToGroup(k)
        it = grp
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
    if pl.get("rot"):
        it.setRotation(float(pl["rot"]))
    return it


class GradientDialog(QDialog):
    """Gradient fill editor: linear/radial + draggable stops + live preview."""

    def __init__(self, parent, initial=None, base_color="#2196f3"):
        super().__init__(parent)
        self.setWindowTitle("Gradient Fill")
        self.setMinimumWidth(420)
        self.spec = _norm_fill(initial) if initial else {
            "kind": "linear", "angle": 0.0,
            "stops": [[0.0, base_color, 255], [1.0, "#ffffff", 255]]}
        if isinstance(self.spec, str):                # flat color in
            self.spec = {"kind": "linear", "angle": 0.0,
                         "stops": [[0.0, self.spec, 255],
                                   [1.0, "#ffffff", 255]]}
        lay = QVBoxLayout(self)
        # preview
        self.preview = QLabel()
        self.preview.setMinimumHeight(64)
        self.preview.setStyleSheet("border:1px solid #444;")
        lay.addWidget(self.preview)
        # kind row
        krow = QHBoxLayout()
        krow.addWidget(QLabel("Type:"))
        self.kind_combo = QComboBox()
        self.kind_combo.addItems(["Linear", "Radial"])
        self.kind_combo.setCurrentIndex(
            0 if self.spec.get("kind") == "linear" else 1)
        self.kind_combo.currentIndexChanged.connect(self._sync)
        krow.addWidget(self.kind_combo)
        krow.addWidget(QLabel("Angle:"))
        self.angle_spin = QSpinBox()
        self.angle_spin.setRange(0, 359)
        self.angle_spin.setValue(int(self.spec.get("angle", 0)))
        self.angle_spin.valueChanged.connect(self._sync)
        krow.addWidget(self.angle_spin)
        lay.addLayout(krow)
        # stops list + editor
        srow = QHBoxLayout()
        self.stop_list = QListWidget()
        self.stop_list.setMaximumHeight(120)
        self.stop_list.currentRowChanged.connect(self._load_stop)
        srow.addWidget(self.stop_list, 1)
        ed = QVBoxLayout()
        self.stop_pos = QSpinBox(); self.stop_pos.setRange(0, 100)
        self.stop_color = QPushButton("Color")
        self.stop_color.clicked.connect(self._pick_stop_color)
        self.stop_alpha = QSpinBox(); self.stop_alpha.setRange(0, 255)
        b_add = QPushButton("＋ Stop")
        b_add.clicked.connect(self._add_stop)
        b_del = QPushButton("✕ Stop")
        b_del.clicked.connect(self._del_stop)
        for w in (QLabel("Pos %"), self.stop_pos, self.stop_color,
                  QLabel("Alpha"), self.stop_alpha, b_add, b_del):
            if isinstance(w, QLabel):
                ed.addWidget(w)
            else:
                ed.addWidget(w)
        self.stop_pos.valueChanged.connect(self._write_stop)
        self.stop_alpha.valueChanged.connect(self._write_stop)
        srow.addLayout(ed)
        lay.addLayout(srow)
        # preview render
        self._tmp_item = QGraphicsRectItem(QRectF(0, 0, 380, 56))
        # buttons
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel |
                              QDialogButtonBox.StandardButton.Apply)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self._apply_requested)
        lay.addWidget(bb)
        self._applied = None
        self._stop_loading = False
        self._reload()
        self._render_preview()

    def result_spec(self):
        return deepcopy(self._applied or self.spec)

    def _apply_requested(self):
        self._applied = deepcopy(self.spec)

    def _reload(self):
        self._stop_loading = True
        self.stop_list.clear()
        for s in self.spec["stops"]:
            self.stop_list.addItem(f"{int(s[0]*100)}%  {s[1]}  α{s[2]}")
        self._stop_loading = False

    def _sync(self):
        if self._stop_loading:
            return
        self.spec["kind"] = "linear" if self.kind_combo.currentIndex() == 0 \
            else "radial"
        if self.spec["kind"] == "linear":
            self.spec["angle"] = float(self.angle_spin.value())
            self.spec.pop("center", None); self.spec.pop("radius", None)
        else:
            self.spec.setdefault("center", [0.5, 0.5])
            self.spec.setdefault("radius", 0.5)
            self.spec.pop("angle", None)
        self._render_preview()

    def _load_stop(self, row):
        if self._stop_loading or row < 0:
            return
        s = self.spec["stops"][row]
        self._stop_loading = True
        self.stop_pos.setValue(int(s[0] * 100))
        self.stop_alpha.setValue(int(s[2] if len(s) > 2 else 255))
        c = QColor(s[1])
        self.stop_color.setStyleSheet(f"background:{s[1]};"
                                      f"color:{'#fff' if c.lightness() < 128 else '#000'};")
        self._stop_loading = False

    def _write_stop(self):
        if self._stop_loading:
            return
        row = self.stop_list.currentRow()
        if row < 0:
            return
        s = self.spec["stops"][row]
        s[0] = self.stop_pos.value() / 100.0
        s[2] = self.stop_alpha.value()
        self.spec["stops"].sort(key=lambda x: x[0])
        self._reload()
        self.stop_list.setCurrentRow(min(row, len(self.spec["stops"]) - 1))
        self._render_preview()

    def _pick_stop_color(self):
        row = self.stop_list.currentRow()
        if row < 0:
            return
        c = QColorDialog.getColor(QColor(self.spec["stops"][row][1]),
                                  self, "Stop color")
        if c.isValid():
            self.spec["stops"][row][1] = c.name()
            self._reload()
            self.stop_list.setCurrentRow(row)
            self._render_preview()

    def _add_stop(self):
        if len(self.spec["stops"]) >= 8:
            return
        mid = 0.5
        used = [s[0] for s in self.spec["stops"]]
        while any(abs(mid - u) < 0.05 for u in used) and mid < 0.99:
            mid += 0.05
        self.spec["stops"].append([round(mid, 2), self.win_color_default(), 255])
        self.spec["stops"].sort(key=lambda x: x[0])
        self._reload()
        self.stop_list.setCurrentRow(len(self.spec["stops"]) - 1)
        self._render_preview()

    @staticmethod
    def win_color_default():
        return "#ffc107"

    def _del_stop(self):
        if len(self.spec["stops"]) <= 2:
            return                      # keep at least 2
        row = self.stop_list.currentRow()
        if row >= 0:
            self.spec["stops"].pop(row)
            self._reload()
            self.stop_list.setCurrentRow(0)
            self._render_preview()

    def _render_preview(self):
        apply_fill_to_item(self._tmp_item, self.spec)
        pm = QPixmap(380, 56)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#888"), 1))
        p.setBrush(self._tmp_item.brush())
        p.drawRect(QRectF(0.5, 0.5, 379, 55))
        p.end()
        self.preview.setPixmap(pm)


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
        self.snap_on = True                  # SnapEngine master switch
        # recorder state
        self._rec_writer = None
        self._rec_fps = 30
        self._rec_w = 1920
        self._rec_h = 1080
        self._rec_quality = 8
        self._rec_path: str | None = None
        self._rec_frame_count = 0
        self._rec_start_time: float | None = None
        self._rec_timer = None

        self.scene = QGraphicsScene(-100000, -100000, 200000, 200000)
        self.scene.selectionChanged.connect(self.update_props_panel)
        self._item_refs: list = []
        self.scene.selectionChanged.connect(self._update_tbox)
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
        # pre-warm LaTeX engine in background (font cache build on first run)
        QTimer.singleShot(200, lambda: latex_to_qpath("x", 20))

    # ------------------------------------------------------------ toolbar
    def _act(self, text, shortcut, fn, checkable=False):
        a = QAction(text, self)
        a.setShortcut(QKeySequence(shortcut))
        a.triggered.connect(fn)
        a.setCheckable(checkable)
        self.addAction(a)
        tb = getattr(self, "_tb", None)
        if tb is not None:
            tb.addAction(a)
        return a

    def _build_toolbar(self):
        tb = self.addToolBar("main")
        self._tb = tb
        tb.setMovable(False)
        self._act("New", "Ctrl+N", self.new_board)
        self._act("Open", "Ctrl+O", self.open_doc)
        self._act("Save", "Ctrl+S", self.save_doc)
        self._act("Flatten export", "Ctrl+Shift+E", self.export_flatten)
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
        self.picker_btn = QPushButton("Pick")
        self.picker_btn.setFixedWidth(34)
        self.picker_btn.setToolTip("Eyedropper - pick color from screen (Ctrl+Shift+I)")
        self.picker_btn.setShortcut("Ctrl+Shift+I")
        self.picker_btn.clicked.connect(self.pick_screen_color)
        tb.addWidget(self.picker_btn)
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
        self._act("Group", "Ctrl+G", self.group_selection)
        self._act("Ungroup", "Ctrl+Shift+G", self.ungroup_selection)
        self._act("Ink→Path", "Ctrl+Shift+K", self.ink_to_path)
        for label, op, tip in [("∪", "unite", "Unite selected shapes (boolean)"),
                               ("−", "subtract", "Subtract 2nd shape from 1st"),
                               ("∩", "intersect", "Intersect shapes")]:
            b = QPushButton(label)
            b.setFixedWidth(30)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, o=op: self.boolean_selection(o))
            tb.addWidget(b)
        tb.addSeparator()
        for label, mode, tip in [
                ("⇤", "left", "Align left"), ("⇔", "hcenter", "Align horizontal centers"),
                ("⇥", "right", "Align right"), ("⇧", "top", "Align top"),
                ("⇕", "vcenter", "Align vertical centers"), ("⇩", "bottom", "Align bottom"),
                ("⇶", "hdist", "Distribute horizontally"), ("⇅", "vdist", "Distribute vertically")]:
            b = QPushButton(label)
            b.setFixedWidth(26)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, m=mode: self.align_selection(m))
            tb.addWidget(b)
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
        b_unlock = QPushButton("Unlock")
        b_unlock.setToolTip("Disassemble selected PDF page into editable vectors")
        b_unlock.clicked.connect(self.unlock_to_vector)
        tb.addWidget(b_unlock)
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
        tb.addSeparator()
        self.rec_btn = QPushButton("● REC")
        self.rec_btn.setFixedWidth(64)
        self.rec_btn.setToolTip("Record board session to MP4 (F9)")
        self.rec_btn.setShortcut("F9")
        self.rec_btn.clicked.connect(self.toggle_recording)
        tb.addWidget(self.rec_btn)
        self.rec_label = QLabel("")
        self.rec_label.setStyleSheet("color:#ff5252; font-weight:bold;")
        tb.addWidget(self.rec_label)
        self.snap_btn = QPushButton("Snap")
        self.snap_btn.setCheckable(True)
        self.snap_btn.setChecked(True)
        self.snap_btn.setFixedWidth(52)
        self.snap_btn.setShortcut("Ctrl+Shift+S")
        self.snap_btn.setToolTip("Geometry snapping: endpoints/midpoints/centers, Shift=15° angles, Alt=off (Ctrl+Shift+S)")
        self.snap_btn.toggled.connect(self.set_snapping)
        tb.addWidget(self.snap_btn)

    # ------------------------------------------------------------ recorder
    def set_snapping(self, on: bool):
        self.snap_on = bool(on)
        if not on:
            self.view._show_snap(None, None)
        self.statusBar().showMessage("Snapping ON" if on else "Snapping OFF")

    REC_PRESETS = [("720p (HD)", 1280, 720), ("1080p (Full HD)", 1920, 1080),
                   ("2K", 2560, 1440), ("4K (Ultra HD)", 3840, 2160)]

    def toggle_recording(self):
        if self._rec_writer is not None:
            self._stop_recording()
        else:
            self._start_recording()

    def _rec_settings_dialog(self) -> bool:
        """Ask resolution/fps/quality; True when confirmed."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Recording Settings")
        lay = QGridLayout(dlg)
        lay.addWidget(QLabel("Resolution:"), 0, 0)
        combo = QComboBox()
        for name, w, h in self.REC_PRESETS:
            combo.addItem(f"{name}  ({w}×{h})")
        combo.setCurrentIndex(1)
        lay.addWidget(combo, 0, 1)
        lay.addWidget(QLabel("FPS:"), 1, 0)
        fps = QSpinBox(); fps.setRange(10, 120); fps.setValue(30)
        lay.addWidget(fps, 1, 1)
        lay.addWidget(QLabel("Quality (1-10):"), 2, 0)
        qual = QSpinBox(); qual.setRange(1, 10); qual.setValue(8)
        lay.addWidget(qual, 2, 1)
        lay.addWidget(QLabel("Region: current view (zoom/pan respected)."), 3, 0, 1, 2)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb, 4, 0, 1, 2)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return False
        _, w, h = self.REC_PRESETS[combo.currentIndex()]
        self._rec_w, self._rec_h = w, h
        self._rec_fps = fps.value()
        self._rec_quality = qual.value()
        return True

    def _start_recording(self):
        if _imageio is None or _np is None:
            QMessageBox.warning(self, "Recorder",
                                "imageio / numpy are not installed.\n"
                                "Install: pip install imageio imageio-ffmpeg numpy")
            return
        if not self._rec_settings_dialog():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Record to MP4", "", "MP4 video (*.mp4)")
        if not path:
            return
        if not path.lower().endswith(".mp4"):
            path += ".mp4"
        try:
            self._rec_writer = _imageio.get_writer(
                path, fps=self._rec_fps, codec="libx264",
                quality=self._rec_quality, macro_block_size=1)
        except Exception as exc:
            QMessageBox.critical(self, "Recorder", f"Could not start recording:\n{exc}")
            return
        self._rec_path = path
        self._rec_frame_count = 0
        self._rec_start_time = time.perf_counter()
        self.rec_btn.setText("■ STOP")
        self.rec_label.setText("● REC")
        self._rec_timer = QTimer(self)
        self._rec_timer.timeout.connect(self._rec_capture_frame)
        self._rec_timer.start(int(1000 / self._rec_fps))
        self.statusBar().showMessage(
            f"Recording {self._rec_w}×{self._rec_h}@{self._rec_fps}fps → {path}")

    def _rec_capture_frame(self):
        if self._rec_writer is None:
            return
        try:
            img = self._rec_grab_frame()
            self._rec_writer.append_data(img)
            self._rec_frame_count += 1
            elapsed = time.perf_counter() - (self._rec_start_time or 0)
            self.rec_label.setText(f"● {elapsed:.0f}s · {self._rec_frame_count}f")
        except Exception as exc:
            self.statusBar().showMessage(f"REC error: {exc}")
            self._stop_recording()
            return

    def _rec_grab_frame(self):
        """Capture current view at target resolution, same world region."""
        vp = self.view.viewport()
        pix = vp.grab()                                  # live pixels incl. background
        if pix.width() < 2 or pix.height() < 2:
            raise RuntimeError("viewport grab failed")
        img = pix.toImage().convertToFormat(QImage.Format.Format_RGB888)
        if (img.width(), img.height()) != (self._rec_w, self._rec_h):
            img = img.scaled(self._rec_w, self._rec_h,
                             Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        # RGB888 lines are 4-byte aligned; build dense array via bytes
        ptr = img.constBits()
        arr = _np.frombuffer(ptr, dtype=_np.uint8,
                             count=img.sizeInBytes()).reshape(
                                 img.height(), img.bytesPerLine())[:, :img.width() * 3]
        return arr.reshape(img.height(), img.width(), 3).copy()

    def _stop_recording(self):
        if self._rec_timer is not None:
            self._rec_timer.stop()
            self._rec_timer.deleteLater()
            self._rec_timer = None
        if self._rec_writer is not None:
            try:
                self._rec_writer.close()
            except Exception:
                pass
            self._rec_writer = None
        duration = time.perf_counter() - (self._rec_start_time or time.perf_counter())
        self.rec_btn.setText("● REC")
        self.rec_label.setText("")
        self.statusBar().showMessage(
            f"Saved {self._rec_frame_count} frames ({duration:.1f}s)"
            + (f" → {self._rec_path}" if self._rec_path else ""))
        self._rec_path = None

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
                self._add_item(payload_to_item(pl))
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
        self._add_item(it)

    # ------------------------------------------------------------ laser
    def laser_press(self, sp: QPointF):
        it = StrokeItem()
        path = QPainterPath(sp)
        path.lineTo(sp + QPointF(0.01, 0.01))
        it.setPath(path)
        it.setPen(QPen(QColor(255, 45, 85), 6, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        it.setZValue(900)
        self._add_item(it)
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

    # ------------------------------------------------------------ properties
    def _add_item(self, it):
        """Add to scene AND keep a Python ref so the Shiboken wrapper (and its
        _payload attribute) survives garbage collection."""
        if it is not None:
            self.scene.addItem(it)
            self._item_refs.append(it)
        return it

    def _iter_sel_payload_items(self):
        for it in self.scene.selectedItems():
            if isinstance(it, BoardGroup):
                for c in it.childItems():
                    if pl_of(c):
                        yield c
            elif pl_of(it):
                yield it

    def _restyle(self, it, color=None, width=None):
        pl = pl_of(it)
        if not pl or pl.get(INSTR_TYPE):
            return
        t = pl.get("type")
        if t == "text":
            if color:
                pl["color"] = color
                it.setDefaultTextColor(QColor(color))
            if width is not None:
                pl["size"] = int(width)
                f = it.font()
                f.setPointSize(max(4, int(width)))
                it.setFont(f)
            return
        if t == "vpath":
            st = pl.setdefault("stroke", {})
            if color:
                st["color"] = color
            if width is not None:
                st["width"] = float(width)
            pen = it.pen()
            if color:
                pen.setColor(QColor(color))
            if width is not None:
                pen.setWidthF(max(0.5, float(width)))
            it.setPen(pen)
            return
        if t == "image":
            return
        if t == "latex":
            if color:
                pl["color"] = color
                it.setBrush(QBrush(QColor(color)))
            if width is not None:
                base = float(pl.get("base", pl.get("size", 30)))
                pl["size"] = float(width)
                it.setScale(float(width) / base)
            return
        old_width = float(pl.get("width", 0))
        if color:
            pl["color"] = color
        if width is not None:
            pl["width"] = float(width)
        if t == "pen" and pl.get("variable"):
            if width is not None and old_width > 0:
                ratio = float(width) / old_width
                pl["widths"] = [round(w * ratio, 2)
                                for w in pl.get("widths", [old_width])]
            it.setPath(_var_stroke_path(pl.get("points", []),
                                        pl.get("widths", [2])))
            it.setBrush(QBrush(_qcolor(pl.get("color", "#000"),
                                       pl.get("alpha", 255))))
            it.setPen(QPen(Qt.PenStyle.NoPen))
            return
        pen = it.pen()
        if color:
            c = QColor(color)
            if t == "highlighter":
                c.setAlpha(pl.get("alpha", 90))
            pen.setColor(c)
        if width is not None:
            pen.setWidthF(max(0.5, float(width)))
        it.setPen(pen)
        if color and t == "arrow":
            if it.brush().style() != Qt.BrushStyle.NoBrush:
                it.setBrush(QBrush(QColor(color)))

    # ------------------------------------------------------------ transform box
    def _update_tbox(self):
        """Show TransformBox around exactly one selectable payload item."""
        v = self.view
        sel = [i for i in self.scene.selectedItems()
               if pl_of(i) and not pl_of(i).get(INSTR_TYPE)
               and not isinstance(i, BoardGroup)]
        if len(sel) == 1 and self.tool == "select":
            it = sel[0]
            v._tbox_rect = it.sceneBoundingRect().adjusted(-1, -1, 1, 1)
            if v._tbox is None:
                v._tbox = TransformBox(v)
                self._add_item(v._tbox)
            v._tbox.setPos(0, 0)
            v._tbox.prepareGeometryChange()
        else:
            if v._tbox is not None:
                self.scene.removeItem(v._tbox)
                if v._tbox in self._item_refs:
                    self._item_refs.remove(v._tbox)
                v._tbox = None
            v._transform_drag = None

    def _tbox_press(self, sp: QPointF, shift: bool) -> bool:
        """Handle press on TransformBox; True when consumed."""
        v = self.view
        if v._tbox is None or self.tool != "select":
            return False
        mode = v._tbox.handle_at(sp)
        if mode is None:
            return False
        sel = [i for i in self.scene.selectedItems()
               if pl_of(i) and not pl_of(i).get(INSTR_TYPE)]
        if not sel:
            return False
        it = sel[0]
        r0 = QRectF(v._tbox_rect)
        cx, cy = r0.center().x(), r0.center().y()
        # anchor = fixed opposite corner (resize) or rect center (rotate)
        anchors = {"nw": QPointF(r0.right(), r0.bottom()),
                   "se": QPointF(r0.left(), r0.top()),
                   "ne": QPointF(r0.left(), r0.bottom()),
                   "sw": QPointF(r0.right(), r0.top()),
                   "n": QPointF(cx, r0.bottom()),
                   "s": QPointF(cx, r0.top()),
                   "e": QPointF(r0.left(), cy),
                   "w": QPointF(r0.right(), cy)}
        anchor = anchors.get(mode, r0.center())
        v._transform_drag = {"mode": mode, "item": it,
                             "pl0": deepcopy(pl_of(it)), "rect0": r0,
                             "anchor": anchor, "shift": shift}
        self.push_undo()
        return True

    def _tbox_move(self, sp: QPointF, shift: bool, alt: bool) -> bool:
        v = self.view
        d = v._transform_drag
        if d is None:
            return False
        mode, it = d["mode"], d["item"]
        r0, anchor = d["rect0"], d["anchor"]
        pl0 = d["pl0"]
        if mode == "rot":
            c = r0.center()
            # angle of grab point vs vertical-up through center
            ang = math.degrees(math.atan2(sp.y() - c.y(), sp.x() - c.x())
                               + math.pi / 2)
            if shift:
                ang = round(ang / 15.0) * 15.0
            d["applied"] = ang
            v._tbox_rect = QRectF(c - QPointF(r0.width() / 2, r0.height() / 2),
                                 r0.size())
            # visual: rotate about center
            it.setTransform(QTransform().translate(c.x(), c.y()).rotate(
                ang).translate(-c.x(), -c.y()))
            return True
        # resize: compute new rect corner/edge from anchor
        left, top, right, bottom = r0.left(), r0.top(), r0.right(), r0.bottom()
        if "e" in mode:
            right = sp.x()
        if "w" in mode:
            left = sp.x()
        if "s" in mode:
            bottom = sp.y()
        if "n" in mode:
            top = sp.y()
        new_r = QRectF(QPointF(left, top), QPointF(right, bottom)).normalized()
        sx = new_r.width() / max(1e-6, r0.width())
        sy = new_r.height() / max(1e-6, r0.height())
        corner = mode in ("nw", "ne", "se", "sw")
        if corner and not shift:
            s = max(abs(sx), abs(sy))
            sx = s if abs(sx) > 1e-9 else s
            sy = s if abs(sy) > 1e-9 else s
            # re-derive rect with uniform scale about anchor
            w0, h0 = r0.width(), r0.height()
            new_w = w0 * s * (1 if new_r.width() >= 0 else -1)
            new_h = h0 * s * (1 if new_r.height() >= 0 else -1)
            if "w" in mode:
                left = anchor.x() - new_w
            if "n" in mode:
                top = anchor.y() - new_h
            if "e" in mode:
                right = anchor.x() + new_w
            if "s" in mode:
                bottom = anchor.y() + new_h
            new_r = QRectF(QPointF(left, top), QPointF(right, bottom)).normalized()
            sx = new_r.width() / max(1e-6, r0.width())
            sy = new_r.height() / max(1e-6, r0.height())
        # live visual: rebuild geometry from scaled copy of the original payload
        pl = deepcopy(pl0)
        scale_payload(pl, sx, sy, anchor.x(), anchor.y())
        it._payload = pl
        self._rebuild_item_geometry(it, pl)
        v._tbox_rect = it.sceneBoundingRect().adjusted(-1, -1, 1, 1)
        v._tbox.prepareGeometryChange()
        d["sx"], d["sy"] = sx, sy
        return True

    def _tbox_release(self, sp: QPointF) -> bool:
        v = self.view
        d = v._transform_drag
        if d is None:
            return False
        v._transform_drag = None
        it = d["item"]
        if d.get("mode") == "rot":
            ang = d.get("applied", 0.0)
            it.setTransform(QTransform())          # clear visual transform
            if abs(ang) > 0.05:
                pl = pl_of(it)
                c = d["rect0"].center()
                rotate_payload(pl, ang, c.x(), c.y())
                self._rebuild_item_geometry(it, pl)
        else:
            # payload already updated live in _tbox_move; just finalize box
            pass
        self._update_tbox()
        self.update_props_panel()
        return True

    def _rebuild_item_geometry(self, it, pl):
        """Refresh item geometry in-place from its (already edited) payload."""
        t = pl.get("type")
        if t == "vpath":
            it.setPath(_vpath_to_qpath(pl.get("nodes") or [],
                                       bool(pl.get("closed"))))
            st = pl.get("stroke") or {}
            it.setPen(self.view._pen(st.get("color", "#000"),
                                     float(st.get("width", 3)),
                                     int(st.get("alpha", 255))))
            it.setRotation(float(pl.get("rot", 0.0)))
        elif t in ("pen", "highlighter"):
            if pl.get("variable") and pl.get("widths"):
                it.setPath(_var_stroke_path(pl["points"], pl["widths"]))
            else:
                it.setPath(_smooth_stroke_path(pl["points"]))
            it.setPen(self.view._pen(pl.get("color", "#000"),
                                    float(pl.get("width", 3)),
                                    int(pl.get("alpha", 255))))
        elif t == "polygon":
            pts = pl.get("points", [])
            path = QPainterPath(QPointF(*pts[0])) if pts else QPainterPath()
            for p in pts[1:]:
                path.lineTo(QPointF(*p))
            it.setPath(path)
        elif t == "line":
            it.setLine(QLineF(QPointF(*pl["p1"]), QPointF(*pl["p2"])))
            it.setPen(self.view._pen(pl.get("color", "#000"), float(pl.get("width", 2))))
        elif t == "arrow":
            a, b = QPointF(*pl["p1"]), QPointF(*pl["p2"])
            it.setPath(self.view._arrow_path(a, b))
            pl["head"] = [[p.x(), p.y()] for p in self.view._arrow_head(a, b)]
            it.setPen(self.view._pen(pl.get("color", "#000"), float(pl.get("width", 2))))
        elif t in ("rect", "oval"):
            it.setRect(QRectF(QPointF(pl["x1"], pl["y1"]),
                              QPointF(pl["x2"], pl["y2"])))
            it.setPen(self.view._pen(pl.get("color", "#000"), float(pl.get("width", 2))))
            it.setRotation(float(pl.get("rot", 0.0)))
        elif t == "text":
            it.setPos(QPointF(*pl.get("pos", [0, 0])))
            f = QFont("Segoe UI", max(1, int(pl.get("size", 18))))
            it.setFont(f)
            it.setRotation(float(pl.get("rot", 0.0)))
        elif t in ("latex", "image"):
            it.setPos(QPointF(*pl.get("pos", [0, 0])))
            if t == "latex":
                try:
                    it.setPath(latex_to_qpath(pl.get("tex", ""),
                                               float(pl.get("size", 28))))
                except Exception:
                    pass
                it.setScale(float(pl.get("scale", 1.0)))
            it.setRotation(float(pl.get("rot", 0.0)))
        elif t == "compass":
            c, p2 = QPointF(*pl["center"]), QPointF(*pl["p2"])
            r = float(pl.get("radius", 10))
            path = QPainterPath()
            import math as _m
            a0 = _m.atan2(p2.y() - c.y(), p2.x() - c.x())
            path.arcMoveTo(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), 0)
            path.arcTo(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), 0, 360)
            it.setPath(path)
            it.setPen(self.view._pen(pl.get("color", "#000"), float(pl.get("width", 2))))
        if hasattr(it, "setRotation"):
            cur = it.rotation()
            want = float(pl.get("rot", 0.0))
            if abs(cur - want) > 1e-9 and t not in ("rect", "oval", "text",
                                                    "latex", "image"):
                it.setRotation(want)
        # gradient coords are relative to bbox: rebuild brush after transforms
        if pl.get("fill") and t in ("rect", "oval", "polygon", "vpath"):
            apply_fill_to_item(it, pl["fill"])

    def update_props_panel(self):
        self._props_loading = True
        items = list(self._iter_sel_payload_items())
        if not items:
            self.prop_info.setText("no selection")
            self.prop_color_btn.setEnabled(False)
            self.prop_width.setEnabled(False)
            self._props_loading = False
            return
        self.prop_color_btn.setEnabled(True)
        self.prop_width.setEnabled(True)
        pl = pl_of(items[0])
        is_text = pl.get("type") == "text"
        color = pl.get("color", "#000000")
        self.prop_color_btn.setStyleSheet(
            f"background:{color}; color:white; font-weight:bold;")
        value = int(pl.get("size", 18)) if is_text else int(pl.get("width", 2))
        self.prop_width.setValue(max(self.prop_width.minimum(),
                                     min(self.prop_width.maximum(), value)))
        self.prop_width_lbl.setText(
            f"{'Size' if is_text else 'W'} {value}")
        kind = pl.get("type", "?")
        self.prop_info.setText(
            f"{len(items)} selected — {kind}" + (" (group)" if any(
                isinstance(i, BoardGroup) for i in self.scene.selectedItems()) else ""))
        self._props_loading = False

    def edit_selection_fill(self):
        """Open gradient dialog; apply fill to selected fillable items."""
        items = [i for i in self._iter_sel_payload_items()
                 if pl_of(i) and pl_of(i).get("type")
                 in ("rect", "oval", "polygon", "vpath")]
        if not items:
            self.statusBar().showMessage(
                "Select a shape/path to fill (rect, ellipse, polygon, vpath)")
            return
        first = pl_of(items[0])
        dlg = GradientDialog(self, initial=first.get("fill"),
                             base_color=self.color)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        spec = dlg.result_spec()
        self.push_undo()
        for it in items:
            pl = pl_of(it)
            pl["fill"] = deepcopy(spec)
            apply_fill_to_item(it, spec)
            if pl.get("type") == "vpath":
                it.update()
        self.statusBar().showMessage(
            "Fill applied" + (" (gradient)" if isinstance(spec, dict) else ""))

    DASH_PATTERNS = {"solid": None, "dashed": [8, 6], "dotted": [2, 4]}

    def _stroke_store(self, pl):
        """vpath stores stroke params under 'stroke'; others at top level."""
        if pl.get("type") == "vpath":
            return pl.setdefault("stroke", {})
        return pl

    def apply_prop_dash(self, idx):
        if getattr(self, "_props_loading", False):
            return
        items = list(self._iter_sel_payload_items())
        if not items:
            return
        style = self.prop_dash.itemText(idx)
        self.push_undo()
        for it in items:
            pl = pl_of(it)
            if not pl:
                continue
            st = self._stroke_store(pl)
            st["dash"] = self.DASH_PATTERNS.get(style)
            self._refresh_item_pen(it, pl)
        self.statusBar().showMessage(f"Stroke: {style}")

    def apply_prop_join(self, idx):
        if getattr(self, "_props_loading", False):
            return
        items = list(self._iter_sel_payload_items())
        if not items:
            return
        style = self.prop_join.itemText(idx)
        jmap = {"round": Qt.PenJoinStyle.RoundJoin,
                "miter": Qt.PenJoinStyle.MiterJoin,
                "bevel": Qt.PenJoinStyle.BevelJoin}
        self.push_undo()
        for it in items:
            pl = pl_of(it)
            if not pl:
                continue
            st = self._stroke_store(pl)
            st["join"] = style
            self._refresh_item_pen(it, pl)
        self.statusBar().showMessage(f"Joins: {style}")

    def apply_prop_alpha(self, val):
        self.prop_alpha_lbl.setText(f"{val}%")
        if getattr(self, "_props_loading", False):
            return
        items = list(self._iter_sel_payload_items())
        if not items:
            return
        alpha = max(1, int(val * 255 / 100))
        self.push_undo()
        for it in items:
            pl = pl_of(it)
            if not pl:
                continue
            st = self._stroke_store(pl)
            st["alpha"] = alpha
            self._refresh_item_pen(it, pl)
        self.statusBar().showMessage(f"Opacity {val}%")

    def _refresh_item_pen(self, it, pl):
        """Rebuild the item pen honoring dash/join/alpha from its payload."""
        st = self._stroke_store(pl)
        color = st.get("color", pl.get("color", "#000000"))
        width = float(st.get("width", pl.get("width", 3)))
        alpha = int(st.get("alpha", 255))
        dash = st.get("dash")
        join_name = st.get("join", "round")
        join = {"round": Qt.PenJoinStyle.RoundJoin,
                "miter": Qt.PenJoinStyle.MiterJoin,
                "bevel": Qt.PenJoinStyle.BevelJoin}.get(join_name,
                                                        Qt.PenJoinStyle.RoundJoin)
        pen = QPen(_qcolor(color, alpha), width, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap, join)
        if dash:
            pen.setDashPattern(dash)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        it.setPen(pen)

    def pick_prop_color(self):
        c = QColorDialog.getColor(QColor(self.color), self, "Apply color to selection")
        if not c.isValid():
            return
        for it in list(self._iter_sel_payload_items()):
            self._restyle(it, color=c.name())
        self.update_props_panel()

    def apply_prop_width(self, v):
        self.prop_width_lbl.setText(str(v))
        if self._props_loading:
            return
        for it in list(self._iter_sel_payload_items()):
            self._restyle(it, width=float(v))
        self.update_props_panel()

    # ------------------------------------------------------------ clipboard
    CLIP_MIME = "application/x-interactive-whiteboard"

    @staticmethod
    def _svg_escape(t: str) -> str:
        return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _vpath_svg_d(self, pl: dict) -> str:
        """SVG path data for a vpath payload: M + C segments only."""
        nodes = pl.get("nodes") or []
        if not nodes:
            return ""
        closed = bool(pl.get("closed"))
        n = len(nodes)
        parts = [f'M {nodes[0]["p"][0]:.2f} {nodes[0]["p"][1]:.2f}']
        segs = range(n if closed else n - 1)
        for i in segs:
            p0, p1, p2, p3 = _vp_seg_bezier(nodes, i)
            parts.append(f'C {p1.x():.2f} {p1.y():.2f} {p2.x():.2f} {p2.y():.2f} '
                         f'{p3.x():.2f} {p3.y():.2f}')
        if closed:
            parts.append("Z")
        return " ".join(parts)

    def _svg_gradient_def(self, gid: str, fl: dict, r: QRectF) -> str:
        """<defs> gradient entry in userSpaceOnUse coords for rect r."""
        stops = "".join(
            f'<stop offset="{s[0]:.3f}" stop-color="{s[1]}"'
            + (f' stop-opacity="{s[2]/255:.2f}"' if len(s) > 2 and s[2] < 255
               else "") + "/>"
            for s in fl.get("stops", []))
        if fl.get("kind") == "radial":
            cc = fl.get("center", [0.5, 0.5])
            cx = r.left() + cc[0] * r.width()
            cy = r.top() + cc[1] * r.height()
            rad = fl.get("radius", 0.5) * max(r.width(), r.height())
            return (f'<radialGradient id="{gid}" gradientUnits="userSpaceOnUse" '
                    f'cx="{cx:.1f}" cy="{cy:.1f}" r="{rad:.1f}">{stops}'
                    f'</radialGradient>')
        ang = math.radians(fl.get("angle", 0.0))
        cx, cy = r.center().x(), r.center().y()
        L = max(1e-6, r.width() / 2.0)
        x1, y1 = cx - math.cos(ang) * L, cy - math.sin(ang) * L
        x2, y2 = cx + math.cos(ang) * L, cy + math.sin(ang) * L
        return (f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" '
                f'x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}">'
                f'{stops}</linearGradient>')

    def _svg_fill_attr(self, fl, r: QRectF, defs: list) -> str:
        """fill="..." attribute; gradients register into defs and return url()."""
        fl = _norm_fill(fl)
        if not fl:
            return 'fill="none"'
        if isinstance(fl, str):
            return f'fill="{fl}"'
        gid = f"g{len(defs)}"
        defs.append(self._svg_gradient_def(gid, fl, r))
        return f'fill="url(#{gid})"'

    def _selection_svg(self, items, rect: QRectF) -> str:
        """Compact SVG of the selection (Word 2016+ pastes it as vector)."""
        out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{rect.left():.1f} '
               f'{rect.top():.1f} {rect.width():.1f} {rect.height():.1f}" '
               f'width="{rect.width():.0f}" height="{rect.height():.0f}">']
        defs: list = []
        out.append("")                       # defs placeholder (index 1)
        for it in sorted(items, key=lambda i: i.zValue()):
            pl = pl_of(it)
            if not pl:
                continue
            t = pl.get("type")
            col = pl.get("color", "#000")
            w = max(0.5, float(pl.get("width", 2)))
            if t in ("pen", "highlighter"):
                pts = " ".join(f"{p[0]:.1f},{p[1]:.1f}" for p in pl.get("points", []))
                op = pl.get("alpha", 255)
                extra = f' opacity="{op / 255:.2f}"' if op < 255 else ""
                out.append(f'<polyline points="{pts}" fill="none" stroke="{col}" '
                           f'stroke-width="{w}" stroke-linecap="round" '
                           f'stroke-linejoin="round"{extra}/>')
            elif t == "line":
                a, b = pl["p1"], pl["p2"]
                out.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" '
                           f'y2="{b[1]:.1f}" stroke="{col}" stroke-width="{w}"/>')
            elif t == "arrow":
                a, b = pl["p1"], pl["p2"]
                head = pl.get("head") or []
                hp = " ".join(f"{p[0]:.1f},{p[1]:.1f}" for p in head)
                out.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" '
                           f'y2="{b[1]:.1f}" stroke="{col}" stroke-width="{w}"/>')
                if hp:
                    out.append(f'<polygon points="{hp}" fill="{col}"/>')
            elif t == "rect":
                x, y = min(pl["x1"], pl["x2"]), min(pl["y1"], pl["y2"])
                ww, hh = abs(pl["x2"] - pl["x1"]), abs(pl["y2"] - pl["y1"])
                fa = self._svg_fill_attr(pl.get("fill"),
                                         QRectF(x, y, ww, hh), defs)
                out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{ww:.1f}" '
                           f'height="{hh:.1f}" {fa} stroke="{col}" '
                           f'stroke-width="{w}"/>')
            elif t == "oval":
                cx = (pl["x1"] + pl["x2"]) / 2
                cy = (pl["y1"] + pl["y2"]) / 2
                rx, ry = abs(pl["x2"] - pl["x1"]) / 2, abs(pl["y2"] - pl["y1"]) / 2
                fa = self._svg_fill_attr(
                    pl.get("fill"), QRectF(cx - rx, cy - ry, 2 * rx, 2 * ry), defs)
                out.append(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" '
                           f'ry="{ry:.1f}" {fa} stroke="{col}" '
                           f'stroke-width="{w}"/>')
            elif t == "polygon":
                pts = " ".join(f"{p[0]:.1f},{p[1]:.1f}" for p in pl.get("points", []))
                pb = QRectF()
                for p in pl.get("points", []):
                    pb = pb.united(QRectF(p[0], p[1], 0.01, 0.01))
                fa = self._svg_fill_attr(pl.get("fill"), pb, defs)
                out.append(f'<polygon points="{pts}" {fa} '
                           f'stroke="{col}" stroke-width="{w}"/>')
            elif t == "vpath":
                d = self._vpath_svg_d(pl)
                st = pl.get("stroke") or {}
                scol = st.get("color", col)
                sw = float(st.get("width", w))
                op = st.get("alpha", 255)
                extra = f' opacity="{op / 255:.2f}"' if op < 255 else ""
                fl = pl.get("fill")
                if fl:
                    fb = QRectF()
                    for nd in pl.get("nodes", []):
                        fb = fb.united(QRectF(nd["p"][0], nd["p"][1], 0.01, 0.01))
                    fa = self._svg_fill_attr(fl, fb, defs)
                    if st.get("dash"):
                        dsh = " ".join(str(x) for x in st["dash"])
                        extra += f' stroke-dasharray="{dsh}"'
                else:
                    fa = 'fill="none"'
                out.append(f'<path d="{d}" {fa} stroke="{scol}" '
                           f'stroke-width="{sw:.2f}" stroke-linecap="round" '
                           f'stroke-linejoin="round"{extra}/>')
            elif t == "compass":
                cx, cy = pl.get("center", [0, 0])
                r = float(pl.get("radius", 10))
                p2 = pl.get("p2", [cx + r, cy])
                out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" '
                           f'fill="none" stroke="{col}" stroke-width="{w}"/>')
                out.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{p2[0]:.1f}" '
                           f'y2="{p2[1]:.1f}" stroke="{col}" stroke-width="{w}"/>')
            elif t == "text":
                x, y = pl.get("pos", [0, 0])
                size = float(pl.get("size", 18))
                lines = pl.get("text", "").split("\n")
                sp = "".join(
                    f'<tspan x="{x:.1f}" dy="{size * 1.2 if i else 0:.1f}">'
                    f'{self._svg_escape(ln)}</tspan>'
                    for i, ln in enumerate(lines))
                out.append(f'<text x="{x:.1f}" y="{y + size * 0.95:.1f}" '
                            f'font-family="Segoe UI" font-size="{size:.1f}" '
                            f'fill="{col}">{sp}</text>')
            elif t == "latex":
                d = qpath_to_svg_d(it.path())
                out.append(f'<path d="{d}" fill="{col}" fill-rule="evenodd"/>')
            elif t == "image":
                out.append(f'<image x="{pl.get("pos",[0,0])[0]:.1f}" '
                           f'y="{pl.get("pos",[0,0])[1]:.1f}" '
                           f'width="{it.pixmap().width() * it.scale():.0f}" '
                           f'height="{it.pixmap().height() * it.scale():.0f}" '
                           f'href="data:image/png;base64,{pl.get("png", "")}"/>')
        out.append("</svg>")
        if defs:
            out[1] = "<defs>" + "".join(defs) + "</defs>"
        return "\n".join(out)

    def _put_word_clipboard(self, payloads: list, img_transparent: QImage,
                            rect: QRectF, items=None):
        """Dual-render clipboard: PNG(alpha) + white DIB + SVG vector + payloads."""
        img_white = img_transparent.copy()
        img_white.fill(Qt.GlobalColor.white)
        p = QPainter(img_white)
        self.scene.render(p, QRectF(img_white.rect()), rect)
        p.end()

        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img_transparent.save(buf, "PNG")

        mime = QMimeData()
        mime.setData(self.CLIP_MIME,
                     bytes(json.dumps(payloads, ensure_ascii=False), "utf-8"))
        mime.setData("image/png", bytes(buf.data()))
        svg_src = items if items is not None else [
            i for i in self.scene.items() if pl_of(i) and i.isVisible()]
        mime.setData("image/svg+xml",
                     bytes(self._selection_svg(svg_src, rect), "utf-8"))
        mime.setImageData(img_white)          # DIB fallback for old Word
        QApplication.clipboard().setMimeData(mime)

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
        sync_scene_payloads(self)
        items = self._selected_items()
        if not items:
            self.statusBar().showMessage("Nothing selected")
            return
        payloads = []
        for it in items:
            if isinstance(it, BoardGroup):
                payloads.append({"type": "group",
                                 "items": [deepcopy(pl_of(c))
                                           for c in it.childItems() if pl_of(c)],
                                 "layer": int(pl_of(it).get("layer", 0))})
            else:
                payloads.append(deepcopy(pl_of(it)))
        rect = QRectF()
        for it in items:
            rect = rect.united(it.sceneBoundingRect())
        rect = rect.marginsAdded(QMarginsF(10, 10, 10, 10))
        img = self._render_board(rect, 192, True)
        self._put_word_clipboard(payloads, img, rect, items)
        if cut:
            self.push_undo()
            for it in items:
                self.scene.removeItem(it)
            self.statusBar().showMessage(
                f"Cut {len(items)} — paste in Word as PNG/SVG vector")
        else:
            self.statusBar().showMessage(
                f"Copied {len(items)} — Word paste: PNG or vector SVG")

    def _paste_payloads(self, payloads: list) -> int:
        if not payloads:
            return 0
        self.push_undo()
        n = 0
        for pl in payloads:
            if not isinstance(pl, dict):
                continue
            layer = pl.get("layer", self.current_layer)
            if not (0 <= int(layer) < len(self.layers)):
                layer = self.current_layer
            pl = deepcopy(pl)
            pl["layer"] = int(layer)
            it = payload_to_item(pl)
            if it is None:
                continue
            self._add_item(it)
            it.setSelected(True)
            n += 1
        self._apply_layer_visibility()
        return n

    def _html_rows(self, html: str) -> list:
        """Extract <tr><td>...</td></tr> cell texts from html (Excel/Word)."""
        import re
        rows = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html,
                             re.I | re.S | re.M):
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr,
                               re.I | re.S | re.M)
            if cells:
                rows.append([re.sub(r"<[^>]+>", "", c).replace("&nbsp;", " ")
                             .replace("&amp;", "&").replace("&lt;", "<")
                             .replace("&gt;", ">").strip()
                             for c in cells])
        return rows

    def _table_payloads(self, rows: list, origin: QPointF) -> list:
        """Excel/Word table -> grid lines + text cell payloads."""
        out = []
        if not rows:
            return out
        COL_W, ROW_H, TSZ = 110.0, 34.0, 14
        ncols = max(len(r) for r in rows)
        W, H = COL_W * ncols, ROW_H * len(rows)
        x0, y0 = origin.x() - W / 2, origin.y() - H / 2
        lines = {"vertical": [], "horizontal": []}
        for c in range(ncols + 1):
            x = x0 + c * COL_W
            lines["vertical"].append((x, y0, x, y0 + H))
        for r in range(len(rows) + 1):
            y = y0 + r * ROW_H
            lines["horizontal"].append((x0, y, x0 + W, y))
        for grp in lines.values():
            for x1, y1, x2, y2 in grp:
                out.append({"type": "line", "p1": [x1, y1], "p2": [x2, y2],
                            "color": "#607d8b", "width": 1.0,
                            "layer": self.current_layer})
        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                if not cell:
                    continue
                out.append({"type": "text",
                             "pos": [x0 + c * COL_W + 8, y0 + r * ROW_H + 7],
                             "text": cell, "size": TSZ, "color": "#111111",
                             "layer": self.current_layer})
        return out

    def paste_clipboard(self):
        cb = QApplication.clipboard()
        mime = cb.mimeData()
        if mime and mime.hasFormat(self.CLIP_MIME):
            try:
                payloads = json.loads(bytes(mime.data(self.CLIP_MIME)).decode("utf-8"))
            except Exception:
                payloads = []
            if payloads:
                n = self._paste_payloads(payloads)
                self.statusBar().showMessage(f"Pasted {n} object(s)")
                return
        # Office paste: HTML (Excel/Word tables) -> grid
        if mime and mime.hasFormat("text/html"):
            html = bytes(mime.data("text/html")).decode("utf-8", "ignore")
            rows = self._html_rows(html)
            if rows:
                center = self.view.mapToScene(
                    self.view.viewport().rect().center())
                pls = self._table_payloads(rows, center)
                if pls:
                    self.push_undo()
                    n = 0
                    for p in pls:
                        it = payload_to_item(p)
                        if it:
                            self._add_item(it)
                            n += 1
                    self.statusBar().showMessage(
                        f"Pasted table {len(rows)}×{max(len(r) for r in rows)}"
                        f" as {n} objects")
                    return
        # plain text -> text item
        if mime and mime.hasText():
            txt = mime.text().strip()
            if txt:
                self.push_undo()
                center = self.view.mapToScene(
                    self.view.viewport().rect().center())
                it = payload_to_item({"type": "text",
                                      "pos": [center.x(), center.y()],
                                      "text": txt[:2000], "size": 18,
                                      "color": self.color,
                                      "layer": self.current_layer})
                self._add_item(it)
                it.setSelected(True)
                self.statusBar().showMessage("Pasted text")
                return
        img = cb.image()
        if not img.isNull():
            buf = QBuffer()
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            img.save(buf, "PNG")
            self.push_undo()
            center = self.view.mapToScene(self.view.viewport().rect().center())
            scale = min(1.0, 700.0 / max(1, img.width()))
            it = payload_to_item({"type": "image",
                                  "png": base64.b64encode(buf.data()).decode(),
                                  "pos": [center.x() - img.width() * scale / 2,
                                          center.y() - img.height() * scale / 2],
                                  "scale": scale, "layer": self.current_layer})
            self._add_item(it)
            it.setSelected(True)
            self.statusBar().showMessage("Pasted image from clipboard")

    def duplicate_selection(self):
        items = self._selected_items()
        if not items:
            return
        self.push_undo()
        for it in items:
            pl = deepcopy(pl_of(it))
            translate_payload(pl, 20, 20)
            ni = payload_to_item(pl)
            if ni:
                self._add_item(ni)
                it.setSelected(False)
                ni.setSelected(True)

    # ------------------------------------------------------------ flatten export
    def _content_rect(self, selection_only: bool) -> QRectF:
        if selection_only:
            items = self._selected_items()
        else:
            items = [i for i in self.scene.items()
                     if pl_of(i) and not pl_of(i).get(INSTR_TYPE)]
        rect = QRectF()
        for it in items:
            rect = rect.united(it.sceneBoundingRect())
        if rect.isNull():
            return QRectF(0, 0, 800, 600)
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
        for it in self.scene.items():
            if (isinstance(it, InstrumentItem) or pl_of(it) is None) and it.isVisible():
                hidden.append((it, True))
                it.setVisible(False)
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
                pt = f.pointSizeF() if f.pointSizeF() > 0 else float(f.pixelSize())
                px = max(6, int(round(pt * scale * 96.0 / 72.0)))
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
            payloads = []
            if cb_sel.isChecked():
                payloads = [deepcopy(pl_of(it)) for it in self._selected_items()]
            self._put_word_clipboard(payloads, img, current_rect())
            self.statusBar().showMessage(
                f"Copied at {res_line.value()} ppi — Word paste: PNG/SVG")
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
            pl = pl_of(it)
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
            self._add_item(it)
            dlg.accept()
        ins.clicked.connect(do_insert)
        lst.itemDoubleClicked.connect(lambda _: do_insert())
        close.clicked.connect(dlg.reject)
        dlg.resize(520, 480)
        dlg.exec()

    # ------------------------------------------------------------ unlock page
    def unlock_to_vector(self):
        """Disassemble an imported PDF page into editable vector objects."""
        import pymupdf
        imgs = [it for it in self._selected_items()
                if pl_of(it).get("src_pdf")]
        if not imgs:
            QMessageBox.information(
                self, "Unlock",
                "Select an imported PDF page first (from 📄 In).")
            return
        self.push_undo()
        total = 0
        for it in imgs:
            pl = pl_of(it)
            doc = pymupdf.open(pl["src_pdf"])
            page = doc[int(pl.get("src_page", 0))]
            pw = max(1.0, float(pl.get("page_pt", [page.rect.width])[0]))
            pm = it.pixmap()
            k = pm.width() / pw
            ox, oy = it.pos().x(), it.pos().y()
            new_items = []

            def P(x, y):
                return [ox + x * k, oy + y * k]

            # --- text spans → real text objects
            for block in page.get_text("dict")["blocks"]:
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        txt = span["text"].strip()
                        if not txt:
                            continue
                        sx, sy = span["origin"]
                        col = "#%06x" % span["color"]
                        new_items.append(payload_to_item({
                            "type": "text",
                            "pos": P(sx, sy - span["size"]),
                            "text": txt,
                            "size": max(6.0, span["size"] * k),
                            "color": col, "layer": self.current_layer}))

            # --- vector drawings → strokes / polygons
            for d in page.get_drawings():
                pts = []
                for item in d["items"]:
                    op = item[0]
                    if op == "l":
                        a, b = item[1], item[2]
                        if not pts:
                            pts.append((a.x, a.y))
                        pts.append((b.x, b.y))
                    elif op == "c":
                        p0, p1, p2, p3 = item[1:5]
                        if not pts:
                            pts.append((p0.x, p0.y))
                        for i in range(1, 9):
                            t = i / 8.0
                            mt = 1 - t
                            x = (mt**3 * p0.x + 3 * mt * mt * t * p1.x +
                                 3 * mt * t * t * p2.x + t**3 * p3.x)
                            y = (mt**3 * p0.y + 3 * mt * mt * t * p1.y +
                                 3 * mt * t * t * p2.y + t**3 * p3.y)
                            pts.append((x, y))
                    elif op == "re":
                        r = item[1]
                        pts += [(r.x0, r.y0), (r.x1, r.y0),
                                (r.x1, r.y1), (r.x0, r.y1), (r.x0, r.y0)]
                if len(pts) < 2:
                    continue
                stroke = d.get("color")
                fill = d.get("fill")
                col = ("#%02x%02x%02x" % tuple(int(round(c * 255)) for c in stroke)) if stroke else "#333333"
                width = max(0.5, float(d.get("width") or 1.0))
                payload = {"type": "pen",
                           "points": [P(x, y) for x, y in pts],
                           "width": width * k if width * k > 0.8 else width,
                           "color": col, "alpha": 255,
                           "layer": self.current_layer}
                if fill:
                    payload["type"] = "polygon"
                    payload["fill"] = ("#%02x%02x%02x" % tuple(int(round(c * 255)) for c in fill))
                new_items.append(payload_to_item(payload))

            for ni in new_items:
                self._add_item(ni)
            self.scene.removeItem(it)
            total += len(new_items)
            doc.close()
        self._sync_page_store()
        self.statusBar().showMessage(
            f"Unlocked: {total} vector objects — page is now fully editable")

    # ------------------------------------------------------------ LaTeX equations
    def open_equation_dialog(self, sp: QPointF | None = None):
        self.statusBar().showMessage("Loading math engine… (first run builds font cache)")
        try:
            latex_to_qpath("x", 20)          # warm-up: import + font cache
        except Exception as exc:
            QMessageBox.critical(self, "LaTeX",
                                 f"Math engine failed to load:\n{exc}\n\n"
                                 "Reinstall with: pip install matplotlib")
            return
        self.statusBar().showMessage("Math engine ready")
        dlg = QDialog(self)
        dlg.setWindowTitle("Equation — LaTeX (mathtext)")
        v = QVBoxLayout(dlg)
        tip = QLabel(r"Examples:  \frac{a}{b}   \int_0^1 x^2 dx   \sqrt{b^2-4ac}   \sum_{i=1}^{n} i")
        tip.setStyleSheet("color:#607d8b; font-size:11px;")
        v.addWidget(tip)
        edit = QPlainTextEdit()
        edit.setPlaceholderText(r"\int_{-\infty}^{\infty} e^{-x^2} dx = \sqrt{\pi}")
        edit.setFixedHeight(70)
        v.addWidget(edit)
        preview = QLabel("  preview  ")
        preview.setMinimumHeight(90)
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setStyleSheet("background:#0f141b; border-radius:6px; color:white;")
        v.addWidget(preview)

        def render_preview():
            tex = edit.toPlainText().strip()
            if not tex:
                preview.setText("  (empty)  ")
                return
            try:
                path = latex_to_qpath(tex, 30)
                br = path.boundingRect()
                if br.isEmpty():
                    preview.setText("  (nothing to render)  ")
                    return
                img = QImage(int(br.width()) + 20, int(br.height()) + 20,
                             QImage.Format.Format_ARGB32_Premultiplied)
                img.fill(Qt.GlobalColor.transparent)
                p = QPainter(img)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.translate(10 - br.left(), 10 - br.top())
                p.setPen(QPen(Qt.PenStyle.NoPen))
                p.setBrush(QBrush(QColor(self.color)))
                p.drawPath(path)
                p.end()
                pm = QPixmap.fromImage(img)
                if pm.width() > 560:
                    pm = pm.scaledToWidth(560, Qt.TransformationMode.SmoothTransformation)
                preview.setPixmap(pm)
            except Exception as exc:
                preview.setText(f"error: {exc}")
        t = QTimer(dlg)
        t.setSingleShot(True)
        t.timeout.connect(render_preview)
        edit.textChanged.connect(lambda: t.start(350))
        render_preview()

        row = QHBoxLayout()
        b_ins = QPushButton("Insert as vector")
        b_ins.setObjectName("accent")
        cancel = QPushButton("Cancel")
        row.addStretch(1)
        row.addWidget(b_ins)
        row.addWidget(cancel)
        v.addLayout(row)

        def do_insert():
            tex = edit.toPlainText().strip()
            if not tex:
                return
            try:
                path = latex_to_qpath(tex, 30)
            except Exception as exc:
                QMessageBox.critical(dlg, "LaTeX", f"Cannot render:\n{exc}")
                return
            self.push_undo()
            target = sp if sp is not None else \
                self.view.mapToScene(self.view.viewport().rect().center())
            it = payload_to_item({"type": "latex", "tex": tex, "size": 30, "base": 30,
                                  "pos": [target.x(), target.y()],
                                  "color": self.color, "scale": 1.0,
                                  "layer": self.current_layer})
            self._add_item(it)
            it.setSelected(True)
            self.statusBar().showMessage("Equation inserted as pure vector")
            dlg.accept()
        b_ins.clicked.connect(do_insert)
        cancel.clicked.connect(dlg.reject)
        dlg.resize(640, 320)
        edit.setFocus()
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
            self._add_item(it)
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
                    self._add_item(it)
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
                self._add_item(it)
                y += (text.count("\n") + 2.2) * size
            key_txt = [f"{i}. {a}" for i, (_t, _q, a) in enumerate(qs, 1)]
            it = payload_to_item({"type": "text", "pos": [x, y + 40],
                                  "text": f"—— {legacy.WORKSHEET_LANGS[meta['lang']]['answer_key']} ——\n" + "\n".join(key_txt),
                                  "size": 13, "color": self.color,
                                  "layer": self.current_layer})
            self._add_item(it)
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
            ("Text", "", "text"), ("LaTeX", "ƒx", "latex"),
            ("Laser", "", "laser"),
            ("V-Pen", "✎", "vpen"), ("Nodes", "⦿", "nodeedit"),
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

        # ---- properties panel ----
        plabel = QLabel("PROPERTIES")
        plabel.setStyleSheet("color:#78909c; letter-spacing:2px; font-size:11px;")
        v.addWidget(plabel)
        prow = QHBoxLayout()
        self.prop_color_btn = QPushButton("■")
        self.prop_color_btn.setFixedWidth(34)
        self.prop_color_btn.clicked.connect(self.pick_prop_color)
        prow.addWidget(self.prop_color_btn)
        self.prop_width = QSlider(Qt.Orientation.Horizontal)
        self.prop_width.setRange(1, 40)
        self.prop_width.setValue(3)
        self.prop_width.valueChanged.connect(self.apply_prop_width)
        prow.addWidget(self.prop_width, 1)
        self.prop_width_lbl = QLabel("3")
        prow.addWidget(self.prop_width_lbl)
        self.prop_fill_btn = QPushButton("Fill")
        self.prop_fill_btn.clicked.connect(self.edit_selection_fill)
        prow.addWidget(self.prop_fill_btn)
        v.addLayout(prow)

        # stroke style row (dash + join)
        strow = QHBoxLayout()
        self.prop_dash = QComboBox()
        self.prop_dash.addItems(["solid", "dashed", "dotted"])
        self.prop_dash.setToolTip("Stroke dash style")
        self.prop_dash.currentIndexChanged.connect(self.apply_prop_dash)
        strow.addWidget(self.prop_dash, 1)
        self.prop_join = QComboBox()
        self.prop_join.addItems(["round", "miter", "bevel"])
        self.prop_join.setToolTip("Stroke corner join")
        self.prop_join.currentIndexChanged.connect(self.apply_prop_join)
        strow.addWidget(self.prop_join, 1)
        v.addLayout(strow)

        # opacity row
        oprow = QHBoxLayout()
        oprow.addWidget(QLabel("Opacity"))
        self.prop_alpha = QSlider(Qt.Orientation.Horizontal)
        self.prop_alpha.setRange(0, 100)
        self.prop_alpha.setValue(100)
        self.prop_alpha.valueChanged.connect(self.apply_prop_alpha)
        oprow.addWidget(self.prop_alpha, 1)
        self.prop_alpha_lbl = QLabel("100%")
        oprow.addWidget(self.prop_alpha_lbl)
        v.addLayout(oprow)
        self.prop_info = QLabel("no selection")
        self.prop_info.setStyleSheet("color:#607d8b; font-size:11px;")
        v.addWidget(self.prop_info)
        self._props_loading = False

        # ---- swatches ----
        swlbl = QLabel("SWATCHES")
        swlbl.setStyleSheet("color:#78909c; letter-spacing:2px; font-size:11px;")
        v.addWidget(swlbl)
        sw_grid = QGridLayout()
        sw_grid.setSpacing(4)
        all_sw = list(dict.fromkeys(self.SWATCHES + self._saved_swatches()))
        for i, col in enumerate(all_sw[:14]):
            b = QPushButton()
            b.setFixedSize(22, 22)
            b.setToolTip(col)
            b.setStyleSheet(f"background:{col}; border:1px solid #555;")
            b.clicked.connect(lambda _=False, c=col: self._apply_swatch(c))
            sw_grid.addWidget(b, i // 7, i % 7)
        v.addLayout(sw_grid)

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
        if key not in ("vpen", "nodeedit"):
            self.view._vpen_finish(commit=False)
            self.view._nodeedit_exit()
        self._update_tbox()
        self.statusBar().showMessage(f"Tool: {key}")

    def keyPressEvent(self, e):
        if self.tool == "vpen":
            if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.view._vpen_finish(commit=True)
                return
            if e.key() == Qt.Key.Key_Escape:
                self.view._vpen_finish(commit=False)
                return
        if self.tool == "nodeedit":
            if e.key() == Qt.Key.Key_Escape:
                self.view._nodeedit_exit()
                return
            if e.key() == Qt.Key.Key_Delete:
                self.view._nodeedit_delete_selected()
                return
            if e.key() == Qt.Key.Key_S:
                self.view._nodeedit_toggle_type("smooth")
                return
            if e.key() == Qt.Key.Key_C:
                self.view._nodeedit_toggle_type("corner")
                return
        super().keyPressEvent(e)

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
            self._remember_swatch(self.color)

    def pick_screen_color(self):
        """Eyedropper: magnifier-free screen pick (click through dialogs)."""
        self.statusBar().showMessage("Eyedropper: click any pixel on screen…")
        dlg = QColorDialog(QColor(self.color), self)
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        dlg.setWindowTitle("Pick color (grab screen pixel)")
        # native dialog on Windows offers its own screen picker
        dlg.setOptions(QColorDialog.ColorDialogOption.DontUseNativeDialog
                       if sys.platform == "darwin" else
                       QColorDialog.ColorDialogOption(0))
        if dlg.exec() == QColorDialog.DialogCode.Accepted:
            c = dlg.currentColor()
        else:
            c = QColor()
        if c.isValid():
            self.color = c.name()
            self.color_btn.setStyleSheet(
                f"background:{self.color}; color:white; font-weight:bold;")
            self._remember_swatch(self.color)
            self.statusBar().showMessage(f"Color: {self.color}")
        else:
            self.statusBar().showMessage("Pick cancelled")

    SWATCHES = ["#111111", "#e53935", "#fb8c00", "#fdd835", "#43a047",
                "#00acc1", "#1e88e5", "#8e24aa", "#d81b60", "#ffffff"]

    def _remember_swatch(self, hexcol: str):
        """Add color to saved swatches (max 10, most-recent-first)."""
        try:
            sw = json.loads(Path(self._swatch_file()).read_text(encoding="utf-8"))
        except Exception:
            sw = []
        sw = [c for c in sw if c != hexcol]
        sw.insert(0, hexcol)
        sw = sw[:10]
        try:
            Path(self._swatch_file()).write_text(
                json.dumps(sw), encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def _swatch_file():
        return Path.home() / ".whiteboard_swatches.json"

    def _saved_swatches(self) -> list:
        try:
            sw = json.loads(Path(self._swatch_file()).read_text(encoding="utf-8"))
            return sw if isinstance(sw, list) else []
        except Exception:
            return []

    def _apply_swatch(self, hexcol: str):
        self.color = hexcol
        self.color_btn.setStyleSheet(
            f"background:{hexcol}; color:white; font-weight:bold;")

    def edit_text_item(self, it):
        """Enable in-place editing for a text item; payload syncs on focus-out."""
        pl = pl_of(it)
        if not pl:
            return
        self.push_undo()
        it.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextEditorInteraction)
        it.setFocus()
        # one-shot: when the user clicks elsewhere, commit payload text
        def _commit():
            doc = it.document()
            pl["text"] = doc.toPlainText()
            it.setTextInteractionFlags(
                Qt.TextInteractionFlag.NoTextInteraction)
            if it.scene() is not None:
                it.clearFocus()
            self.statusBar().showMessage("Text updated")
        it._text_commit = _commit
        # install focus-out hook via scene focus processing
        if not hasattr(self, "_text_edit_watch"):
            self._text_edit_watch = []
        self._text_edit_watch.append((it, _commit))

    def _commit_text_edits(self):
        """Flush any in-place text edits (called on view focus-out)."""
        if not getattr(self, "_text_edit_watch", None):
            return
        pending = self._text_edit_watch
        self._text_edit_watch = []
        for it, fn in pending:
            try:
                if it is not None and it.scene() is not None:
                    fn()
            except RuntimeError:
                pass                                # item already gone

    def add_text_at(self, sp: QPointF):
        text, ok = QInputDialog.getMultiLineText(self, "Text", "Enter text:")
        if not ok or not text.strip():
            return
        self.push_undo()
        it = payload_to_item({"type": "text", "pos": [sp.x(), sp.y()], "text": text,
                              "size": 20, "color": self.color,
                              "layer": self.current_layer})
        self._add_item(it)
        it.setSelected(True)

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
        # strong refs first (Shiboken wrappers keep _payload attrs alive),
        # then any scene items still holding payloads
        for it in self._item_refs:
            try:
                sync_item_payload_pos(it)
            except RuntimeError:
                pass
        grouped = set()
        for it in self._item_refs:
            if isinstance(it, BoardGroup):
                for c in it.childItems():
                    grouped.add(id(c))
        seen = set()
        items = []
        live_refs = []
        for it in list(self._item_refs):
            try:
                if it.scene() is self.scene:
                    live_refs.append(it)
            except RuntimeError:
                continue                     # dead wrapper
        self._item_refs = live_refs
        for it in live_refs + list(self.scene.items()):
            key = shiboken_key(it)
            if key in seen:
                continue
            seen.add(key)
            items.append(it)
        items.sort(key=lambda i: i.zValue())
        out = []
        for it in items:
            pl = pl_of(it)
            if not pl or pl.get(INSTR_TYPE):
                continue
            if isinstance(it, BoardGroup):
                kids = [deepcopy(pl_of(c)) for c in it.childItems() if pl_of(c)]
                out.append({"type": "group", "items": kids,
                            "layer": int(pl.get("layer", 0))})
                continue
            if id(it) in grouped:
                continue
            out.append(deepcopy(pl))
        return out

    def ink_to_path(self):
        """Convert selected freehand strokes into editable vpath nodes."""
        items = [i for i in self._selected_items()
                 if pl_of(i) and pl_of(i).get("type") in ("pen", "highlighter")]
        if not items:
            self.statusBar().showMessage(
                "Select one or more pen strokes (Ink→Path)")
            return
        self.push_undo()
        n_total = 0
        for it in items:
            pl = pl_of(it)
            pts = pl.get("points") or []
            if len(pts) < 2:
                continue
            simplified = _rdp_simplify(pts, 1.4) if len(pts) > 3 else pts
            nodes = _ink_to_vpath(simplified)
            st = {"color": pl.get("color", "#000000"),
                  "width": float(pl.get("width", 3)),
                  "alpha": int(pl.get("alpha", 255))}
            new_pl = {"type": "vpath", "closed": False, "nodes": nodes,
                      "stroke": st, "fill": None,
                      "rot": 0.0, "layer": int(pl.get("layer", 0))}
            ni = payload_to_item(new_pl)
            if ni is None:
                continue
            self._add_item(ni)
            ni.setSelected(True)
            it.setSelected(False)
            self.scene.removeItem(it)
            if it in self._item_refs:
                self._item_refs.remove(it)
            n_total += len(nodes)
        if n_total:
            self.statusBar().showMessage(
                f"Converted to editable path ({n_total} nodes) — use Nodes tool")

    def align_selection(self, mode: str):
        """Align/distribute selected payload items by bounding boxes."""
        items = [i for i in self._iter_sel_payload_items()
                 if pl_of(i) and not pl_of(i).get(INSTR_TYPE)]
        need = 3 if mode in ("hdist", "vdist") else 2
        if len(items) < need:
            self.statusBar().showMessage(
                f"Select {need}+ objects to {mode}")
            return
        rects = {id(i): i.sceneBoundingRect() for i in items}
        allr = QRectF()
        for r in rects.values():
            allr = allr.united(r)
        self.push_undo()
        moved = 0
        if mode == "hdist":
            xs = sorted(items, key=lambda i: rects[id(i)].left())
            total = allr.width() - sum(rects[id(i)].width() for i in items)
            gaps = total / (len(items) - 1) if len(items) > 1 else 0
            cur = allr.left()
            for it in xs:
                dx = cur - rects[id(it)].left()
                if abs(dx) > 1e-9:
                    it.moveBy(dx, 0)
                    sync_item_payload_pos(it)
                    moved += 1
                cur += rects[id(it)].width() + gaps
        elif mode == "vdist":
            ys = sorted(items, key=lambda i: rects[id(i)].top())
            total = allr.height() - sum(rects[id(i)].height() for i in items)
            gaps = total / (len(items) - 1) if len(items) > 1 else 0
            cur = allr.top()
            for it in ys:
                dy = cur - rects[id(it)].top()
                if abs(dy) > 1e-9:
                    it.moveBy(0, dy)
                    sync_item_payload_pos(it)
                    moved += 1
                cur += rects[id(it)].height() + gaps
        else:
            targets = {"left": lambda r: (allr.left() - r.left(), 0),
                       "right": lambda r: (allr.right() - r.right(), 0),
                       "hcenter": lambda r: (allr.center().x() - r.center().x(), 0),
                       "top": lambda r: (0, allr.top() - r.top()),
                       "bottom": lambda r: (0, allr.bottom() - r.bottom()),
                       "vcenter": lambda r: (0, allr.center().y() - r.center().y())}
            fn = targets.get(mode)
            if fn is None:
                self.pop_undo()
                return
            for it in items:
                dx, dy = fn(rects[id(it)])
                if abs(dx) > 1e-9 or abs(dy) > 1e-9:
                    it.moveBy(dx, dy)
                    sync_item_payload_pos(it)     # bake move into payload
                    moved += 1
        self.statusBar().showMessage(f"{mode}: moved {moved}/{len(items)}")

    def boolean_selection(self, op: str):
        """Boolean combine exactly two selected shape payloads."""
        items = [i for i in self._iter_sel_payload_items()
                 if pl_of(i) and pl_of(i).get("type")
                 in ("rect", "oval", "polygon", "vpath")]
        if len(items) != 2:
            self.statusBar().showMessage("Select exactly 2 shapes for boolean")
            return
        # order = selection order (topmost last => A under B)
        ordered = sorted(items, key=lambda i: i.zValue())
        pl_a = pl_of(ordered[0])
        pl_b = pl_of(ordered[1])
        res = boolean_payloads(pl_a, pl_b, op)
        if res is None:
            self.statusBar().showMessage(f"{op}: empty result — nothing done")
            return
        self.push_undo()
        ni = payload_to_item(res)
        if ni is None:
            self.pop_undo()
            return
        self._add_item(ni)
        ni.setSelected(True)
        for it in items:
            self.scene.removeItem(it)
            if it in self._item_refs:
                self._item_refs.remove(it)
        self.statusBar().showMessage(f"Boolean {op}: path with "
                                     f"{len(res['nodes'])} nodes")

    def group_selection(self):
        items = self._selected_items()
        items = [i for i in items if not isinstance(i, BoardGroup)]
        if len(items) < 2:
            self.statusBar().showMessage("Select 2+ objects to group")
            return
        self.push_undo()
        grp = BoardGroup()
        self._add_item(grp)
        for it in items:
            it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            grp.addToGroup(it)
        grp.setSelected(True)
        self.statusBar().showMessage(f"Grouped {len(items)} objects (Ctrl+Shift+G to ungroup)")

    def ungroup_selection(self):
        groups = [i for i in self.scene.selectedItems()
                  if isinstance(i, BoardGroup)]
        if not groups:
            self.statusBar().showMessage("Select a group to ungroup")
            return
        self.push_undo()
        n = 0
        for grp in groups:
            kids = list(grp.childItems())
            for c in kids:
                grp.removeFromGroup(c)
                c.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                c.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
                c.setSelected(True)
                n += 1
            self.scene.destroyItemGroup(grp)
        self.statusBar().showMessage(f"Ungrouped into {n} objects")

    def push_undo(self):
        self.undo_stack.append(deepcopy(self._payloads()))
        if len(self.undo_stack) > 60:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def pop_undo(self):
        if self.undo_stack:
            self.undo_stack.pop()

    def _restore(self, payloads):
        for it in list(self.scene.items()):
            if isinstance(it, InstrumentItem) or it.parentItem() is not None:
                continue
            self.scene.removeItem(it)
        for pl in payloads:
            it = payload_to_item(pl)
            if it:
                self._add_item(it)
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
        self._sync_page_store()
        path = self.current_file or "board.wbd"
        path, _f = QFileDialog.getSaveFileName(self, "Save document", path,
                                               "Whiteboard document (*.wbd)")
        if not path:
            return
        data = {"app": APP_ID, "version": DOC_VERSION,
                "theme": "dark" if self.dark else "light",
                "fg_color": self.color, "current_page": self.page_idx,
                "layers": deepcopy(self.layers),
                "current_layer": self.current_layer,
                "pages": [{"bg_kind": "dots", "bg_image": None, "objects": pg}
                          for pg in self.pages]}
        Path(path).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.current_file = path
        self.statusBar().showMessage(f"Saved: {path} ({len(self.pages)} pages)")

    def open_doc(self):
        path, _f = QFileDialog.getOpenFileName(self, "Open document", "",
                                               "Whiteboard document (*.wbd)")
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            raw_layers = data.get("layers")
            if isinstance(raw_layers, list) and raw_layers:
                self.layers = [{"name": str(l.get("name", f"Layer {i + 1}")),
                                "visible": bool(l.get("visible", True))}
                               for i, l in enumerate(raw_layers) if isinstance(l, dict)]
            self._refresh_layer_combo()
            pages = data.get("pages") or [{}]
            self.pages = [list(pg.get("objects", [])) for pg in pages] or [[]]
            self.page_idx = max(0, min(int(data.get("current_page", 0)),
                                       len(self.pages) - 1))
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.current_file = path
            self._restore(self.pages[self.page_idx])
            self.page_label.setText(f"Page {self.page_idx + 1}/{len(self.pages)}")
            self.statusBar().showMessage(
                f"Opened: {path} ({len(self.pages)} pages)")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Could not open:\n{exc}")

    def export_png(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export PNG", "board.png", "PNG (*.png)")
        if not path:
            return
        r = self.scene.itemsBoundingRect().marginsAdded(QMarginsF(40, 40, 40, 40))
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




