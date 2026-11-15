"""Application style — one place that owns the focus ring.

``QProxyStyle`` lets every widget (including native Qt controls) draw the same
focus indicator without changing its geometry: no padding compensation, no
layout shift, no per-widget ``paintEvent``.

Widgets that already express focus through their own QSS border (inputs,
primary buttons, nav items) opt out by property so the app never paints two
rings at once.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle

from npsc_gui.design.builder import build_qss
from npsc_gui.design.tokens import Theme, get_theme

#: Object names whose focus state is fully owned by the stylesheet border.
_QSS_FOCUS_OBJECTS = {
    "PrimaryButton",
    "SecondaryButton",
    "GhostButton",
    "DangerButton",
    "IconButton",
    "HeaderIconButton",
    "ModeToggleBtn",
    "NPSCNavItem",
    "NPSCSegment",
    "SimpleAdvToggle",
    "HelpIconButton",
    "ClearButton",
}


class PremiumStyle(QProxyStyle):
    """Draws a rounded accent focus ring for widgets without a QSS focus state."""

    def __init__(self, focus_color: str = "#5FC8F2", radius: int = 8) -> None:
        super().__init__("Fusion")
        self._focus_color = QColor(focus_color)
        self._radius = radius

    def set_focus_color(self, color: str) -> None:
        self._focus_color = QColor(color)

    def set_radius(self, radius: int) -> None:
        self._radius = radius

    def drawPrimitive(self, element, option, painter, widget=None) -> None:  # noqa: N802
        if element == QStyle.PrimitiveElement.PE_FrameFocusRect:
            if widget is not None and widget.objectName() in _QSS_FOCUS_OBJECTS:
                return
            state = option.state
            if state & QStyle.StateFlag.State_HasFocus:
                painter.save()
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                painter.setPen(
                    QPen(
                        self._focus_color,
                        2,
                        Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap,
                    )
                )
                painter.setBrush(Qt.BrushStyle.NoBrush)
                rect = QRectF(option.rect).adjusted(2.0, 2.0, -2.0, -2.0)
                painter.drawRoundedRect(rect, self._radius, self._radius)
                painter.restore()
                return
        super().drawPrimitive(element, option, painter, widget)


_STYLE: PremiumStyle | None = None


def apply_design(app: QApplication, theme: Theme) -> PremiumStyle:
    """Install the stylesheet and the focus style on ``app``.

    Called once at startup and again when the theme or language changes.
    """
    global _STYLE
    app.setProperty("npsc_theme_name", theme.name)
    app.setStyleSheet(build_qss(theme))

    if _STYLE is None:
        _STYLE = PremiumStyle(theme.palette.border_focus, theme.radius.md)
        app.setStyle(_STYLE)
    else:
        _STYLE.set_focus_color(theme.palette.border_focus)
        _STYLE.set_radius(theme.radius.md)
    return _STYLE


def premium_style() -> PremiumStyle | None:
    return _STYLE


def active_theme() -> Theme:
    """The theme currently installed on the application (defaults to dark)."""
    app = QApplication.instance()
    name = app.property("npsc_theme_name") if app is not None else None
    return get_theme(name if name in ("dark", "light") else "dark")


def focus_color(theme: Theme | None = None) -> str:
    t = theme or get_theme("dark")
    return t.palette.border_focus


__all__ = [
    "PremiumStyle",
    "apply_design",
    "premium_style",
    "active_theme",
    "focus_color",
]
