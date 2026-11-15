from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from npsc_gui.design.style import apply_design, get_theme
from npsc_gui.main_window import MainWindow
from npsc_gui.splash import PremiumSplash


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("NeuroPrompt Semantic Compiler")
    app.setOrganizationName("NPSC")
    app.setApplicationDisplayName("NeuroPrompt Semantic Compiler")

    # High-DPI: let Qt honour the Windows scale factor with fractional rounding
    # so 125 %/150 % displays do not round layout metrics inconsistently.
    try:
        from PySide6.QtCore import Qt as _Qt

        app.setAttribute(_Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    except Exception:
        pass

    apply_design(app, get_theme("dark"))

    # Build the window first: the splash must never delay startup.
    window = MainWindow()

    def reveal_window() -> None:
        window.show()
        window.raise_()
        window.activateWindow()

    splash = PremiumSplash(duration_ms=1200, on_finished=reveal_window)
    splash.center_on_screen()
    splash.show()

    # If the splash is somehow not delivered, the window still appears.
    QTimer.singleShot(1600, reveal_window)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
