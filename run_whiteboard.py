"""Dev launcher: run WhiteboardPro straight from source (no build step).

    python run_whiteboard.py

Path-portable on purpose — do NOT hardcode an absolute checkout path here,
otherwise the file is useless on any other machine/clone.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import whiteboard_qt

whiteboard_qt.main()
