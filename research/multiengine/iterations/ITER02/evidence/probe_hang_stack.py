"""Minimal Qt hang reproducer with a timed faulthandler stack dump."""
import faulthandler
import sys
import time

from PySide6.QtWidgets import QApplication

from npsc_gui.design import get_theme
from npsc_gui.design.style import apply_design
from npsc_gui.main_window import MainWindow

faulthandler.dump_traceback_later(15, repeat=False, exit=True, file=sys.stderr)
app = QApplication([])
windows = []
for i in range(8):
    t0 = time.perf_counter()
    windows.append(MainWindow())
    print(f"WINDOW_{i}_CREATED {time.perf_counter() - t0:.3f}s", flush=True)
for i, w in enumerate(windows):
    t0 = time.perf_counter()
    w.close()
    print(f"WINDOW_{i}_CLOSED {time.perf_counter() - t0:.3f}s", flush=True)
print("CALLING_APPLY_DESIGN", flush=True)
t0 = time.perf_counter()
apply_design(app, get_theme("dark"))
print(f"APPLY_RETURNED {time.perf_counter() - t0:.3f}s", flush=True)
faulthandler.cancel_dump_traceback_later()
