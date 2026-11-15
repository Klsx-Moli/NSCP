"""Compatibility shim — the real tokens live in ``npsc_gui.design.tokens``.

Kept so historical imports (``SPACING``, ``RADIUS``, ``MOTION``, ``TYPOGRAPHY``,
``SHADOWS``) keep working. New code must import from ``npsc_gui.design``.
"""
from __future__ import annotations

from npsc_gui.design.tokens import (
    DARK,
    LIGHT,
    Border,
    Metrics,
    Motion,
    Palette,
    Radius,
    Shadow,
    Spacing,
    Typography,
    get_theme,
)

SPACING = Spacing()
RADIUS = Radius()
MOTION = Motion()
BORDER = Border()
SHADOW = Shadow()
METRICS = Metrics()
TYPOGRAPHY = Typography()
PALETTE_DARK = DARK
PALETTE_LIGHT = LIGHT

__all__ = [
    "SPACING",
    "RADIUS",
    "MOTION",
    "BORDER",
    "SHADOW",
    "METRICS",
    "TYPOGRAPHY",
    "PALETTE_DARK",
    "PALETTE_LIGHT",
    "DARK",
    "LIGHT",
    "Palette",
    "Spacing",
    "Radius",
    "Border",
    "Shadow",
    "Typography",
    "Motion",
    "Metrics",
    "get_theme",
]
