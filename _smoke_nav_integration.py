# -*- coding: utf-8 -*-
"""Temporary integration smoke test: does nav_tools work inside the real app?

Runs offscreen, builds the actual MainWindow, then drives the navigation
controller the way a user would (wheel zoom, middle-drag pan, space pan,
rotate canvas, fit, 100%) and checks the invariants that matter:

  * the scene point under the cursor stays under the cursor when zooming
  * content tracks the pointer 1:1 when panning
  * the zoom readout matches the real transform
  * drawing still works (a pen stroke lands at the scene point we clicked)
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt, QEvent
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication

import whiteboard_qt as wb

# Headless guard: MainWindow.add_text_at() calls QInputDialog.getMultiLineText(),
# a MODAL dialog that blocks the whole script forever when run offscreen.
# Stub it so section 6 can create a text item and keep going.
from PySide6.QtWidgets import QInputDialog

QInputDialog.getMultiLineText = staticmethod(lambda *a, **k: ("smoke", True))
QInputDialog.getText = staticmethod(lambda *a, **k: ("smoke", True))

FAILS = []


def check(name, ok, detail=""):
    print(("  [PASS] " if ok else "  [FAIL] ") + name + (
        "  — " + detail if detail else ""))
    if not ok:
        FAILS.append(name)


def mouse(kind, pos, btn=Qt.MouseButton.LeftButton, mods=Qt.KeyboardModifier.NoModifier):
    return QMouseEvent(kind, QPointF(*pos), QPointF(*pos),
                       QPointF(*pos), btn, btn, mods)


def wheel(pos, dy):
    # pixelDelta / angleDelta must be QPoint (integers), not QPointF —
    # PySide6 6.11 rejects the float variant with a TypeError.
    return QWheelEvent(QPointF(*pos), QPointF(*pos), QPoint(0, 0),
                       QPoint(0, dy), Qt.MouseButton.NoButton,
                       Qt.KeyboardModifier.NoModifier,
                       Qt.ScrollPhase.NoScrollPhase, False)


app = QApplication.instance() or QApplication(sys.argv)
win = wb.MainWindow()
win.resize(1200, 800)
win.show()
app.processEvents()

view = win.view
vp = view.nav.vp

print("\n1. Wiring")
check("MainWindow has a nav controller", hasattr(view, "nav"))
check("scrollbars hidden (infinite canvas)",
      view.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
check("tool buttons for hand/zoom/rotate exist",
      all(k in win.tool_buttons for k in ("hand", "zoom", "rotate_canvas")),
      str(sorted(win.tool_buttons)))
check("navigator panel present in the sidebar",
      getattr(win, "navigator", None) is not None)

print("\n2. Wheel zoom anchors at the cursor (R2)")
before = vp.to_scene(QPointF(400, 300))
view.wheelEvent(wheel((400, 300), 120))
app.processEvents()
after = vp.to_scene(QPointF(400, 300))
drift = (after - before).manhattanLength()
check("scene point under cursor did not move", drift < 1e-6, f"drift={drift:.2e}")
check("zoom actually changed", abs(vp.zoom - 1.0) > 1e-9, f"zoom={vp.zoom:.4f}")
check("zoom label matches the model",
      win.zoom_label.text() == f"{int(round(vp.zoom * 100))}%",
      win.zoom_label.text())

print("\n3. Middle-drag pan is 1:1 (R1)")
p0 = vp.to_scene(QPointF(300, 300))
view.mousePressEvent(mouse(QEvent.Type.MouseButtonPress, (300, 300),
                           Qt.MouseButton.MiddleButton))
view.mouseMoveEvent(mouse(QEvent.Type.MouseMove, (345, 330),
                          Qt.MouseButton.MiddleButton))
view.mouseReleaseEvent(mouse(QEvent.Type.MouseButtonRelease, (345, 330),
                             Qt.MouseButton.MiddleButton))
app.processEvents()
p1 = vp.to_scene(QPointF(300, 300))
moved = p1 - p0
exp = QPointF(-45, -30) / vp.zoom
err = (moved - exp).manhattanLength() * vp.zoom
check("content followed the pointer exactly", err < 0.02, f"err={err:.4f} px")

print("\n4. Space-bar temporary pan override (R5)")
win.set_tool("pen")
view.nav.key_press(type("E", (), {"key": lambda s: Qt.Key.Key_Space,
                                  "modifiers": lambda s: Qt.KeyboardModifier.NoModifier,
                                  "isAutoRepeat": lambda s: False})())
q0 = vp.to_scene(QPointF(500, 400))
view.mousePressEvent(mouse(QEvent.Type.MouseButtonPress, (500, 400)))
view.mouseMoveEvent(mouse(QEvent.Type.MouseMove, (520, 400)))
view.mouseReleaseEvent(mouse(QEvent.Type.MouseButtonRelease, (520, 400)))
app.processEvents()
q1 = vp.to_scene(QPointF(500, 400))
moved = (q1 - q0) * vp.zoom
check("space-drag panned without drawing",
      abs(moved.x() + 20) < 0.02 and abs(moved.y()) < 0.02,
      f"moved=({moved.x():.3f}, {moved.y():.3f}) expected (-20, 0)")
check("no stroke was created while panning",
      view._creating is None and view._vp_item is None)
# Release Space again — otherwise nav._space stays True for the rest of the
# run and every later left-press is swallowed as a pan (section 7 then sees
# "no stroke" and reports a phantom failure).
view.nav.key_release(type("E", (), {"key": lambda s: Qt.Key.Key_Space,
                                    "modifiers": lambda s: Qt.KeyboardModifier.NoModifier,
                                    "isAutoRepeat": lambda s: False})())
app.processEvents()
check("space release restores normal drawing mode", view.nav._space is False)

print("\n5. Rotate canvas + zoom still coherent")
vp.rotate_by(30.0)
app.processEvents()
check("rotation applied", abs(vp.rotation - 30.0) < 1e-6, f"{vp.rotation:.3f} deg")
m11 = view.transform().m11()
check("m11 is no longer the zoom factor (rotation aware)",
      abs(m11 - vp.zoom) > 1e-6, f"m11={m11:.4f} zoom={vp.zoom:.4f}")
check("zoom label still reports the true factor",
      win.zoom_label.text() == f"{int(round(vp.zoom * 100))}%",
      win.zoom_label.text())
s = vp.to_scene(QPointF(600, 400))
view.wheelEvent(wheel((600, 400), -120))
app.processEvents()
drift = (vp.to_scene(QPointF(600, 400)) - s).manhattanLength()
check("zoom stays anchored while rotated", drift < 1e-6, f"drift={drift:.2e}")
vp.reset_rotation()
app.processEvents()

print("\n6. Fit / 100% / zoom actions")
win.add_text_at(QPointF(0.0, 0.0))
app.processEvents()
win.fit_content()
app.processEvents()
check("fit_content works and updates the label",
      win.zoom_label.text() == f"{int(round(vp.zoom * 100))}%",
      win.zoom_label.text())
win._zoom(1.2)
app.processEvents()
check("_zoom routes through the nav model",
      win.zoom_label.text() == f"{int(round(vp.zoom * 100))}%",
      win.zoom_label.text())
vp.actual_size()
app.processEvents()
check("100 % is exact", abs(vp.zoom - 1.0) < 1e-12, f"{vp.zoom}")

print("\n7. Drawing still lands where you click")
win.set_tool("pen")
target = vp.to_scene(QPointF(700, 500))
view.mousePressEvent(mouse(QEvent.Type.MouseButtonPress, (700, 500)))
view.mouseMoveEvent(mouse(QEvent.Type.MouseMove, (760, 540)))
view.mouseReleaseEvent(mouse(QEvent.Type.MouseButtonRelease, (760, 540)))
app.processEvents()
pl = getattr(view._creating, "_payload", None) or None
strokes = [i for i in win._item_refs
           if (getattr(i, "_payload", None) or {}).get("type") == "pen"]
ok = False
detail = "no stroke"
if strokes:
    first = QPointF(*strokes[-1]._payload["points"][0])
    ok = (first - target).manhattanLength() < 1e-6
    detail = f"first point={first.x():.2f},{first.y():.2f} target={target.x():.2f},{target.y():.2f}"
check("pen stroke starts at the clicked scene point", ok, detail)

print("\n8. Select tool still selects (nav does not eat it)")
win.set_tool("select")
check("drag mode is rubber band for select",
      view.dragMode() == wb.QGraphicsView.DragMode.RubberBandDrag)

print("\n" + "=" * 68)
if FAILS:
    print(f"  {len(FAILS)} FAILED: " + ", ".join(FAILS))
    sys.exit(1)
print("  all integration checks passed")
print("=" * 68)
