import math

import pytest

from semantic_memory import SemanticMemory
from semantic_ranking import rerank_results, retrieval_metrics


def add(memory, message="m", content="abc", vector=(1, 2), episode="e", **kwargs):
    return memory.add(episode=episode, message=message, role="tool", tool_call="call",
                      content=content, start=0, end=len(content), vector=vector, **kwargs)


def test_session_isolation_and_restart(tmp_path):
    path = tmp_path / "memory.sqlite"
    with SemanticMemory(path, session_id="a", embedding_id="v1", dimension=2) as m:
        assert add(m)
        assert not add(m)
        assert m.recall(episode="e", message="m")["content"] == "abc"
    with SemanticMemory(path, session_id="b", embedding_id="v1", dimension=2) as m:
        assert m.search([1, 2]) == []
        assert m.recall(episode="e", message="m") is None
        assert add(m, content="different")
    with SemanticMemory(path, session_id="a", embedding_id="v1", dimension=2) as m:
        assert m.search([1, 2])[0]["text"] == "abc"
        assert m.recall(episode="e", message="m", offset=1, limit=1)["next_offset"] == 2


def test_reindex_and_conflict(tmp_path):
    path = tmp_path / "m.sqlite"
    with SemanticMemory(path, session_id="s", embedding_id="v1", dimension=2) as m:
        add(m)
        with pytest.raises(ValueError, match="immutable"):
            add(m, content="changed")
        with pytest.raises(ValueError, match="replay"):
            add(m, vector=(2, 1))
        assert add(m, message="other")  # identical content, different event
    with SemanticMemory(path, session_id="s", embedding_id="v2", dimension=3) as m:
        assert m.search([1, 2, 3]) == []
        assert add(m, vector=(1, 2, 3))
        assert len(m.search([1, 2, 3])) == 1
    with pytest.raises(ValueError, match="dimension conflict"):
        SemanticMemory(path, session_id="s", embedding_id="v2", dimension=2)


def test_cosine_not_dot_product(tmp_path):
    with SemanticMemory(tmp_path / "m.sqlite", session_id="s", embedding_id="v1", dimension=2) as m:
        add(m, message="large", vector=(1000, 1000))
        add(m, message="aligned", vector=(1, 0))
        assert [r["message"] for r in m.search([1, 0])] == ["aligned", "large"]
        assert math.isclose(m.search([1, 0])[0]["score"], 1)


@pytest.mark.parametrize("bad", [[0, 0], [True, 1], [float("nan"), 1], [float("inf"), 1], [1], ["1", 2]])
def test_bad_vectors(tmp_path, bad):
    with SemanticMemory(tmp_path / "m.sqlite", session_id="s", embedding_id="v1", dimension=2) as m:
        with pytest.raises(ValueError):
            add(m, vector=bad)
        assert m.recall(episode="e", message="m") is None


def test_corrupt_source_rejected(tmp_path):
    with SemanticMemory(tmp_path / "m.sqlite", session_id="s", embedding_id="v1", dimension=2) as m:
        add(m)
        with m.db:
            m.db.execute("UPDATE sources SET content='tampered'")
        with pytest.raises(ValueError, match="integrity"):
            m.search([1, 2])
        with pytest.raises(ValueError, match="integrity"):
            m.recall(episode="e", message="m")


def test_reranker_explicit_indices_and_order():
    rows = [{"index": 2, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.1},
            {"index": 1, "relevance_score": 0.5}]
    assert rerank_results(["a", "b", "c"], {"results": rows}) == [
        ("c", 0.9), ("b", 0.5), ("a", 0.1)]
    assert rerank_results(["a", "b", "c"], {"results": rows[::-1]}) == [
        ("c", 0.9), ("b", 0.5), ("a", 0.1)]


@pytest.mark.parametrize("rows", [
    [{"index": 0, "relevance_score": 1}],
    [{"index": 0, "relevance_score": 1}, {"index": 0, "relevance_score": 2}],
    [{"index": True, "relevance_score": 1}, {"index": 0, "relevance_score": 2}],
    [{"index": 2, "relevance_score": 1}, {"index": 0, "relevance_score": 2}],
    [{"index": 1, "relevance_score": float("nan")}, {"index": 0, "relevance_score": 2}],
])
def test_rerank_rejects_invalid_response(rows):
    with pytest.raises(ValueError):
        rerank_results(["a", "b"], {"results": rows})


def test_metrics_cutoff_multiple_gold_and_no_answer():
    m = retrieval_metrics(["wrong", "a", "b"], ["a", "b"], k=2)
    assert m["recall_at_k"] == 0.5 and m["precision_at_k"] == 0.5
    assert m["mrr_at_k"] == 0.5 and not m["top1_hit"]
    assert retrieval_metrics([], ["a"], k=4)["recall_at_k"] == 0
    assert retrieval_metrics([], [], k=4)["recall_at_k"] is None
    assert retrieval_metrics(["a"], [], k=4)["false_answer"]
    with pytest.raises(ValueError):
        retrieval_metrics(["a", "a"], ["a"], k=2)
