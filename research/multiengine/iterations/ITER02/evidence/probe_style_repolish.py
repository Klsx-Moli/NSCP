"""Probe: cost of apply_design after N live MainWindow instances."""
import sys
import time

from PySide6.QtWidgets import QApplication

N = int(sys.argv[1]) if len(sys.argv) > 1 else 0
app = QApplication([])
from npsc_gui.design import get_theme
from npsc_gui.design.style import apply_design
from npsc_gui.main_window import MainWindow

windows = [MainWindow() for _ in range(N)]
for w in windows:
    w.close()
print(f"CREATED={len(windows)}", flush=True)
for name in ("dark", "light"):
    t0 = time.perf_counter()
    apply_design(app, get_theme(name))
    print(f"APPLY {name}: {time.perf_counter() - t0:.3f}s", flush=True)
