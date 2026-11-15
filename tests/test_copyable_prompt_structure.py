"""The copyable prompt must carry real structure, not just the original text.

Before this change, ``optimized_prompt`` was the user's text plus a profile
header and one generic closing line: copying it gave nothing new. These tests
pin the structure that now must be present, and that adding it never loses the
user's own words or invents content.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from npsc_service import CompileRequest, compile_prompt

PROMPT = (
    "Implementa un endpoint POST /api/v1/tickets en Python con FastAPI que valide "
    "title (string, 1-120) y priority (low|medium|high). Responde 201 y 422. "
    "Incluye tests con pytest. Sin sudo."
)


@pytest.fixture(scope="module")
def compiled():
    return compile_prompt(
        CompileRequest(original=PROMPT, target="codex", profile="STANDARD")
    )


REQUIRED_SECTIONS = (
    "Role:",
    "Objective:",
    "Tasks:",
    "Constraints:",
    "Expected output:",
    "Verification:",
    "If blocked:",
)


@pytest.mark.parametrize("section", REQUIRED_SECTIONS)
def test_copyable_prompt_has_each_section(compiled, section):
    assert section in compiled["optimized_prompt"], (
        f"missing {section!r} in the prompt the user copies"
    )


def test_objective_keeps_the_user_words_verbatim(compiled):
    assert PROMPT.strip() in compiled["optimized_prompt"]


def test_constraints_use_canonical_form_for_traceability(compiled):
    """The verifier looks for ``no_sudo``; the prompt must contain it."""
    assert "no_sudo" in compiled["optimized_prompt"]


def test_no_unsupported_additions_are_reported(compiled):
    """The prompt's own scaffolding must not be scored as invented content."""
    report = compiled["context_loss_report"]
    assert report["unsupported_addition_score"] == 0, report.get("unsupported_additions")
    assert report["precision_score"] == 100


def test_prompt_remains_useful_and_not_bloated(compiled):
    """Structure is added, but the prompt does not become an essay."""
    optimized = compiled["optimized_prompt"]
    assert len(optimized) < len(PROMPT) * 8
    assert "assistant" not in optimized.lower().split("role:")[0]


def test_fast_profile_stays_minimal(compiled):
    """FAST is the exception: it must stay compact by design."""
    result = compile_prompt(
        CompileRequest(original="arregla este bug sin sudo", target="codex", profile="FAST")
    )
    optimized = result["optimized_prompt"]
    assert "Verification:" not in optimized
    assert "no_sudo" in optimized
