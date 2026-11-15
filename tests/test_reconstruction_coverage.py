"""Coverage of multi-sentence inputs in both outputs.

History: the reconstructed artifact used to carry ONLY the first sentence as
its goal, so requirements stated later ("responde 422", "lee app.py") were
missing from it. That defect is fixed: the goal now spans the whole request
(bounded), and both outputs keep later requirements.

These tests keep the fix pinned.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from npsc_service import CompileRequest, compile_prompt

MULTI_SENTENCE = (
    "Implementa un endpoint POST /api/v1/tickets en Python con FastAPI que valide "
    "title (string, 1-120) y priority (low|medium|high). Responde 201 con el ticket "
    "creado y 422 con errores de validacion. Incluye tests con pytest."
)


@pytest.fixture(scope="module")
def compiled():
    return compile_prompt(
        CompileRequest(original=MULTI_SENTENCE, target="codex", profile="AUTO")
    )


def test_goal_spans_the_whole_request(compiled):
    goal = compiled["semantics"]["goal"]
    assert "POST /api/v1/tickets" in goal
    assert "422" in goal, "requirements from later sentences must reach the goal"


def test_optimized_prompt_preserves_the_whole_input(compiled):
    optimized = compiled["optimized_prompt"]
    assert "422" in optimized
    assert "201" in optimized
    assert "low|medium|high" in optimized
    assert "pytest" in optimized


def test_reconstructed_artifact_keeps_later_sentences(compiled):
    reconstructed = compiled["reconstructed"]
    assert "422" in reconstructed
    assert "201" in reconstructed


def test_goal_is_bounded_for_long_inputs():
    """A long rambling prompt must not become an essay-length goal."""
    long_text = " ".join(
        f"Frase numero {index} con detalle adicional irrelevante." for index in range(60)
    )
    result = compile_prompt(
        CompileRequest(original=long_text, target="codex", profile="AUTO")
    )
    assert len(result["semantics"]["goal"]) <= 720


def test_literals_are_never_corrupted_by_sentence_splitting(compiled):
    """Versions and decimals must survive verbatim (regression for 3.8/3.12)."""
    text = "migrate from Python 3.8 to 3.12, ratio 0.75, check app.py"
    result = compile_prompt(
        CompileRequest(original=text, target="codex", profile="AUTO")
    )
    goal = result["semantics"]["goal"]
    assert "3.8" in goal
    assert "3.12" in goal
    assert "app.py" in goal
