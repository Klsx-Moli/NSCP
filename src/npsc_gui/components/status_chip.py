"""Status chip — small semantic pill with dot + text.

Variants: ok, warn, error, info.
Colors controlled via QSS property chipState.
"""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel


class StatusChip(QFrame):
    """Semantic status indicator chip (dot + text)."""

    _STATE_TO_CHIP = {
        "idle": "idle",
        "ready": "ok",
        "working": "working",
        "success": "ok",
        "warning": "warn",
        "error": "error",
    }

    def __init__(self, text: str = "", state: str = "ok", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("NPSCChip")
        self.state = state
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 10, 3)
        layout.setSpacing(5)

        self._dot = QLabel()
        self._dot.setObjectName("ChipDot")
        self._dot.setFixedSize(6, 6)

        self._text = QLabel(text)
        self._text.setObjectName("ChipText")

        layout.addWidget(self._dot)
        layout.addWidget(self._text)
        self.set_state(state)

    def set_text(self, text: str) -> None:
        self._text.setText(text)

    def set_state(self, state: str) -> None:
        """Set semantic state: idle, ready, working, success, warning, error."""
        self.state = state
        chip_state = self._STATE_TO_CHIP.get(state, state)
        self.setProperty("chipState", chip_state)
        for w in (self, self._dot, self._text):
            w.style().unpolish(w)
            w.style().polish(w)
