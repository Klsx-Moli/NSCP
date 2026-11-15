"""ScanRing — Premium animated ring indicator combining Driver Booster's
dominant circle concept with Auslogics-style status reporting.

Features:
- Smooth arc-based progress (no GIFs, no GPU shaders)
- Pulsing glow during active scan
- Semantic color states: idle, scanning, success, warning, error
- Sublabel + percentage display
- KDE X11 / GTX 660 safe (pure QPainter + QTimer @ 50ms)
"""
from __future__ import annotations

import math

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout
from npsc_gui.design.style import active_theme
from npsc_gui.design.motion import motion_enabled


class ScanRing(QFrame):
    """Premium circular progress / status ring.

    Draws an arc-based progress indicator that looks like a scanning ring.
    Used as the hero element in the main dashboard.
    """

    value_changed = Signal(int)
    state_changed = Signal(str)

    def __init__(self, size: int = 140, ring_width: int = 5, parent=None) -> None:
        super().__init__(parent)
        self._size = size
        self._ring_width = ring_width
        self._value = 0
        self._state = "idle"
        self._pulse = 0.0
        self._fwd = True
        self._sub_label = "preservación"

        self.setFixedSize(size, size)
        self.setFrameShape(QFrame.NoFrame)

        theme = active_theme()
        t = theme.typography
        primary_family = t.family.split(",")[0].strip().strip('"')

        # Value label centered inside the ring
        inner = QVBoxLayout(self)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setAlignment(Qt.AlignCenter)
        inner.setSpacing(0)

        self._val_label = QLabel("—")
        self._val_label.setAlignment(Qt.AlignCenter)
        vfont = QFont(primary_family, t.display_size + 4, t.display_weight)
        vfont.setStyleStrategy(QFont.PreferAntialias)
        self._val_label.setFont(vfont)

        self._sub_lbl = QLabel(self._sub_label)
        self._sub_lbl.setAlignment(Qt.AlignCenter)
        sfont = QFont(primary_family, t.caption_size, t.label_weight)
        self._sub_lbl.setFont(sfont)

        inner.addWidget(self._val_label)
        inner.addWidget(self._sub_lbl)

        # Pulse timer for active scanning animation
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(50)
        self._pulse_timer.timeout.connect(self._on_pulse_tick)

        self._apply_colors()

    # ─── Public API ─────────────────────────────────────────────

    def set_value(self, value: int | str) -> None:
        if isinstance(value, str):
            self._val_label.setText(value)
            self.update()
            return
        self._value = max(0, min(100, value))
        self._val_label.setText(str(self._state_value_display()))
        self.value_changed.emit(self._value)
        self.update()

    def set_sub_label(self, text: str) -> None:
        self._sub_label = text
        self._sub_lbl.setText(text)

    def set_state(self, state: str) -> None:
        """ScanRing states: idle, scanning, success, warning, error."""
        self._state = state
        if state == "scanning":
            if motion_enabled():
                self._pulse_timer.start()
            self._val_label.setText("0")
        else:
            self._pulse_timer.stop()
        self._apply_colors()
        self.state_changed.emit(state)
        self.update()

    def scanning_start(self) -> None:
        self.set_state("scanning")
        self._value = 0
        self._val_label.setText("0")

    def scanning_progress(self, pct: int) -> None:
        self._value = max(0, min(100, pct))
        self._val_label.setText(str(self._value))
        self.update()

    def scanning_finish(self, score: int) -> None:
        self._pulse_timer.stop()
        self._value = score
        if score >= 85:
            self.set_state("success")
        elif score >= 60:
            self.set_state("warning")
        else:
            self.set_state("error")
        self._val_label.setText(str(score))

    # ─── Painting ───────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        r = self._ring_width / 2.0
        rect = QRectF(r, r, self._size - self._ring_width, self._size - self._ring_width)

        # Background ring (always drawn)
        bg_pen = QPen(self._colors["track"], self._ring_width, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(bg_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(rect)

        # Arc for progress
        if self._value > 0 and self._state != "idle":
            fg_pen = QPen(self._colors["arc"], self._ring_width, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(fg_pen)
            span = int(-self._value * 3.6 * 16)  # Qt uses 1/16 degree units
            painter.drawArc(rect, 90 * 16, span)

        if self._state == "scanning" and motion_enabled():
            glow_alpha = int(30 + 20 * math.sin(self._pulse))
            glow_color = QColor(self._colors["arc"])
            glow_color.setAlpha(glow_alpha)
            glow_pen = QPen(glow_color, self._ring_width + 3, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(glow_pen)
            painter.drawEllipse(rect.adjusted(2, 2, -2, -2))

        painter.end()

    # ─── Internals ──────────────────────────────────────────────

    def _state_value_display(self) -> str:
        if self._state == "scanning":
            return str(self._value)
        if self._state == "idle":
            return "—"
        return str(self._value)

    def _on_pulse_tick(self) -> None:
        if self._fwd:
            self._pulse += 0.08
            if self._pulse >= math.pi:
                self._fwd = False
        else:
            self._pulse -= 0.08
            if self._pulse <= 0:
                self._fwd = True
        self.update()

    def _apply_colors(self) -> None:
        theme = active_theme()
        p = theme.palette
        arc_color = {
            "idle": p.accent_brand,
            "scanning": p.accent_primary,
            "success": p.success,
            "warning": p.warning,
            "error": p.error,
        }.get(self._state, p.accent_brand)
        self._colors = {"track": QColor(p.track), "arc": QColor(arc_color)}
        self._val_label.setStyleSheet(
            f"color: {arc_color}; background: transparent; border: none;"
        )
        self._sub_lbl.setStyleSheet(
            f"color: {p.text_tertiary}; background: transparent; border: none;"
        )
