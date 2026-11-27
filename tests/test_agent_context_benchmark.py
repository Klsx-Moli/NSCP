import importlib.util
from pathlib import Path

import pytest

from agent_context import MARKER, _estimate, plan_request

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "_request_benchmark", ROOT / "tools" / "benchmark_agent_context.py")
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def test_differential_benchmark_reports_unknowns_and_unmet_budget():
    rows = benchmark.fixture(12, focused=True)
    results = benchmark.compare(rows, 1)
    assert len(results) == 5
    assert all(not row["fits_metered_budget"] for row in results)
    assert all(row["estimated_tokens_saved"] >= 0 for row in results)
    assert any(row["exact_recovery"] == "pass" for row in results)
    assert all(row.get("focus_protected", 1) >= 1 for row in results)


def test_benchmark_rejects_mutated_tool_metadata_and_missing_reference():
    rows = benchmark.fixture(12)
    plan = plan_request(rows, rows, 1)
    changed = next(row for row in plan.messages if row["role"] == "tool"
                   and row["content"].startswith(MARKER))
    changed["tool_call_id"] = "tampered"
    with pytest.raises(AssertionError, match="metadata"):
        benchmark._validate(rows, plan)
    plan = plan_request(rows, rows, 1)
    changed = next(row for row in plan.messages if row["role"] == "tool"
                   and row["content"].startswith(MARKER))
    changed["content"] = MARKER
    with pytest.raises(AssertionError, match="reference"):
        benchmark._validate(rows, plan)


def test_all_routes_preserve_same_focus_and_recover_exactly():
    rows = benchmark.fixture(12, focused=True)
    before = _estimate(rows)
    results = benchmark.compare(rows, int(before * 0.8))
    assert all(row["tokens_after"] <= before for row in results)
    assert all(row["exact_recovery"] in ("pass", "not_applicable") for row in results)
    assert all(row.get("focus_protected", 1) >= 1 for row in results)
