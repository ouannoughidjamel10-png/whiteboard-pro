# -*- coding: utf-8 -*-
"""
nav_tools.py — Professional navigation toolkit for Interactive Whiteboard Pro (Qt edition)

Clean-room re-implementation of the navigation tool family that ships with
Adobe Illustrator (internally named "Adobe Scroll Tool" = the Hand/Pan tool,
plus its flyout companions: Zoom Tool, Rotate Canvas Tool, and the Navigator
panel).

WHY THIS FILE EXISTS
--------------------
The stock implementation panned by nudging integer scrollbar values:

    h.setValue(h.value() - int(delta.x()))

Measured problems (verified on PySide6 6.11 with an offscreen harness):

  1. `int()` truncation loses up to 1 px per mouse-move event. Over a long
     drag the canvas lags behind the pointer -> "rubbery" feel.
  2. It stops working entirely when the content is smaller than the viewport
     (scrollbars have no range) -> you cannot pan an empty board.
  3. It cannot express canvas rotation, and `transform().m11()` stops being
     the zoom factor as soon as rotation is introduced.
  4. QGraphicsView *re-normalises* the scrollbars after `setTransform()`, so
     panning by mutating the transform alone is silently cancelled.

THE FIX — an "infinite canvas" viewport we own:
  * the scene rect is grown to a huge fixed box and the scrollbars are hidden
    (they are meaningless on an infinite canvas, and Illustrator-style
    navigation does not need them);
  * the full scene -> view transform is stored as (zoom, rotation, anchor)
    and applied with exact float precision;
  * every operation re-asserts an anchor invariant, so any offset Qt injects
    is measured and cancelled automatically.

FIVE GOLDEN RULES (these are what make it *feel* professional)
  R1  Panning is strictly 1:1 with the pointer, in screen pixels, full float
      precision. No easing, no acceleration, no integer truncation.
  R2  Zooming pins the scene point under the cursor to the cursor.
  R3  Panning follows the SCREEN axes even when the canvas is rotated.
  R4  View changes are NEVER pushed on the undo stack.
  R5  Space bar and the middle button give a TEMPORARY pan override that
      never destroys an in-progress stroke, and always restores the previous
      tool and cursor.

Drop-in usage: see PATCH-NOTES at the bottom of this file.
"""

from __future__ import annotations

import math

from PySide6.QtCore import (QEvent, QObject, QPoint, QPointF, QRect, QRectF,
                            QSize, Qt, Signal)
from PySide6.QtGui import (QBrush, QColor, QCursor, QPainter, QPen, QPixmap,
                           QTransform)
from PySide6.QtWidgets import (QApplication, QGraphicsView, QLineEdit,
                               QPlainTextEdit, QRubberBand, QSizePolicy,
                               QTextEdit, QWidget)

# --------------------------------------------------------------------------
# Tunables
# --------------------------------------------------------------------------

#: Illustrator's zoom ladder, as fractions (3.13 % ... 6400 %).
ZOOM_STEPS = (0.0313, 0.0417, 0.0625, 0.0833, 0.125, 0.1667, 0.25, 0.3333,
              0.5, 0.6667, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0,
              24.0, 32.0, 64.0)

MIN_ZOOM = 0.02           # 2 %
MAX_ZOOM = 64.0           # 6400 %

#: Continuous wheel zoom per 120 "degrees" (one standard mouse notch).
WHEEL_ZOOM_BASE = 1.15
#: Snap to exactly 100 % when we land this close (Illustrator does this).
SNAP_100_TOLERANCE = 0.02

#: "zoom"   -> plain wheel zooms at the cursor (whiteboard-friendly, default)
#: "scroll" -> plain wheel scrolls; Ctrl/Alt/Cmd+wheel zooms (Illustrator default)
WHEEL_MODE = "zoom"
WHEEL_SCROLL_SPEED = 1.0  # px of scroll per wheel degree

#: Arrow-key nudge, in screen px. Shift multiplies by NUDGE_BIG_FACTOR.
NUDGE_PX = 20.0
NUDGE_BIG_FACTOR = 5.0
#: PageUp / PageDown scroll, as a fraction of the viewport height.
PAGE_FRACTION = 0.9

#: Half-size of the virtual canvas, in scene units.
CANVAS_HALF = 500_000.0

CURSOR_HAND_OPEN = Qt.CursorShape.OpenHandCursor
CURSOR_HAND_CLOSED = Qt.CursorShape.ClosedHandCursor
CURSOR_ZOOM = Qt.CursorShape.CrossCursor
CURSOR_ROTATE = Qt.CursorShape.SizeAllCursor


# --------------------------------------------------------------------------
# Viewport model
# --------------------------------------------------------------------------

class NavViewport(QObject):
    """Exact, rotation-aware scene <-> view mapping for a QGraphicsView.

    The model owns only (zoom, rotation).  Position is NEVER stored as an
    absolute translation, because QGraphicsView does not let us own it:
    measured on PySide6 6.11, `setTransform(QTransform().translate(94, 79))`
    comes back as `transform().m31() == 0` with the 94/79 folded into the
    internal scroll offset instead.  Any absolute-translation model therefore
    silently disagrees with `mapToScene()`, which is what all the drawing
    tools read.

    So the rule is:

      * READS always go through `view.viewportTransform()` — the one true
        scene -> view mapping, identical to what `mapToScene()` uses.
      * WRITES are always RELATIVE to the current transform
        (`transform := T(d) * transform`), which Qt leaves alone because a
        pure translation does not change the scrollbar range.

    Every operation then re-measures the result and corrects any residual
    error, so we are immune to whatever re-normalisation Qt performs.
    """

    changed = Signal(float)

    def __init__(self, view: QGraphicsView):
        super().__init__(view)
        self.view = view
        self._z = 1.0
        self._rot = 0.0
        self._as = QPointF()      # anchor, scene coords
        self._av = QPointF()      # anchor, view coords (screen px)
        self.install_canvas()
        self._normalize()
        self._av = self.center()
        self._as = self.to_scene(self._av)
        self._apply()
        view.viewport().installEventFilter(self)

    # ---------------------------------------------------------- installation
    def install_canvas(self):
        """Turn the view into an infinite canvas owned by this model."""
        v = self.view
        v.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        v.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        # Scrollbars are meaningless (and harmful) on an infinite canvas.
        v.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        v.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sc = v.scene()
        if sc is None:
            return
        cur = sc.sceneRect()
        # Only ever GROW the scene rect, so we never disturb loaded documents.
        if cur.width() < CANVAS_HALF or cur.height() < CANVAS_HALF:
            sc.setSceneRect(QRectF(-CANVAS_HALF, -CANVAS_HALF,
                                   2 * CANVAS_HALF, 2 * CANVAS_HALF))

    # ------------------------------------------------------------- plumbing
    def center(self) -> QPointF:
        r = self.view.viewport().rect()
        return QPointF(r.width() / 2.0, r.height() / 2.0)

    def viewport_transform(self) -> QTransform:
        """The one true scene -> view mapping (what mapToScene() uses)."""
        return self.view.viewportTransform()

    def to_scene(self, p) -> QPointF:
        """View pixels -> scene units (float exact, rotation aware)."""
        inv, _ok = self.viewport_transform().inverted()
        return inv.map(QPointF(p))

    def to_view(self, p) -> QPointF:
        """Scene units -> view pixels (float exact, rotation aware)."""
        return self.viewport_transform().map(QPointF(p))

    def _normalize(self):
        """Fold any scroll offset Qt introduced back into our transform.

        QGraphicsView renders with
            viewportTransform() = Translate(-scroll) * transform()
        and it freely shuffles translation between the two — measured on
        PySide6 6.11, `setTransform(Translate(94, 79))` came back with
        `transform().m31() == 0` and `scroll == -94`.

        That shuffling is harmless for rendering, but it breaks any model
        that stores its own translation.  So we force `scroll` to 0 and move
        the equivalent translation into `transform()`.  `viewportTransform()`
        — and therefore `mapToScene()`, which every drawing tool uses — is
        left bit-for-bit unchanged.
        """
        h, vv = self.view.horizontalScrollBar(), self.view.verticalScrollBar()
        for _ in range(4):
            sx, sy = h.value(), vv.value()
            if sx == 0 and sy == 0:
                return
            self.view.setTransform(
                QTransform().translate(-sx, -sy) * self.view.transform())
            h.setValue(0)
            vv.setValue(0)

    def _apply(self):
        """Push (zoom, rotation, anchor) into the view, then verify."""
        self._normalize()
        m = (QTransform()
             .translate(self._av.x(), self._av.y())
             .rotate(self._rot)
             .scale(self._z, self._z)
             .translate(-self._as.x(), -self._as.y()))
        self.view.setTransform(m)
        self._normalize()
        # Safety net: re-assert the anchor invariant by measurement.  With
        # scroll pinned at 0 this is a no-op; it costs 1 compare otherwise.
        for _ in range(4):
            err = self._av - self.to_view(self._as)
            if abs(err.x()) < 1e-7 and abs(err.y()) < 1e-7:
                break
            self.view.setTransform(
                QTransform().translate(err.x(), err.y())
                * self.view.transform())
            self._normalize()
        self.changed.emit(self._z)

    def _reanchor(self):
        """Re-express the anchor at the viewport centre (keeps numbers sane)."""
        self._normalize()
        self._av = self.center()
        self._as = self.to_scene(self._av)

    # ------------------------------------------------------------- readouts
    @property
    def zoom(self) -> float:
        return self._z

    @property
    def rotation(self) -> float:
        return self._rot

    def visible_rect(self) -> QRectF:
        """Scene rect currently visible (axis-aligned bounding box)."""
        r = self.view.viewport().rect()
        return QRectF(self.to_scene(QPointF(r.topLeft())),
                      self.to_scene(QPointF(r.bottomRight()))).normalized()

    # -------------------------------------------------------------- panning
    def eventFilter(self, obj, ev):
        """Keep the centred scene point stable when the viewport resizes."""
        try:
            if (obj is self.view.viewport()
                    and ev.type() == QEvent.Type.Resize):
                old, new = ev.oldSize(), ev.size()
                if old.isValid() and not old.isEmpty() and not new.isEmpty():
                    old_centre = QPointF(old.width() / 2.0, old.height() / 2.0)
                    if old_centre != self.center():
                        self.pan_to(self.to_scene(old_centre), self.center())
        except RuntimeError:
            pass                      # view already torn down
        return False

    def shift_view(self, dx: float, dy: float):
        """Move the CONTENT by (dx, dy) screen pixels — strictly 1:1.

        This is the heart of the Pan tool: content tracks the pointer exactly.
        """
        self._av = QPointF(self._av.x() + dx, self._av.y() + dy)
        self._apply()
        self._reanchor()

    def pan_to(self, scene_pt: QPointF, view_pt: QPointF | None = None):
        """Put scene point `scene_pt` at view point `view_pt` (default centre)."""
        target = QPointF(view_pt) if view_pt is not None else self.center()
        cur = self.to_view(scene_pt)
        self.shift_view(target.x() - cur.x(), target.y() - cur.y())

    def center_on(self, scene_pt: QPointF):
        self.pan_to(scene_pt, self.center())

    def nudge(self, dx: float, dy: float):
        """Arrow-key style nudge in screen px (view moves, content opposes)."""
        self.shift_view(-dx, -dy)

    def scroll_page(self, direction: int):
        h = self.view.viewport().height() * PAGE_FRACTION
        self.nudge(0.0, h * direction)

    # --------------------------------------------------------------- zooming
    def zoom_at(self, anchor, new_zoom: float):
        """Zoom so the scene point under `anchor` stays under `anchor`."""
        z = max(MIN_ZOOM, min(MAX_ZOOM, float(new_zoom)))
        if abs(z - 1.0) < SNAP_100_TOLERANCE:
            z = 1.0
        p = self.to_scene(anchor)
        self._z = z
        self._apply()
        q = self.to_view(p)
        self.shift_view(float(anchor.x()) - q.x(), float(anchor.y()) - q.y())

    def set_zoom(self, z: float, anchor=None):
        self.zoom_at(self.center() if anchor is None else anchor, z)

    def step_zoom(self, anchor, direction: int):
        """Walk Illustrator's zoom ladder one notch up (+1) or down (-1)."""
        cur = self._z
        if direction > 0:
            nxt = next((s for s in ZOOM_STEPS if s > cur * 1.001), ZOOM_STEPS[-1])
        else:
            nxt = next((s for s in reversed(ZOOM_STEPS) if s < cur * 0.999),
                       ZOOM_STEPS[0])
        self.zoom_at(anchor, nxt)

    def actual_size(self, anchor=None):
        """100 % (Illustrator Ctrl+1)."""
        self.zoom_at(self.center() if anchor is None else anchor, 1.0)

    def zoom_to_rect(self, view_rect: QRectF):
        r = view_rect.normalized()
        if r.width() < 4 or r.height() < 4:
            return
        vp = self.view.viewport().rect()
        z = min(vp.width() / r.width(), vp.height() / r.height())
        c = QPointF(r.center())
        self._z = max(MIN_ZOOM, min(MAX_ZOOM, self._z * z))
        self._apply()                       # keeps the centre point
        self.center_on(self.to_scene(c))

    def fit(self, scene_rect: QRectF | None = None, margin: float = 60.0):
        """Fit content (or an explicit rect) in the window — uniform scale."""
        sc = self.view.scene()
        if sc is None:
            return
        r = scene_rect if scene_rect is not None else sc.itemsBoundingRect()
        if r is None or r.isEmpty():
            self.zoom_at(self.center(), 1.0)
            return
        r = QRectF(r).adjusted(-margin, -margin, margin, margin)
        vp = self.view.viewport().rect()
        if vp.width() <= 0 or vp.height() <= 0 or r.width() <= 0 or r.height() <= 0:
            return
        z = min(vp.width() / r.width(), vp.height() / r.height())
        # Uniform scale first, then centre — never IgnoreAspectRatio.
        self._z = max(MIN_ZOOM, min(MAX_ZOOM, z))
        self._apply()
        self.center_on(QPointF(r.center()))

    # ------------------------------------------------------------- rotation
    def rotate_at(self, anchor, degrees: float):
        p = self.to_scene(anchor)
        self._rot = float(degrees) % 360.0
        self._apply()
        q = self.to_view(p)
        self.shift_view(float(anchor.x()) - q.x(), float(anchor.y()) - q.y())

    def rotate_by(self, delta_deg: float, anchor=None):
        self.rotate_at(self.center() if anchor is None else anchor,
                       self._rot + delta_deg)

    def reset_rotation(self, anchor=None):
        self.rotate_at(self.center() if anchor is None else anchor, 0.0)


# --------------------------------------------------------------------------
# Navigation controller — the tool behaviours
# --------------------------------------------------------------------------

class NavigationController(QObject):
    """Handles Pan / Zoom / Rotate-Canvas for a BoardView.

    The host view calls :meth:`press`, :meth:`move`, :meth:`release`,
    :meth:`wheel`, :meth:`key_press`, :meth:`key_release` and
    :meth:`double_click`. Each returns True when the event was consumed.
    """

    NAV_TOOLS = ("hand", "zoom", "rotate_canvas")

    def __init__(self, view: QGraphicsView, get_tool, on_status=None):
        super().__init__(view)
        self.view = view
        self.vp = NavViewport(view)
        self._get_tool = get_tool
        self._on_status = on_status or (lambda msg: None)

        self._space = False
        self._panning = False
        self._pan_last = QPointF()
        self._rotating = False
        self._rot_base = 0.0
        self._rot_start = 0.0
        self._marquee: QRubberBand | None = None
        self._marquee_start = QPointF()
        self._marquee_out = False
        self._saved_cursor: QCursor | None = None
        self._cursor_overridden = False

    # ------------------------------------------------------------- helpers
    def tool(self):
        return self._get_tool()

    @staticmethod
    def _is_text_focus() -> bool:
        w = QApplication.focusWidget()
        return isinstance(w, (QLineEdit, QTextEdit, QPlainTextEdit))

    def _set_cursor(self, shape):
        if not self._cursor_overridden:
            self._saved_cursor = self.view.cursor()
            self._cursor_overridden = True
        self.view.setCursor(shape)

    def _restore_cursor(self):
        if self._cursor_overridden:
            self.view.setCursor(self._saved_cursor
                                if self._saved_cursor is not None
                                else Qt.CursorShape.ArrowCursor)
            self._cursor_overridden = False
            self._saved_cursor = None

    def _cursor_for_tool(self):
        t = self.tool()
        if t == "hand":
            return CURSOR_HAND_OPEN
        if t == "zoom":
            return CURSOR_ZOOM
        if t == "rotate_canvas":
            return CURSOR_ROTATE
        return None

    def tool_changed(self, key=None):
        """Call from the host's set_tool() so cursors stay in sync."""
        cur = self._cursor_for_tool()
        if cur is None:
            self._restore_cursor()
        else:
            self._set_cursor(cur)

    def _status(self):
        self._on_status(f"{int(round(self.vp.zoom * 100))} %"
                        + (f"  rot {self.vp.rotation:.1f} deg"
                           if abs(self.vp.rotation) > 0.05 else ""))

    # ------------------------------------------------------------- pointers
    def press(self, e) -> bool:
        btn = e.button()
        if btn == Qt.MouseButton.MiddleButton:
            self._start_pan(e.position())
            return True
        if btn != Qt.MouseButton.LeftButton:
            return False
        if self._space:
            self._start_pan(e.position())
            return True
        t = self.tool()
        if t == "hand":
            self._start_pan(e.position())
            return True
        if t == "zoom":
            out = bool(e.modifiers() & Qt.KeyboardModifier.AltModifier)
            self._start_marquee(e.position(), out)
            return True
        if t == "rotate_canvas":
            self._start_rotate(e.position())
            return True
        return False

    def move(self, e) -> bool:
        if self._panning:
            p = QPointF(e.position())
            self.vp.shift_view(p.x() - self._pan_last.x(),
                               p.y() - self._pan_last.y())
            self._pan_last = p
            return True
        if self._rotating:
            c = self.vp.center()
            p = QPointF(e.position())
            a = math.degrees(math.atan2(p.y() - c.y(), p.x() - c.x()))
            self.vp.rotate_at(c, self._rot_base + (a - self._rot_start))
            self._status()
            return True
        if self._marquee is not None:
            r = QRectF(self._marquee_start, QPointF(e.position())).normalized()
            self._marquee.setGeometry(r.toRect())
            return True
        return False

    def release(self, e) -> bool:
        if self._panning:
            self._panning = False
            if self._space or self.tool() == "hand":
                self._set_cursor(CURSOR_HAND_OPEN)
            else:
                self._restore_cursor()
            return True
        if self._rotating:
            self._rotating = False
            self._status()
            return True
        if self._marquee is not None:
            r = QRectF(self._marquee_start, QPointF(e.position())).normalized()
            self._marquee.hide()
            self._marquee.deleteLater()
            self._marquee = None
            if r.width() > 6 and r.height() > 6:
                sr = QRectF(self.vp.to_scene(r.topLeft()),
                            self.vp.to_scene(r.bottomRight()))
                self.vp.fit(sr, margin=0.0)
            else:
                self.vp.step_zoom(QPointF(e.position()),
                                  -1 if self._marquee_out else 1)
            self._status()
            return True
        return False

    def double_click(self, e) -> bool:
        t = self.tool()
        if t == "hand":
            self.vp.fit()
            self._status()
            return True
        if t == "zoom":
            self.vp.actual_size(QPointF(e.position()))
            self._status()
            return True
        if t == "rotate_canvas":
            self.vp.reset_rotation()
            self._status()
            return True
        return False

    # ------------------------------------------------------------ internals
    def _start_pan(self, pos):
        self._panning = True
        self._pan_last = QPointF(pos)
        self._set_cursor(CURSOR_HAND_CLOSED)

    def _start_rotate(self, pos):
        c = self.vp.center()
        self._rotating = True
        self._rot_base = self.vp.rotation
        self._rot_start = math.degrees(
            math.atan2(float(pos.y()) - c.y(), float(pos.x()) - c.x()))
        self._set_cursor(CURSOR_ROTATE)

    def _start_marquee(self, pos, zoom_out=False):
        self._marquee_out = zoom_out
        self._marquee_start = QPointF(pos)
        self._marquee = QRubberBand(QRubberBand.Shape.Rectangle,
                                    self.view.viewport())
        self._marquee.setGeometry(QRect(QPoint(pos.toPoint()), QSize()))
        self._marquee.show()

    # ---------------------------------------------------------------- wheel
    def wheel(self, e) -> bool:
        mods = e.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        pos = QPointF(e.position())
        ang = e.angleDelta()

        zoom_requested = (WHEEL_MODE == "zoom") or ctrl or alt
        if not zoom_requested:
            # Illustrator default: wheel scrolls, Shift+wheel scrolls sideways.
            if shift:
                step = ang.x() or ang.y()
                self.vp.shift_view(-step * WHEEL_SCROLL_SPEED, 0.0)
            else:
                self.vp.nudge(0.0, -ang.y() * WHEEL_SCROLL_SPEED
                              - ang.x() * 0.0)
            e.accept()
            self._status()
            return True

        if shift and not (ctrl or alt):
            step = ang.y() or ang.x()
            self.vp.shift_view(-step * WHEEL_SCROLL_SPEED, 0.0)
            e.accept()
            return True

        d = ang.y() if ang.y() != 0 else ang.x()
        if d == 0:
            e.accept()
            return True
        factor = WHEEL_ZOOM_BASE ** (d / 120.0)
        self.vp.zoom_at(pos, self.vp.zoom * factor)
        e.accept()
        self._status()
        return True

    # ------------------------------------------------------------- keyboard
    def key_press(self, e) -> bool:
        if self._is_text_focus():
            return False
        k = e.key()
        mods = e.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)

        # ---- temporary Pan override (Illustrator "tool suspended by spacebar")
        if k == Qt.Key.Key_Space:
            if self.tool() in ("vpen", "nodeedit"):
                return False          # the host owns Space for those tools
            if not e.isAutoRepeat():
                self._space = True
                self._set_cursor(CURSOR_HAND_OPEN)
            return True               # consume: never activate a focused button

        if k in (Qt.Key.Key_Left, Qt.Key.Key_Right,
                 Qt.Key.Key_Up, Qt.Key.Key_Down):
            step = NUDGE_PX * (NUDGE_BIG_FACTOR if shift else 1.0)
            dx = step if k == Qt.Key.Key_Right else (
                -step if k == Qt.Key.Key_Left else 0.0)
            dy = step if k == Qt.Key.Key_Down else (
                -step if k == Qt.Key.Key_Up else 0.0)
            self.vp.nudge(dx, dy)
            return True

        if k in (Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
            self.vp.scroll_page(1 if k == Qt.Key.Key_PageDown else -1)
            return True

        if k == Qt.Key.Key_Home:
            r = self.view.scene().itemsBoundingRect() if self.view.scene() else QRectF()
            if not r.isEmpty():
                self.vp.center_on(QPointF(r.center().x(), r.top()))
            return True
        if k == Qt.Key.Key_End:
            r = self.view.scene().itemsBoundingRect() if self.view.scene() else QRectF()
            if not r.isEmpty():
                self.vp.center_on(QPointF(r.center().x(), r.bottom()))
            return True

        # ---- Zoom tool modifiers: Ctrl/Cmd = zoom-out, Alt = zoom-out
        if self.tool() == "zoom" and k in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.vp.step_zoom(self.vp.center(), -1 if ctrl else 1)
            self._status()
            return True
        if self.tool() == "zoom" and k == Qt.Key.Key_Minus:
            self.vp.step_zoom(self.vp.center(), -1)
            self._status()
            return True
        return False

    def key_release(self, e) -> bool:
        if e.key() == Qt.Key.Key_Space:
            if self._space:
                self._space = False
                if self._panning:
                    self._panning = False
                cur = self._cursor_for_tool()
                if cur is not None:
                    self._set_cursor(cur)
                else:
                    self._restore_cursor()
            return True
        return False


# --------------------------------------------------------------------------
# Navigator panel (Illustrator's "AdobeNavigator")
# --------------------------------------------------------------------------

class NavigatorPanel(QWidget):
    """Thumbnail of the board with a draggable view rectangle.

    Click or drag inside to recentre the view; the red rectangle always shows
    what the main canvas is currently displaying.
    """

    def __init__(self, view: QGraphicsView, vp: NavViewport,
                 width=190, height=140):
        super().__init__()
        self.view = view
        self.vp = vp
        self.setFixedSize(width, height)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setToolTip("Navigator — drag to move the view")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dragging = False
        vp.changed.connect(self.update)

    # ------------------------------------------------------------- mapping
    def _world(self) -> QRectF:
        sc = self.view.scene()
        if sc is None:
            return QRectF(0, 0, 1, 1)
        r = sc.itemsBoundingRect()
        vis = self.vp.visible_rect()
        if r.isEmpty():
            r = vis
        r = QRectF(r).united(vis)
        pad = max(r.width(), r.height()) * 0.05 + 1.0
        return r.adjusted(-pad, -pad, pad, pad)

    def _to_panel(self, p: QPointF) -> QPointF:
        w = self._world()
        return QPointF((p.x() - w.left()) / w.width() * self.width(),
                       (p.y() - w.top()) / w.height() * self.height())

    def _to_scene(self, p: QPointF) -> QPointF:
        w = self._world()
        return QPointF(w.left() + p.x() / self.width() * w.width(),
                       w.top() + p.y() / self.height() * w.height())

    # -------------------------------------------------------------- events
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#1e2a38"))
        w = self._world()
        scale = min(self.width() / w.width(), self.height() / w.height())
        ox = (self.width() - w.width() * scale) / 2.0
        oy = (self.height() - w.height() * scale) / 2.0
        self._ox, self._oy, self._sc = ox, oy, scale

        def mp(pt: QPointF) -> QPointF:
            return QPointF(ox + (pt.x() - w.left()) * scale,
                           oy + (pt.y() - w.top()) * scale)

        # content silhouette
        sc = self.view.scene()
        if sc is not None:
            r = sc.itemsBoundingRect()
            if not r.isEmpty():
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#37474f"))
                p.drawRect(QRectF(mp(r.topLeft()), mp(r.bottomRight())))

        # visible rect (rotated polygon, so rotation shows up correctly)
        vp = self.view.viewport().rect()
        corners = [self.vp.to_scene(QPointF(pt)) for pt in
                   (vp.topLeft(), vp.topRight(), vp.bottomRight(), vp.bottomLeft())]
        pts = [mp(c) for c in corners]
        p.setPen(QPen(QColor("#ff5252"), 1.5))
        p.setBrush(QBrush(QColor(255, 82, 82, 40)))
        p.drawPolygon(pts)
        p.end()

    def _move_to(self, pos):
        w = self._world()
        scale = min(self.width() / w.width(), self.height() / w.height())
        ox = (self.width() - w.width() * scale) / 2.0
        oy = (self.height() - w.height() * scale) / 2.0
        sp = QPointF(w.left() + (pos.x() - ox) / scale,
                     w.top() + (pos.y() - oy) / scale)
        self.vp.center_on(sp)
        self.update()

    def mousePressEvent(self, e):
        self._dragging = True
        self._move_to(QPointF(e.position()))
        self.view.update()

    def mouseMoveEvent(self, e):
        if self._dragging:
            self._move_to(QPointF(e.position()))
            self.view.update()

    def mouseReleaseEvent(self, e):
        self._dragging = False


# --------------------------------------------------------------------------
# PATCH NOTES — how to wire this into whiteboard_qt.py
# --------------------------------------------------------------------------
#
# 1.  import
#         from nav_tools import NavigationController, NavigatorPanel
#
# 2.  BoardView.__init__, right after the existing setup:
#         self.nav = NavigationController(
#             self, get_tool=lambda: self.win.tool,
#             on_status=lambda m: self.win.statusBar().showMessage(m))
#
# 3.  BoardView.wheelEvent:
#         def wheelEvent(self, e):
#             if self.nav.wheel(e):
#                 return
#             super().wheelEvent(e)
#
# 4.  BoardView.mousePressEvent — first lines (after _commit_text_edits):
#         if self.nav.press(e):
#             return
#
# 5.  BoardView.mouseMoveEvent — replace the `if self._panning:` block with:
#         if self.nav.move(e):
#             return
#
# 6.  BoardView.mouseReleaseEvent — replace the `if self._panning:` block with:
#         if self.nav.release(e):
#             return
#
# 7.  BoardView.mouseDoubleClickEvent:
#         def mouseDoubleClickEvent(self, e):
#             if self.nav.double_click(e):
#                 return
#             super().mouseDoubleClickEvent(e)
#
# 8.  MainWindow.keyPressEvent / keyReleaseEvent — first lines:
#         if self.view.nav.key_press(e):  return
#         if self.view.nav.key_release(e): return
#
# 9.  MainWindow.set_tool — call `self.view.nav.tool_changed(key)`
#
# 10. MainWindow._zoom / update_zoom_label / fit_content:
#         def _zoom(self, f):
#             self.view.nav.vp.zoom_at(self.view.nav.vp.center(),
#                                      self.view.nav.vp.zoom * f)
#             self.update_zoom_label()
#         def update_zoom_label(self):
#             self.zoom_label.setText(f"{int(round(self.view.nav.vp.zoom*100))}%")
#         def fit_content(self):
#             self.view.nav.vp.fit()
#             self.update_zoom_label()
#
# 11. Sidebar tool grid: add
#         ("Hand", "H", "hand"), ("Zoom", "Z", "zoom"), ("Rotate", "⟳", "rotate_canvas")
#
# 12. Optional navigator: `side_layout.addWidget(NavigatorPanel(self.view, self.view.nav.vp))`
# --------------------------------------------------------------------------
