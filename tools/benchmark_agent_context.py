"""Offline differential benchmark for NSCP request planning.

Synthetic cases are explicitly labeled; this is not a provider or semantic
benchmark. No network, LLM, credentials, real session data or billing involved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from time import perf_counter

from agent_context import MARKER, STRATEGIES, _estimate, _ref, plan_request, recall


def fixture(batches, *, focused=False):
    rows = [{"role": "system", "content": "Preserve user instructions."},
            {"role": "user", "content": "Audit repository. Never push."},
            {"role": "assistant", "content": "Read-only inspection."}]
    for i in range(batches):
        size = 12 + (i * 31) % 90
        body = (f"synthetic path src/module_{i}.py: test result {i}\n"
                + ("line: sample build output 0123456789\n" * size))
        rows.extend([
            {"role": "assistant", "content": None,
             "tool_calls": [{"id": f"call-{i}", "type": "function",
                             "function": {"name": "read", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": f"call-{i}", "content": body,
             "message_uid": f"message-{i}"},
            {"role": "assistant", "content": f"Inspected module {i}."},
        ])
    query = "Inspect src/module_0.py again." if focused else "Continue read-only."
    rows.extend([{"role": "user", "content": query},
                 {"role": "assistant", "content": "Continuing."}])
    return rows


def _digest(rows):
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _validate(original, plan):
    """Check exact structural preservation and rehydration, not task success."""
    changed = 0
    refs = []
    for old, new in zip(original, plan.messages):
        if old == new:
            continue
        if (old["role"] != "tool" or not new["content"].startswith(MARKER)
                or {k: v for k, v in old.items() if k != "content"}
                != {k: v for k, v in new.items() if k != "content"}):
            raise AssertionError("Message role or metadata changed")
        ref = _ref(old)
        if ref not in new["content"]:
            raise AssertionError("Missing original reference")
        chunks, offset = [], 0
        while offset is not None:
            page = recall(original, ref, offset=offset, limit=4000)
            chunks.append(page["content"])
            offset = page["next_offset"]
        if "".join(chunks) != old["content"]:
            raise AssertionError("Inexact recovery")
        refs.append(ref)
        changed += 1
    if len(original) != len(plan.messages) or sorted(refs) != sorted(plan.report["references"]):
        raise AssertionError("Message count or reference manifest mismatch")
    return changed


def compare(rows, budget, *, keep_recent=8):
    before = _digest(rows)
    tokens = _estimate(rows)
    results = [{"strategy": "unchanged", "tokens_before": tokens, "tokens_after": tokens,
                "estimated_tokens_saved": 0, "unchanged_prefix_messages": len(rows),
                "fits_metered_budget": tokens <= budget, "changed_results": 0,
                "exact_recovery": "not_applicable", "planning_ms": 0.0}]
    for strategy in STRATEGIES:
        started = perf_counter()
        plan = plan_request(rows, rows, budget, strategy=strategy, keep_recent=keep_recent)
        elapsed = (perf_counter() - started) * 1000
        changed = _validate(rows, plan)
        if _digest(rows) != before or _estimate(plan.messages) != plan.report["tokens_after"]:
            raise AssertionError("Input mutated or inaccurate heuristic")
        results.append({
            "strategy": strategy, "selected_strategy": plan.report["selected_strategy"],
            "tokens_before": tokens, "tokens_after": plan.report["tokens_after"],
            "estimated_tokens_saved": plan.report["estimated_tokens_saved"],
            "unchanged_prefix_messages": plan.report["unchanged_prefix_messages"],
            "fits_metered_budget": plan.report["fits_metered_budget"],
            "focus_protected": plan.report["focus_protected"], "changed_results": changed,
            "exact_recovery": "pass" if changed else "not_applicable",
            "planning_ms": round(elapsed, 3),
        })
    return results


def run_benchmark():
    cases = []
    for batches, focused in ((12, False), (60, False), (60, True)):
        rows = fixture(batches, focused=focused)
        before = _estimate(rows)
        for pressure, ratio in (("moderate", 0.8), ("high", 0.35), ("unreachable", 0.01)):
            budget = max(1, int(before * ratio))
            cases.append({"name": f"{batches}-batches-{focused}-{pressure}",
                          "messages": len(rows), "budget": budget, "focus": focused,
                          "fixture_sha256": _digest(rows), "results": compare(rows, budget)})
    return {"schema": "nscp/request-benchmark/v1",
            "data_origin": "synthetic", "token_accounting": "utf8_heuristic",
            "provider_tokens": None, "cache_hits": None, "billed_cost": None,
            "semantic_task_success": None, "cases": cases}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    result = run_benchmark()
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        # A benchmark report is an explicit output, not a conversation store.
        args.out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
