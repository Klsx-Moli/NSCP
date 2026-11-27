"""Motion helpers — every animation in the app goes through here.

Rules enforced by this module:
- Durations and easings come from ``design.tokens.Motion``; no literal ms or
  cubic-bezier values elsewhere.
- Animations target cheap properties only (opacity on small widgets, geometry,
  or a custom property). No opacity effect on top-level windows.
- ``ui/reduce_motion`` turns every duration into 0 ms, so animations collapse
  to an immediate state change instead of being skipped inconsistently.
"""
from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRect,
    QSettings,
    QObject,
)

from npsc_gui.design.tokens import Motion, Theme

_SETTING_KEY = "ui/reduce_motion"

#: In-process override so a preference change applies immediately, without a
#: round-trip to the registry and without depending on QSettings availability.
_reduce_override: bool | None = None


def motion_enabled() -> bool:
    """True when animations are allowed (the default)."""
    return not reduce_motion()


def reduce_motion() -> bool:
    """True when the user asked for reduced motion."""
    if _reduce_override is not None:
        return _reduce_override
    raw = QSettings().value(_SETTING_KEY, False)
    if isinstance(raw, str):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    return bool(raw)


def set_motion_enabled(enabled: bool) -> None:
    """Persist the *reduce motion* preference and apply it immediately."""
    global _reduce_override
    _reduce_override = not enabled
    QSettings().setValue(_SETTING_KEY, not enabled)


def _duration(motion: Motion, duration: int | None) -> int:
    if reduce_motion():
        return motion.instant
    return duration if duration is not None else motion.short


def _easing(motion: Motion, curve: QEasingCurve | None, fallback: str) -> QEasingCurve:
    if curve is not None:
        return curve
    table = {
        motion.ease_enter: QEasingCurve.Type.OutCubic,
        motion.ease_exit: QEasingCurve.Type.InCubic,
        motion.ease_standard: QEasingCurve.Type.InOutCubic,
        motion.ease_fast: QEasingCurve.Type.OutQuad,
    }
    return QEasingCurve(table.get(fallback, QEasingCurve.Type.OutCubic))


def animate_property(
    obj: QObject,
    property_name: bytes | str,
    end_value: object,
    *,
    theme: Theme | None = None,
    duration: int | None = None,
    easing: QEasingCurve | None = None,
    easing_name: str | None = None,
    on_finished=None,
) -> QPropertyAnimation:
    """Animate ``property_name`` of ``obj`` to ``end_value`` and return the animation."""
    motion = (theme.motion if theme else Motion())
    anim = QPropertyAnimation(obj, property_name, obj)
    anim.setEndValue(end_value)
    anim.setDuration(_duration(motion, duration))
    anim.setEasingCurve(_easing(motion, easing, easing_name or motion.ease_standard))
    if on_finished is not None:
        anim.finished.connect(on_finished)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


def animate_opacity(
    widget,
    end_opacity: float,
    *,
    theme: Theme | None = None,
    duration: int | None = None,
    easing: QEasingCurve | None = None,
    easing_name: str | None = None,
    on_finished=None,
):
    """Fade a small widget in/out using ``QGraphicsOpacityEffect``.

    Only for small components (toasts, cards, chips) — never for top-level
    windows, where the effect causes flicker and DPI issues.
    """
    from PySide6.QtWidgets import QGraphicsOpacityEffect

    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(end_opacity)
        widget.setGraphicsEffect(effect)
    return animate_property(
        effect,
        b"opacity",
        end_opacity,
        theme=theme,
        duration=duration,
        easing=easing,
        easing_name=easing_name,
        on_finished=on_finished,
    )


def reveal(widget, *, theme: Theme | None = None, offset: int = 8) -> None:
    """Fade a freshly shown panel in with a cheap opacity-only animation.

    Never animates ``geometry`` on a layout-managed widget: doing so fights the
    layout and the sibling widgets overlap while the animation runs.
    """
    if not motion_enabled() or widget is None or not widget.isVisible():
        return
    from PySide6.QtWidgets import QGraphicsOpacityEffect

    motion = theme.motion if theme else Motion()
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)

    fade = QPropertyAnimation(effect, b"opacity", widget)
    fade.setDuration(motion.short)
    fade.setStartValue(0.0)
    fade.setEndValue(1.0)
    fade.setEasingCurve(QEasingCurve.Type.OutCubic)
    fade.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


def fade_in(widget, *, theme: Theme | None = None, duration: int | None = None) -> None:
    """Fade an already-visible small widget in without moving it."""
    if not motion_enabled() or widget is None:
        return
    motion = theme.motion if theme else Motion()
    animate_opacity(
        widget,
        1.0,
        theme=theme,
        duration=duration if duration is not None else motion.micro,
        easing_name=motion.ease_enter,
    )


def pulse(widget, *, theme: Theme | None = None) -> None:
    """A single subtle attention pulse for a status element."""
    if not motion_enabled() or widget is None:
        return
    from PySide6.QtWidgets import QGraphicsOpacityEffect

    motion = theme.motion if theme else Motion()
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)

    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(motion.medium)
    anim.setStartValue(1.0)
    anim.setKeyValueAt(0.45, 0.45)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


def animate_geometry(
    widget,
    end_rect: QRect,
    *,
    theme: Theme | None = None,
    duration: int | None = None,
    easing: QEasingCurve | None = None,
    easing_name: str | None = None,
    on_finished=None,
) -> QPropertyAnimation:
    """Animate a widget's geometry (layout transitions, panel reveals)."""
    return animate_property(
        widget,
        b"geometry",
        end_rect,
        theme=theme,
        duration=duration,
        easing=easing,
        easing_name=easing_name,
        on_finished=on_finished,
    )


__all__ = [
    "motion_enabled",
    "reduce_motion",
    "set_motion_enabled",
    "animate_property",
    "animate_opacity",
    "animate_geometry",
    "reveal",
    "fade_in",
    "pulse",
]
