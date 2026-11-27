"""Field — labelled control with help, error and focus state.

The container owns the border and the focus ring, so the inner native widget can
keep a transparent border and the focus state never shifts the layout.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from npsc_gui.design.style import active_theme


class Field(QFrame):
    """A form field: label above, control inside, help/error below."""

    def __init__(
        self,
        label: str = "",
        control: QWidget | None = None,
        help_text: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("NPSCField")
        self.setProperty("fieldState", "default")

        theme = active_theme()
        s = theme.spacing
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(s.md, s.sm, s.md, s.sm)
        self._layout.setSpacing(4)

        if label:
            self._label = QLabel(label)
            self._label.setObjectName("FieldLabel")
            self._layout.addWidget(self._label)

        self._control = control
        if control is not None:
            self._layout.addWidget(control)
            control.installEventFilter(self)

        self._help = QLabel(help_text)
        self._help.setObjectName("FieldHelp")
        self._help.setWordWrap(True)
        self._help.setVisible(bool(help_text))
        self._layout.addWidget(self._help)

        self._error = QLabel("")
        self._error.setObjectName("FieldError")
        self._error.setWordWrap(True)
        self._error.setVisible(False)
        self._layout.addWidget(self._error)

    # ── public API ────────────────────────────────────────────────────────

    @property
    def control(self) -> QWidget | None:
        return self._control

    def set_label(self, text: str) -> None:
        self._label.setText(text)

    def set_help(self, text: str) -> None:
        self._help.setText(text)
        self._help.setVisible(bool(text))

    def set_error(self, message: str) -> None:
        self._error.setText(message)
        self._error.setVisible(bool(message))
        self.setProperty("fieldState", "error" if message else "default")
        self._refresh()

    def clear_error(self) -> None:
        self.set_error("")

    def set_enabled(self, enabled: bool) -> None:
        if self._control is not None:
            self._control.setEnabled(enabled)
        self.setProperty("fieldState", "disabled" if not enabled else "default")
        self._refresh()

    # ── internals ──────────────────────────────────────────────────────────

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt API)
        if obj is self._control and event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            if event.type() == QEvent.Type.FocusIn and self._error.text():
                self.setProperty("fieldState", "error")
            else:
                self.setProperty("fieldState", "focus" if event.type() == QEvent.Type.FocusIn else "default")
            self._refresh()
        return super().eventFilter(obj, event)

    def _refresh(self) -> None:
        self.style().unpolish(self)
        self.style().polish(self)


__all__ = ["Field"]
