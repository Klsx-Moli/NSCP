"""Documented limitation: the reconstructed artifact uses ONLY the first sentence.

The benchmark (tools/benchmark/run_benchmark.py) found that when an input has
several sentences, requirements stated after the first one are absent from the
`reconstructed` artifact. The copyable `optimized_prompt` keeps them because it
embeds the original text.

These tests pin the CURRENT behaviour so the defect is visible and cannot
regress silently into something worse. When the extractor learns to carry the
full objective, these tests should be updated to assert preservation instead.
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
    "creado y 422 con errores de validacion."
)


@pytest.fixture(scope="module")
def compiled():
    return compile_prompt(
        CompileRequest(original=MULTI_SENTENCE, target="codex", profile="AUTO")
    )


def test_first_sentence_is_captured_as_goal(compiled):
    goal = compiled["semantics"]["goal"]
    assert "POST /api/v1/tickets" in goal
    assert "low|medium|high" in goal


def test_optimized_prompt_preserves_the_whole_input(compiled):
    """The copyable prompt embeds the original text, so nothing is lost."""
    optimized = compiled["optimized_prompt"]
    assert "422" in optimized
    assert "201" in optimized
    assert "low|medium|high" in optimized


@pytest.mark.xfail(
    reason=(
        "Known limitation: the reconstructed artifact only carries the first "
        "sentence of the input, so requirements stated later are missing."
    ),
    strict=True,
)
def test_reconstructed_artifact_keeps_later_sentences(compiled):
    reconstructed = compiled["reconstructed"]
    assert "422" in reconstructed
    assert "201" in reconstructed


def test_literals_are_never_corrupted_by_sentence_splitting(compiled):
    """Versions and decimals must survive verbatim (regression for 3.8/3.12)."""
    text = "migrate from Python 3.8 to 3.12, ratio 0.75, check app.py"
    result = compile_prompt(
        CompileRequest(original=text, target="codex", profile="AUTO")
    )
    goal = result["semantics"]["goal"]
    assert "3.8" in goal
    assert "3.12" in goal
