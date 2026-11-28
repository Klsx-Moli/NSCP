"""Isolated reproduction of cross-QApplication PremiumStyle reuse.

Run with QT_QPA_PLATFORM=offscreen and PYTHONPATH=<worktree>/src.
Exits 0 if both applications can be styled, nonzero/hangs on the stale-style path.
"""
import sys
import time

from PySide6.QtWidgets import QApplication

from npsc_gui.design import style as style_module
from npsc_gui.design import get_theme

mode = sys.argv[1] if len(sys.argv) > 1 else "reuse"
app1 = QApplication([])
t0 = time.perf_counter()
style_module.apply_design(app1, get_theme("dark"))
print(f"APP1_OK elapsed={time.perf_counter()-t0:.3f}", flush=True)
app1 = None
import gc
gc.collect()

app2 = QApplication([])
if mode == "reset":
    style_module._STYLE = None
t0 = time.perf_counter()
style_module.apply_design(app2, get_theme("light"))
print(f"APP2_OK mode={mode} elapsed={time.perf_counter()-t0:.3f}", flush=True)
