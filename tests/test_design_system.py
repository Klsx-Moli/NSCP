"""Design system + component tests.

Verifies the invariants the visual layer relies on: single source of truth,
no duplicate selectors, WCAG contrast on every text/border pair, and the
behaviour of the reusable components (states, exclusivity, result rendering).
"""
from __future__ import annotations

import os
import re
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import dataclasses

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QComboBox

import i18n
from npsc_gui.components import (
    Field,
    ProgressIndicator,
    ResultCard,
    SegmentedControl,
    StatusChip,
    Toast,
)
from npsc_gui.design import build_qss, get_theme
from npsc_gui.design.builder import build_qss as builder_build
from npsc_gui.design.style import PremiumStyle, apply_design
from npsc_gui.theme import QSS_DARK, QSS_LIGHT, get_qss

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# ── helpers ────────────────────────────────────────────────────────────────

def _lin(c: float) -> float:
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _lum(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _contrast(a: str, b: str) -> float:
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _selectors(qss: str) -> list[str]:
    return [m.strip() for m in re.findall(r"^([^\n{}]+?)\s*\{", qss, re.MULTILINE)]


# ── tokens ─────────────────────────────────────────────────────────────────

def test_tokens_are_frozen():
    theme = get_theme("dark")
    with pytest.raises(dataclasses.FrozenInstanceError):
        theme.palette.text_primary = "#000000"  # type: ignore[misc]


def test_theme_exposes_both_palettes():
    dark = get_theme("dark")
    light = get_theme("light")
    assert dark.name == "dark" and light.name == "light"
    assert dark.palette.bg_base != light.palette.bg_base
    assert dark.spacing.xs == 4 and dark.spacing.xxxl == 48
    assert dark.radius.sm == 6 and dark.radius.xl == 20
    assert dark.motion.instant == 0 and dark.motion.micro == 120
    assert dark.motion.long == 450


# ── builder ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("theme_name", ["dark", "light"])
def test_builder_has_no_duplicate_selectors(theme_name):
    selectors = _selectors(get_qss(theme_name))
    duplicates = {s for s in selectors if selectors.count(s) > 1}
    assert not duplicates, f"duplicates: {sorted(duplicates)}"


@pytest.mark.parametrize("theme_name", ["dark", "light"])
def test_builder_emits_state_rules(theme_name):
    qss = get_qss(theme_name)
    for state in (":hover", ":pressed", ":disabled", ":selected", ":checked"):
        assert state in qss, f"{theme_name} missing {state}"


def test_builder_source_has_no_hardcoded_colours():
    source = (get_theme("dark").palette.__class__.__module__ and
              open(os.path.join(os.path.dirname(__file__), "..", "src", "npsc_gui", "design", "builder.py"),
                   encoding="utf-8").read())
    assert not re.findall(r"#[0-9A-Fa-f]{6}\b", source)


def test_theme_facade_is_single_source():
    assert get_qss("dark") == build_qss(get_theme("dark"))
    assert get_qss("light") == build_qss(get_theme("light"))
    assert QSS_DARK == builder_build(get_theme("dark"))
    assert QSS_LIGHT == builder_build(get_theme("light"))


def test_typography_family_is_declared_and_available():
    """At least one concrete configured family must exist on the Qt host."""
    from PySide6.QtGui import QFontDatabase

    typography = get_theme("dark").typography
    available = set(QFontDatabase.families())
    if not available:
        pytest.skip("Qt platform reports no fonts (offscreen/minimal)")
    for stack in (typography.family, typography.display_family, typography.mono_family):
        candidates = {f.strip().strip('"') for f in stack.split(",")}
        assert candidates & available, f"{stack!r} has no installed family"


# ── contrast ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("theme_name", ["dark", "light"])
@pytest.mark.parametrize(
    "text_token",
    ["text_primary", "text_secondary", "text_tertiary", "accent_brand", "success", "warning", "error"],
)
@pytest.mark.parametrize("surface", ["bg_base", "bg_surface", "bg_raised", "bg_input"])
def test_text_contrast_meets_aa(theme_name, text_token, surface):
    palette = get_theme(theme_name).palette
    ratio = _contrast(getattr(palette, text_token), getattr(palette, surface))
    assert ratio >= 4.5, f"{theme_name} {text_token} on {surface}: {ratio:.2f}:1"


@pytest.mark.parametrize("theme_name", ["dark", "light"])
@pytest.mark.parametrize("filled", ["accent_primary", "accent_hover", "success_filled", "error_filled"])
def test_text_on_filled_accent_meets_aa(theme_name, filled):
    palette = get_theme(theme_name).palette
    ratio = _contrast(palette.text_on_accent, getattr(palette, filled))
    assert ratio >= 4.5, f"{theme_name} on {filled}: {ratio:.2f}:1"


@pytest.mark.parametrize("theme_name", ["dark", "light"])
@pytest.mark.parametrize("surface", ["bg_raised", "bg_input", "bg_surface", "bg_base"])
def test_interactive_border_meets_non_text_contrast(theme_name, surface):
    palette = get_theme(theme_name).palette
    ratio = _contrast(palette.border_strong, getattr(palette, surface))
    assert ratio >= 3.0, f"{theme_name} border_strong on {surface}: {ratio:.2f}:1"


# ── components ─────────────────────────────────────────────────────────────

def test_status_chip_maps_all_six_states():
    chip = StatusChip("text", "idle")
    expected = {
        "idle": "idle",
        "ready": "ok",
        "working": "working",
        "success": "ok",
        "warning": "warn",
        "error": "error",
    }
    for state, chip_state in expected.items():
        chip.set_state(state)
        assert chip.state == state
        assert chip.property("chipState") == chip_state


def test_segmented_control_is_exclusive_and_indexed():
    control = SegmentedControl()
    control.add_segment("Uno", "1")
    control.add_segment("Dos", "2")
    control.set_current_index(1)
    assert control.current_index() == 1
    assert control.current_data() == "2"
    control.set_current_data("1")
    assert control.current_index() == 0
    assert control._buttons[0].isChecked() and not control._buttons[1].isChecked()


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
        (0, [], ["e"], "error"),
    ],
)
def test_result_card_states(score, warnings, errors, expected):
    card = ResultCard()
    card.set_result(_result(score, warnings, errors, ["c"]))
    assert card.chip.state == expected
    assert card.score_label.text() == str(score)
    assert card.copy_button.isEnabled()


def test_result_card_idle_and_clear():
    card = ResultCard()
    assert card.chip.state == "idle"
    assert not card.copy_button.isEnabled()
    card.set_working()
    assert card.chip.state == "working"
    card.set_result(_result(90))
    card.clear()
    assert card.chip.state == "idle"
    assert card.score_label.text() == "—"


def test_field_error_and_focus_states():
    field = Field("Perfil", QComboBox())
    assert field.property("fieldState") == "default"
    field.set_error("Campo obligatorio")
    assert field.property("fieldState") == "error"
    assert field._error.isVisibleTo(field)
    field.clear_error()
    assert field.property("fieldState") == "default"
    field.set_enabled(False)
    assert field.property("fieldState") == "disabled"


def test_progress_indicator_indeterminate():
    bar = ProgressIndicator()
    assert (bar.minimum(), bar.maximum()) == (0, 100)
    bar.set_indeterminate(True)
    assert (bar.minimum(), bar.maximum()) == (0, 0)
    bar.set_variant("success")
    assert bar.property("progressState") == "success"


def test_toast_state_and_message(qapp):
    toast = Toast()
    toast.show_message("Copiado", "success", duration_ms=60000)
    assert toast.property("toastState") == "success"
    assert toast._text.text() == "Copiado"
    toast.hide_now()
    assert toast.property("toastState") == "success"


def test_apply_design_installs_focus_style(qapp):
    style = apply_design(qapp, get_theme("dark"))
    assert isinstance(style, PremiumStyle)
    assert qapp.property("npsc_theme_name") == "dark"
    apply_design(qapp, get_theme("light"))
    assert qapp.property("npsc_theme_name") == "light"


# ── i18n ───────────────────────────────────────────────────────────────────

def test_new_result_keys_exist_in_all_languages():
    languages = sorted(i18n.SUPPORTED_LANGUAGES)
    new_keys = [k for k in i18n._TRANSLATIONS if k.startswith(("result.", "toast.", "field."))]
    assert len(new_keys) >= 20
    for key in new_keys:
        options = i18n._TRANSLATIONS[key]
        for language in languages:
            assert options.get(language), f"{key} missing {language}"


def test_tr_resolves_new_keys():
    i18n.set_language("en")
    assert i18n.tr("result.title") == "Prompt compiled"
    i18n.set_language("es")
    assert i18n.tr("result.title") == "Prompt compilado"
