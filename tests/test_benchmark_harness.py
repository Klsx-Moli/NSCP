"""The improvement harness itself must be trustworthy.

If the measurement drifts (a metric silently stops working, the corpus loses
diversity, or the harness starts rewarding length), the reported percentages
become fiction. These tests pin the harness contract.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "tools", "benchmark")
)

from run_benchmark import (  # noqa: E402
    aggregate,
    literal_requirements,
    preserved_ratio,
    structure_score,
)


def test_literal_requirements_finds_checkable_things():
    text = (
        "POST /api/v1/tickets con priority (low|medium|high), "
        "responde 422, lee app.py y usa `request_id`."
    )
    found = literal_requirements(text)
    assert "POST /api/v1/tickets" in found
    assert "low|medium|high" in found
    assert "422" in found
    assert "app.py" in found


def test_literal_requirements_ignores_trivial_numbers():
    assert literal_requirements("hazlo en 3 pasos") == set()


def test_preserved_ratio_detects_loss():
    raw = "responde 422 y 201, usa app.py"
    assert preserved_ratio(raw, raw)[0] == 1.0
    ratio, missing = preserved_ratio(raw, "responde correctamente")
    assert ratio == 0.0
    assert "422" in missing and "app.py" in missing


def test_structure_score_rewards_real_structure_only():
    plain = "arregla mi codigo"
    structured = (
        "Role: engineer\nGoal: fix it\nTasks: analyze\nConstraints: none\n"
        "Expected output: patch\nStyle: concise\nVerify: run tests\n"
        "If blocked, report the blocker."
    )
    assert structure_score(plain)[0] == 0
    assert structure_score(structured)[0] >= 7


def test_structure_score_does_not_reward_padding():
    """Repeating the same words must not add structure signals."""
    padded = "goal goal goal goal goal goal goal goal"
    assert structure_score(padded)[0] <= 1


def test_aggregate_never_rewards_expansion():
    """Token expansion is reported but must not appear as a positive score."""
    rows = []
    agg = aggregate(rows)
    assert "median_token_expansion" in agg
    assert "score" not in agg


def test_corpus_is_varied_and_independent():
    path = os.path.join(
        os.path.dirname(__file__), "..", "tools", "benchmark", "corpus.json"
    )
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    cases = data["cases"]

    assert len(cases) >= 30, "corpus too small to be meaningful"
    groups = {c["group"] for c in cases}
    assert len(groups) >= 7, f"corpus lacks variety: {groups}"
    languages = {c["language"] for c in cases}
    assert len(languages) >= 5, f"corpus lacks languages: {languages}"

    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "duplicate case ids"

    texts = [c["raw"] for c in cases]
    assert len(texts) == len(set(texts)), "duplicate prompts in corpus"

    # Questions from forums must be represented, per the evaluation brief.
    assert any(c["group"] == "forum" for c in cases)
    assert any(c["group"] == "vague" for c in cases)
    assert any(c["group"] == "technical" for c in cases)
    assert any(c["group"] == "writing" for c in cases)


def test_corpus_does_not_reuse_the_shipped_examples():
    """The benchmark must not measure itself on examples/ prompts."""
    here = os.path.dirname(__file__)
    with open(
        os.path.join(here, "..", "tools", "benchmark", "corpus.json"), encoding="utf-8"
    ) as handle:
        corpus = json.load(handle)["cases"]

    examples_dir = os.path.join(here, "..", "examples")
    example_texts = set()
    for name in os.listdir(examples_dir):
        if name.endswith(".txt"):
            with open(os.path.join(examples_dir, name), encoding="utf-8") as handle:
                example_texts.add(handle.read().strip())

    overlapping = [c["id"] for c in corpus if c["raw"].strip() in example_texts]
    assert not overlapping, f"corpus reuses shipped examples: {overlapping}"
