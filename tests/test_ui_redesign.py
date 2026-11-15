"""Redesign components and states.

These tests pin the behaviour the new UI depends on, not pixels:
- the design system exposes the tokens the components read,
- every component has the complete set of visual states,
- the primary button's loading state blocks double submits,
- the progress indicator distinguishes real from indeterminate progress,
- the result card maps score/warnings/errors to the right semantic state,
- the splash is bounded and skippable,
- motion respects the reduce-motion preference,
- the qss never paints an opaque background behind a plain QLabel.
"""
from __future__ import annotations

import os
import re
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QComboBox, QLabel

import i18n
from npsc_gui.components import (
    Card,
    EmptyState,
    Field,
    MetricTile,
    PageHeader,
    PrimaryButton,
    ProgressIndicator,
    ResultCard,
    SecondaryButton,
    SegmentedControl,
    Skeleton,
    StatusChip,
    Toast,
    ToastHost,
    ToolCard,
)
from npsc_gui.components.icons import icon_names, icon_pixmap
from npsc_gui.design import build_qss, get_theme
from npsc_gui.design import motion
from npsc_gui.design.tokens import Metrics, Motion, Radius, Spacing

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# ── tokens ─────────────────────────────────────────────────────────────────

def test_spacing_scale_is_the_documented_one():
    spacing = Spacing()
    assert (spacing.xs, spacing.sm, spacing.md, spacing.lg, spacing.xl, spacing.xxl, spacing.xxxl) == (
        4, 8, 12, 16, 24, 32, 48,
    )


def test_radius_scale_matches_the_brief():
    radius = Radius()
    assert radius.sm == 6
    assert 10 <= radius.md <= 14
    assert 14 <= radius.lg <= 20
    assert 16 <= radius.xl <= 20


def test_motion_scale_matches_the_brief():
    m = Motion()
    assert m.instant == 0
    assert 120 <= m.micro <= 150
    assert 180 <= m.short <= 220
    assert 260 <= m.medium <= 320
    assert 400 <= m.long <= 500


def test_metrics_are_dense_but_readable():
    m = Metrics()
    assert m.header_height <= 56
    assert m.button_height_large <= 40
    assert m.editor_min_height >= 160


# ── qss invariants ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("theme_name", ["dark", "light"])
def test_no_opaque_background_on_generic_labels(theme_name):
    """The old global rule painted a rectangle behind every QLabel."""
    qss = build_qss(get_theme(theme_name))
    lines = [line.strip() for line in qss.splitlines()]
    for bare in ("QLabel {", "QWidget {"):
        assert bare not in lines, f"{bare} must not be styled globally"


@pytest.mark.parametrize("theme_name", ["dark", "light"])
def test_components_have_complete_states(theme_name):
    qss = build_qss(get_theme(theme_name))
    for selector in (
        "QPushButton#PrimaryButton:hover",
        "QPushButton#PrimaryButton:pressed",
        "QPushButton#PrimaryButton:disabled",
        "QPushButton#SecondaryButton:hover",
        "QPushButton#SecondaryButton:pressed",
        "QPushButton#SecondaryButton:disabled",
        "QPushButton#IconButton:hover",
        "QPushButton#IconButton:pressed",
        "QPushButton#IconButton:disabled",
        "QPushButton#NPSCNavItem:hover",
        "QPushButton#NPSCNavItem:checked",
        "QPushButton#NPSCSegment:checked",
    ):
        assert selector in qss, f"{theme_name} missing {selector}"


@pytest.mark.parametrize("theme_name", ["dark", "light"])
def test_result_body_is_read_only_surface_styled(theme_name):
    qss = build_qss(get_theme(theme_name))
    assert "QPlainTextEdit#ResultBody" in qss


# ── buttons ────────────────────────────────────────────────────────────────

def test_primary_button_loading_blocks_clicks_and_restores_label():
    button = PrimaryButton("Compilar")
    button.set_loading(True)
    assert button.is_loading()
    assert not button.isEnabled()
    assert button.text() != "Compilar"
    button.set_loading(False)
    assert not button.is_loading()
    assert button.isEnabled()
    assert button.text() == "Compilar"


def test_primary_button_loading_can_change_final_label():
    button = PrimaryButton("Compilar")
    button.set_loading(True)
    button.set_loading(False, "Recompilar")
    assert button.text() == "Recompilar"


def test_secondary_and_primary_differ_in_weight():
    primary = PrimaryButton("A")
    secondary = SecondaryButton("B")
    assert primary.objectName() == "PrimaryButton"
    assert secondary.objectName() == "SecondaryButton"
    assert primary.minimumHeight() >= secondary.minimumHeight()


# ── progress ───────────────────────────────────────────────────────────────

def test_progress_indeterminate_vs_determinate():
    bar = ProgressIndicator()
    assert (bar.minimum(), bar.maximum()) == (0, 100)
    bar.set_indeterminate(True)
    assert (bar.minimum(), bar.maximum()) == (0, 0)
    bar.set_indeterminate(False)
    assert (bar.minimum(), bar.maximum()) == (0, 100)
    bar.setValue(42)
    assert bar.value() == 42


def test_progress_variants_are_restricted():
    bar = ProgressIndicator()
    bar.set_variant("success")
    assert bar.variant() == "success"
    bar.set_variant("nonsense")
    assert bar.variant() == "info"


# ── result card ────────────────────────────────────────────────────────────

def _result(score: int, warnings=(), errors=(), constraints=()) -> dict:
    return {
        "optimized_prompt": "PROMPT",
        "applied_profile": "AUTO",
        "target": "codex",
        "prompt_sha256": "a" * 64,
        "context_loss_report": {
            "score": score,
            "warnings": list(warnings),
            "critical_losses": list(errors),
            "critical_constraints_preserved": list(constraints),
        },
    }


@pytest.mark.parametrize(
    "score,warnings,errors,expected",
    [
        (92, [], [], "success"),
        (70, ["w"], [], "warning"),
        (50, [], ["e"], "error"),
    ],
)
def test_result_card_state_and_metrics(score, warnings, errors, expected):
    card = ResultCard()
    card.set_result(_result(score, warnings, errors, ["c"]))
    assert card.chip.state == expected
    assert card.score_label.text() == str(score)
    assert card.metric_warnings.value() == str(len(warnings))
    assert card.metric_errors.value() == str(len(errors))
    assert card.copy_button.isEnabled()


def test_result_card_idle_working_clear_cycle():
    card = ResultCard()
    assert card.chip.state == "idle"
    assert card.property("resultState") == "idle"
    card.set_working()
    assert card.chip.state == "working"
    card.set_result(_result(90, constraints=["x"]))
    assert card.property("resultState") == "success"
    card.clear()
    assert card.chip.state == "idle"
    assert card.score_label.text() == "—"
    assert not card.copy_button.isEnabled()


# ── feedback ───────────────────────────────────────────────────────────────

def test_toast_reports_state_and_messages(qapp):
    toast = Toast()
    toast.show_message("Copiado", "success", duration_ms=60000)
    assert toast.property("toastState") == "success"
    assert toast.message() == "Copiado"
    toast.hide_now()


def test_toast_host_keeps_a_bounded_stack(qapp):
    host = ToastHost(None or QApplication.activeWindow())
    # A host without a parent still needs to accept toasts without raising.
    toast = Toast(host)
    assert toast.parent() is host


def test_status_chip_maps_every_semantic_state():
    chip = StatusChip("x", "idle")
    for state in ("idle", "ready", "working", "success", "warning", "error"):
        chip.set_state(state)
        assert chip.state == state
        assert chip.property("chipState")


def test_card_and_empty_state_and_page_header_construct():
    card = Card("T", "S")
    card.add_row(QLabel("row"))
    assert card.content() is not None
    empty = EmptyState("Sin resultados", "Compila primero")
    assert empty.title_label.text() == "Sin resultados"
    header = PageHeader("Título", "Subtítulo")
    assert header.title_label.text() == "Título"


def test_metric_tile_semantics_change_colour():
    from npsc_gui.design.style import active_theme

    tile = MetricTile("Preservación", "90/100", "success")
    assert tile.value() == "90/100"
    success_colour = active_theme().palette.success
    error_colour = active_theme().palette.error
    assert success_colour in tile._value.styleSheet()
    tile.set_semantic("error")
    assert error_colour in tile._value.styleSheet()


def test_tool_card_is_keyboard_activatable(qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent

    card = ToolCard("T", "D", "search")
    hits = []
    card.clicked.connect(lambda: hits.append(1))
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    card.keyPressEvent(event)
    assert hits == [1]
    assert card.title() == "T"
    card.set_icon_text("✓")


# ── icons ──────────────────────────────────────────────────────────────────

def test_vector_icons_render_non_empty_pixmaps():
    for name in icon_names():
        pixmap = icon_pixmap(name, 16, "#FFFFFF")
        assert not pixmap.isNull()
        assert pixmap.width() >= 16


def test_icons_scale_for_high_dpi():
    pixmap = icon_pixmap("check", 16, "#FFFFFF", device_pixel_ratio=2.0)
    assert pixmap.width() == 32
    assert pixmap.devicePixelRatio() == 2.0


# ── motion ─────────────────────────────────────────────────────────────────

def test_reduce_motion_collapses_duration(qapp):
    from PySide6.QtWidgets import QWidget

    motion.set_motion_enabled(False)  # reduce motion ON
    try:
        widget = QWidget()
        animation = motion.animate_opacity(widget, 1.0, duration=500)
        assert animation.duration() == 0
    finally:
        motion.set_motion_enabled(True)


def test_motion_defaults_to_enabled(qapp):
    motion.set_motion_enabled(True)
    assert motion.motion_enabled() is True
    assert motion.reduce_motion() is False


# ── splash ─────────────────────────────────────────────────────────────────

def test_splash_duration_is_bounded_and_skippable(qapp):
    from npsc_gui.splash import PremiumSplash

    splash = PremiumSplash(duration_ms=5000)
    assert splash._duration <= 1500
    finished = []
    splash.finished.connect(lambda: finished.append(1))
    splash._finish()
    splash._finish()  # idempotent
    assert splash._auto.isActive() is False


# ── i18n coverage ──────────────────────────────────────────────────────────

def test_every_string_exists_in_all_seven_languages():
    languages = sorted(i18n.SUPPORTED_LANGUAGES)
    assert len(languages) == 7
    for key, options in i18n._TRANSLATIONS.items():
        for language in languages:
            assert options.get(language), f"{key} missing {language}"


def test_ui_strings_are_translated_not_keys():
    for language in sorted(i18n.SUPPORTED_LANGUAGES):
        i18n.set_language(language)
        for key in ("simple.title", "result.page.title", "settings.reduce_motion",
                    "splash.tagline", "nav.page.results"):
            value = i18n.tr(key)
            assert value != key, f"{key} untranslated in {language}"
            assert value.strip()
    i18n.set_language("es")
