from dataclasses import dataclass

import pytest

from local_retrieval import RetrievalConfig, SemanticSpanSelector


@dataclass(frozen=True)
class Span:
    id: int
    start: int
    end: int
    text: str


def fake_server(monkeypatch):
    calls = []

    def post(port, path, payload, timeout):
        calls.append((port, path, payload))
        if path == "/rerank":
            return {"results": [{"index": i, "relevance_score": i} for i in range(len(payload["documents"]))]}
        return {"data": [{"index": i, "embedding": [len(text), 1]} for i, text in enumerate(payload["input"])]}

    monkeypatch.setattr("local_retrieval._post", post)
    return calls


def test_exact_reuse_keeps_order_and_returns_independent_vectors(monkeypatch):
    calls = fake_server(monkeypatch)
    selector = SemanticSpanSelector(RetrievalConfig(8081, dimension=2, cache_entries=8, max_requests=2))
    first = selector.embed(["abc", "x", "abc", "y", "z"])
    assert first[0] == first[2] and first[0] is not first[2]
    first[0][0] = 999
    second = selector.embed(["y", "abc", "new", "abc"])
    assert second[1] == first[2] == second[3]
    assert [p[2]["input"] for p in calls] == [["abc", "x", "y", "z"], ["new"]]
    assert selector.cache_stats() == {"entry_limit": 8, "entries": 5, "cache_hits": 3,
                                      "deduplicated_inputs": 1, "successful_inputs_sent": 5}
    assert selector.embed(["abc"]) == [first[2]]
    with pytest.raises(ValueError, match="budget"):
        selector.embed(["unknown"])
    assert selector.requests == 2


def test_lru_and_selector_isolation(monkeypatch):
    calls = fake_server(monkeypatch)
    config = RetrievalConfig(8081, dimension=2, cache_entries=2)
    first = SemanticSpanSelector(config)
    first.embed(["a", "b"])
    first.embed(["a"])
    first.embed(["c"])
    first.embed(["b"])
    second = SemanticSpanSelector(config)
    second.embed(["b"])
    assert [p[2]["input"] for p in calls] == [["a", "b"], ["c"], ["b"], ["b"]]
    assert first.cache_stats()["entries"] == 2
    assert second.cache_stats()["cache_hits"] == 0
    assert SemanticSpanSelector(RetrievalConfig(8081, dimension=16384, cache_entries=64)).cache_stats()["entry_limit"] == 4


def test_failure_invalidates_old_and_partial_vectors(monkeypatch):
    calls = fake_server(monkeypatch)
    import local_retrieval
    original = local_retrieval._post
    selector = SemanticSpanSelector(RetrievalConfig(8081, dimension=2, cache_entries=16))
    selector.embed(["old"])

    def fail_second(port, path, payload, timeout):
        if payload["input"] == ["e"]:
            return {"data": [{"index": 0, "embedding": [0, 0]}]}
        return original(port, path, payload, timeout)

    monkeypatch.setattr(local_retrieval, "_post", fail_second)
    with pytest.raises(ValueError, match="Zero vector"):
        selector.embed(["a", "b", "c", "d", "e"])
    assert selector.cache_stats()["entries"] == 0
    assert selector.cache_stats()["successful_inputs_sent"] == 1
    assert selector.requests == 3
    monkeypatch.setattr(local_retrieval, "_post", original)
    selector.embed(["old", "a"])
    assert calls[-1][2]["input"] == ["old", "a"]


def test_cache_cannot_extend_total_deadline(monkeypatch):
    calls = fake_server(monkeypatch)
    now = [0.0]
    monkeypatch.setattr("local_retrieval.time.monotonic", lambda: now[0])
    selector = SemanticSpanSelector(RetrievalConfig(8081, dimension=2, cache_entries=8, total_timeout=1))
    selector.embed(["abc"])
    now[0] = 1.0
    with pytest.raises(TimeoutError):
        selector.embed(["abc"])
    assert len(calls) == 1 and selector.cache_stats()["entries"] == 0


def test_two_sources_keep_distinct_ids_and_rerank_is_not_cached(monkeypatch):
    calls = fake_server(monkeypatch)
    selector = SemanticSpanSelector(RetrievalConfig(8081, 8082, dimension=2, cache_entries=8, max_requests=3))
    assert selector("query", [Span(0, 0, 3, "abc")]) == [0]
    assert selector("query", [Span(99, 7, 10, "abc")]) == [99]
    assert [p[1] for p in calls] == ["/v1/embeddings", "/rerank", "/rerank"]
    assert selector.last_selection["embedding_cache"]["cache_hits"] == 2


@pytest.mark.parametrize("value", [True, -1, 65, 1.5, None])
def test_invalid_cache_limits(value):
    with pytest.raises(ValueError):
        RetrievalConfig(8081, cache_entries=value)


def test_default_does_not_cache(monkeypatch):
    calls = fake_server(monkeypatch)
    selector = SemanticSpanSelector(RetrievalConfig(8081, dimension=2))
    selector.embed(["a", "a"])
    selector.embed(["a"])
    assert [p[2]["input"] for p in calls] == [["a", "a"], ["a"]]
    assert selector.cache_stats()["entries"] == 0
