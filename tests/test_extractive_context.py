import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from agent_context import MARKER, _estimate, recall
from extractive_context import (
    _PREVIEW, OllamaSpanSelector, candidate_pool, plan_extractive_request, rank_spans, split_spans,
)


def history():
    return [
        {"role": "system", "content": "Never push."},
        {"role": "user", "content": "Inspect historical logs."},
        {"role": "assistant", "content": "Inspecting."},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c", "type": "function", "function": {"name": "read", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c", "content":
         "noise ordinary output\n" * 300 + "unicorn permission revoked: never publish\n"
         + "noise ordinary output\n" * 300, "metadata": {"source": "log"}},
        {"role": "assistant", "content": "Inspection ended."},
        {"role": "user", "content": "Find unicorn permission."},
    ]


def test_exact_spans_unicode_and_bm25():
    text = ("😀 alpha\n" * 50) + "unicorn permission revoked\n" + ("漢 beta\n" * 100)
    spans = split_spans(text, 128)
    assert "".join(s.text for s in spans) == text
    assert all(s.text == text[s.start:s.end] for s in spans)
    assert "unicorn" in spans[rank_spans(spans, "unicorn")[0]].text
    assert rank_spans(spans, "nonexistent") == []


def test_plan_excerpts_exact_source_and_recall():
    rows = history()
    original = deepcopy(rows)
    plan = plan_extractive_request(rows, rows, 1200, keep_recent=1)
    assert rows == original
    assert plan.report["fits_metered_budget"]
    assert _estimate(plan.messages) == plan.report["tokens_after"] <= 1200
    assert plan.report["semantic_equivalence"] == "not_verified"
    assert plan.report["excerpts"]
    assert plan.messages[4]["content"].startswith(MARKER)
    assert plan.messages[4]["metadata"] == rows[4]["metadata"]
    assert plan.messages[:4] == rows[:4] and plan.messages[5:] == rows[5:]
    body = json.loads(plan.messages[4]["content"].split(_PREVIEW, 1)[1])
    ref = plan.report["references"][0]
    assert any("never publish" in s["text"] for s in body)
    for span, manifest in zip(body, plan.report["excerpts"][0]["spans"]):
        part = recall(rows, ref, offset=span["start"], limit=span["end"] - span["start"])
        assert part["content"] == span["text"]
        assert hashlib.sha256(span["text"].encode()).hexdigest() == manifest["sha256"]
    assert plan == plan_extractive_request(rows, rows, 1200, keep_recent=1)


@pytest.mark.parametrize("bad", [[True], [999999], [0, 0], ["0"], {"ids": [0]}, list(range(7))])
def test_invalid_model_ids_only_fallback_to_exact_lexical(bad):
    rows = history()
    p = plan_extractive_request(rows, rows, 1200, keep_recent=1,
                                selector=lambda query, spans: bad)
    assert p.report["selector_calls"] == p.report["selector_failures"] == 1
    assert p.report["excerpts"][0]["route"] == "bm25_fallback"
    assert "never publish" in p.messages[4]["content"]


def test_valid_model_ids_not_generated_text_and_empty_respected():
    rows = history()
    def select(query, spans):
        return [spans[0].id]
    p = plan_extractive_request(rows, rows, 1200, keep_recent=1, selector=select)
    assert p.report["excerpts"][0]["route"] == "local_ids"
    assert p.report["selector_calls"] == 1 and not p.report["selector_failures"]
    empty = plan_extractive_request(rows, rows, 1200, keep_recent=1,
                                    selector=lambda query, spans: [])
    assert not empty.report["excerpts"] and _PREVIEW not in empty.messages[4]["content"]


def test_no_selection_if_unreachable_missing_source_or_protected():
    rows = history()
    def never(*args):
        pytest.fail("selector should not run")
    for budget, source in [(1, rows), (1200, rows[5:])]:
        p = plan_extractive_request(rows, source, budget, keep_recent=1, selector=never)
        assert not p.report["excerpts"] and not p.report["selector_calls"]
    rows[4]["pinned"] = True
    p = plan_extractive_request(rows, rows, 1200, keep_recent=1, selector=never)
    assert p.messages == rows


def test_reserve_and_replay_never_rewrite_existing_preview():
    rows = history()
    p = plan_extractive_request(rows, rows, 1200, keep_recent=1, preview_reserve=300)
    assert p.report["budget"] == 1200
    assert p.report["tokens_after"] <= 1200
    replay = plan_extractive_request(p.messages, rows, 1200, keep_recent=1)
    assert replay.messages == p.messages


def test_local_selector_only_accepts_ids_from_transmitted_pool(monkeypatch):
    spans = split_spans("abc " * 500, 128)
    seen = []
    def fake(messages, config):
        payload = json.loads(messages[-1]["content"])
        seen.extend(payload["candidates"])
        return SimpleNamespace(content=json.dumps([payload["candidates"][0]["id"]]))
    monkeypatch.setattr("extractive_context.complete_summary", fake)
    result = OllamaSpanSelector()("query", spans)
    assert result == [seen[0]["id"]]
    monkeypatch.setattr("extractive_context.complete_summary",
                        lambda *args: SimpleNamespace(content='{"text":"fabricated"}'))
    with pytest.raises(ValueError):
        OllamaSpanSelector()("query", spans)


def test_call_limit_and_large_source_skip():
    rows = history()
    p = plan_extractive_request(rows, rows, 1200, keep_recent=1,
                                selector=lambda *args: pytest.fail("call limit"), max_model_calls=0)
    assert p.report["selector_calls"] == 0
    assert p.report["excerpts"]
    rows[4]["content"] = "unicorn " * 20000
    p = plan_extractive_request(rows, rows, 1200, keep_recent=1)
    assert p.report["skipped_sources"] == 1 and not p.report["excerpts"]


def test_candidate_pool_diversity_and_nonlexical_coverage():
    spans = split_spans(("repeat word\n" * 10 + "pad" * 4) * 200, 128)
    ranked = rank_spans(spans, "repeat")
    pool = candidate_pool(spans, ranked)
    assert len(pool) <= 24
    assert len({s.text for s in pool}) == len(pool)
    distinct = split_spans("".join(f"{i:04d}" + "x" * 124 for i in range(100)), 128)
    sampled = candidate_pool(distinct, [])
    assert len(sampled) == 24
    assert sampled[0].id == 0 and sampled[-1].id == 99
    assert any(40 <= span.id <= 60 for span in sampled)


def test_failed_selection_reports_without_leaking_error_body():
    rows = history()
    def fail(*args):
        raise RuntimeError("private text should not enter report")
    plan = plan_extractive_request(rows, rows, 1200, keep_recent=1, selector=fail)
    assert plan.report["selector_attempts"] == [
        {"message_index": 4, "offered_candidates": plan.report["selector_attempts"][0]["offered_candidates"],
         "outcome": "failed", "error_type": "RuntimeError"}]
    assert "private text" not in json.dumps(plan.report)
    assert plan.report["excerpts"][0]["route"] == "bm25_fallback"


def test_cli_offline_extractive_route(tmp_path, capsys):
    from npsc_agent_cli import run_cli
    path = tmp_path / "hist.json"
    path.write_text(json.dumps(history()), encoding="utf-8")
    assert run_cli(["plan", "--input", str(path), "--transcript", str(path),
                    "--budget", "1200", "--keep-recent", "1", "--excerpts", "bm25"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["report"]["schema"] == "nscp/extractive-plan/v1"
    assert payload["report"]["excerpts"]
