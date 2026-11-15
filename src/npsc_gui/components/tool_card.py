"""Tool card — action card with a vector icon, title and description."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from npsc_gui.components.icons import icon_pixmap
from npsc_gui.design.style import active_theme


class ToolCard(QFrame):
    """Card representing a secondary tool/action.

    Keyboard accessible: focusable, activates with Return/Space, and shows a
    focus ring because the QSS target is ``QFrame#NPSCToolCard:focus``.
    """

    clicked = Signal()

    def __init__(
        self,
        title: str = "",
        description: str = "",
        icon_name: str = "spark",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("NPSCToolCard")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        theme = active_theme()
        s = theme.spacing

        layout = QVBoxLayout(self)
        layout.setContentsMargins(s.lg, s.lg, s.lg, s.lg)
        layout.setSpacing(s.sm)

        top = QHBoxLayout()
        top.setSpacing(s.sm)

        self._icon = QLabel()
        self._icon.setObjectName("ToolCardIcon")
        self._icon.setFixedSize(QSize(28, 28))
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_name = icon_name
        self._apply_icon(theme.palette.accent_brand)

        self._title = QLabel(title)
        self._title.setObjectName("ToolCardTitle")

        top.addWidget(self._icon)
        top.addWidget(self._title)
        top.addStretch(1)

        self._desc = QLabel(description)
        self._desc.setObjectName("ToolCardDesc")
        self._desc.setWordWrap(True)

        layout.addLayout(top)
        layout.addWidget(self._desc)

    def _apply_icon(self, colour: str) -> None:
        self._icon.setPixmap(icon_pixmap(self._icon_name, 18, colour))

    def set_icon_name(self, name: str) -> None:
        self._icon_name = name
        self._apply_icon(active_theme().palette.accent_brand)

    def set_icon_text(self, text: str) -> None:
        """Backwards-compatible: map the old glyph to a vector icon name."""
        mapping = {"⌕": "search", "✓": "check", "⎘": "copy", "◇": "spark"}
        self.set_icon_name(mapping.get(text, "spark"))

    def set_title(self, text: str) -> None:
        self._title.setText(text)

    def title(self) -> str:
        return self._title.text()

    def set_description(self, text: str) -> None:
        self._desc.setText(text)

    def description(self) -> str:
        return self._desc.text()

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)


__all__ = ["ToolCard"]
