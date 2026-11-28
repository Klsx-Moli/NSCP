import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "specialized_benchmark", Path(__file__).resolve().parents[1] / "tools" / "benchmark_specialized_engines.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def test_embedding_response_reordered():
    response = {"data": [{"index": 1, "embedding": [0, 5]},
                         {"index": 0, "embedding": [8, 0]}]}
    assert bench.embedding_results(response, 2, 2) == [[1, 0], [0, 1]]
    response["data"][0]["index"] = 0
    with pytest.raises(ValueError):
        bench.embedding_results(response, 2, 2)


def test_empty_and_missing_cases_are_not_perfect_recall():
    result = bench.summary({})
    assert all(not r["complete"] and r["recall_at_k"] is None for r in result.values())
    assert all(r["expected_answerable_cases"] == 13 for r in result.values())


def test_corpus_answer_keys_and_rankings():
    assert len({c[0] for c in bench.CASES}) == len(bench.CASES)
    assert all(set(gold) <= set(bench.DOCS) for _, _, gold in bench.CASES)
    assert len(bench.dataset_digest()) == 64
    assert len(set(bench.fuse(["a", "b"], ["b", "c"], limit=3))) == 3
    assert bench.fuse(["a", "b"], ["b", "c"], limit=3)[0] == "b"
