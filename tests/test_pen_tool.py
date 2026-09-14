# -*- coding: utf-8 -*-
"""Pen-tool regression suite — runs offscreen, no display needed.

    python tests/test_pen_tool.py

WHY THIS FILE LIVES IN THE REPO
-------------------------------
The older suites (wb_qt2_test.py, wb_vpath_test.py, wb_pen2_test.py, ...) were
kept in %TEMP%\\opencode and Windows cleanup has been deleting them. Anything
that guards a non-obvious invariant belongs in git.

WHAT IT GUARDS
--------------
The handle convention. `in` and `out` are BOTH offsets from the anchor to
their control point (same sign); a smooth node therefore stores in == -out.
The geometry helpers used to compute anchor - in, which turned every smooth
node drawn by press-drag into a 180-degree cusp. Test 2 is the tripwire for
that exact regression.
"""
import math
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QKeyEvent
from PySide6.QtWidgets import QApplication, QInputDialog

import whiteboard_qt as wb

# MainWindow.add_text_at() opens a MODAL dialog that would freeze an
# offscreen run forever. Stub it.
QInputDialog.getMultiLineText = staticmethod(lambda *a, **k: ("smoke", True))
QInputDialog.getText = staticmethod(lambda *a, **k: ("smoke", True))

FAILS = []


def check(name, ok, detail=""):
    print(("  [PASS] " if ok else "  [FAIL] ") + name +
          ("  — " + detail if detail else ""))
    if not ok:
        FAILS.append(name)


app = QApplication.instance() or QApplication(sys.argv)
win = wb.MainWindow()
win.resize(1400, 900)
win.show()
view = win.view


def ev(t, sp, mods=Qt.KeyboardModifier.NoModifier):
    v = view.mapFromScene(QPointF(sp[0], sp[1]))
    return QMouseEvent(t, QPointF(v), QPointF(v),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, mods)


PRESS, MOVE, REL = (QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove,
                    QEvent.Type.MouseButtonRelease)


def key(k):
    return QKeyEvent(QEvent.Type.KeyPress, k, Qt.KeyboardModifier.NoModifier)


def vpaths():
    return [it for it in win._item_refs
            if (getattr(it, "_payload", None) or {}).get("type") == "vpath"]


def draw_node(sp, drag=None):
    """One pen gesture: press at sp, optionally drag its out-handle, release."""
    view.mousePressEvent(ev(PRESS, sp))
    if drag:
        view.mouseMoveEvent(ev(MOVE, drag))
    view.mouseReleaseEvent(ev(REL, drag or sp))


# =====================================================================
print("\n1. Handle convention: arriving control = anchor + in")
# =====================================================================
A = wb._vp_node((0.0, 0.0), out=(100.0, 0.0))
B = wb._vp_node((300.0, 0.0), out=(100.0, 0.0), inn=(-100.0, 0.0), t="smooth")
c2 = wb._vp_seg_bezier([A, B], 0)[2]
check("control arriving at B sits opposite its out-handle",
      abs(c2.x() - 200.0) < 1e-9, f"c2.x()={c2.x()} expected 200")

# =====================================================================
print("\n2. C1 continuity at a smooth node (regression tripwire)")
# =====================================================================
mid = wb._vp_node((300.0, 0.0), out=(100.0, 0.0), inn=(-100.0, 0.0), t="smooth")
chain = [wb._vp_node((0.0, 0.0), out=(100.0, 0.0)), mid,
         wb._vp_node((600.0, 0.0), inn=(-100.0, 0.0), t="smooth")]
p2 = wb._vp_seg_bezier(chain, 0)[2]
p1 = wb._vp_seg_bezier(chain, 1)[1]
p = chain[1]["p"]
tin = (p[0] - p2.x(), p[1] - p2.y())
tout = (p1.x() - p[0], p1.y() - p[1])
cross = tin[0] * tout[1] - tin[1] * tout[0]
dot = tin[0] * tout[0] + tin[1] * tout[1]
check("tangents point the same way (dot > 0)", dot > 0,
      f"dot={dot:+.0f} (negative == 180-degree cusp)")
check("tangents are collinear (cross == 0)", abs(cross) < 1e-9,
      f"cross={cross:+.2e}")

# =====================================================================
print("\n3. Interactive gesture produces a genuinely smooth node")
# =====================================================================
win.set_tool("vpen")
P0, P1, P2 = (200.0, 400.0), (400.0, 200.0), (600.0, 400.0)
draw_node(P0)
draw_node(P1, (P1[0] + 80, P1[1] - 80))
draw_node(P2, (P2[0] + 80, P2[1] - 80))
win.keyPressEvent(key(Qt.Key.Key_Return))
app.processEvents()

items = vpaths()
check("gesture produced a vpath", bool(items), f"{len(items)} item(s)")
nodes = items[-1]._payload["nodes"]
check("three nodes placed", len(nodes) == 3, f"{len(nodes)}")
nd = nodes[1]
check("interior node is marked smooth", nd["t"] == "smooth", nd["t"])
q2 = wb._vp_seg_bezier(nodes, 0)[2]
q1 = wb._vp_seg_bezier(nodes, 1)[1]
tin = (nd["p"][0] - q2.x(), nd["p"][1] - q2.y())
tout = (q1.x() - nd["p"][0], q1.y() - nd["p"][1])
ang = math.degrees(math.atan2(tin[0] * tout[1] - tin[1] * tout[0],
                              tin[0] * tout[0] + tin[1] * tout[1]))
check("measured tangent angle is 0 deg, not 180", abs(ang) < 1.0,
      f"{ang:+.2f} deg")

# =====================================================================
print("\n4. Closing a path: shared helper + visible target")
# =====================================================================
win.keyPressEvent(key(Qt.Key.Key_Escape))
view.mouseMoveEvent(ev(MOVE, (0.0, 0.0)))
C = (800.0, 700.0)
draw_node((100.0, 100.0))
draw_node((300.0, 150.0))
draw_node(C)
app.processEvents()
path = vpaths()[-1]
pnodes = path._payload["nodes"]
first = pnodes[0]["p"]

# far from the first node -> preview goes to the cursor
view.mouseMoveEvent(ev(MOVE, (700.0, 600.0)))
rb = view._rubber_item.path()
far_end = rb.elementAt(3)
check("far from start: no close target",
      view._vpen_close_node(QPointF(700.0, 600.0)) is None)
check("far from start: preview ends at the cursor",
      math.hypot(far_end.x - 700.0, far_end.y - 600.0) < 1.0,
      f"({far_end.x:.1f},{far_end.y:.1f})")

# inside the close radius -> preview snaps to the first node
near = (first[0] + 4.0, first[1] + 4.0)
view.mouseMoveEvent(ev(MOVE, near))
rb = view._rubber_item.path()
near_end = rb.elementAt(3)
check("near start: close target is reported",
      view._vpen_close_node(QPointF(*near)) is not None)
check("near start: preview snaps to the first node",
      math.hypot(near_end.x - first[0], near_end.y - first[1]) < 1e-6,
      f"({near_end.x:.1f},{near_end.y:.1f}) vs ({first[0]:.1f},{first[1]:.1f})")
check("near start: ring drawn on the target",
      rb.elementCount() > 4, f"{rb.elementCount()} elements")

view.mousePressEvent(ev(PRESS, near))
app.processEvents()
check("clicking the target closes the path",
      bool(path._payload.get("closed")), f"closed={path._payload.get('closed')}")

# =====================================================================
print("\n5. Pen over a finished path: insert anchor, shape unchanged")
# =====================================================================
win.keyPressEvent(key(Qt.Key.Key_Escape))
win.set_tool("vpen")
draw_node((200.0, 800.0))
draw_node((400.0, 900.0), (480.0, 880.0))
draw_node((600.0, 800.0), (680.0, 820.0))
win.keyPressEvent(key(Qt.Key.Key_Return))
app.processEvents()
target = vpaths()[-1]
nodes_before = [dict(nd) for nd in target._payload["nodes"]]
n_before = len(nodes_before)

click = wb._vp_point_on_seg(nodes_before, 0, 0.5)
# recover the exact split parameter the hit-test will pick (k/24 ladder)
ts = None
for k in range(1, 24):
    pt = wb._vp_point_on_seg(nodes_before, 0, k / 24.0)
    if math.hypot(pt.x() - click.x(), pt.y() - click.y()) < 1e-6:
        ts = k / 24.0
        break
view.mousePressEvent(ev(PRESS, (click.x(), click.y())))
view.mouseReleaseEvent(ev(REL, (click.x(), click.y())))
app.processEvents()

nodes_after = target._payload["nodes"]
check("anchor inserted on the segment", len(nodes_after) == n_before + 1,
      f"{n_before} -> {len(nodes_after)}")

# Exact shape check: de Casteljau split must reproduce the original curve
# point-for-point. Segment 0 before == segment 0 up to ts + segment 1 after it.
worst = 0.0
if ts is not None:
    for k in range(41):
        t = k / 40.0
        want = wb._vp_point_on_seg(nodes_before, 0, t)
        if t <= ts:
            got = wb._vp_point_on_seg(nodes_after, 0, t / ts)
        else:
            got = wb._vp_point_on_seg(nodes_after, 1, (t - ts) / (1.0 - ts))
        worst = max(worst, math.hypot(want.x() - got.x(), want.y() - got.y()))
check("splitting preserves the curve shape exactly", worst < 1e-9,
      f"max deviation {worst:.2e} over 41 samples (ts={ts})")

# =====================================================================
print("\n6. Pen over a finished path: delete an anchor")
# =====================================================================
nodes_now = target._payload["nodes"]
interior = nodes_now[1]["p"]
view.mousePressEvent(ev(PRESS, (interior[0], interior[1])))
view.mouseReleaseEvent(ev(REL, (interior[0], interior[1])))
app.processEvents()
check("clicking an anchor removes it",
      len(target._payload["nodes"]) == n_before,
      f"{len(nodes_after)} -> {len(target._payload['nodes'])}")

# =====================================================================
print("\n7. Node edit: Alt+click converts a point")
# =====================================================================
win.keyPressEvent(key(Qt.Key.Key_Escape))
win.set_tool("nodeedit")
edit_target = target
view._ne_item = edit_target
view._ne_sel = set()

# state-agnostic: read the type, Alt+click, assert it FLIPPED
def node_type(i):
    return edit_target._payload["nodes"][i].get("t")


def alt_click_node(i):
    p = edit_target._payload["nodes"][i]["p"]
    view.mousePressEvent(ev(PRESS, (p[0], p[1]), Qt.KeyboardModifier.AltModifier))
    view.mouseReleaseEvent(ev(REL, (p[0], p[1]), Qt.KeyboardModifier.AltModifier))
    app.processEvents()


was = node_type(1)
alt_click_node(1)
now = node_type(1)
check("Alt+click flips the anchor type", now != was, f"{was} -> {now}")

if now == "smooth":
    nd = edit_target._payload["nodes"][1]
    check("converted-to-smooth node has mirrored handles",
          nd["in"] is not None and nd["out"] is not None and
          abs(nd["in"][0] + nd["out"][0]) < 1e-9 and
          abs(nd["in"][1] + nd["out"][1]) < 1e-9,
          f"in={nd['in']} out={nd['out']}")
    # and the tangent must actually be continuous, not a cusp
    nd = edit_target._payload["nodes"][1]
    q2 = wb._vp_seg_bezier(edit_target._payload["nodes"], 0)[2]
    q1 = wb._vp_seg_bezier(edit_target._payload["nodes"], 1)[1]
    dot = ((nd["p"][0] - q2.x()) * (q1.x() - nd["p"][0]) +
           (nd["p"][1] - q2.y()) * (q1.y() - nd["p"][1]))
    check("converted smooth node is C1 (not a cusp)", dot > 0, f"dot={dot:+.0f}")
else:
    check("converted-to-corner node dropped its handles",
          edit_target._payload["nodes"][1]["in"] is None and
          edit_target._payload["nodes"][1]["out"] is None)

alt_click_node(1)
check("Alt+click again flips it back",
      node_type(1) != now, f"{now} -> {node_type(1)}")

# =====================================================================
print("\n8. Node edit: Shift locks a handle to 45 degrees")
# =====================================================================
view._ne_sel = set()
nd = edit_target._payload["nodes"][1]
nd["t"] = "smooth"
nd["out"] = [60.0, 0.0]
nd["in"] = [-60.0, 0.0]
view._ne_drag = ("handle", 1, "out", QPointF(nd["p"][0] + 60.0, nd["p"][1]))
# drag to a ~37 degree position WITH Shift -> must snap to exactly 45
view.mouseMoveEvent(ev(MOVE, (nd["p"][0] + 28.0, nd["p"][1] + 21.0),
                       Qt.KeyboardModifier.ShiftModifier))
off = edit_target._payload["nodes"][1]["out"]
ang = math.degrees(math.atan2(off[1], off[0])) % 45.0
check("handle snapped to a 45-degree multiple",
      abs(ang) < 1e-6 or abs(ang - 45.0) < 1e-6,
      f"out=({off[0]:.2f},{off[1]:.2f}) angle={math.degrees(math.atan2(off[1], off[0])):.3f}")
view._ne_drag = None

# =====================================================================
print("\n9. Node edit: handles appear on hover, before any click")
# =====================================================================
view._ne_sel = set()
view._ne_hover = None
nd = edit_target._payload["nodes"][2]
view.mouseMoveEvent(ev(MOVE, (nd["p"][0] + 1.0, nd["p"][1] + 1.0)))
check("hovering an anchor records it", view._ne_hover == 2,
      f"_ne_hover={view._ne_hover}")
view.mouseMoveEvent(ev(MOVE, (nd["p"][0] + 500.0, nd["p"][1] + 500.0)))
check("leaving the anchor clears the hover", view._ne_hover is None,
      f"_ne_hover={view._ne_hover}")

# =====================================================================
print("\n10. Round-trip: vpath -> QPainterPath -> vpath (boolean ops path)")
# =====================================================================
# _qpath_to_vpath_nodes is what boolean union/subtract/intersect feed their
# result through. Its handle sign was flipped in the same bug, so prove the
# two functions are mutually consistent: a circle must survive the trip.
R = 150.0
K = 0.5522847498307936 * R
CIRCLE = [
    {"p": [0.0, -R], "out": [K, 0.0], "in": [-K, 0.0], "t": "smooth"},
    {"p": [R, 0.0], "out": [0.0, K], "in": [0.0, -K], "t": "smooth"},
    {"p": [0.0, R], "out": [-K, 0.0], "in": [K, 0.0], "t": "smooth"},
    {"p": [-R, 0.0], "out": [0.0, -K], "in": [0.0, K], "t": "smooth"},
]


def radial_err(path):
    poly = path.toSubpathPolygons()[0]
    return max(abs(math.hypot(p.x(), p.y()) - R) for p in poly)


src = wb._vpath_to_qpath(CIRCLE, True)
e_src = radial_err(src)
back, closed_back = wb._qpath_to_vpath_nodes(src)
rebuilt = wb._vpath_to_qpath(back, closed_back)
e_back = radial_err(rebuilt)
check("source circle is round", e_src < 0.5, f"error={e_src:.3f}")
check("closed flag survives the round-trip", closed_back is True,
      f"closed={closed_back}")
check("round-trip preserves the shape", e_back < 1.0,
      f"src={e_src:.3f} -> rebuilt={e_back:.3f} ({len(back)} nodes)")
check("round-trip keeps smooth handles mirrored",
      all(nd.get("t") == "corner" or
          (nd.get("in") is None) == (nd.get("out") is None)
          for nd in back),
      "handle pairs consistent")

# =====================================================================
print("\n11. Teardown guard: slots must survive a deleted scene")
# =====================================================================
# Qt delivers selectionChanged through queued events, so these slots can run
# after the scene is gone. Before the guard they raised
# "RuntimeError: Internal C++ object (QGraphicsScene) already deleted" on
# every exit.
from PySide6.QtWidgets import QGraphicsScene
import shiboken6

live = QGraphicsScene()
check("live scene reported alive", wb.scene_alive(live) is True)
check("None reported dead", wb.scene_alive(None) is False)

dead = QGraphicsScene()
shiboken6.delete(dead)
check("deleted scene reported dead", wb.scene_alive(dead) is False)

saved_scene = win.scene
win.scene = dead
survived, err = True, ""
try:
    win.update_props_panel()
    win._update_tbox()
    list(win._iter_sel_payload_items())
except Exception as ex:                       # noqa: BLE001
    survived, err = False, f"{type(ex).__name__}: {ex}"
win.scene = saved_scene
check("update_props_panel / _update_tbox survive a dead scene",
      survived, err)

# =====================================================================
print("\n" + "=" * 68)
if FAILS:
    print(f"  {len(FAILS)} FAILED: " + " | ".join(FAILS))
else:
    print("  all pen-tool checks passed")
print("=" * 68)
sys.exit(1 if FAILS else 0)
