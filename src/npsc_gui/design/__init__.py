"""NSCP design system — public API.

``tokens`` owns every colour, size, radius, shadow, duration and easing.
``builder`` turns a :class:`~npsc_gui.design.tokens.Theme` into QSS.
``components`` holds the reusable widgets.
"""
from __future__ import annotations

from npsc_gui.design.builder import build_qss
from npsc_gui.design.tokens import (
    DARK,
    DARK_THEME,
    LIGHT,
    LIGHT_THEME,
    Border,
    Metrics,
    Motion,
    Palette,
    Radius,
    Semantic,
    Shadow,
    Spacing,
    State,
    Theme,
    Typography,
    get_theme,
)

__all__ = [
    "build_qss",
    "get_theme",
    "Theme",
    "Palette",
    "Spacing",
    "Radius",
    "Border",
    "Shadow",
    "Typography",
    "Motion",
    "Metrics",
    "State",
    "Semantic",
    "DARK",
    "LIGHT",
    "DARK_THEME",
    "LIGHT_THEME",
]
