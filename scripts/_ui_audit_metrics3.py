"""Idle-state visibility + font availability check (needs a QApplication first)."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

app = QApplication([])

print("== FONT AVAILABILITY ==")
fams = set(QFontDatabase.families())
for want in ("Inter", "Segoe UI", "Segoe UI Variable", "Noto Sans", "Cascadia Code", "JetBrains Mono", "Consolas", "Carlito", "Calibri"):
    print(f"  {want:20s} {'FOUND' if want in fams else 'MISSING'}")

from npsc_gui.main_window import MainWindow

w = MainWindow()
w.resize(1440, 900)
w.show()
app.processEvents()

print("\n== IDLE WIDGET VISIBILITY (simple mode, no compile yet) ==")
targets = [
    ("simple_health (4 metric pills)", getattr(w, "simple_health", None)),
    ("simple_scan_container", getattr(w, "simple_scan_container", None)),
    ("simple_scan_ring", getattr(w, "simple_scan_ring", None)),
    ("simple_scan_status", getattr(w, "simple_scan_status", None)),
    ("simple_progress", getattr(w, "simple_progress", None)),
    ("simple_cancel_btn", getattr(w, "simple_cancel_btn", None)),
    ("adv_frame", getattr(w, "adv_frame", None)),
    ("extreme_health", getattr(w, "extreme_health", None)),
    ("progress_strip", getattr(w, "progress_strip", None)),
]
for label, widget in targets:
    if widget is None:
        print(f"  {label:32s} MISSING")
    else:
        print(f"  {label:32s} visible={widget.isVisible()}")

print("\n== SIMPLE HOME LAYOUT ORDER (what the user sees top->bottom) ==")
page = w.simple_stack.widget(0)
lay = page.layout()
for i in range(lay.count()):
    item = lay.itemAt(i)
    if item.widget() is not None:
        wd = item.widget()
        print(f"  [{i}] {wd.metaObject().className():22s} obj={wd.objectName() or '-':24s} visible={wd.isVisible()} h={wd.sizeHint().height()}")
    elif item.layout() is not None:
        print(f"  [{i}] <layout> spacing={item.layout().spacing()}")

w.close()
app.quit()
