"""NPSC theme — backward-compatible facade over the design system.

The visual layer lives in ``npsc_gui.design``:

- ``npsc_gui.design.tokens``  — every colour, size, radius, shadow, duration.
- ``npsc_gui.design.builder`` — ``build_qss(theme)`` generates the stylesheet.

This module keeps the historical import surface (``get_qss``, ``QSS``,
``QSS_DARK``, ``QSS_LIGHT``) so existing callers do not change.
"""
from __future__ import annotations

from npsc_gui.design.builder import build_qss
from npsc_gui.design.tokens import DARK_THEME, LIGHT_THEME, Theme, get_theme

QSS_DARK = build_qss(DARK_THEME)
QSS_LIGHT = build_qss(LIGHT_THEME)
QSS = QSS_DARK


def get_qss(theme: str = "dark") -> str:
    """Return the QSS for the given theme name (``"dark"`` or ``"light"``)."""
    if theme == "light":
        return QSS_LIGHT
    if theme == "dark":
        return QSS_DARK
    return build_qss(get_theme(theme))


__all__ = ["get_qss", "QSS", "QSS_DARK", "QSS_LIGHT", "build_qss", "Theme", "get_theme"]
