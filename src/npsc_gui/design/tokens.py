"""NSCP design tokens — the single source of truth for the visual layer.

Every colour, size, radius, shadow, duration and easing used by the GUI is
declared here. Widgets and the QSS builder must not contain literal colours,
pixel sizes or durations.

Contrast targets (WCAG 2.1, verified by ``tests/test_design_system.py``):
- text on its surface: >= 4.5:1 (AA body text)
- interactive field boundaries: >= 3:1 (non-text UI component contrast)
- decorative surface separators: intentionally lower, they carry no state
  meaning and are never the only cue for a control.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass


# ─── Spacing ────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Spacing:
    xs: int = 4
    sm: int = 8
    md: int = 12
    lg: int = 16
    xl: int = 24
    xxl: int = 32
    xxxl: int = 48


# ─── Radius ─────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Radius:
    dot: int = 3      # status dots
    sm: int = 6       # small controls (checkbox, chips)
    md: int = 10      # inputs, buttons, dropdowns
    lg: int = 14      # cards, panels
    xl: int = 20      # large surfaces, modals
    pill: int = 13    # pills: radius must stay <= height/2, Qt clamps large values


# ─── Borders ────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Border:
    width: int = 1
    focus_width: int = 2


# ─── Elevation ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Shadow:
    """Documented elevation. Qt QSS has no box-shadow; ``design.elevation``
    applies these to floating surfaces only (toasts, popovers, splash)."""

    card: str = "0 1px 2px rgba(0, 0, 0, 0.20)"
    elevated: str = "0 4px 12px rgba(0, 0, 0, 0.24)"
    popover: str = "0 8px 24px rgba(0, 0, 0, 0.32)"


# ─── Typography ─────────────────────────────────────────────────────────────
# Prefer native fonts on each platform, with installed-family fallbacks.
if sys.platform == "win32":
    _BODY_FONT = '"Segoe UI Variable Text", "Segoe UI", Tahoma, sans-serif'
    _DISPLAY_FONT = '"Segoe UI Variable Display", ' + _BODY_FONT
    _MONO_FONT = '"Cascadia Code", Consolas, "Courier New", monospace'
elif sys.platform == "darwin":
    _BODY_FONT = '"Helvetica Neue", Helvetica, Arial, sans-serif'
    _DISPLAY_FONT = _BODY_FONT
    _MONO_FONT = 'Menlo, Monaco, monospace'
else:
    _BODY_FONT = '"DejaVu Sans", "Liberation Sans", "Noto Sans", Lato, sans-serif'
    _DISPLAY_FONT = _BODY_FONT
    _MONO_FONT = '"DejaVu Sans Mono", "Liberation Mono", "Noto Sans Mono", monospace'


@dataclass(frozen=True)
class Typography:
    family: str = _BODY_FONT
    display_family: str = _DISPLAY_FONT
    mono_family: str = _MONO_FONT

    display_size: int = 24
    display_weight: int = 600
    display_tracking: str = "-0.4px"

    title_size: int = 16
    title_weight: int = 600
    title_tracking: str = "-0.1px"

    section_size: int = 11
    section_weight: int = 600
    section_tracking: str = "0.8px"

    tracking_section: str = "0.8px"
    tracking_button: str = "0.2px"
    tracking_metric: str = "0px"
    tracking_pill: str = "0.2px"

    body_size: int = 13
    body_weight: int = 400

    label_size: int = 12
    label_weight: int = 500

    caption_size: int = 11
    caption_weight: int = 400

    code_size: int = 12
    code_weight: int = 400

    control_size: int = 12
    control_weight: int = 500

    metric_size: int = 30
    metric_weight: int = 600


# ─── Palette ────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Palette:
    # Surfaces (depth is expressed with surface steps, not heavy shadows)
    bg_base: str
    bg_surface: str
    bg_raised: str
    bg_overlay: str
    bg_input: str
    bg_sidebar: str
    bg_header: str
    bg_status: str
    bg_button: str
    bg_button_hover: str
    bg_button_pressed: str
    bg_hover: str
    bg_selected: str

    # Borders
    border_default: str
    border_subtle: str
    border_strong: str
    border_input: str
    border_focus: str

    # Text
    text_primary: str
    text_secondary: str
    text_tertiary: str
    text_on_accent: str

    # Accent
    accent_primary: str
    accent_hover: str
    accent_pressed: str
    accent_brand: str
    accent_soft_bg: str
    accent_soft_border: str

    # Semantic
    success: str
    success_filled: str
    warning: str
    warning_filled: str
    error: str
    error_filled: str
    info: str

    # Chips: background is the foreground colour at low alpha over the surface
    chip_success_bg: str
    chip_success_fg: str
    chip_warning_bg: str
    chip_warning_fg: str
    chip_error_bg: str
    chip_error_fg: str
    chip_info_bg: str
    chip_info_fg: str
    chip_neutral_bg: str
    chip_neutral_fg: str

    # Navigation
    nav_active_bg: str
    nav_active_border: str
    nav_active_text: str

    # Progress / track
    track: str
    track_soft: str


DARK = Palette(
    bg_base="#0A0C0F",
    bg_surface="#0F1216",
    bg_raised="#141920",
    bg_overlay="#1A212A",
    bg_input="#0C1014",
    bg_sidebar="#0B0E12",
    bg_header="#0C0F13",
    bg_status="#0A0C0F",
    bg_button="#1A2028",
    bg_button_hover="#222A34",
    bg_button_pressed="#2A333F",
    bg_hover="rgba(255, 255, 255, 0.045)",
    bg_selected="rgba(95, 200, 242, 0.10)",
    border_default="#262E38",
    border_subtle="#1C232B",
    border_strong="#5F6B7A",
    border_input="#29323D",
    border_focus="#5FC8F2",
    text_primary="#EDF1F5",
    text_secondary="#AEB7C2",
    text_tertiary="#8C96A3",
    text_on_accent="#FFFFFF",
    accent_primary="#1B6096",
    accent_hover="#1F6FA8",
    accent_pressed="#174E7A",
    accent_brand="#5FC8F2",
    accent_soft_bg="rgba(95, 200, 242, 0.10)",
    accent_soft_border="rgba(95, 200, 242, 0.32)",
    success="#3CC98C",
    success_filled="#15724C",
    warning="#E7B04A",
    warning_filled="#8A5A0B",
    error="#F07287",
    error_filled="#B3243C",
    info="#5FC8F2",
    chip_success_bg="rgba(60, 201, 140, 0.13)",
    chip_success_fg="#3CC98C",
    chip_warning_bg="rgba(231, 176, 74, 0.13)",
    chip_warning_fg="#E7B04A",
    chip_error_bg="rgba(240, 114, 135, 0.13)",
    chip_error_fg="#F07287",
    chip_info_bg="rgba(95, 200, 242, 0.12)",
    chip_info_fg="#5FC8F2",
    chip_neutral_bg="rgba(255, 255, 255, 0.05)",
    chip_neutral_fg="#AEB7C2",
    nav_active_bg="rgba(95, 200, 242, 0.11)",
    nav_active_border="#5FC8F2",
    nav_active_text="#7FD4F7",
    track="#232B35",
    track_soft="#1A2129",
)

LIGHT = Palette(
    bg_base="#EEF1F5",
    bg_surface="#FFFFFF",
    bg_raised="#FFFFFF",
    bg_overlay="#FFFFFF",
    bg_input="#FFFFFF",
    bg_sidebar="#F7F9FB",
    bg_header="#FFFFFF",
    bg_status="#F2F4F7",
    bg_button="#E8ECF1",
    bg_button_hover="#DDE3EA",
    bg_button_pressed="#D2D9E2",
    bg_hover="rgba(13, 27, 42, 0.04)",
    bg_selected="rgba(22, 106, 158, 0.08)",
    border_default="#D5DCE4",
    border_subtle="#E4E9EF",
    border_strong="#6B7683",
    border_input="#C3CCD6",
    border_focus="#166A9E",
    text_primary="#12161B",
    text_secondary="#414B57",
    text_tertiary="#525D6B",
    text_on_accent="#FFFFFF",
    accent_primary="#166A9E",
    accent_hover="#1C7BB5",
    accent_pressed="#12557F",
    accent_brand="#166A9E",
    accent_soft_bg="rgba(22, 106, 158, 0.08)",
    accent_soft_border="rgba(22, 106, 158, 0.28)",
    success="#176B46",
    success_filled="#176B46",
    warning="#7A4E08",
    warning_filled="#7A4E08",
    error="#A82336",
    error_filled="#A82336",
    info="#166A9E",
    chip_success_bg="rgba(23, 107, 70, 0.10)",
    chip_success_fg="#176B46",
    chip_warning_bg="rgba(122, 78, 8, 0.10)",
    chip_warning_fg="#7A4E08",
    chip_error_bg="rgba(168, 35, 54, 0.10)",
    chip_error_fg="#A82336",
    chip_info_bg="rgba(22, 106, 158, 0.09)",
    chip_info_fg="#166A9E",
    chip_neutral_bg="rgba(13, 27, 42, 0.05)",
    chip_neutral_fg="#414B57",
    nav_active_bg="rgba(22, 106, 158, 0.09)",
    nav_active_border="#166A9E",
    nav_active_text="#12557F",
    track="#D8DEE6",
    track_soft="#E6EBF0",
)


# ─── Component metrics ──────────────────────────────────────────────────────
@dataclass(frozen=True)
class Metrics:
    header_height: int = 56
    statusbar_height: int = 26
    sidebar_width: int = 216
    progress_thickness: int = 4
    button_height: int = 32
    button_height_large: int = 40
    input_height: int = 34
    chip_height: int = 24
    icon_button_size: int = 30
    nav_item_height: int = 34
    tab_height: int = 34
    result_card_width: int = 880
    content_max_width: int = 1240
    rail_width: int = 312
    editor_min_height: int = 190
    dropdown_arrow_width: int = 4
    dropdown_arrow_height: int = 5


# ─── Motion ─────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Motion:
    instant: int = 0
    micro: int = 120
    short: int = 200
    medium: int = 280
    long: int = 450

    ease_enter: str = "cubic-bezier(0.16, 1, 0.3, 1)"
    ease_exit: str = "cubic-bezier(0.4, 0, 1, 1)"
    ease_standard: str = "cubic-bezier(0.4, 0, 0.2, 1)"
    ease_fast: str = "cubic-bezier(0.2, 0, 0, 1)"


# ─── States ─────────────────────────────────────────────────────────────────
class State:
    """Component state names consumed by widgets and the QSS builder."""

    DEFAULT = "default"
    HOVER = "hover"
    PRESSED = "pressed"
    FOCUS = "focus"
    SELECTED = "selected"
    DISABLED = "disabled"
    LOADING = "loading"
    ERROR = "error"
    SUCCESS = "success"


class Semantic:
    """StatusChip / ResultCard semantic variants."""

    IDLE = "idle"
    READY = "ready"
    WORKING = "working"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


# ─── Theme ──────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Theme:
    name: str
    palette: Palette
    spacing: Spacing = Spacing()
    radius: Radius = Radius()
    border: Border = Border()
    shadow: Shadow = Shadow()
    typography: Typography = Typography()
    motion: Motion = Motion()
    metrics: Metrics = Metrics()


DARK_THEME = Theme(name="dark", palette=DARK)
LIGHT_THEME = Theme(name="light", palette=LIGHT)


def get_theme(name: str = "dark") -> Theme:
    """Return the theme for ``name`` (``"dark"`` or ``"light"``)."""
    return LIGHT_THEME if name == "light" else DARK_THEME
