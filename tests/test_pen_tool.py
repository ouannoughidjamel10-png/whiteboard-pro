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


def scene_pt(sp):
    """Where a synthetic event aimed at `sp` ACTUALLY lands.

    QMouseEvent carries view (integer pixel) coordinates and the handler calls
    mapToScene on them, so the scene point is quantised by the view transform.
    Real mice are quantised the same way - compare against this, not against
    the nominal coordinate, or the test is asserting something impossible.
    """
    return view.mapToScene(view.mapFromScene(QPointF(sp[0], sp[1])))


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
print("\n12. Flip / reflect the selection")
# =====================================================================
win.set_tool("select")


def make_vpath(nodes, x_off=0.0):
    pl = {"type": "vpath", "closed": False,
          "nodes": [dict(nd) for nd in nodes],
          "stroke": {"color": "#111111", "width": 3, "alpha": 255},
          "fill": None, "rot": 0.0, "layer": 0}
    for nd in pl["nodes"]:
        nd["p"] = [nd["p"][0] + x_off, nd["p"][1]]
    item = wb.payload_to_item(pl)
    win._add_item(item)
    return item


SHAPE = [{"p": [0.0, 0.0], "out": [30.0, 0.0], "in": None, "t": "corner"},
         {"p": [100.0, 40.0], "out": None, "in": [-20.0, 0.0], "t": "corner"},
         {"p": [160.0, 0.0], "out": None, "in": None, "t": "corner"}]

shape = make_vpath(SHAPE)
win.scene.clearSelection()
shape.setSelected(True)
app.processEvents()

box0 = shape.sceneBoundingRect()
nodes0 = [list(nd["p"]) for nd in shape._payload["nodes"]]
cx0 = box0.center().x()

win.flip_selection("h")
app.processEvents()
nodes1 = [list(nd["p"]) for nd in shape._payload["nodes"]]
box1 = shape.sceneBoundingRect()
expect = [[2 * cx0 - x, y] for x, y in nodes0]
worst = max(math.hypot(a[0] - b[0], a[1] - b[1])
            for a, b in zip(nodes1, expect))
check("horizontal flip mirrors every node about the selection centre",
      worst < 1e-6, f"max deviation {worst:.2e}")
check("flipped box keeps its size",
      abs(box1.width() - box0.width()) < 1e-6 and
      abs(box1.height() - box0.height()) < 1e-6,
      f"{box0.width():.2f}x{box0.height():.2f} -> "
      f"{box1.width():.2f}x{box1.height():.2f}")
check("flipped box keeps its centre",
      math.hypot(box1.center().x() - cx0,
                 box1.center().y() - box0.center().y()) < 1e-6)

win.flip_selection("h")                     # involution
app.processEvents()
nodes2 = [list(nd["p"]) for nd in shape._payload["nodes"]]
worst2 = max(math.hypot(a[0] - b[0], a[1] - b[1])
             for a, b in zip(nodes2, nodes0))
check("flipping twice returns the original", worst2 < 1e-6,
      f"max deviation {worst2:.2e}")

cy0 = box0.center().y()
win.flip_selection("v")
app.processEvents()
nodes3 = [list(nd["p"]) for nd in shape._payload["nodes"]]
expect_v = [[x, 2 * cy0 - y] for x, y in nodes0]
worst3 = max(math.hypot(a[0] - b[0], a[1] - b[1])
             for a, b in zip(nodes3, expect_v))
check("vertical flip mirrors about the centre", worst3 < 1e-6,
      f"max deviation {worst3:.2e}")
win.flip_selection("v")                     # restore

# =====================================================================
print("\n13. Flip: text mirrors its BOX, not just its origin")
# =====================================================================
# text/latex/image payloads carry only an origin and their box grows
# right/down, so a naive origin mirror leaves them hanging off the axis.
txt = wb.payload_to_item({"type": "text", "pos": [0.0, 0.0], "text": "AB",
                          "size": 40, "color": "#111111", "layer": 0})
win._add_item(txt)
ref = make_vpath(SHAPE, x_off=200.0)        # pulls the flip axis off-centre
app.processEvents()

win.scene.clearSelection()
txt.setSelected(True)
ref.setSelected(True)
app.processEvents()
axis_cx = txt.sceneBoundingRect().united(ref.sceneBoundingRect()).center().x()
tb0 = txt.sceneBoundingRect()
rb0 = ref.sceneBoundingRect()

win.flip_selection("h")
app.processEvents()
tb1 = txt.sceneBoundingRect()
rb1 = ref.sceneBoundingRect()

# the two boxes should have swapped sides
check("text box lands mirrored on the far side of the axis",
      abs(tb1.left() - (2 * axis_cx - tb0.right())) < 0.01,
      f"left {tb0.left():.1f} -> {tb1.left():.1f}, "
      f"expected {2 * axis_cx - tb0.right():.1f}")
check("reference box also mirrored",
      abs(rb1.left() - (2 * axis_cx - rb0.right())) < 0.01,
      f"left {rb0.left():.1f} -> {rb1.left():.1f}")
check("text stays readable (box size unchanged)",
      abs(tb1.width() - tb0.width()) < 1e-6,
      f"width {tb0.width():.2f} -> {tb1.width():.2f}")

# =====================================================================
print("\n14. Flip a GROUP (child payloads are the source of truth)")
# =====================================================================
ga = make_vpath(SHAPE, x_off=0.0)
gb = make_vpath(SHAPE, x_off=200.0)
win.scene.clearSelection()
ga.setSelected(True)
gb.setSelected(True)
app.processEvents()
win.group_selection()
app.processEvents()

grp = None
for candidate in win._item_refs:
    if isinstance(candidate, wb.BoardGroup):
        grp = candidate
        break

if grp is None:
    check("group created from the selection", False, "no BoardGroup found")
else:
    win.scene.clearSelection()
    grp.setSelected(True)
    app.processEvents()
    gbox0 = grp.sceneBoundingRect()
    kids0 = [c.sceneBoundingRect() for c in grp.childItems()]

    win.flip_selection("h")
    app.processEvents()
    gbox1 = grp.sceneBoundingRect()
    kids1 = [c.sceneBoundingRect() for c in grp.childItems()]

    check("group box keeps its centre and size",
          abs(gbox1.center().x() - gbox0.center().x()) < 1e-6 and
          abs(gbox1.width() - gbox0.width()) < 1e-6,
          f"centre {gbox0.center().x():.2f}->{gbox1.center().x():.2f}, "
          f"width {gbox0.width():.2f}->{gbox1.width():.2f}")

    cxg = gbox0.center().x()
    worst_g = 0.0
    for cb0, cb1 in zip(kids0, kids1):
        worst_g = max(worst_g, abs(cb1.left() - (2 * cxg - cb0.right())))
    check("every child inside the group mirrored", worst_g < 0.01,
          f"max deviation {worst_g:.4f} px")

# =====================================================================
print("\n15. Precision HUD: live X/Y readout at a constant screen size")
# =====================================================================
win.set_tool("vpen")
q = scene_pt((321.0, 654.0))
view.mouseMoveEvent(ev(MOVE, (321.0, 654.0)))
app.processEvents()
check("HUD appears while the pen tool is active", view._hud_item is not None)
txt = view._hud_item.toPlainText() if view._hud_item else ""
check("HUD shows the cursor coordinates",
      f"X {q.x():.1f}" in txt and f"Y {q.y():.1f}" in txt, repr(txt))

# a live path adds the pending segment's length + angle
draw_node((5000.0, 5000.0))
draw_node((5100.0, 5000.0))
view.mouseMoveEvent(ev(MOVE, (5200.0, 5000.0)))
app.processEvents()
txt = view._hud_item.toPlainText()
check("HUD adds length + angle while drawing", "\u0394" in txt and "\u2220" in txt,
      repr(txt))

# counter-scaled: constant screen size at any zoom
z0 = view.transform().m11()
s0 = view._hud_item.scale()
win._zoom(2.0)
view.mouseMoveEvent(ev(MOVE, (5200.0, 5000.0)))
app.processEvents()
s1 = view._hud_item.scale()
check("HUD stays the same size on screen when zooming",
      abs(s0 * z0 - 1.0) < 1e-6 and abs(s1 * view.transform().m11() - 1.0) < 1e-6,
      f"scale*zoom: {s0 * z0:.6f} then {s1 * view.transform().m11():.6f}")

win.set_tool("select")
app.processEvents()
check("HUD disappears when the tool changes", view._hud_item is None)

# =====================================================================
print("\n16. Exact numeric node placement (sidebar X / Y)")
# =====================================================================
# drawn far from everything else so the pen does not hit an existing path
win.set_tool("vpen")
draw_node((6000.0, 6000.0))
draw_node((6100.0, 6000.0))
draw_node((6200.0, 6100.0))
win.keyPressEvent(key(Qt.Key.Key_Return))
app.processEvents()
num_target = vpaths()[-1]

win.set_tool("nodeedit")
view._ne_item = num_target
view._ne_sel = {1}
view._ne_redraw()
app.processEvents()
check("X/Y boxes enable for a single selected node",
      win.node_x.isEnabled() and win.node_y.isEnabled(),
      f"enabled={win.node_x.isEnabled()}")
cur = num_target._payload["nodes"][1]["p"]
check("boxes show the node's current position",
      abs(win.node_x.value() - cur[0]) < 1e-9 and
      abs(win.node_y.value() - cur[1]) < 1e-9,
      f"({win.node_x.value()}, {win.node_y.value()}) vs {cur}")

win.node_x.setValue(6123.75)
win.node_y.setValue(5957.5)
app.processEvents()
p = num_target._payload["nodes"][1]["p"]
check("typing places the node exactly",
      abs(p[0] - 6123.75) < 1e-9 and abs(p[1] - 5957.5) < 1e-9,
      f"({p[0]}, {p[1]})")

end_pt = wb._vp_seg_bezier(num_target._payload["nodes"], 0)[3]
check("the rendered geometry followed the typed value",
      abs(end_pt.x() - 6123.75) < 1e-9 and abs(end_pt.y() - 5957.5) < 1e-9,
      f"({end_pt.x()}, {end_pt.y()})")

view._ne_sel = set()
view._ne_redraw()
app.processEvents()
check("boxes disable when no single node is selected",
      not win.node_x.isEnabled())

# =====================================================================
print("\n17. Curve tool: drag an anchor -> straight lines become curves")
# =====================================================================
# a dead-straight 3-point polyline, every node a corner with NO handles:
# exactly what the pen tool leaves behind after plain clicks.
STRAIGHT = [{"p": [8000.0, 8000.0], "out": None, "in": None, "t": "corner"},
            {"p": [8100.0, 8000.0], "out": None, "in": None, "t": "corner"},
            {"p": [8200.0, 8000.0], "out": None, "in": None, "t": "corner"}]
poly = make_vpath(STRAIGHT)
app.processEvents()
win.set_tool("curve")

mid_anchor = (8100.0, 8000.0)
q_drag = scene_pt((8100.0, 7900.0))
view.mousePressEvent(ev(PRESS, mid_anchor))
view.mouseMoveEvent(ev(MOVE, (8100.0, 7900.0)))
view.mouseReleaseEvent(ev(REL, (8100.0, 7900.0)))
app.processEvents()

pn = poly._payload["nodes"]
check("dragged anchor became smooth", pn[1]["t"] == "smooth", pn[1]["t"])
check("its handles are mirrored",
      pn[1]["out"] is not None and pn[1]["in"] is not None and
      abs(pn[1]["in"][0] + pn[1]["out"][0]) < 1e-9 and
      abs(pn[1]["in"][1] + pn[1]["out"][1]) < 1e-9,
      f"out={pn[1]['out']} in={pn[1]['in']}")
want = (q_drag.x() - mid_anchor[0], q_drag.y() - mid_anchor[1])
check("handle follows the drag vector",
      abs(pn[1]["out"][0] - want[0]) < 1e-9 and
      abs(pn[1]["out"][1] - want[1]) < 1e-9,
      f"out={pn[1]['out']} expected {want}")
check("the end anchors did not move",
      pn[0]["p"] == [8000.0, 8000.0] and pn[2]["p"] == [8200.0, 8000.0],
      f"{pn[0]['p']} / {pn[2]['p']}")

q2 = wb._vp_seg_bezier(pn, 0)[2]
q1 = wb._vp_seg_bezier(pn, 1)[1]
tin = (pn[1]["p"][0] - q2.x(), pn[1]["p"][1] - q2.y())
tout = (q1.x() - pn[1]["p"][0], q1.y() - pn[1]["p"][1])
dot = tin[0] * tout[0] + tin[1] * tout[1]
check("the bend is a real C1 curve, not a cusp", dot > 0, f"dot={dot:+.0f}")

# =====================================================================
print("\n18. Curve tool: drag a segment -> it bends, ends stay put")
# =====================================================================
STRAIGHT2 = [{"p": [9000.0, 9000.0], "out": None, "in": None, "t": "corner"},
             {"p": [9100.0, 9000.0], "out": None, "in": None, "t": "corner"}]
seg = make_vpath(STRAIGHT2)
app.processEvents()
win.set_tool("curve")

target = (9050.0, 8900.0)                 # pull the midpoint 100 px up
view.mousePressEvent(ev(PRESS, (9050.0, 9000.0)))
view.mouseMoveEvent(ev(MOVE, target))
view.mouseReleaseEvent(ev(REL, target))
app.processEvents()

sn = seg._payload["nodes"]
check("the two end anchors stayed exactly in place",
      sn[0]["p"] == [9000.0, 9000.0] and sn[1]["p"] == [9100.0, 9000.0],
      f"{sn[0]['p']} / {sn[1]['p']}")
check("the segment gained handles on both ends",
      sn[0]["out"] is not None and sn[1]["in"] is not None,
      f"out={sn[0]['out']} in={sn[1]['in']}")

# B(0.5) = (P0 + 3c1 + 3c2 + P3)/8, so adding 4d/3 to both controls puts the
# curve's midpoint exactly under the cursor. Verify that, not an approximation.
b_mid = wb._vp_point_on_seg(sn, 0, 0.5)
q_cursor = scene_pt(target)
err = math.hypot(b_mid.x() - q_cursor.x(), b_mid.y() - q_cursor.y())
check("the curve's midpoint lands exactly under the cursor", err < 1e-9,
      f"midpoint=({b_mid.x():.4f}, {b_mid.y():.4f}) "
      f"cursor=({q_cursor.x():.4f}, {q_cursor.y():.4f}) err={err:.2e}")

# it must still be one smooth arc, not a zig-zag
check("the bent segment is a clean single curve",
      abs(wb._vp_point_on_seg(sn, 0, 0.5).y() - q_cursor.y()) < 1e-9 and
      wb._vp_point_on_seg(sn, 0, 0.25).y() > q_cursor.y(),
      f"t=0.5 y={wb._vp_point_on_seg(sn, 0, 0.5).y():.2f}, "
      f"t=0.25 y={wb._vp_point_on_seg(sn, 0, 0.25).y():.2f}")

win.set_tool("select")

# =====================================================================
print("\n19. Sidebar scrolls, so the bottom panels stay reachable")
# =====================================================================
# The panel is ~1440 px tall and the layout refuses to shrink below ~1300, so
# on a short window the parent used to CLIP it: PROPERTIES, NODE X/Y, SWATCHES
# and the Shape Library button were unreachable.
from PySide6.QtWidgets import QScrollArea, QWidget as _QWidget

win.resize(1500, 900)
win.show()
app.processEvents()
sa = win.findChild(QScrollArea, "sidebarScroll")
check("the sidebar is wrapped in a scroll area", sa is not None)
if sa is not None:
    inner = sa.widget()
    check("the scroll area hosts the whole sidebar panel",
          inner is not None and inner.objectName() == "sidebar")
    bar = sa.verticalScrollBar()
    check("a vertical scrollbar exists and has room to travel",
          bar.maximum() > 0, f"maximum={bar.maximum()}")

    kids = [c for c in inner.findChildren(_QWidget) if c.parent() is inner]
    lowest = max(kids, key=lambda w: w.y())
    before = lowest.mapTo(sa.viewport(), lowest.rect().topLeft()).y()
    bar.setValue(bar.maximum())
    app.processEvents()
    after = lowest.mapTo(sa.viewport(), lowest.rect().topLeft()).y()
    vh = sa.viewport().height()
    check("the lowest widget scrolls into the visible area",
          0 <= after < vh,
          f"y {before} -> {after} in a {vh} px viewport")
    check("the new NODE X / Y boxes are inside the panel",
          win.node_x.parent() is inner and win.node_y.parent() is inner,
          f"parent={win.node_x.parent().objectName() if win.node_x.parent() else None}")

# =====================================================================
print("\n20. Break the handle: Alt on the last anchor -> straight line")
# =====================================================================
win.keyPressEvent(key(Qt.Key.Key_Escape))
win.set_tool("vpen")
# a smooth node needs press-drag, which is what gives it both handles
view.mousePressEvent(ev(PRESS, (2000.0, 2000.0)))
view.mouseReleaseEvent(ev(REL, (2000.0, 2000.0)))
view.mousePressEvent(ev(PRESS, (2100.0, 2000.0)))
view.mouseMoveEvent(ev(MOVE, (2140.0, 1960.0)))
view.mouseReleaseEvent(ev(REL, (2140.0, 1960.0)))
app.processEvents()

brk = vpaths()[-1]
nd = brk._payload["nodes"][-1]
check("press-drag produced a smooth node with both handles",
      nd["t"] == "smooth" and nd["in"] is not None and nd["out"] is not None,
      f"t={nd['t']} in={nd['in']} out={nd['out']}")
in_before = list(nd["in"])

# Alt+click straight on that anchor = break the pair
view.mousePressEvent(ev(PRESS, tuple(nd["p"]), Qt.KeyboardModifier.AltModifier))
view.mouseReleaseEvent(ev(REL, tuple(nd["p"]), Qt.KeyboardModifier.AltModifier))
app.processEvents()
nd = brk._payload["nodes"][-1]
check("Alt+click drops the outgoing handle", nd["out"] is None, f"out={nd['out']}")
check("the incoming handle is left untouched", nd["in"] == in_before,
      f"in {in_before} -> {nd['in']}")
check("the anchor is flagged asym, not smooth", nd["t"] == "asym", nd["t"])

# now continue with a plain click: that segment must be dead straight
view.mousePressEvent(ev(PRESS, (2300.0, 2000.0)))
view.mouseReleaseEvent(ev(REL, (2300.0, 2000.0)))
app.processEvents()
pn = brk._payload["nodes"]
seg = wb._vp_seg_bezier(pn, len(pn) - 2)
straight = (abs(seg[1].x() - seg[0].x()) < 1e-9 and
            abs(seg[1].y() - seg[0].y()) < 1e-9 and
            abs(seg[2].x() - seg[3].x()) < 1e-9 and
            abs(seg[2].y() - seg[3].y()) < 1e-9)
check("the next segment comes out a straight line", straight,
      f"c1=({seg[1].x():.2f},{seg[1].y():.2f}) c2=({seg[2].x():.2f},{seg[2].y():.2f}) "
      f"for ({seg[0].x():.1f},{seg[0].y():.1f})->({seg[3].x():.1f},{seg[3].y():.1f})")

# =====================================================================
print("\n21. Alt+DRAG pulls a fresh out handle without moving the in one")
# =====================================================================
view.mousePressEvent(ev(PRESS, (2400.0, 2000.0)))
view.mouseMoveEvent(ev(MOVE, (2440.0, 1960.0)))
view.mouseReleaseEvent(ev(REL, (2440.0, 1960.0)))
app.processEvents()
nd = brk._payload["nodes"][-1]
check("plain drag mirrors the pair (smooth)",
      nd["t"] == "smooth" and abs(nd["in"][0] + nd["out"][0]) < 1e-9,
      f"t={nd['t']} out={nd['out']} in={nd['in']}")

in_keep = list(nd["in"])
view.mousePressEvent(ev(PRESS, tuple(nd["p"]), Qt.KeyboardModifier.AltModifier))
q_drag = scene_pt((2500.0, 2060.0))
view.mouseMoveEvent(ev(MOVE, (2500.0, 2060.0), Qt.KeyboardModifier.AltModifier))
view.mouseReleaseEvent(ev(REL, (2500.0, 2060.0), Qt.KeyboardModifier.AltModifier))
app.processEvents()
nd = brk._payload["nodes"][-1]
want = [q_drag.x() - nd["p"][0], q_drag.y() - nd["p"][1]]
check("the out handle follows the Alt-drag",
      nd["out"] is not None and
      abs(nd["out"][0] - want[0]) < 1e-9 and abs(nd["out"][1] - want[1]) < 1e-9,
      f"out={nd['out']} expected {want}")
check("the in handle did NOT mirror the new out handle",
      nd["in"] == in_keep,
      f"in {in_keep} -> {nd['in']} (a mirror would be {-want[0]:.1f},{-want[1]:.1f})")
check("still flagged asym", nd["t"] == "asym", nd["t"])

# =====================================================================
print("\n22. The rubber preview tells the truth about the click")
# =====================================================================
# It used to add the PREVIOUS node's in-handle to the arriving control, so it
# drew a curve that a plain click never produced.
win.keyPressEvent(key(Qt.Key.Key_Escape))
win.set_tool("vpen")
view.mousePressEvent(ev(PRESS, (3000.0, 3000.0)))
view.mouseReleaseEvent(ev(REL, (3000.0, 3000.0)))
view.mousePressEvent(ev(PRESS, (3100.0, 3000.0)))
view.mouseMoveEvent(ev(MOVE, (3140.0, 3040.0)))
view.mouseReleaseEvent(ev(REL, (3140.0, 3040.0)))
app.processEvents()
prev_item = vpaths()[-1]

target = (3200.0, 3100.0)
view.mouseMoveEvent(ev(MOVE, target))              # idle hover = preview
app.processEvents()
rb = view._rubber_item.path()
p_c1 = rb.elementAt(1)
p_c2 = rb.elementAt(2)
p_end = rb.elementAt(3)

view.mousePressEvent(ev(PRESS, target))            # commit it
view.mouseReleaseEvent(ev(REL, target))
app.processEvents()
pn = prev_item._payload["nodes"]
seg = wb._vp_seg_bezier(pn, len(pn) - 2)
q = scene_pt(target)

check("the preview ends where the click lands",
      math.hypot(p_end.x - q.x(), p_end.y - q.y()) < 1e-6,
      f"preview end ({p_end.x:.2f},{p_end.y:.2f}) vs click ({q.x():.2f},{q.y():.2f})")
check("the preview's start control equals the committed one",
      abs(p_c1.x - seg[1].x()) < 1e-6 and abs(p_c1.y - seg[1].y()) < 1e-6,
      f"preview ({p_c1.x:.2f},{p_c1.y:.2f}) vs committed ({seg[1].x():.2f},{seg[1].y():.2f})")
check("the preview's end control equals the committed one",
      abs(p_c2.x - seg[2].x()) < 1e-6 and abs(p_c2.y - seg[2].y()) < 1e-6,
      f"preview ({p_c2.x:.2f},{p_c2.y:.2f}) vs committed ({seg[2].x():.2f},{seg[2].y():.2f})")
win.keyPressEvent(key(Qt.Key.Key_Escape))

# =====================================================================
print("\n23. Sidebar fits horizontally: both tool columns are reachable")
# =====================================================================
# Adding the scroll area exposed a trap: a QLabel without word wrap reports its
# whole text as minimumSizeHint, so setWidgetResizable handed the panel 570 px
# (then 392 px after wrapping) and clipped the surplus with no horizontal
# scrollbar. The second tool column - V-Pen, Curve - became unclickable.
sa2 = win.findChild(QScrollArea, "sidebarScroll")
inner2 = sa2.widget()
check("the panel is no wider than its viewport",
      inner2.width() <= sa2.viewport().width(),
      f"panel {inner2.width()} px vs viewport {sa2.viewport().width()} px")

vw = inner2.width()
edges = {}
for key, btn in win.tool_buttons.items():
    edges[key] = btn.mapTo(inner2, btn.rect().topRight()).x()
worst_key = max(edges, key=lambda k: edges[k])
check("every tool button sits inside the panel width",
      edges[worst_key] <= vw,
      f"rightmost is {worst_key} at {edges[worst_key]} px, panel is {vw} px")

for key in ("vpen", "nodeedit", "curve"):
    check(f"the {key} button is fully visible",
          edges[key] <= vw,
          f"right edge {edges[key]} px vs {vw} px")

check("the two tool columns do not overlap",
      win.tool_buttons["select"].mapTo(inner2, win.tool_buttons["select"].rect().topRight()).x()
      < win.tool_buttons["vpen"].mapTo(inner2, win.tool_buttons["vpen"].rect().topLeft()).x(),
      f"col0 ends {edges['select']}, col1 starts "
      f"{win.tool_buttons['vpen'].mapTo(inner2, win.tool_buttons['vpen'].rect().topLeft()).x()}")

# =====================================================================
print("\n24. Tool icons are actually rendered (they never were before)")
# =====================================================================
# The tool table carried a glyph field that nothing ever read, so every button
# was text-only. These checks fail loudly if the icons stop being drawn.
missing = [k for k, b in win.tool_buttons.items() if b.icon().isNull()]
check("every tool button has a non-null icon", not missing, f"missing: {missing}")

bad_size = [k for k, b in win.tool_buttons.items()
            if b.iconSize().width() < 16 or b.iconSize().height() < 16]
check("every button has a usable icon size", not bad_size, f"too small: {bad_size}")

check("the label sits under the icon",
      all(b.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextUnderIcon
          for b in win.tool_buttons.values()))

check("every button still carries its name as text",
      all(b.text().strip() for b in win.tool_buttons.values()),
      str([b.text() for b in win.tool_buttons.values()]))

# distinct tools must not share a picture (catches copy-paste in the drawing)
import hashlib
sigs = {}
for key in win.tool_buttons:
    img = wb.tool_icon(key, 32).pixmap(32, 32).toImage()
    sigs.setdefault(hashlib.md5(bytes(img.constBits())).hexdigest(), []).append(key)
dupes = [v for v in sigs.values() if len(v) > 1]
check("no two tools share the same icon", not dupes, f"duplicates: {dupes}")
check("all 17 tool icons are distinct",
      len(sigs) == len(win.tool_buttons),
      f"{len(sigs)} distinct for {len(win.tool_buttons)} tools")

# =====================================================================
print("\n" + "=" * 68)
if FAILS:
    print(f"  {len(FAILS)} FAILED: " + " | ".join(FAILS))
else:
    print("  all pen-tool checks passed")
print("=" * 68)
sys.exit(1 if FAILS else 0)
