"""Branded startup splash.

Design constraints that this implementation honours:
- It is part of the same visual system: same tokens, same typography, same
  accent as the app. No GIF, no stock artwork.
- The mark is drawn procedurally (a scanning arc over the "N" monogram), so it
  is crisp at any DPI and costs one cheap repaint per frame.
- Maximum 1.5 s, skippable with a click or Escape, and it never blocks startup:
  the main window is built before the splash is shown.
- It leaves with a short fade instead of being cut off.
"""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QApplication, QFrame, QGraphicsOpacityEffect, QWidget

from i18n import tr
from npsc_gui.design.motion import motion_enabled
from npsc_gui.design.style import get_theme


class _BrandMark(QWidget):
    """The monogram plus a scanning arc, painted with QPainter."""

    def __init__(self, size: int = 76, parent=None) -> None:
        super().__init__(parent)
        self._size = size
        self._phase = 0.0
        self.setFixedSize(size, size)
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        if motion_enabled():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.018) % 1.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt API)
        theme = get_theme("dark")
        palette = theme.palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRectF(0, 0, self._size, self._size)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(palette.accent_primary))
        painter.drawRoundedRect(rect, self._size * 0.26, self._size * 0.26)

        # Monogram
        font = QFont("Segoe UI Variable Display", int(self._size * 0.42), QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "N")

        # Scanning arc: a thin highlight that travels around the mark.
        if motion_enabled():
            arc_rect = rect.adjusted(3.5, 3.5, -3.5, -3.5)
            pen = QPen(QColor(palette.accent_brand), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            pen.setColor(QColor(255, 255, 255, 190))
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            start_angle = int((self._phase * 360.0) * 16)
            painter.drawArc(arc_rect, start_angle, int(78 * 16))
        painter.end()


class PremiumSplash(QWidget):
    """Branded, skippable splash. No GIF, no window-level opacity effect."""

    finished = Signal()

    DEFAULT_DURATION = 1200

    def __init__(self, duration_ms: int = DEFAULT_DURATION, on_finished=None) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.SplashScreen
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self._duration = max(400, min(1500, duration_ms))
        self._on_finished = on_finished
        self._closing = False

        theme = get_theme("dark")
        p = theme.palette
        t = theme.typography
        s = theme.spacing

        self.setFixedSize(460, 300)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        card = QFrame(self)
        card.setObjectName("SplashCard")
        card.setGeometry(0, 0, 460, 300)
        card.setStyleSheet(
            f"QFrame#SplashCard {{ background-color: {p.bg_surface};"
            f" border: 1px solid {p.border_default};"
            f" border-radius: {theme.radius.xl}px; }}"
        )
        self._card = card

        from PySide6.QtWidgets import QLabel, QVBoxLayout

        layout = QVBoxLayout(card)
        layout.setContentsMargins(s.xxl, s.xxl, s.xxl, s.xl)
        layout.setSpacing(s.xs)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._mark = _BrandMark(76, card)
        layout.addWidget(self._mark, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(s.md)

        title = QLabel("NeuroPrompt")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {p.text_primary}; font-size: {t.title_size + 5}px;"
            f" font-weight: 600; background: transparent;"
        )
        layout.addWidget(title)

        tagline = QLabel(tr("splash.tagline"))
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setStyleSheet(
            f"color: {p.text_tertiary}; font-size: {t.caption_size + 1}px;"
            " background: transparent;"
        )
        layout.addWidget(tagline)

        layout.addSpacing(s.lg)
        self._bar = QFrame(card)
        self._bar.setFixedHeight(2)
        self._bar.setMinimumWidth(200)
        self._bar.setStyleSheet(
            f"background-color: {p.track_soft}; border: none; border-radius: 1px;"
        )
        layout.addWidget(self._bar, 0, Qt.AlignmentFlag.AlignHCenter)

        self._fill = QFrame(self._bar)
        self._fill.setFixedHeight(2)
        self._fill.setStyleSheet(
            f"background-color: {p.accent_brand}; border: none; border-radius: 1px;"
        )

        layout.addSpacing(s.md)
        self._hint = QLabel(tr("splash.skip"))
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint.setStyleSheet(
            f"color: {p.text_tertiary}; font-size: {t.caption_size - 1}px;"
            " background: transparent;"
        )
        layout.addWidget(self._hint)

        self._progress = 0.0
        self._accepting = True

        self._fade = QGraphicsOpacityEffect(card)
        self._fade.setOpacity(1.0)
        card.setGraphicsEffect(self._fade)

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        self._auto = QTimer(self)
        self._auto.setSingleShot(True)
        self._auto.timeout.connect(self._finish)
        self._auto.start(self._duration)

        self._mark.start()

    # ── lifecycle ─────────────────────────────────────────────────────────

    def center_on_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(
            area.x() + (area.width() - self.width()) // 2,
            area.y() + (area.height() - self.height()) // 2,
        )

    def showEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().showEvent(event)
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def _tick(self) -> None:
        self._progress = min(1.0, self._progress + 16.0 / self._duration)
        width = int(self._bar.width() * self._progress)
        self._fill.setGeometry(0, 0, max(2, width), 2)
        if self._progress >= 1.0:
            self._timer.stop()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().resizeEvent(event)
        width = int(self._bar.width() * self._progress)
        self._fill.setGeometry(0, 0, max(2, width), 2)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self._finish()

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Space, Qt.Key.Key_Return):
            self._finish()
            event.accept()
            return
        super().keyPressEvent(event)

    def _finish(self) -> None:
        """Close once, with a short fade, then notify exactly one listener."""
        if self._closing:
            return
        self._closing = True
        self._accepting = False
        self._auto.stop()
        self._timer.stop()
        self._mark.stop()

        if not motion_enabled():
            self._complete()
            return

        from PySide6.QtCore import QPropertyAnimation

        animation = QPropertyAnimation(self._fade, b"opacity", self)
        animation.setDuration(160)
        animation.setStartValue(1.0)
        animation.setEndValue(0.0)
        animation.setEasingCurve(QEasingCurve.Type.InCubic)
        animation.finished.connect(self._complete)
        animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _complete(self) -> None:
        self.hide()
        callback = self._on_finished
        self._on_finished = None
        if callback is not None:
            callback()
        self.finished.emit()
        self.deleteLater()


__all__ = ["PremiumSplash"]
