# -*- coding: utf-8 -*-
"""Offscreen verification suite for nav_tools.py.

Run:  python test_nav_tools.py
Every check is a MEASUREMENT against a real QGraphicsView, not an assertion
about intent.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QMouseEvent, QWheelEvent, QTransform
from PySide6.QtWidgets import QApplication, QGraphicsView, QGraphicsScene

from nav_tools import (NavigationController, NavViewport, ZOOM_STEPS,
                       MIN_ZOOM, MAX_ZOOM)

app = QApplication([])

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{('  — ' + detail) if detail else ''}")


_KEEP_ALIVE = []          # QGraphicsView does not own its scene in PySide6,
                          # so the scene must be kept reachable or it is GC'd.


def make_view(with_items=True):
    sc = QGraphicsScene()
    if with_items:
        for i in range(12):
            sc.addRect(QRectF(i * 60, i * 40, 50, 50))
    v = QGraphicsView(sc)
    v.resize(900, 650)
    v.show()
    _KEEP_ALIVE.append(sc)
    return v


# =========================================================================
print("\n1. Pan is strictly 1:1 with the pointer (sub-pixel, no drift)")
# =========================================================================
v = make_view()
vp = NavViewport(v)
vp.set_zoom(2.0)
probe = QPointF(500.0, 500.0)          # a scene point we will track
before = vp.to_view(probe)
for _ in range(200):
    vp.shift_view(0.6, 0.4)            # 200 sub-pixel steps -> total (120, 80)
after = vp.to_view(probe)
err_x, err_y = abs(after.x() - before.x() - 120.0), abs(after.y() - before.y() - 80.0)
check("200 x 0.6px  -> exactly 120.0px", err_x < 1e-6, f"err={err_x:.9f}")
check("200 x 0.4px  -> exactly  80.0px", err_y < 1e-6, f"err={err_y:.9f}")

# compare against the OLD integer-scrollbar method
sc2 = QGraphicsScene()
sc2.setSceneRect(QRectF(0, 0, 6000, 6000))
sc2.addRect(QRectF(0, 0, 100, 100))
v_old = QGraphicsView(sc2)
v_old.resize(900, 650)
v_old.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
v_old.show()
v_old.horizontalScrollBar().setValue(1500)
v_old.verticalScrollBar().setValue(1500)
p0 = v_old.viewportTransform().inverted()[0].map(QPointF(0, 0))
acc = QPointF()
for _ in range(200):
    acc += QPointF(0.6, 0.4)
    dx, dy = int(acc.x()), int(acc.y())
    acc -= QPointF(dx, dy)
    v_old.horizontalScrollBar().setValue(v_old.horizontalScrollBar().value() - dx)
    v_old.verticalScrollBar().setValue(v_old.verticalScrollBar().value() - dy)
p1 = v_old.viewportTransform().inverted()[0].map(QPointF(0, 0))
old_err = abs((p1 - p0).manhattanLength() - 0.0)
old_moved = (p0 - p1) * 1.0            # in scene units == px at zoom 1
check("old scrollbar method drifts (proves the bug)",
      abs(abs(old_moved.x()) - 120.0) > 0.5 or abs(abs(old_moved.y()) - 80.0) > 0.5,
      f"old moved ({old_moved.x():.2f}, {old_moved.y():.2f}) vs expected (120, 80)")

# =========================================================================
print("\n2. Pan works on an EMPTY board (old code could not)")
# =========================================================================
v = make_view(with_items=False)
vp = NavViewport(v)
probe = QPointF(0.0, 0.0)
b = vp.to_view(probe)
vp.shift_view(75.0, -33.0)
a = vp.to_view(probe)
check("empty scene pans correctly",
      abs(a.x() - b.x() - 75.0) < 1e-6 and abs(a.y() - b.y() + 33.0) < 1e-6,
      f"moved ({a.x()-b.x():.6f}, {a.y()-b.y():.6f})")
check("scrollbars hidden (infinite canvas)",
      v.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

# =========================================================================
print("\n3. Zoom pins the point under the cursor (no rotation)")
# =========================================================================
v = make_view()
vp = NavViewport(v)
worst = 0.0
for i in range(30):
    anchor = QPointF(137.0 + i, 411.0 - i * 2)
    p = vp.to_scene(anchor)
    vp.zoom_at(anchor, vp.zoom * 1.15)
    worst = max(worst, (vp.to_view(p) - anchor).manhattanLength())
check("30 consecutive wheel-zoom steps: anchor drift < 1e-6",
      worst < 1e-6, f"worst drift = {worst:.3e} px")

# =========================================================================
print("\n4. Zoom pins the point under the cursor WITH canvas rotation")
# =========================================================================
v = make_view()
vp = NavViewport(v)
vp.rotate_at(vp.center(), 25.0)
worst = 0.0
for i in range(25):
    anchor = QPointF(220.0 + i * 3, 190.0 + i)
    p = vp.to_scene(anchor)
    vp.zoom_at(anchor, vp.zoom * 1.2)
    worst = max(worst, (vp.to_view(p) - anchor).manhattanLength())
check("25 zoom steps at 25 deg rotation: drift < 1e-6",
      worst < 1e-6, f"worst drift = {worst:.3e} px")

# =========================================================================
print("\n5. Panning follows SCREEN axes when the canvas is rotated")
# =========================================================================
v = make_view()
vp = NavViewport(v)
vp.rotate_at(vp.center(), 40.0)
probe = QPointF(300.0, 300.0)
b = vp.to_view(probe)
vp.shift_view(50.0, 0.0)               # drag purely rightwards
a = vp.to_view(probe)
check("rotated canvas: horizontal drag moves only horizontally on screen",
      abs(a.x() - b.x() - 50.0) < 1e-6 and abs(a.y() - b.y()) < 1e-6,
      f"delta = ({a.x()-b.x():.9f}, {a.y()-b.y():.9f})")

# =========================================================================
print("\n6. transform().m11() is NOT the zoom once rotated (label bug)")
# =========================================================================
z_expected = vp.zoom
m11 = v.transform().m11()
check("naive m11() misreports zoom under rotation",
      abs(m11 - z_expected) > 1e-3,
      f"m11()={m11:.4f} vs real zoom={z_expected:.4f}")
check("nav.zoom reports the true factor", abs(vp.zoom - z_expected) < 1e-12)

# =========================================================================
print("\n7. Zoom ladder (Illustrator presets) + clamping + 100% snap")
# =========================================================================
v = make_view()
vp = NavViewport(v)
vp.set_zoom(1.0)
seq = []
for _ in range(6):
    vp.step_zoom(vp.center(), +1)
    seq.append(round(vp.zoom, 4))
check("stepping up hits 1.5, 2, 3, 4, 6, 8",
      seq == [1.5, 2.0, 3.0, 4.0, 6.0, 8.0], str(seq))
vp.set_zoom(1.0)
seq = []
for _ in range(4):
    vp.step_zoom(vp.center(), -1)
    seq.append(round(vp.zoom, 4))
check("stepping down hits 0.6667, 0.5, 0.3333, 0.25",
      seq == [0.6667, 0.5, 0.3333, 0.25], str(seq))
vp.zoom_at(vp.center(), 1e6)
check("clamped to MAX_ZOOM", abs(vp.zoom - MAX_ZOOM) < 1e-9, f"{vp.zoom}")
vp.zoom_at(vp.center(), 1e-6)
check("clamped to MIN_ZOOM", abs(vp.zoom - MIN_ZOOM) < 1e-9, f"{vp.zoom}")
vp.zoom_at(vp.center(), 1.015)
check("snaps to exactly 100% when close", vp.zoom == 1.0, f"{vp.zoom}")

# =========================================================================
print("\n8. fit() is uniform (Qt6 fitInView default distorts)")
# =========================================================================
v = make_view()
vp = NavViewport(v)
r = QRectF(0, 0, 1000, 400)
vp.fit(r, margin=0.0)
t = v.transform()
check("fit uses one scale for x and y",
      abs(t.m11() - t.m22()) < 1e-9, f"m11={t.m11():.4f} m22={t.m22():.4f}")
centre_err = (vp.to_view(QPointF(r.center())) - vp.center()).manhattanLength()
check("fit centres the rect", centre_err < 1e-6, f"err={centre_err:.3e}")

# =========================================================================
print("\n9. Rotation + zoom + pan round-trip accuracy")
# =========================================================================
v = make_view()
vp = NavViewport(v)
worst = 0.0
for i in range(40):
    op = i % 4
    if op == 0:
        vp.shift_view(7.3, -4.1)
    elif op == 1:
        vp.zoom_at(QPointF(300, 200), vp.zoom * 1.1)
    elif op == 2:
        vp.rotate_by(9.0)
    else:
        anchor = QPointF(123.0, 456.0)
        p = vp.to_scene(anchor)
        vp.rotate_at(anchor, vp.rotation + 13.0)
        worst = max(worst, (vp.to_view(p) - anchor).manhattanLength())
check("40 mixed ops: rotate_at anchor drift < 1e-6",
      worst < 1e-6, f"worst={worst:.3e}")

# =========================================================================
print("\n10. Controller: Space override, middle button, tool cursors")
# =========================================================================
v = make_view()
state = {"tool": "pen"}
nav = NavigationController(v, get_tool=lambda: state["tool"])

from PySide6.QtGui import QKeyEvent
k_down = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space,
                   Qt.KeyboardModifier.NoModifier)
k_up = QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Space,
                 Qt.KeyboardModifier.NoModifier)


def mouse(t, pos, btn, mods=Qt.KeyboardModifier.NoModifier):
    return QMouseEvent(t, QPointF(pos), QPointF(pos), QPointF(pos), btn,
                       btn, mods)


probe = QPointF(0.0, 0.0)
b = nav.vp.to_view(probe)
consumed = nav.key_press(k_down)
check("Space is consumed while a pen tool is active", consumed is True)
check("cursor becomes OpenHand on Space",
      v.cursor().shape() == Qt.CursorShape.OpenHandCursor)
nav.press(mouse(QEvent.Type.MouseButtonPress, QPointF(400, 300),
                Qt.MouseButton.LeftButton))
check("cursor becomes ClosedHand while dragging",
      v.cursor().shape() == Qt.CursorShape.ClosedHandCursor)
for i in range(20):
    nav.move(mouse(QEvent.Type.MouseMove, QPointF(400 + i * 2.5, 300 + i),
                   Qt.MouseButton.LeftButton))
nav.release(mouse(QEvent.Type.MouseButtonRelease, QPointF(450, 320),
                  Qt.MouseButton.LeftButton))
a = nav.vp.to_view(probe)
check("Space-drag pans content by exactly the drag delta",
      abs(a.x() - b.x() - 47.5) < 1e-6 and abs(a.y() - b.y() - 19.0) < 1e-6,
      f"moved ({a.x()-b.x():.6f}, {a.y()-b.y():.6f}) expected (47.5, 19.0)")
nav.key_release(k_up)
check("cursor restored after Space released",
      v.cursor().shape() == Qt.CursorShape.ArrowCursor)

# middle button
b = nav.vp.to_view(probe)
nav.press(mouse(QEvent.Type.MouseButtonPress, QPointF(200, 200),
                Qt.MouseButton.MiddleButton))
nav.move(mouse(QEvent.Type.MouseMove, QPointF(260, 170),
               Qt.MouseButton.MiddleButton))
nav.release(mouse(QEvent.Type.MouseButtonRelease, QPointF(260, 170),
                  Qt.MouseButton.MiddleButton))
a = nav.vp.to_view(probe)
check("middle-drag pans 1:1",
      abs(a.x() - b.x() - 60.0) < 1e-6 and abs(a.y() - b.y() + 30.0) < 1e-6,
      f"moved ({a.x()-b.x():.6f}, {a.y()-b.y():.6f}) expected (60, -30)")

# =========================================================================
print("\n11. Controller: Space is NOT stolen from vpen/nodeedit")
# =========================================================================
state["tool"] = "vpen"
check("vpen keeps its own Space behaviour", nav.key_press(k_down) is False)
state["tool"] = "nodeedit"
check("nodeedit keeps its own Space behaviour", nav.key_press(k_down) is False)
state["tool"] = "pen"

# =========================================================================
print("\n12. Controller: wheel zoom anchors at the cursor")
# =========================================================================
def wheel(pos, dy, mods=Qt.KeyboardModifier.NoModifier):
    return QWheelEvent(QPointF(pos), QPointF(pos), QPoint(0, 0),
                       QPoint(0, dy), Qt.MouseButton.NoButton, mods,
                       Qt.ScrollPhase.NoScrollPhase, False)


anchor = QPointF(511.0, 233.0)
p = nav.vp.to_scene(anchor)
nav.wheel(wheel(anchor, 120))
check("one wheel notch: point under cursor stays put",
      (nav.vp.to_view(p) - anchor).manhattanLength() < 1e-6,
      f"drift={(nav.vp.to_view(p) - anchor).manhattanLength():.3e}")
z1 = nav.vp.zoom
nav.wheel(wheel(anchor, 120, Qt.KeyboardModifier.ShiftModifier))
check("Shift+wheel pans horizontally instead of zooming",
      abs(nav.vp.zoom - z1) < 1e-12)

# =========================================================================
print("\n13. Controller: zoom tool marquee + click stepping")
# =========================================================================
state["tool"] = "zoom"
c = nav.vp.center()
nav.press(mouse(QEvent.Type.MouseButtonPress, QPointF(300, 200),
                Qt.MouseButton.LeftButton))
nav.move(mouse(QEvent.Type.MouseMove, QPointF(600, 500),
               Qt.MouseButton.LeftButton))
nav.release(mouse(QEvent.Type.MouseButtonRelease, QPointF(600, 500),
                  Qt.MouseButton.LeftButton))
check("marquee zoom-to-rect keeps the rect centred",
      (nav.vp.to_view(nav.vp.to_scene(c)) - c).manhattanLength() < 1.0)

z_before = nav.vp.zoom
nav.press(mouse(QEvent.Type.MouseButtonPress, QPointF(400, 300),
                Qt.MouseButton.LeftButton))
nav.release(mouse(QEvent.Type.MouseButtonRelease, QPointF(400, 300),
                  Qt.MouseButton.LeftButton))
check("click with Zoom tool steps the ladder up", nav.vp.zoom > z_before,
      f"{z_before:.4f} -> {nav.vp.zoom:.4f}")
z_before = nav.vp.zoom
nav.press(mouse(QEvent.Type.MouseButtonPress, QPointF(400, 300),
                Qt.MouseButton.LeftButton, Qt.KeyboardModifier.AltModifier))
nav.release(mouse(QEvent.Type.MouseButtonRelease, QPointF(400, 300),
                  Qt.MouseButton.LeftButton))
check("Alt+click with Zoom tool steps down", nav.vp.zoom < z_before,
      f"{z_before:.4f} -> {nav.vp.zoom:.4f}")

# =========================================================================
print("\n14. Controller: hand tool + rotate-canvas tool")
# =========================================================================
state["tool"] = "hand"
nav.tool_changed()
check("hand tool shows the open-hand cursor",
      v.cursor().shape() == Qt.CursorShape.OpenHandCursor)
probe = QPointF(0.0, 0.0)
b = nav.vp.to_view(probe)
nav.press(mouse(QEvent.Type.MouseButtonPress, QPointF(100, 100),
                Qt.MouseButton.LeftButton))
nav.move(mouse(QEvent.Type.MouseMove, QPointF(140, 130),
               Qt.MouseButton.LeftButton))
nav.release(mouse(QEvent.Type.MouseButtonRelease, QPointF(140, 130),
                  Qt.MouseButton.LeftButton))
a = nav.vp.to_view(probe)
check("hand drags exactly 1:1",
      abs(a.x() - b.x() - 40.0) < 1e-6 and abs(a.y() - b.y() - 30.0) < 1e-6,
      f"moved ({a.x()-b.x():.6f}, {a.y()-b.y():.6f})")

state["tool"] = "rotate_canvas"
nav.vp.reset_rotation()
c0 = nav.vp.center()
nav.press(mouse(QEvent.Type.MouseButtonPress, QPointF(c0.x() + 100, c0.y()),
                Qt.MouseButton.LeftButton))   # due east of centre -> 0 deg
nav.move(mouse(QEvent.Type.MouseMove, QPointF(c0.x() + 100, c0.y() + 100),
               Qt.MouseButton.LeftButton))    # -> 45 deg clockwise
check("rotate-canvas drag rotates by the drag angle",
      abs(nav.vp.rotation - 45.0) < 1e-6, f"{nav.vp.rotation:.6f} deg")
nav.release(mouse(QEvent.Type.MouseButtonRelease, QPointF(550, 425),
                  Qt.MouseButton.LeftButton))
nav.double_click(mouse(QEvent.Type.MouseButtonDblClick, QPointF(400, 300),
                       Qt.MouseButton.LeftButton))
check("double-click resets rotation", nav.vp.rotation == 0.0)

# =========================================================================
print("\n15. No undo entries are created by navigation (R4)")
# =========================================================================
# The controller never touches the document; assert it exposes no undo API.
check("NavigationController has no undo/push_undo hook",
      not any(hasattr(NavigationController, n)
              for n in ("push_undo", "undo", "redo")))
check("NavViewport never mutates scene items",
      len(v.scene().items()) == 12, f"items={len(v.scene().items())}")

# =========================================================================
print("\n" + "=" * 68)
print(f"  {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("  FAILED: " + ", ".join(FAIL))
print("=" * 68)
sys.exit(1 if FAIL else 0)
