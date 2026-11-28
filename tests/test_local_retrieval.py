import pytest

from extractive_context import Span, plan_extractive_request
from local_retrieval import RetrievalConfig, SemanticSpanSelector, embedding_results


def test_embeddings_are_mapped_by_index_and_normalized():
    r = {"data": [{"index": 1, "embedding": [0, 5]}, {"index": 0, "embedding": [8, 0]}]}
    assert embedding_results(r, 2, 2) == [[1, 0], [0, 1]]
    r["data"][0]["index"] = 0
    with pytest.raises(ValueError):
        embedding_results(r, 2, 2)


@pytest.mark.parametrize("kw", [{"embedding_port": True}, {"embedding_port": None},
                               {"embedding_port": 0}, {"reranker_port": 8081},
                               {"dimension": 0}, {"timeout": float("nan")},
                               {"max_requests": 0}])
def test_invalid_policy(kw):
    args = {"embedding_port": 8081}
    args.update(kw)
    with pytest.raises(ValueError):
        RetrievalConfig(**args)


def test_semantic_ranking_reranking_and_actual_request_limit(monkeypatch):
    spans = [Span(0, 0, 5, "noise"), Span(1, 5, 11, "target"), Span(2, 11, 16, "other")]
    def post(port, path, data, timeout):
        if path == "/v1/embeddings":
            vectors = {"query": [1, 0], "noise": [0, 1], "target": [1, 0], "other": [1, 1]}
            return {"data": [{"index": i, "embedding": vectors[s]}
                             for i, s in reversed(list(enumerate(data["input"])))]}
        assert data["documents"] == ["target", "other", "noise"]
        return {"results": [{"index": 1, "relevance_score": 0.9},
                            {"index": 0, "relevance_score": 0.8},
                            {"index": 2, "relevance_score": 0.1}]}
    monkeypatch.setattr("local_retrieval._post", post)
    selector = SemanticSpanSelector(RetrievalConfig(8081, 8082, dimension=2, max_requests=2))
    assert selector("query", spans) == [2, 1, 0]
    assert selector.requests == 2
    with pytest.raises(ValueError, match="budget"):
        selector("query", spans)
    assert selector.requests == 2


def test_invalid_endpoint_response_fails_without_retry(monkeypatch):
    def post(*args):
        return {"data": [{"index": 0, "embedding": [0, 0]}]}
    monkeypatch.setattr("local_retrieval._post", post)
    selector = SemanticSpanSelector(RetrievalConfig(8081, dimension=2))
    with pytest.raises(ValueError):
        selector("query", [Span(0, 0, 3, "abc")])
    assert selector.requests == 1


def history():
    source = "".join(f"line{i:03d} " + "x" * 115 + "\n" for i in range(90))
    source += "Current restriction: never publish production.\n"
    return [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "previous"},
        {"role": "assistant", "content": "inspect"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call", "type": "function", "function": {"name": "read", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "call", "content": source},
        {"role": "assistant", "content": "done"},
        {"role": "user", "content": "What obligations apply?"},
    ]


def test_extractive_all_pool_offers_semantic_target_not_just_sample():
    rows = history()
    seen = []
    def select(query, spans):
        seen.extend(spans)
        return [s.id for s in spans if "never publish" in s.text]
    result = plan_extractive_request(rows, rows, 1300, keep_recent=1,
                                     selector=select, selector_route="embedding",
                                     selector_pool="bounded_all")
    assert len(seen) > 24
    assert result.report["excerpts"][0]["route"] == "embedding"
    assert "never publish" in result.messages[4]["content"]
    assert result.report["fits_metered_budget"]
    assert result.report["selector_attempts"][0]["offered_candidates"] == len(seen)


def test_oversize_semantic_pool_is_not_silently_sampled():
    rows = history()
    rows[4]["content"] *= 3
    def never(*args):
        pytest.fail("oversized pool must not be silently sampled")
    result = plan_extractive_request(rows, rows, 1300, keep_recent=1,
                                     selector=never, selector_route="embedding",
                                     selector_pool="bounded_all")
    assert result.report["selector_calls"] == 0
    assert result.report["selector_attempts"][0]["outcome"] == "pool_limit"



def test_exact_duplicate_occurrences_cost_one_embedding(monkeypatch):
    spans = [Span(0, 0, 3, "abc"), Span(1, 3, 6, "abc"),
             Span(2, 6, 9, "def"), Span(3, 9, 12, "abc")]
    calls = []

    def post(port, path, data, timeout):
        calls.append(data["input"])
        return {"data": [{"index": i, "embedding": [1, 0]}
                         for i in range(len(data["input"]))]}

    monkeypatch.setattr("local_retrieval._post", post)
    selector = SemanticSpanSelector(RetrievalConfig(8081, dimension=2, max_requests=1))
    assert selector("query", spans) == [0, 2]
    assert calls == [["query", "abc", "def"]]
    assert selector.last_selection["occurrence_groups"] == {0: [0, 1, 3], 2: [2]}
    assert selector.last_selection["duplicate_occurrences"] == 2


def test_preview_deduplicates_even_if_selector_returns_repeated_text():
    rows = history()
    rows[4]["content"] = "a" * 384 * 20 + "unique critical evidence " + "b" * 300
    original = rows[4]["content"]
    result = plan_extractive_request(rows, rows, 1300, keep_recent=1,
        selector=lambda query, spans: [0, 1, 2, len(spans) - 1],
        selector_route="embedding", selector_pool="bounded_all")
    assert result.report["duplicate_preview_spans_skipped"] == 2
    assert len(result.report["excerpts"][0]["spans"]) == 2
    assert rows[4]["content"] == original
    assert "unique critical evidence" in result.messages[4]["content"]
