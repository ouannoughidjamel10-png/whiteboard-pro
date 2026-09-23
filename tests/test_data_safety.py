# -*- coding: utf-8 -*-
"""Data-safety suite — runs offscreen, no display needed.

    python tests/test_data_safety.py

WHY THIS FILE EXISTS
--------------------
The tools worked long before the safety net did. Measured on the real window
before these fixes: closing the window discarded unsaved work in silence, there
was no autosave and no recovery file, the title never said whether the document
was saved, and `save_doc` wrote straight over the target with `write_text`, so a
write that died half way (disk full, power cut) destroyed the previous document
— reproduced as 78 good bytes becoming 325 truncated bytes that no longer
parsed as JSON.

WHAT IT GUARDS
--------------
1. dirty tracking + a title that shows the file name and an unsaved marker
2. closeEvent: Save / Discard / Cancel, and Cancel really cancels
3. an atomic save that cannot destroy the previous file
4. autosave + crash recovery
"""
import json
import os
import pathlib
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QCloseEvent, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog

import whiteboard_qt as wb

QInputDialog.getMultiLineText = staticmethod(lambda *a, **k: ("smoke", True))
QInputDialog.getText = staticmethod(lambda *a, **k: ("smoke", True))

FAILS = []


def check(name, ok, detail=""):
    print(("  [PASS] " if ok else "  [FAIL] ") + name +
          ("  — " + detail if detail else ""))
    if not ok:
        FAILS.append(name)


TMP = pathlib.Path(tempfile.mkdtemp(prefix="wb_safety_"))
REC = TMP / "recovery.wbd"

# ---------------------------------------------------------------- fake dialogs
# A real QMessageBox.exec() blocks forever offscreen with nobody to click it.
# Install a recording stand-in for the whole suite instead.
RealBox = wb.QMessageBox


class FakeButton:
    def __init__(self, text):
        self._text = text

    def text(self):
        return self._text


class FakeBox:
    """Stands in for QMessageBox; records what the app tried to tell the user."""

    Icon = RealBox.Icon
    ButtonRole = RealBox.ButtonRole
    StandardButton = RealBox.StandardButton
    CHOSEN = {"text": None}          # which button clickedButton() returns
    QUESTION = {"answer": RealBox.StandardButton.Yes}
    CRITICALS = []                   # every critical() the app raised
    QUESTIONS = []                   # every question() the app asked

    def __init__(self, *a, **k):
        self._buttons = {}

    def setIcon(self, *a):
        pass

    def setWindowTitle(self, *a):
        pass

    def setText(self, *a):
        pass

    def setInformativeText(self, *a):
        pass

    def addButton(self, text, role):
        b = FakeButton(text)
        self._buttons[text] = b
        return b

    def setDefaultButton(self, *a):
        pass

    def exec(self):
        pass

    def clickedButton(self):
        return self._buttons.get(self.CHOSEN["text"])

    @classmethod
    def question(cls, *a, **k):
        cls.QUESTIONS.append(a[1] if len(a) > 1 else "")
        return cls.QUESTION["answer"]

    @classmethod
    def critical(cls, *a, **k):
        cls.CRITICALS.append(a[1] if len(a) > 1 else "")
        return cls.StandardButton.Ok


wb.QMessageBox = FakeBox

app = QApplication.instance() or QApplication(sys.argv)
win = wb.MainWindow()
win.resize(1400, 900)
win.show()
win._recovery_file = lambda: REC          # never touch the real one
view = win.view

_real_write_text = pathlib.Path.write_text


def ev(t, sp):
    v = view.mapFromScene(QPointF(sp[0], sp[1]))
    return QMouseEvent(t, QPointF(v), QPointF(v),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)


def key(k):
    return QKeyEvent(QEvent.Type.KeyPress, k, Qt.KeyboardModifier.NoModifier)


def stroke(pts):
    view.mousePressEvent(ev(QEvent.Type.MouseButtonPress, pts[0]))
    for p in pts[1:]:
        view.mouseMoveEvent(ev(QEvent.Type.MouseMove, p))
    view.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, pts[-1]))
    app.processEvents()


def objects():
    win._sync_page_store()
    return [pl for pg in win.pages for pl in pg]


_draw_n = [0]


def draw_something():
    """One committed vpath, each call in fresh space so nothing is re-hit.

    Two gestures, not one: a single pen gesture leaves a one-node path, and
    _vpen_finish(commit=True) rightly discards that — measured, and the reason
    an earlier version of this suite drew nothing at all.
    """
    _draw_n[0] += 1
    dx = 1500.0 * _draw_n[0]
    win.keyPressEvent(key(Qt.Key.Key_Escape))
    win.set_tool("vpen")
    stroke([(dx, 200.0), (dx + 100, 250.0), (dx + 200, 200.0)])
    stroke([(dx + 300, 400.0), (dx + 400, 450.0), (dx + 500, 400.0)])
    win.keyPressEvent(key(Qt.Key.Key_Return))
    app.processEvents()
    win.set_tool("select")


# =====================================================================
print("\n1. Dirty tracking and the title bar")
# =====================================================================
check("a fresh board is not dirty", win.is_dirty() is False,
      "is_dirty=%s" % win.is_dirty())
check("the title says Untitled", "Untitled" in win.windowTitle(),
      "title=%r" % win.windowTitle())
check("no unsaved marker on a clean board", "*" not in win.windowTitle(),
      "title=%r" % win.windowTitle())

draw_something()
check("drawing produced an object", len(objects()) >= 1,
      "objects=%d" % len(objects()))
check("drawing marks the document dirty", win.is_dirty() is True,
      "objects=%d" % len(objects()))
check("the title now carries the unsaved marker",
      win.windowTitle().rstrip().endswith("*"),
      "title=%r" % win.windowTitle())

# =====================================================================
print("\n2. A failed save must never destroy the previous document")
# =====================================================================
DOC = TMP / "lesson.wbd"
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(DOC), "wbd"))

# first, a good save of the current board
check("the first save succeeds", win.save_doc() is True)
check("the document exists after saving", DOC.exists(),
      "%d bytes" % (DOC.stat().st_size if DOC.exists() else 0))
good = DOC.read_text(encoding="utf-8")
check("a clean document drops the unsaved marker",
      not win.windowTitle().rstrip().endswith("*"),
      "title=%r" % win.windowTitle())

# make the board differ from what is on disk, then kill the write half way
draw_something()
check("the board is dirty again before the second save", win.is_dirty() is True)


def half_then_die(self, text, *a, **k):
    if str(self).endswith(".tmp"):
        _real_write_text(self, text[: len(text) // 2], *a, **k)   # bytes land
        raise OSError(28, "No space left on device")              # then it dies
    return _real_write_text(self, text, *a, **k)


pathlib.Path.write_text = half_then_die
FakeBox.CRITICALS.clear()
try:
    returned = win.save_doc()
except BaseException as exc:                       # noqa: BLE001
    returned = exc
finally:
    pathlib.Path.write_text = _real_write_text

check("a mid-write failure is reported, not swallowed",
      returned is False, "save_doc returned %r" % (returned,))
check("the user is told the save failed", len(FakeBox.CRITICALS) == 1,
      "critical dialogs=%d" % len(FakeBox.CRITICALS))
check("the previous document SURVIVED the failed save",
      DOC.read_text(encoding="utf-8") == good,
      "%d bytes now, %d before" % (DOC.stat().st_size, len(good)))
try:
    json.loads(DOC.read_text(encoding="utf-8"))
    parsed = True
except Exception:
    parsed = False
check("the surviving document still parses as JSON", parsed)
check("the failed save left the document dirty", win.is_dirty() is True)

# a successful save keeps a .bak of what it replaced
BAK = pathlib.Path(str(DOC) + ".bak")
before_second = DOC.read_text(encoding="utf-8")
check("the second save succeeds", win.save_doc() is True)
check("a .bak of the previous version is kept", BAK.exists(),
      "%s" % (BAK.name if BAK.exists() else "missing"))
check("the .bak holds the version that was replaced",
      BAK.exists() and BAK.read_text(encoding="utf-8") == before_second)
check("no half-written .tmp is left behind",
      not list(TMP.glob("*.tmp")), "dir=%s" % sorted(p.name for p in TMP.iterdir()))

# =====================================================================
print("\n3. Autosave and crash recovery")
# =====================================================================
win._clear_recovery()
check("clearing removes the recovery copy", not REC.exists())

win._set_clean()
win._autosave()
check("autosave writes nothing while the board is clean", not REC.exists(),
      "recovery exists=%s" % REC.exists())

draw_something()
win._autosave()
check("autosave wrote a recovery copy", REC.exists(),
      "%d bytes" % (REC.stat().st_size if REC.exists() else 0))
rec_data = json.loads(REC.read_text(encoding="utf-8")) if REC.exists() else {}
rec_objects = sum(len(pg.get("objects", [])) for pg in rec_data.get("pages", []))
check("the recovery copy holds the unsaved objects", rec_objects >= 1,
      "objects=%d" % rec_objects)

QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(DOC), "wbd"))
win.save_doc()
check("a successful save deletes the recovery copy", not REC.exists(),
      "recovery exists=%s" % REC.exists())

# =====================================================================
print("\n4. Recovery is offered at startup — and only on a real launch")
# =====================================================================
draw_something()
win._autosave()                     # make a fresh recovery copy to find
check("a recovery copy exists to offer", REC.exists(),
      "%d bytes" % (REC.stat().st_size if REC.exists() else 0))

wb.RECOVERY_ON_START = False
win._offer_recovery()
check("automated runs never block on the recovery dialog", REC.exists(),
      "recovery untouched=%s" % REC.exists())

FakeBox.QUESTION["answer"] = RealBox.StandardButton.Yes
wb.RECOVERY_ON_START = True
try:
    win._offer_recovery()
finally:
    wb.RECOVERY_ON_START = False

check("answering Yes restores the recovered work", len(objects()) >= 1,
      "objects=%d" % len(objects()))
check("recovered work counts as unsaved", win.is_dirty() is True)

# =====================================================================
print("\n5. Closing the window with unsaved work")
# =====================================================================
check("MainWindow defines closeEvent",
      "closeEvent" in wb.MainWindow.__dict__)

win._set_clean()
e = QCloseEvent()
win.closeEvent(e)
check("a clean board closes without asking", e.isAccepted() is True)

draw_something()
check("the board is dirty before the close test", win.is_dirty() is True)

FakeBox.CHOSEN["text"] = "Cancel"
e = QCloseEvent()
win.closeEvent(e)
check("Cancel really cancels the close", e.isAccepted() is False,
      "accepted=%s" % e.isAccepted())
check("Cancel keeps the work on the board", len(objects()) >= 1)

FakeBox.CHOSEN["text"] = "Discard"
e = QCloseEvent()
win.closeEvent(e)
check("Discard closes the window", e.isAccepted() is True)
check("Discard clears the recovery copy", not REC.exists())

# Save: the file dialog is wired to a real path, so this must hit the disk
draw_something()
win._set_clean()
draw_something()
FakeBox.CHOSEN["text"] = "Save"
e = QCloseEvent()
win.closeEvent(e)
check("Save closes the window", e.isAccepted() is True)
check("Save actually wrote the document", DOC.exists())
check("Save left nothing dirty", win.is_dirty() is False,
      "is_dirty=%s" % win.is_dirty())

# =====================================================================
print("\n6. The round trip still works after all of that")
# =====================================================================
saved = json.loads(DOC.read_text(encoding="utf-8"))
saved_n = sum(len(pg.get("objects", [])) for pg in saved.get("pages", []))
win.clear_board()
check("the board is empty after clear", len(objects()) == 0)
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(DOC), "wbd"))
win.open_doc()
check("reopening restored every object", len(objects()) == saved_n,
      "%d saved, %d restored" % (saved_n, len(objects())))
check("an opened document is not dirty", win.is_dirty() is False)

# =====================================================================
print("\n" + "=" * 68)
if FAILS:
    print("  FAILED: %d" % len(FAILS))
    for f in FAILS:
        print("    - " + f)
else:
    print("  all data-safety checks passed")
print("=" * 68)
sys.exit(1 if FAILS else 0)
