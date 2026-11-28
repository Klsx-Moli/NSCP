import importlib.util
import json
from pathlib import Path

import pytest

from extractive_context import _PREVIEW, plan_extractive_request

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "_extractive_benchmark", ROOT / "tools" / "benchmark_extractive_context.py")
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def test_benchmark_preserves_unknown_and_distinguishes_answer_key_from_model():
    result = benchmark.run_benchmark()
    assert len(result["cases"]) == 12
    assert result["actual_model_accuracy"] is None
    assert result["provider_tokens"] is None and result["billed_cost"] is None
    for case in result["cases"]:
        routes = {r["route"]: r for r in case["results"]}
        assert set(routes) == {"references", "bm25", "oracle_answer_key"}
        assert not routes["references"]["expected_evidence_visible"]
        assert all(r["model_calls"] == 0 and r["semantic_task_success"] is None
                   for r in routes.values())
        assert all(r["estimated_after"] <= r["estimated_before"] for r in routes.values())
    assert any(r["expected_evidence_visible"] for c in result["cases"]
               for r in c["results"] if r["route"] == "bm25")


def test_benchmark_detects_invented_excerpt_even_if_manifest_unchanged():
    _, query, evidence = benchmark.CASES[0]
    rows = benchmark.fixture(query, evidence)
    plan = plan_extractive_request(rows, rows, 1200, keep_recent=1)
    assert plan.report["excerpts"]
    marker, raw = plan.messages[4]["content"].split(_PREVIEW, 1)
    body = json.loads(raw)
    body[0]["text"] += " invented"
    plan.messages[4]["content"] = marker + _PREVIEW + json.dumps(body)
    with pytest.raises(AssertionError, match="differs from source"):
        benchmark._verify(rows, plan)


def test_benchmark_detects_corrupted_span_digest():
    _, query, evidence = benchmark.CASES[0]
    rows = benchmark.fixture(query, evidence)
    plan = plan_extractive_request(rows, rows, 1200, keep_recent=1)
    plan.report["excerpts"][0]["spans"][0]["sha256"] = "0" * 64
    with pytest.raises(AssertionError, match="digest"):
        benchmark._verify(rows, plan)


def test_benchmark_no_clobber(tmp_path):
    out = tmp_path / "existing.json"
    out.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        benchmark.main(["--out", str(out)])
    assert out.read_text(encoding="utf-8") == "keep"
