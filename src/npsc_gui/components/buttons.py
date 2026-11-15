"""Button components — PrimaryButton, SecondaryButton, GhostButton, IconButton.

Visual states live in the QSS builder (tokens); these classes only set the
object name that selects the right style and apply the token metrics that Qt
cannot express in a stylesheet (fixed icon size, cursor, focus policy).

``PrimaryButton`` owns a real loading state: while ``set_loading(True)`` the
label is replaced by a spinner glyph, the button keeps its width and ignores
clicks, so the primary action never looks frozen or double-fires.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QPushButton

from npsc_gui.design.style import active_theme

_PRIMARY = "PrimaryButton"
_SECONDARY = "SecondaryButton"
_GHOST = "GhostButton"
_ICON = "IconButton"
_DANGER = "DangerButton"

_SPINNER_FRAMES = ("◐", "◓", "◑", "◒")


class _TokenButton(QPushButton):
    """Base: applies token metrics that QSS cannot express."""

    _object_name = ""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        if self._object_name:
            self.setObjectName(self._object_name)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_compact(self, compact: bool = True) -> None:
        """Reduce vertical padding for dense toolbars."""
        self.setProperty("compact", "true" if compact else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class PrimaryButton(_TokenButton):
    """The single dominant action of a context."""

    _object_name = _PRIMARY

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        theme = active_theme()
        self.setMinimumHeight(theme.metrics.button_height_large)
        self._idle_text = text
        self._loading = False
        self._spinner_index = 0
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(110)
        self._spinner_timer.timeout.connect(self._tick_spinner)

    def set_loading(self, loading: bool, text: str | None = None) -> None:
        """Show a spinner glyph and block clicks until ``loading`` is False."""
        if loading == self._loading:
            return
        self._loading = loading
        self.setProperty("loading", "true" if loading else "false")
        if loading:
            self._idle_text = self.text()
            self.setEnabled(False)
            self._spinner_index = 0
            self.setText(_SPINNER_FRAMES[0])
            self._spinner_timer.start()
        else:
            self._spinner_timer.stop()
            self.setEnabled(True)
            self.setText(text if text is not None else self._idle_text)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_idle_text(self, text: str) -> None:
        """Update the label used when the button returns from loading."""
        self._idle_text = text
        if not self._loading:
            self.setText(text)

    def is_loading(self) -> bool:
        return self._loading

    def _tick_spinner(self) -> None:
        self._spinner_index = (self._spinner_index + 1) % len(_SPINNER_FRAMES)
        self.setText(_SPINNER_FRAMES[self._spinner_index])


class SecondaryButton(_TokenButton):
    """Supporting action with clearly less visual weight."""

    _object_name = _SECONDARY

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setMinimumHeight(active_theme().metrics.button_height)


class GhostButton(_TokenButton):
    """Low-emphasis action (inline links, dense toolbars)."""

    _object_name = _GHOST

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setMinimumHeight(24)


class DangerButton(_TokenButton):
    """Destructive or cancelling action."""

    _object_name = _DANGER

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setMinimumHeight(active_theme().metrics.button_height)


class IconButton(_TokenButton):
    """Compact square button for a single glyph or icon, with a tooltip."""

    _object_name = _ICON

    def __init__(
        self,
        glyph: str = "",
        tooltip: str = "",
        parent=None,
    ) -> None:
        super().__init__("", parent)
        size = active_theme().metrics.icon_button_size
        self.setFixedSize(QSize(size, size))
        if glyph:
            self.setText(glyph)
        if tooltip:
            self.setToolTip(tooltip)
            self.setToolTipDuration(4000)
            self.setAccessibleName(tooltip)

    def set_icon(self, icon: QIcon) -> None:
        super().setIcon(icon)
        self.setText("")

    def set_action(self, action: QAction) -> None:
        self.setDefaultAction(action)
        self.setText("")


__all__ = [
    "PrimaryButton",
    "SecondaryButton",
    "GhostButton",
    "IconButton",
    "DangerButton",
]
