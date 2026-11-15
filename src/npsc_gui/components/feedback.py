"""Feedback components — ProgressIndicator, ToastHost, Toast, InlineNotice, Skeleton.

``ProgressIndicator`` paints its own track and chunk so the indeterminate state
is an elegant travelling segment instead of Qt's default busy animation, while
keeping the ``QProgressBar`` API (``setRange``/``value``) that callers and tests
already rely on.

``ToastHost`` is the single non-blocking feedback surface of the app: toasts
stack bottom-right of the window, fade in, never steal focus and never block the
event loop.
"""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from npsc_gui.design import motion
from npsc_gui.components.icons import icon_pixmap
from npsc_gui.design.style import active_theme


class ProgressIndicator(QProgressBar):
    """Determinate progress, or a real indeterminate state when there is none."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("NPSCProgress")
        self.setProperty("progressState", "info")
        theme = active_theme()
        self.setFixedHeight(theme.metrics.progress_thickness)
        self.setTextVisible(False)
        self.setRange(0, 100)
        self.setValue(0)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    # ── state ─────────────────────────────────────────────────────────────

    def set_indeterminate(self, indeterminate: bool = True) -> None:
        if indeterminate:
            self.setRange(0, 0)
            if motion.motion_enabled():
                self._timer.start()
        else:
            self._timer.stop()
            self.setRange(0, 100)
        self.update()

    def set_variant(self, variant: str) -> None:
        """info | success | warning | error."""
        allowed = ("info", "success", "warning", "error")
        self.setProperty("progressState", variant if variant in allowed else "info")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def variant(self) -> str:
        return str(self.property("progressState") or "info")

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self._timer.stop()
        super().hideEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().showEvent(event)
        if self.minimum() == 0 and self.maximum() == 0 and motion.motion_enabled():
            self._timer.start()

    # ── painting ──────────────────────────────────────────────────────────

    def _chunk_color(self) -> QColor:
        p = active_theme().palette
        return QColor(
            {
                "success": p.success,
                "warning": p.warning,
                "error": p.error,
            }.get(self.variant(), p.accent_brand)
        )

    def _tick(self) -> None:
        self._phase = (self._phase + 0.012) % 1.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt API)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        radius = self.height() / 2.0
        track = QRectF(0, 0, self.width(), self.height())

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(active_theme().palette.track_soft))
        painter.drawRoundedRect(track, radius, radius)

        span = int(self.maximum() - self.minimum())
        if span <= 0:
            # Indeterminate: a soft travelling segment with faded tails.
            width = max(28.0, self.width() * 0.22)
            travel = self.width() + width
            x = -width + travel * self._phase
            gradient = QLinearGradient(x, 0, x + width, 0)
            colour = self._chunk_color()
            transparent = QColor(colour)
            transparent.setAlpha(0)
            gradient.setColorAt(0.0, transparent)
            gradient.setColorAt(0.5, colour)
            gradient.setColorAt(1.0, transparent)
            painter.setBrush(gradient)
            painter.drawRoundedRect(QRectF(x, 0, width, self.height()), radius, radius)
            return

        ratio = (self.value() - self.minimum()) / span
        ratio = max(0.0, min(1.0, ratio))
        filled = self.width() * ratio
        if filled <= 0:
            return
        painter.setBrush(self._chunk_color())
        painter.drawRoundedRect(QRectF(0, 0, filled, self.height()), radius, radius)


class Toast(QFrame):
    """Non-blocking feedback that confirms an action and disappears.

    The loading cursor must never be masked by the toast, so it is always
    raised above its siblings and ignores keyboard focus.
    """

    dismissed = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("NPSCToast")
        self.setProperty("toastState", "info")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hide()

        theme = active_theme()
        s = theme.spacing
        layout = QHBoxLayout(self)
        layout.setContentsMargins(s.md, s.sm + 1, s.sm, s.sm + 1)
        layout.setSpacing(s.sm)

        self._dot = QLabel()
        self._dot.setObjectName("ChipDot")
        self._dot.setFixedSize(6, 6)
        layout.addWidget(self._dot, 0, Qt.AlignmentFlag.AlignVCenter)

        self._text = QLabel("")
        self._text.setObjectName("ToastText")
        self._text.setWordWrap(True)
        self._text.setMinimumWidth(180)
        layout.addWidget(self._text, 1)

        self._close = QPushButton("")
        self._close.setObjectName("IconButton")
        self._close.setIcon(
            QIcon(icon_pixmap("close", 12, active_theme().palette.text_tertiary))
        )
        self._close.setFixedSize(20, 20)
        self._close.setToolTip("Cerrar")
        self._close.setAccessibleName("Cerrar notificación")
        self._close.clicked.connect(self.hide_now)
        layout.addWidget(self._close, 0, Qt.AlignmentFlag.AlignVCenter)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide_now)
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(1.0)
        self.setGraphicsEffect(self._effect)

    # ── public API ────────────────────────────────────────────────────────

    def show_message(self, message: str, state: str = "info", duration_ms: int = 2800) -> None:
        self._text.setText(message)
        allowed = ("info", "success", "warning", "error")
        self.setProperty("toastState", state if state in allowed else "info")
        for widget in (self, self._dot, self._text):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.adjustSize()
        self.show()
        self.raise_()
        if motion.motion_enabled():
            self._effect.setOpacity(0.0)
            motion.animate_property(
                self._effect,
                b"opacity",
                1.0,
                duration=active_theme().motion.micro,
                easing=QEasingCurve(QEasingCurve.Type.OutCubic),
            )
        else:
            self._effect.setOpacity(1.0)
        self._timer.stop()
        self._timer.start(duration_ms)

    def hide_now(self) -> None:
        self._timer.stop()
        if not self.isVisible():
            return
        if motion.motion_enabled():
            motion.animate_property(
                self._effect,
                b"opacity",
                0.0,
                duration=active_theme().motion.micro,
                easing=QEasingCurve(QEasingCurve.Type.InCubic),
                on_finished=self._finish_hide,
            )
        else:
            self._finish_hide()

    def _finish_hide(self) -> None:
        self.hide()
        self._effect.setOpacity(1.0)
        self.dismissed.emit(self)

    def message(self) -> str:
        return self._text.text()


class ToastHost(QWidget):
    """Bottom-right stack of toasts that never blocks the app."""

    MAX_VISIBLE = 3

    def __init__(self, parent: QWidget, margin: int = 20) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._margin = margin
        self._toasts: list[Toast] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addStretch(1)
        self._layout = layout

    def show_message(self, message: str, state: str = "info", duration_ms: int = 2800) -> Toast:
        while len(self._toasts) >= self.MAX_VISIBLE:
            self._toasts[0].hide_now()
            self._toasts.pop(0)
        toast = Toast(self)
        toast.dismissed.connect(self._forget)
        self._toasts.append(toast)
        self._layout.addWidget(toast)
        toast.show_message(message, state, duration_ms)
        self._reflow()
        toast.adjustSize()
        self._reflow()
        return toast

    def _forget(self, toast) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
        toast.setParent(None)
        toast.deleteLater()
        self._reflow()

    def _reflow(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.setFixedWidth(max(280, min(420, parent.width() // 3)))
        self.adjustSize()
        height = max(self.sizeHint().height(), 1)
        self.setGeometry(
            parent.width() - self.width() - self._margin,
            parent.height() - height - self._margin,
            self.width(),
            height,
        )
        self.raise_()

    def reposition(self) -> None:
        self._reflow()

    def clear(self) -> None:
        """Dismiss every visible toast (used when a terminal state replaces another)."""
        for toast in list(self._toasts):
            toast.hide_now()
        self._toasts.clear()


class InlineNotice(QFrame):
    """Persistent inline message (form errors, warnings, guidance)."""

    def __init__(self, message: str = "", state: str = "info", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("NPSCInlineNotice")
        self.setProperty("noticeState", "info")

        theme = active_theme()
        s = theme.spacing
        layout = QHBoxLayout(self)
        layout.setContentsMargins(s.md, s.sm, s.md, s.sm)
        layout.setSpacing(s.sm)

        self._text = QLabel(message)
        self._text.setObjectName("InlineNoticeText")
        self._text.setWordWrap(True)
        layout.addWidget(self._text, 1)

        self._action = QPushButton("")
        self._action.setObjectName("SecondaryButton")
        self._action.setCursor(Qt.CursorShape.PointingHandCursor)
        self._action.hide()
        layout.addWidget(self._action, 0, Qt.AlignmentFlag.AlignVCenter)

        self.set_state(state)

    def set_message(self, message: str) -> None:
        self._text.setText(message)
        self.setVisible(bool(message))

    def message(self) -> str:
        return self._text.text()

    def set_state(self, state: str) -> None:
        allowed = ("info", "success", "warning", "error")
        self.setProperty("noticeState", state if state in allowed else "info")
        for widget in (self, self._text):
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def set_action(self, text: str, handler) -> None:
        self._action.setText(text)
        self._action.setVisible(bool(text))
        if text:
            try:
                self._action.clicked.disconnect()
            except RuntimeError:
                pass
            self._action.clicked.connect(handler)


class Skeleton(QFrame):
    """Shimmer placeholder block shown while content loads.

    Painted in one ``paintEvent`` (no child widgets, no layout churn) and
    frozen to a static tint when the user asks for reduced motion.
    """

    def __init__(self, lines: int = 3, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("NPSCSkeleton")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        theme = active_theme()
        self._lines = max(1, lines)
        self._gap = theme.spacing.sm
        self._line_height = 10
        self._phase = 0.0
        self.setMinimumHeight(self._lines * (self._line_height + self._gap) + theme.spacing.sm)
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def _tick(self) -> None:
        self._phase = (self._phase + 0.008) % 1.0
        self.update()

    def showEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().showEvent(event)
        if motion.motion_enabled():
            self._timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self._timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt API)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        palette = active_theme().palette
        base = QColor(palette.bg_button)
        highlight = QColor(palette.bg_button_hover)
        radius = 4.0
        y = 0.0
        widths = (1.0, 0.94, 0.66, 0.88, 0.72)
        for index in range(self._lines):
            width = self.width() * widths[index % len(widths)]
            rect = QRectF(0, y, width, self._line_height)
            path = QPainterPath()
            path.addRoundedRect(rect, radius, radius)
            if motion.motion_enabled():
                offset = (self._phase * (self.width() + 240)) - 240
                gradient = QLinearGradient(offset, 0, offset + 240, 0)
                gradient.setColorAt(0.0, base)
                gradient.setColorAt(0.5, highlight)
                gradient.setColorAt(1.0, base)
                painter.fillPath(path, gradient)
            else:
                painter.fillPath(path, base)
            y += self._line_height + self._gap
        painter.end()


__all__ = [
    "ProgressIndicator",
    "Toast",
    "ToastHost",
    "InlineNotice",
    "Skeleton",
]
