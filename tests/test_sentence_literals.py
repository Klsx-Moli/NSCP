"""Regression: sentence splitting must not destroy literals.

The extractor used to split on every ".", turning "Python 3.12" into
"Python 3", "ratio 0.75" into "ratio 0" and "app.py" into "app". That leaked
into the extracted goal and into the compiled artifact, silently corrupting
version numbers, decimals, IPs and file names.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from semantic_extractor import _sentence_candidates, extract_semantics


@pytest.mark.parametrize(
    "text,expected_fragment",
    [
        ("migrate from Python 3.8 to 3.12 without downtime.", "3.12"),
        ("the ratio is 0.75 and the limit is 1.5.", "0.75"),
        ("check app.py and config.yaml first.", "app.py"),
        ("the host is 10.0.1.25 and the port is 8080.", "10.0.1.25"),
        ("release v2.4.1 shipped today.", "v2.4.1"),
        ("nothing to split here", "nothing to split here"),
    ],
)
def test_sentence_split_preserves_literals(text, expected_fragment):
    sentences = _sentence_candidates(text)
    assert sentences
    assert any(expected_fragment in sentence for sentence in sentences), sentences


def test_sentence_split_still_splits_real_sentences():
    text = "First sentence. Second sentence! Third one?"
    assert _sentence_candidates(text) == [
        "First sentence.",
        "Second sentence!",
        "Third one?",
    ]


def test_extracted_goal_keeps_version_numbers():
    text = (
        "We need to migrate a 400k LOC Django monolith from Python 3.8 to 3.12 "
        "without downtime. Produce a phased plan with rollback at each step."
    )
    goal = extract_semantics(text)["goal"]
    assert "3.8" in goal
    assert "3.12" in goal


def test_extracted_goal_keeps_file_names():
    text = "Lee app.py y arregla el bug que rompe el import."
    goal = extract_semantics(text)["goal"]
    assert "app.py" in goal
