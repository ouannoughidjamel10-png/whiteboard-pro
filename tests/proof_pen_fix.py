# -*- coding: utf-8 -*-
"""Before/after proof of the in-handle sign fix.

Builds ONE circle out of four smooth Bezier nodes (the standard kappa trick)
and renders it twice:

  BEFORE - an inline copy of the old renderer, which computed c2 = anchor - in
  AFTER  - the real _vpath_to_qpath from whiteboard_qt

Under the correct convention a circle comes out a circle. Under the old one
every smooth node collapses into a 180-degree cusp, so the same four nodes
draw a four-pointed star. The radial error is measured, not eyeballed.
"""
import math
import os
import sys

# NOTE: run this on the REAL platform (QT_QPA_PLATFORM=windows). Under
# "offscreen" the font database comes up empty and every glyph is a tofu box.
os.environ.setdefault("QT_QPA_PLATFORM", "windows")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication

import whiteboard_qt as wb

app = QApplication([])

# The offscreen platform does not pick up a usable default font, so every
# glyph renders as a tofu box. Pin a real Windows font explicitly.
BASE_FONT = "Segoe UI"

R = 150.0
K = 0.5522847498307936 * R          # circle-from-cubics constant
NODES = [
    {"p": [0.0, -R], "out": [K, 0.0], "in": [-K, 0.0], "t": "smooth"},
    {"p": [R, 0.0], "out": [0.0, K], "in": [0.0, -K], "t": "smooth"},
    {"p": [0.0, R], "out": [-K, 0.0], "in": [K, 0.0], "t": "smooth"},
    {"p": [-R, 0.0], "out": [0.0, -K], "in": [0.0, K], "t": "smooth"},
]


def old_broken_path(nodes, closed):
    """Verbatim copy of the pre-fix renderer (c2 = anchor - in)."""
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


before = old_broken_path(NODES, True)
after = wb._vpath_to_qpath(NODES, True)


def radial_error(path):
    """Max |distance(centre) - R| over a dense sample. A circle must give ~0."""
    poly = path.toSubpathPolygons()[0]
    worst = 0.0
    for pt in poly:
        worst = max(worst, abs(math.hypot(pt.x(), pt.y()) - R))
    return worst, len(poly)


eb, nb = radial_error(before)
ea, na = radial_error(after)
print(f"target: a circle of radius {R:.0f}")
print(f"  BEFORE (anchor - in): max radial error = {eb:8.2f}   ({nb} samples)")
print(f"  AFTER  (anchor + in): max radial error = {ea:8.2f}   ({na} samples)")
print()
print("A four-node smooth path must draw a circle. Any error above ~1 unit")
print("means the smooth nodes are cusps and the curve loops back on itself.")

# ---------------------------------------------------------------- render
W, H = 720, 460
img_scale = 1.0


def draw(px, path, title, accent, err):
    px.save()
    px.translate(180, 250)
    px.setPen(QPen(QColor("#cfd8dc"), 1))
    px.setBrush(Qt.BrushStyle.NoBrush)
    px.drawEllipse(QPointF(0, 0), R, R)          # the ideal circle
    px.setPen(QPen(QColor(accent), 3.2))
    px.setBrush(Qt.BrushStyle.NoBrush)
    px.drawPath(path)
    px.setPen(QPen(QColor("#90a4ae"), 1))
    for nd in NODES:                              # the anchors themselves
        px.setBrush(QColor("#ffffff"))
        px.drawEllipse(QPointF(*nd["p"]), 4, 4)
    px.restore()
    px.setPen(QColor("#263238"))
    f = QFont(BASE_FONT, 13)
    f.setBold(True)
    px.setFont(f)
    px.drawText(QRectF(0, 12, 720, 30), Qt.AlignmentFlag.AlignHCenter, title)
    f.setBold(False)
    f.setPointSize(10)
    px.setFont(f)
    px.setPen(QColor("#546e7a"))
    px.drawText(QRectF(0, 36, 720, 24), Qt.AlignmentFlag.AlignHCenter,
                f"max radial error = {err:.2f} px")


pix = __import__("PySide6.QtGui", fromlist=["QImage"]).QImage(
    W * 2, H, __import__("PySide6.QtGui", fromlist=["QImage"]).QImage.Format.Format_RGB32)
pix.fill(QColor("#fafafa"))
px = QPainter(pix)
draw(px, before, "قبل الإصلاح  —  BEFORE", "#d32f2f", eb)
px.translate(W, 0)
draw(px, after, "بعد الإصلاح  —  AFTER", "#2e7d32", ea)
px.end()

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "pen_fix_before_after.png")
pix.save(out)
print()
print("saved", out, pix.width(), "x", pix.height())
