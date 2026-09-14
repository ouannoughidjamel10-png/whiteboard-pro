"""P6b: pen-tool math spec — Shift-lock on handle drag, Space anchor-move
during press, Ctrl momentary direct-select, rule-of-thirds guide."""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, Qt, QEvent
from PySide6.QtGui import QMouseEvent, QKeyEvent
from PySide6.QtWidgets import QApplication
import whiteboard_qt as wq

app = QApplication([])
app.setStyleSheet(wq.QSS)
win = wq.MainWindow()
win.resize(1400, 900)
win.show()
view = win.view

def ev(t, pos, mods=Qt.KeyboardModifier.NoModifier):
    return QMouseEvent(t, QPointF(pos), QPointF(pos),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                       mods)

def V(sp): return QPointF(view.mapFromScene(QPointF(sp[0], sp[1])))

def key(k, m=Qt.KeyboardModifier.NoModifier):
    return QKeyEvent(QEvent.Type.KeyPress, k, m)

win.set_tool("vpen")

# --- mathematical ground truth: B(t) formula --------------------------------
P0, P1, P2, P3 = (0, 0), (1, 2), (3, 3), (4, 0)
def B(t):
    u = 1 - t
    return (u*u*u*P0[0] + 3*u*u*t*P1[0] + 3*u*t*t*P2[0] + t*t*t*P3[0],
            u*u*u*P0[1] + 3*u*u*t*P1[1] + 3*u*t*t*P2[1] + t*t*t*P3[1])
# our engine must reproduce it via _vp_point_on_seg
# HANDLE CONVENTION: out = ctrl - anchor AND in = ctrl - anchor (same sign).
# So the arriving control P2 is reached with  inn = P2 - P3.
nodes = [wq._vp_node(P0, out=[P1[0]-P0[0], P1[1]-P0[1]]),
         wq._vp_node(P3, inn=[P2[0]-P3[0], P2[1]-P3[1]], t="smooth")]
for t in (0.0, 0.25, 0.5, 0.75, 1.0):
    qt = wq._vp_point_on_seg(nodes, 0, t)
    bx, by = B(t)
    assert math.hypot(qt.x() - bx, qt.y() - by) < 1e-9, (t, qt, bx, by)
print("1 cubic Bezier B(t) exact match OK")

# --- REAL C1 continuity: mirror a handle and measure the tangents ----------
# Regression guard for the sign bug: a smooth node used to be a 180-degree
# cusp because the geometry helpers did anchor - in while everything else
# stored in = ctrl - anchor.
def tangents_at(nodes, i):
    """(incoming tangent, outgoing tangent) at interior node i."""
    p2 = wq._vp_seg_bezier(nodes, i - 1)[2]
    p1 = wq._vp_seg_bezier(nodes, i)[1]
    p = nodes[i]["p"]
    return ((p[0] - p2.x(), p[1] - p2.y()), (p1.x() - p[0], p1.y() - p[1]))

mid = wq._vp_node((300.0, 0.0), out=(100.0, 0.0), inn=(-100.0, 0.0), t="smooth")
chain = [wq._vp_node((0.0, 0.0), out=(100.0, 0.0)),
         mid,
         wq._vp_node((600.0, 0.0), inn=(-100.0, 0.0), t="smooth")]
tin, tout = tangents_at(chain, 1)
cross = tin[0] * tout[1] - tin[1] * tout[0]
dot = tin[0] * tout[0] + tin[1] * tout[1]
assert dot > 0, f"smooth node has a cusp: dot={dot} (in-handle mirrored wrong)"
assert abs(cross) < 1e-9, f"handles not collinear: cross={cross}"
print(f"2 C1 continuity at a smooth node OK (dot={dot:+.0f}, cross={cross:+.1e})")

# the arriving control of segment 0 must sit at 300 + (-100) = 200, i.e. on the
# OPPOSITE side of the anchor from the out-handle at 400.
c2x = wq._vp_seg_bezier(chain, 0)[2].x()
assert abs(c2x - 200.0) < 1e-9, f"arriving control is at {c2x}, expected 200"
print("3 arriving control lands on the correct side of the anchor OK")

# --- Shift lock on HANDLE drag (45 degrees) ---------------------------------
view.mousePressEvent(ev(QEvent.Type.MouseButtonPress, V((200, 200))))
view.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, V((200, 200))))
view.mousePressEvent(ev(QEvent.Type.MouseButtonPress, V((300, 200))))
# drag handle to a ~37-degree position WITH shift
view.mouseMoveEvent(ev(QEvent.Type.MouseMove, V((300 + 28, 200 + 21)),
                       Qt.KeyboardModifier.ShiftModifier))
pl = wq.pl_of(view._vp_item)
out = pl["nodes"][-1]["out"]
ang = math.degrees(math.atan2(out[1], out[0])) % 45
assert abs(ang) < 1e-6 or abs(ang - 45) < 1e-6, (out, ang)
view.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease,
                          V((300 + 28, 200 + 21))))
print(f"4 Shift handle-lock 45 OK (out={out[0]:.1f},{out[1]:.1f})")

# --- Space during press: move the anchor itself -----------------------------
view.mousePressEvent(ev(QEvent.Type.MouseButtonPress, V((400, 300))))
assert view._vp_drag_node == ["out", len(pl["nodes"]) - 1]
win.keyPressEvent(key(Qt.Key.Key_Space))          # hold space
assert view._vp_drag_node[0] == "anchor"
view.mouseMoveEvent(ev(QEvent.Type.MouseMove, V((450, 340))))
nd = wq.pl_of(view._vp_item)["nodes"][-1]
assert abs(nd["p"][0] - 450) < 1 and abs(nd["p"][1] - 340) < 1, nd["p"]
win.keyReleaseEvent(QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Space,
                              Qt.KeyboardModifier.NoModifier))
assert view._vp_drag_node[0] == "out"             # back to handle mode
view.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, V((450, 340))))
print("5 Space anchor-move OK")

# --- Ctrl momentary direct-select -------------------------------------------
nodes_pl = wq.pl_of(view._vp_item)["nodes"]
target = nodes_pl[0]["p"]
view.mouseMoveEvent(ev(QEvent.Type.MouseMove, V((target[0] + 3, target[1] + 3)),
                       Qt.KeyboardModifier.ControlModifier))
assert view._quick_drag_idx == 0
view.mouseMoveEvent(ev(QEvent.Type.MouseMove, V((120, 210)),
                       Qt.KeyboardModifier.ControlModifier))
nd0 = wq.pl_of(view._vp_item)["nodes"][0]
assert abs(nd0["p"][0] - 120) < 1 and abs(nd0["p"][1] - 210) < 1
view.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, V((120, 210))))
assert view._quick_drag_idx is None
print("6 Ctrl momentary direct-select OK")

# --- rule of thirds guide while dragging ------------------------------------
win.keyPressEvent(key(Qt.Key.Key_Escape))          # clean session first
view.mousePressEvent(ev(QEvent.Type.MouseButtonPress, V((600, 500))))
view.mouseMoveEvent(ev(QEvent.Type.MouseMove, V((600, 500))))
view.mousePressEvent(ev(QEvent.Type.MouseButtonPress, V((700, 500))))
view.mouseMoveEvent(ev(QEvent.Type.MouseMove, V((730, 520))))  # handle drag
rb = view._rubber_item.path()
found = False
dbg = [(round(rb.elementAt(i).x, 1), round(rb.elementAt(i).y, 1))
       for i in range(rb.elementCount())]
for ex, ey in dbg:
    # ellipse elements ring the centre (710, 506.7) within radius ~3
    if math.hypot(ex - (700 + 30 / 3), ey - (500 + 20 / 3)) < 4.5:
        found = True
        break
for i in range(rb.elementCount()):
    e = rb.elementAt(i)
    # thirds from the LAST node (700,500) toward cursor (730,520)
    if abs(e.x - (700 + (730 - 700) / 3)) < 3 and abs(e.y - (500 + (520 - 500) / 3)) < 3:
        found = True
        break
assert found, "thirds marker missing"
view.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, V((730, 520))))
win.keyPressEvent(key(Qt.Key.Key_Escape))
print("7 rule-of-thirds guide OK")

print("PEN MATH SPEC SUITE PASSED — 7/7 green")
