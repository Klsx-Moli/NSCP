"""QSS builder — generates the whole stylesheet from design tokens.

One function, one place. Every selector is emitted exactly once; a duplicate
raises immediately instead of silently overriding an earlier rule.

Depth is expressed with surface steps and 1 px borders. No rule paints an
opaque background behind generic ``QWidget``: that single global rule used to
draw a visible rectangle behind every ``QLabel`` (the "fake tab" artefacts
under the header). Only named surfaces own a background.
"""
from __future__ import annotations

from npsc_gui.design.tokens import Theme


def _block(selector: str, **props: object) -> str:
    lines = [f"{selector} {{"]
    for key, value in props.items():
        lines.append(f"    {key.replace('_', '-')}: {value};")
    lines.append("}")
    return "\n".join(lines)


class _Sheet:
    """Collects QSS blocks and refuses duplicate selectors."""

    def __init__(self) -> None:
        self._blocks: list[str] = []
        self._seen: set[str] = set()

    def add(self, selector: str, **props: object) -> None:
        if selector in self._seen:
            raise ValueError(f"duplicate QSS selector: {selector!r}")
        self._seen.add(selector)
        self._blocks.append(_block(selector, **props))

    def render(self) -> str:
        return "\n\n".join(self._blocks) + "\n"


def build_qss(theme: Theme) -> str:
    """Return the complete application stylesheet for ``theme``."""
    c = theme.palette
    s = theme.spacing
    r = theme.radius
    b = theme.border
    t = theme.typography
    m = theme.metrics
    sh = _Sheet()

    font_family = t.family
    control_padding = f"{s.sm - 2}px {s.md}px"
    inputs = "QComboBox, QLineEdit, QTextEdit, QPlainTextEdit, QListWidget, QSpinBox"

    # ── Global ──────────────────────────────────────────────────────────────
    sh.add(
        "*",
        font_family=font_family,
        font_size=f"{t.body_size}px",
        color=c.text_primary,
    )
    sh.add("QMainWindow", background_color=c.bg_base)
    sh.add(
        "QWidget#RootSurface",
        background_color=c.bg_base,
        color=c.text_primary,
    )
    sh.add("QDialog", background_color=c.bg_surface, color=c.text_primary)
    sh.add(
        "QToolTip",
        background_color=c.bg_overlay,
        color=c.text_primary,
        border=f"{b.width}px solid {c.border_strong}",
        border_radius=f"{r.sm}px",
        padding=f"{s.xs + 2}px {s.sm}px",
        font_size=f"{t.caption_size}px",
    )

    # ── Chrome: header / sidebar / status bar ───────────────────────────────
    sh.add(
        "QFrame#Header",
        background_color=c.bg_header,
        border_bottom=f"{b.width}px solid {c.border_subtle}",
    )
    sh.add(
        "QFrame#StatusBar",
        background_color=c.bg_status,
        border_top=f"{b.width}px solid {c.border_subtle}",
    )
    sh.add(
        "QFrame#Sidebar",
        background_color=c.bg_sidebar,
        border_right=f"{b.width}px solid {c.border_subtle}",
    )
    sh.add(
        "QFrame#SidebarDivider",
        background_color=c.border_subtle,
        border="none",
    )
    sh.add(
        "QLabel#BrandGlyph",
        color=c.text_on_accent,
        background_color=c.accent_primary,
        border_radius=f"{r.md}px",
        font_size=f"{t.title_size}px",
        font_weight=t.display_weight,
    )
    sh.add(
        "QLabel#BrandWordmark",
        font_size=f"{t.body_size + 1}px",
        font_weight=600,
        color=c.text_primary,
        background_color="transparent",
        letter_spacing=t.title_tracking,
    )
    sh.add(
        "QLabel#AppTitle",
        font_size=f"{t.body_size}px",
        font_weight=t.title_weight,
        color=c.text_primary,
        background_color="transparent",
    )
    sh.add(
        "QLabel#AppSubtitle",
        font_size=f"{t.caption_size}px",
        color=c.text_tertiary,
        background_color="transparent",
    )
    sh.add(
        "QLabel#HeaderDivider",
        background_color=c.border_default,
        border="none",
    )
    sh.add(
        "QLabel#Muted, QLabel.Muted",
        color=c.text_tertiary,
        background_color="transparent",
    )
    sh.add(
        "QLabel#SectionLabel",
        font_size=f"{t.section_size}px",
        font_weight=t.section_weight,
        color=c.text_tertiary,
        letter_spacing=t.section_tracking,
        background_color="transparent",
        padding_bottom=f"{s.xs}px",
    )
    sh.add(
        "QLabel#SectionTitle",
        font_size=f"{t.section_size}px",
        font_weight=t.section_weight,
        color=c.text_secondary,
        letter_spacing=t.section_tracking,
        padding_bottom=f"{s.xs}px",
        background_color="transparent",
        border="none",
    )
    sh.add(
        "QLabel#PageTitle",
        font_size=f"{t.display_size}px",
        font_weight=t.display_weight,
        color=c.text_primary,
        letter_spacing=t.display_tracking,
        background_color="transparent",
    )
    sh.add(
        "QLabel#PageSubtitle",
        font_size=f"{t.body_size}px",
        color=c.text_secondary,
        background_color="transparent",
    )
    sh.add(
        "QLabel#FieldLabel",
        font_size=f"{t.label_size}px",
        font_weight=t.label_weight,
        color=c.text_secondary,
        background_color="transparent",
    )
    sh.add(
        "QLabel#MicroLabel",
        font_size=f"{t.caption_size}px",
        color=c.text_tertiary,
        background_color="transparent",
    )
    sh.add(
        "QLabel#ValueStrong",
        font_size=f"{t.control_size}px",
        font_weight=600,
        color=c.text_primary,
        background_color="transparent",
    )
    sh.add(
        "QLabel#MonoText",
        font_family=t.mono_family,
        font_size=f"{t.caption_size}px",
        color=c.text_tertiary,
        background_color="transparent",
    )

    # ── Buttons ─────────────────────────────────────────────────────────────
    sh.add(
        "QPushButton",
        background_color=c.bg_button,
        color=c.text_primary,
        border=f"{b.width}px solid {c.border_default}",
        border_radius=f"{r.md}px",
        padding=control_padding,
        font_weight=t.control_weight,
        font_size=f"{t.control_size}px",
        min_height=f"{m.button_height - 12}px",
    )
    sh.add(
        "QPushButton:hover",
        background_color=c.bg_button_hover,
        border_color=c.border_strong,
    )
    sh.add(
        "QPushButton:pressed, QPushButton:checked",
        background_color=c.bg_button_pressed,
        color=c.text_primary,
        border_color=c.border_strong,
    )
    sh.add(
        "QPushButton:disabled",
        background_color="transparent",
        color=c.text_tertiary,
        border_color=c.border_subtle,
    )
    sh.add(
        'QPushButton[compact="true"]',
        padding=f"{s.xs}px {s.sm + 2}px",
        min_height="24px",
    )
    sh.add(
        "QPushButton#PrimaryButton",
        background_color=c.accent_primary,
        color=c.text_on_accent,
        font_weight=600,
        border=f"{b.width}px solid {c.accent_primary}",
        padding=f"{s.sm}px {s.lg + 2}px",
        font_size=f"{t.control_size}px",
        letter_spacing=t.tracking_button,
        min_height=f"{m.button_height_large - 14}px",
    )
    sh.add(
        "QPushButton#PrimaryButton:hover",
        background_color=c.accent_hover,
        border_color=c.accent_hover,
    )
    sh.add(
        "QPushButton#PrimaryButton:pressed",
        background_color=c.accent_pressed,
        border_color=c.accent_pressed,
        padding_top=f"{s.sm + 1}px",
        padding_bottom=f"{s.sm - 1}px",
    )
    sh.add(
        "QPushButton#PrimaryButton:disabled",
        background_color=c.bg_button,
        color=c.text_tertiary,
        border_color=c.border_default,
    )
    sh.add(
        'QPushButton#PrimaryButton[loading="true"]',
        background_color=c.accent_pressed,
        color=c.text_on_accent,
    )
    sh.add(
        "QPushButton#SecondaryButton",
        background_color="transparent",
        color=c.text_secondary,
        border=f"{b.width}px solid {c.border_default}",
        font_weight=t.control_weight,
        min_height=f"{m.button_height - 12}px",
    )
    sh.add(
        "QPushButton#SecondaryButton:hover",
        color=c.text_primary,
        background_color=c.bg_hover,
        border_color=c.border_strong,
    )
    sh.add(
        "QPushButton#SecondaryButton:pressed",
        background_color=c.bg_button,
        color=c.text_primary,
    )
    sh.add(
        "QPushButton#SecondaryButton:disabled",
        color=c.text_tertiary,
        border_color=c.border_subtle,
        background_color="transparent",
    )
    sh.add(
        "QPushButton#GhostButton",
        background_color="transparent",
        color=c.text_tertiary,
        border=f"{b.width}px solid transparent",
        padding=f"{s.xs}px {s.sm}px",
        min_height="24px",
        font_size=f"{t.caption_size + 1}px",
    )
    sh.add(
        "QPushButton#GhostButton:hover",
        color=c.text_primary,
        background_color=c.bg_hover,
    )
    sh.add(
        "QPushButton#GhostButton:pressed",
        background_color=c.bg_button,
        color=c.text_primary,
    )
    sh.add(
        "QPushButton#GhostButton:disabled",
        color=c.text_tertiary,
        background_color="transparent",
    )
    sh.add(
        "QPushButton#DangerButton",
        background_color="transparent",
        color=c.error,
        border=f"{b.width}px solid {c.border_default}",
    )
    sh.add(
        "QPushButton#DangerButton:hover",
        background_color=c.chip_error_bg,
        border_color=c.error,
        color=c.error,
    )
    sh.add(
        "QPushButton#DangerButton:pressed",
        background_color=c.error_filled,
        border_color=c.error_filled,
        color=c.text_on_accent,
    )
    sh.add(
        "QPushButton#HeaderIconButton",
        padding="0px",
        background_color="transparent",
        border=f"{b.width}px solid transparent",
        color=c.text_tertiary,
        border_radius=f"{r.sm}px",
        font_size=f"{t.body_size}px",
        min_height="0px",
    )
    sh.add(
        "QPushButton#HeaderIconButton:hover",
        background_color=c.bg_hover,
        color=c.text_primary,
        border_color=c.border_default,
    )
    sh.add(
        "QPushButton#HeaderIconButton:pressed",
        background_color=c.bg_button,
        color=c.text_primary,
    )
    sh.add(
        "QPushButton#IconButton",
        padding="0px",
        background_color="transparent",
        border=f"{b.width}px solid transparent",
        color=c.text_tertiary,
        border_radius=f"{r.sm}px",
        font_size=f"{t.body_size}px",
        min_height="0px",
    )
    sh.add(
        "QPushButton#IconButton:hover",
        background_color=c.bg_hover,
        color=c.text_primary,
        border_color=c.border_default,
    )
    sh.add(
        "QPushButton#IconButton:pressed",
        background_color=c.bg_button,
        color=c.text_primary,
    )
    sh.add(
        "QPushButton#IconButton:disabled",
        color=c.text_tertiary,
        background_color="transparent",
        border="none",
    )
    sh.add(
        "QPushButton#ModeToggleBtn",
        background_color="transparent",
        color=c.text_secondary,
        border=f"{b.width}px solid {c.border_default}",
        border_radius=f"{r.sm}px",
        padding=f"{s.xs + 1}px {s.md}px",
        font_weight=500,
        font_size=f"{t.caption_size + 1}px",
        min_height="24px",
    )
    sh.add(
        "QPushButton#ModeToggleBtn:hover",
        background_color=c.bg_hover,
        color=c.text_primary,
        border_color=c.border_strong,
    )
    sh.add(
        "QPushButton#ModeToggleBtn:pressed",
        background_color=c.bg_button,
    )
    sh.add(
        "QPushButton#LinkButton",
        background_color="transparent",
        border="none",
        color=c.accent_brand,
        padding="0px",
        font_size=f"{t.caption_size}px",
        min_height="0px",
    )
    sh.add(
        "QPushButton#LinkButton:hover",
        color=c.text_primary,
    )

    # ── Navigation ──────────────────────────────────────────────────────────
    sh.add(
        "QPushButton#NPSCNavItem",
        text_align="left",
        padding=f"{s.sm}px {s.md}px",
        background_color="transparent",
        border="none",
        border_left=f"{b.width + 2}px solid rgba(0, 0, 0, 0)",
        color=c.text_secondary,
        border_radius="0px",
        font_size=f"{t.control_size}px",
        font_weight=500,
        min_height=f"{m.nav_item_height - 14}px",
    )
    sh.add(
        "QPushButton#NPSCNavItem:hover",
        background_color=c.bg_hover,
        color=c.text_primary,
    )
    sh.add(
        "QPushButton#NPSCNavItem:pressed",
        background_color=c.bg_button,
    )
    sh.add(
        "QPushButton#NPSCNavItem:checked",
        background_color=c.nav_active_bg,
        border_left=f"{b.width + 2}px solid {c.nav_active_border}",
        color=c.nav_active_text,
        font_weight=600,
    )
    sh.add(
        "QPushButton#SidebarToggle",
        background_color="transparent",
        border="none",
        padding="0px",
        border_radius=f"{r.sm}px",
        min_height="24px",
        max_height="24px",
        min_width="28px",
        max_width="28px",
    )
    sh.add(
        "QPushButton#SidebarToggle:hover",
        background_color=c.bg_hover,
    )
    sh.add(
        "QPushButton#SidebarToggle:pressed",
        background_color=c.bg_button,
    )
    sh.add(
        "QLabel#NavGroupLabel",
        padding=f"{s.md}px {s.md}px {s.xs}px",
        font_size=f"{t.section_size}px",
        color=c.text_tertiary,
        font_weight=600,
        letter_spacing=t.section_tracking,
        background_color="transparent",
    )
    sh.add("QFrame#NPSCNavGroup", background_color="transparent", border="none")

    # ── Inputs ──────────────────────────────────────────────────────────────
    sh.add(
        inputs,
        background_color=c.bg_input,
        color=c.text_primary,
        border=f"{b.width}px solid {c.border_input}",
        border_radius=f"{r.md}px",
        padding=f"{s.sm - 1}px {s.sm + 2}px",
        selection_background_color=c.accent_primary,
        selection_color=c.text_on_accent,
        font_size=f"{t.control_size + 1}px",
    )
    sh.add(
        f"{inputs}:hover",
        border_color=c.border_strong,
    )
    sh.add(
        f"{inputs}:focus",
        border_color=c.border_focus,
    )
    sh.add(
        f"{inputs}:disabled",
        color=c.text_tertiary,
        border_color=c.border_subtle,
        background_color=c.bg_surface,
    )
    sh.add(
        "QPlainTextEdit, QTextEdit",
        padding=f"{s.md}px",
        font_size=f"{t.body_size}px",
        line_height="1.5",
    )
    sh.add(
        "QComboBox::drop-down",
        border="none",
        width=f"{s.xl - 4}px",
    )
    sh.add(
        "QComboBox::down-arrow",
        image="none",
        border_left=f"{m.dropdown_arrow_width}px solid transparent",
        border_right=f"{m.dropdown_arrow_width}px solid transparent",
        border_top=f"{m.dropdown_arrow_height}px solid {c.text_tertiary}",
        margin_right=f"{s.xs}px",
    )
    sh.add(
        "QComboBox QAbstractItemView",
        background_color=c.bg_overlay,
        color=c.text_primary,
        border=f"{b.width}px solid {c.border_strong}",
        border_radius=f"{r.sm}px",
        padding=f"{s.xs}px",
        selection_background_color=c.accent_primary,
        selection_color=c.text_on_accent,
        outline="none",
    )
    sh.add(
        "QListWidget::item",
        border_radius=f"{r.sm}px",
        padding=f"{s.sm - 1}px {s.sm}px",
        margin=f"{s.xs // 2}px",
    )
    sh.add(
        "QListWidget::item:selected",
        background_color=c.accent_primary,
        color=c.text_on_accent,
    )
    sh.add(
        "QListWidget::item:hover",
        background_color=c.bg_hover,
    )
    sh.add(
        "QCheckBox",
        color=c.text_primary,
        spacing=f"{s.sm}px",
        background_color="transparent",
        font_size=f"{t.control_size + 1}px",
    )
    sh.add(
        "QCheckBox::indicator",
        width=f"{s.lg}px",
        height=f"{s.lg}px",
        border=f"{b.width}px solid {c.border_strong}",
        border_radius=f"{r.sm - 2}px",
        background_color=c.bg_input,
    )
    sh.add(
        "QCheckBox::indicator:hover",
        border_color=c.accent_brand,
        background_color=c.bg_button,
    )
    sh.add(
        "QCheckBox::indicator:checked",
        background_color=c.accent_primary,
        border_color=c.accent_primary,
        image="none",
    )
    sh.add(
        "QCheckBox:disabled",
        color=c.text_tertiary,
    )
    sh.add(
        "QCheckBox::indicator:disabled",
        border_color=c.border_subtle,
        background_color=c.bg_surface,
    )

    # ── Tabs ────────────────────────────────────────────────────────────────
    sh.add(
        "QTabWidget::pane",
        border=f"{b.width}px solid {c.border_subtle}",
        background_color=c.bg_surface,
        border_radius=f"{r.md}px",
        top="-1px",
    )
    sh.add(
        "QTabWidget::tab-bar",
        alignment="left",
    )
    sh.add(
        "QTabBar",
        background_color="transparent",
    )
    sh.add(
        "QTabBar::tab",
        background_color="transparent",
        color=c.text_tertiary,
        border="none",
        border_bottom=f"{b.width + 1}px solid transparent",
        padding=f"{s.sm - 1}px {s.sm + 1}px",
        margin_right=f"{s.xs // 2}px",
        font_size=f"{t.caption_size + 1}px",
        min_height=f"{m.tab_height - 22}px",
    )
    sh.add(
        "QTabBar::tab:hover",
        color=c.text_primary,
    )
    sh.add(
        "QTabBar::tab:selected",
        color=c.text_primary,
        border_bottom=f"{b.width + 1}px solid {c.accent_brand}",
        font_weight=600,
    )
    sh.add(
        "QTabBar::tab:disabled",
        color=c.text_tertiary,
    )

    # ── Progress ────────────────────────────────────────────────────────────
    sh.add(
        "QProgressBar",
        background_color=c.track_soft,
        border="none",
        border_radius=f"{r.dot}px",
        color=c.text_secondary,
        text_align="center",
        font_weight=600,
        font_size=f"{t.caption_size}px",
        min_height=f"{m.progress_thickness}px",
        max_height=f"{m.progress_thickness}px",
    )
    sh.add(
        "QProgressBar::chunk",
        background_color=c.accent_brand,
        border_radius=f"{r.dot}px",
    )
    sh.add(
        'QProgressBar[progressState="success"]::chunk',
        background_color=c.success,
    )
    sh.add(
        'QProgressBar[progressState="error"]::chunk',
        background_color=c.error,
    )
    sh.add(
        'QProgressBar[progressState="warning"]::chunk',
        background_color=c.warning,
    )

    # ── Splitter / scrollbars ───────────────────────────────────────────────
    sh.add(
        "QSplitter::handle",
        background_color=c.border_subtle,
    )
    sh.add(
        "QSplitter::handle:hover",
        background_color=c.border_strong,
    )
    sh.add(
        "QSplitter::handle:horizontal",
        width=f"{b.width}px",
    )
    sh.add(
        "QSplitter::handle:vertical",
        height=f"{b.width}px",
    )
    sh.add(
        "QScrollArea",
        background_color="transparent",
        border="none",
    )
    sh.add(
        "QScrollArea > QWidget > QWidget",
        background_color="transparent",
    )
    sh.add(
        "QScrollBar:vertical",
        background_color="transparent",
        border="none",
        width="10px",
        margin="2px",
    )
    sh.add(
        "QScrollBar:horizontal",
        background_color="transparent",
        border="none",
        height="10px",
        margin="2px",
    )
    sh.add(
        "QScrollBar::handle:vertical, QScrollBar::handle:horizontal",
        background_color=c.border_default,
        border_radius="3px",
        min_height=f"{s.xl}px",
        min_width=f"{s.xl}px",
    )
    sh.add(
        "QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover",
        background_color=c.border_strong,
    )
    sh.add(
        "QScrollBar::add-line, QScrollBar::sub-line",
        background_color="transparent",
        border="none",
        width="0px",
        height="0px",
    )
    sh.add(
        "QScrollBar::add-page, QScrollBar::sub-page",
        background_color="transparent",
        border="none",
    )

    # ── Status labels (legacy property) ────────────────────────────────────
    sh.add(
        'QLabel[statusState="procesando"], QLabel[statusState="warning"]',
        color=c.warning,
    )
    sh.add(
        'QLabel[statusState="error"], QLabel[statusState="bloqueado"], '
        'QLabel[statusState="blocked"], QLabel[statusState="fail"]',
        color=c.error,
    )
    sh.add(
        'QLabel[statusState="cancelado"]',
        color=c.text_tertiary,
    )
    sh.add(
        'QLabel[statusState="pass"], QLabel[statusState="normal"]',
        color=c.success,
    )

    # ── Context help ────────────────────────────────────────────────────────
    sh.add(
        "QToolButton#HelpIconButton",
        background_color="transparent",
        color=c.text_tertiary,
        border=f"{b.width}px solid transparent",
        border_radius=f"{r.pill}px",
        padding="0px",
        font_weight=600,
        font_size=f"{t.caption_size}px",
    )
    sh.add(
        "QToolButton#HelpIconButton:hover",
        background_color=c.bg_hover,
        color=c.text_primary,
        border_color=c.border_default,
    )
    sh.add(
        "QToolButton#HelpIconButton:focus",
        border_color=c.border_focus,
        color=c.text_primary,
    )
    sh.add(
        "QFrame#ContextHelpPopover",
        background_color=c.bg_overlay,
        color=c.text_primary,
        border=f"{b.width}px solid {c.border_strong}",
        border_radius=f"{r.md}px",
    )
    sh.add(
        "QLabel#ContextHelpTitle",
        color=c.text_primary,
        font_weight=600,
        font_size=f"{t.control_size + 1}px",
        background_color="transparent",
    )
    sh.add(
        "QLabel#ContextHelpBody",
        color=c.text_secondary,
        font_size=f"{t.caption_size + 1}px",
        background_color="transparent",
    )
    sh.add(
        "QToolButton#ContextHelpAction",
        background_color="transparent",
        color=c.accent_brand,
        border="none",
        padding="0px",
        font_size=f"{t.caption_size + 1}px",
    )

    # ── Cards ───────────────────────────────────────────────────────────────
    sh.add(
        "QFrame#NPSCCard",
        background_color=c.bg_surface,
        border=f"{b.width}px solid {c.border_subtle}",
        border_radius=f"{r.lg}px",
    )
    sh.add(
        "QFrame#NPSCPanel",
        background_color=c.bg_surface,
        border=f"{b.width}px solid {c.border_subtle}",
        border_radius=f"{r.lg}px",
    )
    sh.add(
        "QFrame#NPSCResultCard",
        background_color=c.bg_surface,
        border=f"{b.width}px solid {c.border_subtle}",
        border_radius=f"{r.lg}px",
    )
    sh.add(
        "QFrame#NPSCResultCard[resultState=\"success\"]",
        border_color=c.accent_soft_border,
    )
    sh.add(
        "QFrame#NPSCResultCard[resultState=\"warning\"]",
        border_color=c.chip_warning_fg,
    )
    sh.add(
        "QFrame#NPSCResultCard[resultState=\"error\"]",
        border_color=c.chip_error_fg,
    )
    sh.add(
        "QFrame#CardSeparator",
        background_color=c.border_subtle,
        border="none",
    )
    sh.add(
        "QLabel#ResultCardValue",
        font_family=t.display_family,
        font_size=f"{t.metric_size}px",
        font_weight=t.metric_weight,
        color=c.text_tertiary,
        background_color="transparent",
        border="none",
    )
    for semantic, colour in (
        ("success", c.success),
        ("info", c.accent_brand),
        ("warning", c.warning),
        ("error", c.error),
        ("muted", c.text_tertiary),
    ):
        sh.add(f'QLabel#ResultCardValue[semantic="{semantic}"]', color=colour)
    sh.add(
        "QLabel#ResultCardLabel",
        font_size=f"{t.section_size}px",
        color=c.text_tertiary,
        background_color="transparent",
        border="none",
        letter_spacing=t.tracking_pill,
    )
    sh.add(
        "QLabel#ResultTitle",
        font_size=f"{t.title_size}px",
        font_weight=t.title_weight,
        color=c.text_primary,
        letter_spacing=t.title_tracking,
        background_color="transparent",
        border="none",
    )
    sh.add(
        "QLabel#ResultMeta",
        font_size=f"{t.caption_size + 1}px",
        color=c.text_tertiary,
        background_color="transparent",
        border="none",
    )
    sh.add(
        "QLabel#ResultBody",
        font_size=f"{t.body_size}px",
        color=c.text_secondary,
        background_color="transparent",
        border="none",
    )
    sh.add(
        "QPlainTextEdit#ResultBody",
        background_color=c.bg_input,
        border=f"{b.width}px solid {c.border_subtle}",
        border_radius=f"{r.sm}px",
        padding=f"{s.md}px",
        font_family=t.mono_family,
        font_size=f"{t.code_size}px",
        color=c.text_secondary,
        selection_background_color=c.accent_primary,
        selection_color=c.text_on_accent,
    )
    sh.add(
        "QPlainTextEdit#ResultBody:focus",
        border_color=c.border_default,
    )
    sh.add(
        "QLabel#MetricValue",
        font_family=t.display_family,
        font_size=f"{t.title_size + 6}px",
        font_weight=600,
        color=c.text_primary,
        background_color="transparent",
    )
    sh.add(
        "QLabel#MetricCaption",
        font_size=f"{t.caption_size}px",
        color=c.text_tertiary,
        background_color="transparent",
    )

    # ── Tool cards ──────────────────────────────────────────────────────────
    sh.add(
        "QFrame#NPSCToolCard",
        background_color=c.bg_surface,
        border=f"{b.width}px solid {c.border_subtle}",
        border_radius=f"{r.lg}px",
    )
    sh.add(
        "QFrame#NPSCToolCard:hover",
        border_color=c.border_strong,
        background_color=c.bg_raised,
    )
    sh.add(
        "QFrame#NPSCToolCard:focus",
        border_color=c.border_focus,
    )
    sh.add(
        'QFrame#NPSCToolCard[selected="true"]',
        border_color=c.accent_soft_border,
        background_color=c.accent_soft_bg,
    )
    sh.add(
        "QLabel#ToolCardIcon",
        background_color=c.bg_button,
        color=c.accent_brand,
        border_radius=f"{r.sm}px",
        font_size=f"{t.body_size}px",
        border="none",
    )
    sh.add(
        "QLabel#ToolCardTitle",
        font_size=f"{t.control_size + 1}px",
        font_weight=600,
        color=c.text_primary,
        background_color="transparent",
        border="none",
    )
    sh.add(
        "QLabel#ToolCardDesc",
        font_size=f"{t.caption_size + 1}px",
        color=c.text_tertiary,
        background_color="transparent",
        border="none",
    )

    # ── Chips ───────────────────────────────────────────────────────────────
    sh.add(
        "QFrame#NPSCChip",
        background_color=c.chip_neutral_bg,
        border=f"{b.width}px solid transparent",
        border_radius=f"{r.pill}px",
        padding="0px",
        min_height=f"{m.chip_height}px",
    )
    sh.add('QFrame#NPSCChip[chipState="ok"]', background_color=c.chip_success_bg)
    sh.add('QFrame#NPSCChip[chipState="warn"]', background_color=c.chip_warning_bg)
    sh.add('QFrame#NPSCChip[chipState="error"]', background_color=c.chip_error_bg)
    sh.add('QFrame#NPSCChip[chipState="info"]', background_color=c.chip_info_bg)
    sh.add('QFrame#NPSCChip[chipState="idle"]', background_color=c.chip_neutral_bg)
    sh.add('QFrame#NPSCChip[chipState="working"]', background_color=c.chip_info_bg)
    sh.add(
        "QLabel#ChipDot",
        background_color=c.chip_neutral_fg,
        border="none",
        border_radius=f"{r.dot}px",
    )
    sh.add('QFrame#NPSCChip[chipState="ok"] QLabel#ChipDot', background_color=c.chip_success_fg)
    sh.add('QFrame#NPSCChip[chipState="warn"] QLabel#ChipDot', background_color=c.chip_warning_fg)
    sh.add('QFrame#NPSCChip[chipState="error"] QLabel#ChipDot', background_color=c.chip_error_fg)
    sh.add('QFrame#NPSCChip[chipState="info"] QLabel#ChipDot', background_color=c.chip_info_fg)
    sh.add('QFrame#NPSCChip[chipState="working"] QLabel#ChipDot', background_color=c.chip_info_fg)
    sh.add('QFrame#NPSCChip[chipState="idle"] QLabel#ChipDot', background_color=c.chip_neutral_fg)
    sh.add(
        "QLabel#ChipText",
        font_size=f"{t.caption_size}px",
        font_weight=600,
        color=c.chip_neutral_fg,
        background_color="transparent",
        border="none",
    )
    for state, fg in (
        ("ok", c.chip_success_fg),
        ("warn", c.chip_warning_fg),
        ("error", c.chip_error_fg),
        ("info", c.chip_info_fg),
        ("working", c.chip_info_fg),
        ("idle", c.chip_neutral_fg),
    ):
        sh.add(f'QFrame#NPSCChip[chipState="{state}"] QLabel#ChipText', color=fg)

    # ── Circle indicator (legacy, still styled for compatibility) ───────────
    sh.add(
        "QFrame#NPSCCircle",
        background_color="transparent",
        border=f"{b.width + 3}px solid {c.track}",
    )
    sh.add('QFrame#NPSCCircle[circleState="active"]', border_color=c.accent_primary)
    sh.add('QFrame#NPSCCircle[circleState="success"]', border_color=c.success)
    sh.add('QFrame#NPSCCircle[circleState="error"]', border_color=c.error)
    sh.add(
        "QLabel#CircleValue",
        font_size=f"{t.display_size + 4}px",
        font_weight=600,
        color=c.accent_brand,
        background_color="transparent",
        border="none",
    )
    sh.add(
        'QFrame#NPSCCircle[circleState="success"] QLabel#CircleValue',
        color=c.success,
    )
    sh.add(
        'QFrame#NPSCCircle[circleState="error"] QLabel#CircleValue',
        color=c.error,
    )
    sh.add(
        "QLabel#CircleLabel",
        font_size=f"{t.caption_size}px",
        color=c.text_tertiary,
        background_color="transparent",
        border="none",
    )

    # ── Health dashboard ────────────────────────────────────────────────────
    sh.add(
        "QFrame#NPSCHealthDash",
        background_color="transparent",
        border="none",
    )
    sh.add(
        "QFrame#NPSCMetricPill",
        background_color=c.bg_surface,
        border=f"{b.width}px solid {c.border_subtle}",
        border_radius=f"{r.md}px",
        padding=f"{s.sm}px",
    )
    sh.add(
        "QLabel#MetricPillValue",
        font_family=t.display_family,
        font_size=f"{t.title_size}px",
        font_weight=600,
        color=c.text_tertiary,
        background_color="transparent",
        border="none",
        padding="0px",
    )
    sh.add(
        "QLabel#MetricPillLabel",
        background_color="transparent",
        border="none",
        padding="0px",
        color=c.text_tertiary,
        font_size=f"{t.caption_size}px",
        font_weight=500,
        letter_spacing=t.tracking_button,
    )
    sh.add(
        "QLabel#HealthSectionTitle",
        font_size=f"{t.section_size}px",
        font_weight=600,
        color=c.text_tertiary,
        letter_spacing=t.section_tracking,
        background_color="transparent",
    )

    # ── Simple mode ─────────────────────────────────────────────────────────
    sh.add(
        "QLabel#SimpleTitle",
        font_size=f"{t.display_size - 6}px",
        font_weight=600,
        color=c.text_primary,
        background_color="transparent",
        border="none",
    )
    sh.add(
        "QLabel#SimpleSubtitle",
        font_size=f"{t.body_size}px",
        color=c.text_secondary,
        background_color="transparent",
        border="none",
    )
    sh.add(
        "QLabel#SimplePromptLabel",
        font_size=f"{t.label_size}px",
        font_weight=600,
        color=c.text_secondary,
        background_color="transparent",
        border="none",
    )
    sh.add(
        "QLabel#SimpleProfileValue",
        font_size=f"{t.control_size}px",
        font_weight=600,
        color=c.accent_brand,
        background_color="transparent",
        border="none",
    )
    sh.add(
        "QPushButton#SimpleAdvToggle",
        background_color="transparent",
        color=c.text_secondary,
        border=f"{b.width}px solid {c.border_subtle}",
        border_radius=f"{r.sm}px",
        padding=f"{s.xs + 1}px {s.md}px",
        font_size=f"{t.control_size}px",
        text_align="left",
        font_weight=500,
        min_height="26px",
    )
    sh.add(
        "QPushButton#SimpleAdvToggle:hover",
        background_color=c.bg_hover,
        color=c.text_primary,
        border_color=c.border_default,
    )
    sh.add(
        "QPushButton#SimpleAdvToggle:pressed",
        background_color=c.bg_button,
    )
    sh.add(
        "QPushButton#SimpleAdvToggle:checked",
        background_color=c.bg_hover,
        border_color=c.border_default,
        color=c.text_primary,
    )
    sh.add(
        "QFrame#SimpleAdvFrame",
        background_color=c.bg_surface,
        border=f"{b.width}px solid {c.border_subtle}",
        border_radius=f"{r.md}px",
    )
    sh.add(
        "QLabel#SimpleResultHeader",
        font_size=f"{t.title_size}px",
        font_weight=600,
        color=c.success,
        background_color="transparent",
        border="none",
    )
    sh.add(
        'QLabel#SimpleResultHeader[errorState="true"]',
        color=c.error,
    )
    sh.add(
        "QPushButton#SimpleHistBtn",
        background_color="transparent",
        color=c.text_tertiary,
        border="none",
        padding=f"{s.xs}px {s.sm}px",
        min_height="24px",
    )
    sh.add(
        "QPushButton#SimpleHistBtn:hover",
        color=c.text_primary,
        background_color=c.bg_hover,
    )
    sh.add(
        "QLabel#PromptTab",
        font_size=f"{t.control_size}px",
        font_weight=500,
        color=c.text_tertiary,
        padding=f"{s.sm - 2}px {s.md}px",
        background_color="transparent",
        border="none",
    )
    sh.add(
        'QLabel#PromptTab[active="true"]',
        color=c.accent_brand,
        border_bottom=f"{b.width + 1}px solid {c.accent_brand}",
        font_weight=600,
    )
    sh.add(
        "QLabel#HeroStatus",
        font_size=f"{t.caption_size + 1}px",
        color=c.text_tertiary,
        background_color="transparent",
        border="none",
    )
    sh.add(
        "QWidget#SimpleHeroCircle",
        background_color="transparent",
        border="none",
    )
    sh.add(
        "QLabel#SimpleHeroScore",
        font_family=t.display_family,
        font_size=f"{t.display_size + 8}px",
        font_weight=600,
        color=c.accent_brand,
        background_color="transparent",
        border="none",
    )
    sh.add(
        "QLabel#SimpleHeroLabel",
        font_size=f"{t.caption_size}px",
        color=c.text_tertiary,
        background_color="transparent",
        border="none",
    )
    sh.add(
        "QPushButton#PremiumScanBtn",
        background_color=c.accent_primary,
        color=c.text_on_accent,
        font_weight=600,
        font_size=f"{t.body_size}px",
        border=f"{b.width}px solid {c.accent_primary}",
        border_radius=f"{r.md}px",
        padding=f"{s.sm}px {s.lg + 4}px",
    )
    sh.add(
        "QPushButton#PremiumScanBtn:hover",
        background_color=c.accent_hover,
        border_color=c.accent_hover,
    )
    sh.add(
        "QPushButton#PremiumScanBtn:disabled",
        background_color=c.bg_button,
        color=c.text_tertiary,
        border_color=c.border_default,
    )
    sh.add(
        "QLabel#PremiumStatusText",
        font_size=f"{t.caption_size}px",
        color=c.text_tertiary,
        background_color="transparent",
    )
    sh.add(
        "QFrame#PremiumResultCard",
        background_color=c.bg_surface,
        border=f"{b.width}px solid {c.border_subtle}",
        border_radius=f"{r.lg}px",
    )

    # ── Field ───────────────────────────────────────────────────────────────
    sh.add(
        "QFrame#NPSCField",
        background_color="transparent",
        border="none",
    )
    sh.add(
        "QLabel#FieldHelp",
        font_size=f"{t.caption_size}px",
        color=c.text_tertiary,
        background_color="transparent",
    )
    sh.add(
        "QLabel#FieldError",
        font_size=f"{t.caption_size}px",
        font_weight=500,
        color=c.error,
        background_color="transparent",
    )
    sh.add(
        f"QFrame#NPSCField[fieldState=\"error\"] {inputs}",
        border_color=c.error,
    )
    sh.add(
        f"QFrame#NPSCField[fieldState=\"focus\"] {inputs}",
        border_color=c.border_focus,
    )
    sh.add(
        f"QFrame#NPSCField[fieldState=\"disabled\"] {inputs}",
        background_color=c.bg_surface,
        color=c.text_tertiary,
    )

    # ── Empty state / notices / toast / skeleton ───────────────────────────
    sh.add(
        "QFrame#NPSCEmptyState",
        background_color="transparent",
        border="none",
    )
    sh.add(
        "QLabel#EmptyGlyph",
        font_size=f"{t.display_size + 8}px",
        color=c.border_strong,
        background_color="transparent",
        border="none",
    )
    sh.add(
        "QLabel#EmptyTitle",
        font_size=f"{t.title_size}px",
        font_weight=600,
        color=c.text_secondary,
        background_color="transparent",
        border="none",
    )
    sh.add(
        "QLabel#EmptyHint",
        font_size=f"{t.body_size}px",
        color=c.text_tertiary,
        background_color="transparent",
        border="none",
    )
    sh.add(
        "QFrame#NPSCToast",
        background_color=c.bg_overlay,
        border=f"{b.width}px solid {c.border_strong}",
        border_radius=f"{r.md}px",
    )
    sh.add('QFrame#NPSCToast[toastState="success"]', border_color=c.chip_success_fg)
    sh.add('QFrame#NPSCToast[toastState="error"]', border_color=c.chip_error_fg)
    sh.add('QFrame#NPSCToast[toastState="warning"]', border_color=c.chip_warning_fg)
    sh.add(
        "QLabel#ToastText",
        font_size=f"{t.control_size}px",
        color=c.text_primary,
        background_color="transparent",
        border="none",
    )
    sh.add(
        "QFrame#NPSCInlineNotice",
        background_color=c.chip_info_bg,
        border=f"{b.width}px solid transparent",
        border_left=f"{b.width + 2}px solid {c.info}",
        border_radius=f"{r.sm}px",
    )
    sh.add(
        'QFrame#NPSCInlineNotice[noticeState="success"]',
        background_color=c.chip_success_bg,
        border_left=f"{b.width + 2}px solid {c.success}",
    )
    sh.add(
        'QFrame#NPSCInlineNotice[noticeState="warning"]',
        background_color=c.chip_warning_bg,
        border_left=f"{b.width + 2}px solid {c.warning}",
    )
    sh.add(
        'QFrame#NPSCInlineNotice[noticeState="error"]',
        background_color=c.chip_error_bg,
        border_left=f"{b.width + 2}px solid {c.error}",
    )
    sh.add(
        "QLabel#InlineNoticeText",
        font_size=f"{t.control_size}px",
        color=c.text_primary,
        background_color="transparent",
        border="none",
    )
    sh.add(
        "QFrame#NPSCSkeleton",
        background_color="transparent",
        border="none",
    )
    sh.add(
        "QFrame#NPSCSkeletonLine",
        background_color=c.bg_button,
        border="none",
        border_radius=f"{r.sm - 2}px",
    )
    sh.add(
        "QFrame#NPSCProgressTrack",
        background_color=c.track_soft,
        border="none",
        border_radius=f"{r.dot}px",
    )

    # ── Segmented control ───────────────────────────────────────────────────
    sh.add(
        "QFrame#NPSCSegmentedControl",
        background_color=c.bg_input,
        border=f"{b.width}px solid {c.border_subtle}",
        border_radius=f"{r.sm + 2}px",
        padding="2px",
    )
    sh.add(
        "QPushButton#NPSCSegment",
        background_color="transparent",
        color=c.text_tertiary,
        border=f"{b.width}px solid transparent",
        border_radius=f"{r.sm - 1}px",
        padding=f"{s.xs + 1}px {s.md}px",
        font_size=f"{t.caption_size + 1}px",
        font_weight=500,
        min_height="22px",
    )
    sh.add(
        "QPushButton#NPSCSegment:hover",
        color=c.text_primary,
        background_color=c.bg_hover,
    )
    sh.add(
        "QPushButton#NPSCSegment:checked",
        background_color=c.bg_button_hover,
        color=c.text_primary,
        border_color=c.border_default,
        font_weight=600,
    )

    # ── Advanced mode editable sections ────────────────────────────────────
    sh.add(
        "QFrame#AdvancedSectionCard",
        background_color=c.bg_surface,
        border=f"{b.width}px solid {c.border_subtle}",
        border_radius=f"{r.md}px",
    )
    sh.add(
        "QPushButton#CollapseBtn",
        background_color="transparent",
        border="none",
        color=c.text_secondary,
        text_align="left",
        padding=f"{s.xs}px {s.sm}px",
        min_height="24px",
    )
    sh.add(
        "QPushButton#CollapseBtn:hover",
        color=c.text_primary,
        background_color=c.bg_hover,
    )
    sh.add(
        "QLabel#HelpText",
        color=c.text_secondary,
        background_color="transparent",
    )
    sh.add(
        "QFrame#Separator",
        background_color=c.border_subtle,
        border="none",
        max_height=f"{b.width}px",
    )
    sh.add(
        "QLabel#CodeText",
        font_family=t.mono_family,
        font_size=f"{t.code_size}px",
        color=c.text_secondary,
        background_color="transparent",
        border="none",
    )

    return sh.render()
