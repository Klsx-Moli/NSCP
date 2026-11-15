"""Capture real screenshots of the current NSCP UI for audit evidence.

Uses the native Windows QPA because offscreen/minimal ship zero fonts (text renders as tofu).
Patches the worker pacing so the loading state is actually observable.
"""
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtWidgets import QApplication

import npsc_gui.main_window as mw
from npsc_gui.main_window import MainWindow

OUT = Path(__file__).resolve().parents[1] / "screenshots" / "audit_after_phase1"
OUT.mkdir(parents=True, exist_ok=True)

PROMPT = (
    "Implementa una API REST en Rust con cobertura de tests del 90% "
    "y reintentos con backoff exponencial."
)


def spin(seconds: float) -> None:
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


def wait_until(predicate, timeout=60.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.05)
    return False


# Slow the worker so the loading state is capturable (capture-only patch).
def _slow_run(self):
    stages = [
        (10, "Analizando intención"),
        (25, "Detectando restricciones"),
        (40, "Seleccionando perfil"),
        (55, "Generando IR semántica"),
        (70, "Compilando NSL y prompt de ejecución"),
        (85, "Validando preservación"),
        (95, "Generando archivos"),
    ]
    try:
        for value, label in stages[:4]:
            if self.cancel_requested:
                self.canceled.emit()
                return
            self.progress.emit(value, label)
            time.sleep(0.45)
        if self.cancel_requested:
            self.canceled.emit()
            return
        result = self.controller.compile(**self.request)
        if self.cancel_requested:
            self.canceled.emit()
            return
        for value, label in stages[4:]:
            if self.cancel_requested:
                self.canceled.emit()
                return
            self.progress.emit(value, label)
            time.sleep(0.45)
        self.finished.emit(result)
    except Exception as exc:
        self.failed.emit(str(exc))


mw.CompileWorker.run = _slow_run

app = QApplication([])
app.setApplicationName("NSCP")
window = MainWindow()
window.resize(1440, 900)
window.show()
spin(0.5)


def shot(name: str) -> None:
    pix = window.grab()
    path = OUT / f"{name}.png"
    pix.save(str(path))
    pix.toImage().scaled(1200, int(pix.height() * 1200 / pix.width()), Qt.KeepAspectRatio).save(
        str(OUT / f"{name}_small.png")
    )
    print("saved", path.name, pix.width(), "x", pix.height())


# 1. Simple home (idle)
shot("01_simple_home_idle")

# 2. Loading state (mid-flight)
window.simple_prompt_edit.setPlainText(PROMPT)
QApplication.processEvents()
window.compile_current()
spin(1.4)
shot("02_simple_loading")
ok = wait_until(lambda: window.result is not None, timeout=90)
print("compile finished:", ok)
spin(0.4)
shot("03_simple_result_success")

# 3. Extreme mode — dashboard (explicit page)
window._switch_to_mode("extreme")
window._select_page("resumen")
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

# 11. Error state (simple)
window._on_theme_changed(0)
window.simple_prompt_edit.setPlainText(PROMPT)
QApplication.processEvents()
window._on_worker_failed("No se pudo conectar con el backend de compilacion (probe error).")
spin(0.3)
shot("12_simple_error")

print("done")
window.close()
app.quit()
