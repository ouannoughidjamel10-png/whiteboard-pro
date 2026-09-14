# tests/ — how to run the regression suites

All suites run **offscreen**: no display, no clicking, a few seconds each.

```bash
cd <project root>
QT_QPA_PLATFORM=offscreen python tests/test_pen_tool.py       # 21 checks
QT_QPA_PLATFORM=offscreen python tests/wb_penmath_test.py     #  7 checks
QT_QPA_PLATFORM=offscreen python tests/wb_penfix_test.py      #  5 checks
QT_QPA_PLATFORM=offscreen python test_nav_tools.py            # 37 checks
QT_QPA_PLATFORM=offscreen python _smoke_nav_integration.py    # integration
```

Exit code is 0 when everything passes, 1 otherwise — safe to chain.

## Why these live here and not in %TEMP%

The older suites (`wb_qt2_test.py`, `wb_vpath_test.py`, `wb_ink_test.py`,
`wb_color_test.py`, `wb_p4_test.py`, `wb_p5_test.py`, `wb_tbox_test.py`,
`wb_snap_test.py`, `wb_pen2_test.py`, ...) were kept in `%TEMP%\opencode\`.
Windows cleanup deleted them. **Two survived only because they happened to be
modified recently.** Anything that guards a non-obvious invariant belongs in
git, next to the code it protects.

If you find another surviving script in `%TEMP%\opencode\`, copy it here and
make its `sys.path` line relative:

```python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

## test_pen_tool.py — what it protects

| # | Check |
|---|---|
| 1 | Handle convention: the control arriving at a node sits at `anchor + in` |
| 2 | C1 continuity at a smooth node — **tripwire for the 180° cusp bug** |
| 3 | A real press-drag gesture yields a genuinely smooth node (0°, not 180°) |
| 4 | Closing a path: shared helper, preview snaps to node 0, click closes |
| 5 | Pen on a segment inserts an anchor **without changing the shape** |
| 6 | Pen on an anchor removes it |
| 7 | Node edit: Alt+click flips corner ↔ smooth, result is C1 not a cusp |
| 8 | Node edit: Shift locks a handle to 45° |
| 9 | Node edit: handles appear on hover, before any click |
