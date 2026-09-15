"""Fix regression: plain click after smooth node = straight corner segment
(no inherited curvature); PDF/boolean/align buttons reachable."""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, Qt, QEvent
from PySide6.QtGui import QMouseEvent
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
                       Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, mods)

def V(sp): return QPointF(view.mapFromScene(QPointF(sp[0], sp[1])))

win.set_tool("vpen")

# 1) first node + drag (smooth), then a PLAIN click
view.mousePressEvent(ev(QEvent.Type.MouseButtonPress, V((100, 100))))
view.mousePressEvent(ev(QEvent.Type.MouseButtonPress, V((200, 100))))
view.mouseMoveEvent(ev(QEvent.Type.MouseMove, V((240, 80))))    # curve handle
view.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, V((240, 80))))
# now plain click at (300,100)
view.mousePressEvent(ev(QEvent.Type.MouseButtonPress, V((300, 100))))
view.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, V((300, 100))))
nodes = wq.pl_of(view._vp_item)["nodes"]
assert len(nodes) == 3
last = nodes[-1]
# FIX: plain click = corner, NO inherited handles
assert last["t"] == "corner", last
assert last["in"] is None and last["out"] is None, last
print("1 plain click after curve = corner (no inherited curvature) OK")

# 2) geometry: NEXT segment (from the plain-click corner) starts straight:
# its end control points are absent (c2 = p3 exactly)
mid_seg = wq._vp_point_on_seg(nodes, 1, 0.5)
p0, p1, p2, p3 = wq._vp_seg_bezier(nodes, 1)
assert abs(p2.x() - p3.x()) < 1e-9 and abs(p2.y() - p3.y()) < 1e-9  # no in-handle
assert nodes[-1]["in"] is None
print("2 segment ends straight at corner (no in-handle) OK")

# 3) continuing to draw: more plain clicks keep extending
for tx, ty in ((400, 100), (450, 150)):
    view.mousePressEvent(ev(QEvent.Type.MouseButtonPress, V((tx, ty))))
    view.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, V((tx, ty))))
assert len(wq.pl_of(view._vp_item)["nodes"]) == 5
view._vpen_finish(commit=True)
print("3 drawing continues from last point OK")

# 4) sidebar holds boolean/align now; toolbar got slimmer
#    The align and flip buttons are ICONS now (they used to be Unicode glyphs
#    like "⇤"), so identify them by tooltip - the glyph text is gone by design.
BTN = type(win.color_btn)
tb_buttons = [b.text() for b in win._tb.findChildren(BTN)]
assert not any(t in ("∪", "∩") for t in tb_buttons), tb_buttons
side = win.centralWidget().findChildren(BTN)
side_text = [b.text() for b in side]
side_tips = [b.toolTip() for b in side]
assert any("∪" in t for t in side_text), side_text
assert any(t.startswith("Align left") for t in side_tips), side_tips
assert any(t.startswith("Flip horizontally") for t in side_tips), side_tips
print("4 boolean/align/flip are in the sidebar OK")

# 5) PDF In still present in toolbar
assert any("PDF" in t for t in tb_buttons), tb_buttons
print("5 PDF In reachable in toolbar OK")

win.set_tool("select")
print("PEN FIX SUITE PASSED — 5/5 green")
