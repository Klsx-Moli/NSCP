"""Slow scanning bar overlay for text inputs.

A thin horizontal bar that drifts from bottom to top of its parent widget,
semi-transparent, purely decorative. Respects ``ui/reduce_motion``.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QWidget

from npsc_gui.design.motion import motion_enabled
from npsc_gui.design.style import active_theme


class ScanBar(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        theme = active_theme()
        p = theme.palette
        self._color = p.accent_brand
        self.setFixedHeight(3)
        self.setStyleSheet(
            f"background: {self._color}; border: none; border-radius: 2px;"
        )
        # Semi-transparent via opacity effect on the small bar only.
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        _eff = QGraphicsOpacityEffect(self)
        _eff.setOpacity(0.45)
        self.setGraphicsEffect(_eff)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.hide()

        self._step = 0.0
        self._speed = 0.004  # fraction of height per tick
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        if not motion_enabled():
            self.hide()
            return
        self.show()
        self._step = 0.0
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _tick(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        h = parent.height()
        w = parent.width()
        if w <= 0 or h <= 0:
            return
        self.setFixedWidth(w)
        self._step += self._speed
        if self._step >= 1.0:
            self._step = 0.0
        y = int(h * (1.0 - self._step))
        self.move(0, max(0, min(h - self.height(), y)))
        self.raise_()
