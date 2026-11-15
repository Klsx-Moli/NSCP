"""Capture real screenshots of the current NSCP UI (offscreen) for audit evidence."""
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from npsc_gui.main_window import MainWindow

OUT = Path(__file__).resolve().parents[1] / "screenshots" / "audit_before"
OUT.mkdir(parents=True, exist_ok=True)


def spin(seconds: float) -> None:
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


def wait_until(predicate, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.05)
    return False


app = QApplication([])
app.setApplicationName("NSCP")
window = MainWindow()
window.resize(1440, 900)
window.show()
spin(0.4)


def shot(name: str) -> None:
    pix = window.grab()
    path = OUT / f"{name}.png"
    pix.save(str(path))
    print("saved", path, pix.width(), "x", pix.height())


# 1. Simple home (idle)
shot("01_simple_home_idle")

# 2. Loading state
window.simple_prompt_edit.setPlainText(
    "Implementa una API REST en Rust con cobertura de tests del 90% y reintentos con backoff exponencial."
)
QApplication.processEvents()
window.compile_current()
spin(0.45)
shot("02_simple_loading")
ok = wait_until(lambda: window.result is not None, timeout=60)
print("compile finished:", ok)
spin(0.5)
shot("03_simple_result_success")

# 3. Extreme mode dashboard
window._switch_to_mode("extreme")
spin(0.4)
shot("04_extreme_dashboard")

# 4. Extreme compiler page
window._select_page("compilar")
spin(0.3)
shot("05_extreme_compiler")

# 5. Extreme results page
window._select_page("resultados")
spin(0.3)
shot("06_extreme_results")

# 6. Validation
window._select_page("validacion")
spin(0.3)
shot("07_extreme_validation")

# 7. Glossary
window._select_page("glosario")
spin(0.3)
shot("08_extreme_glossary")

# 8. Settings
window._select_page("configuracion")
spin(0.3)
shot("09_extreme_settings")

# 9. Advanced page
window._select_page("avanzado")
spin(0.3)
shot("10_extreme_advanced")

# 10. Light theme
window._select_page("configuracion")
spin(0.2)
window._on_theme_changed(1)
window._switch_to_mode("simple")
spin(0.4)
shot("11_simple_light_theme")

print("done")
window.close()
app.quit()
