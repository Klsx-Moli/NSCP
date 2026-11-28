"""Real Qwen3.5 benchmark of OllamaSpanSelector vs BM25 on synthetic cases.

No production file is modified. Oracle answer keys from the synthetic benchmark
are used ONLY as reference labels, never as model output.
"""
import json
import sys
import time
from pathlib import Path

E = Path(__file__).parent
SRC = "<ITER03_WORKTREE>/src"
TOOLS = "<ITER03_WORKTREE>/tools"
sys.path[:0] = [SRC, TOOLS]

import extractive_context as ex
from local_summary import LocalSummaryConfig
from benchmark_extractive_context import CASES, fixture

MODEL = "qwen3.5:4b-q4_K_M"
SHA = "97ea9e987656bf64234cfc56ee3a89196a3b579d"
selector_config = LocalSummaryConfig(model=MODEL, num_ctx=8192, num_predict=128, timeout=90)
selector = ex.OllamaSpanSelector(selector_config)

telemetry = []
real_complete = ex.complete_summary


def measured_complete(messages, config):
    t0 = time.perf_counter()
    result = real_complete(messages, config)
    telemetry.append({
        "duration_s": round(time.perf_counter() - t0, 3),
        "model": result.model,
        "prompt_eval_count": result.prompt_eval_count,
        "eval_count": result.eval_count,
        "input_wire_bytes": result.input_wire_bytes,
        "raw_content": result.content[:300],
    })
    return result


ex.complete_summary = measured_complete

custom = [
    ("semantic_access", "¿Quién puede acceder ahora al servidor?",
     "La autorización anterior quedó anulada y no rige."),
]
cases = list(CASES) + custom
report = {
    "schema": "nscp/extractive-model-benchmark/v1",
    "sha": SHA,
    "model": MODEL,
    "route_under_test": "OllamaSpanSelector -> real loopback Ollama",
    "reference_only": "synthetic oracle_answer_key from tools/benchmark_extractive_context.py",
    "token_accounting": "provider prompt_eval_count/eval_count from /api/chat",
    "billed_cost": None,
    "cases": [],
    "repetitions": [],
}

for name, query, evidence in cases:
    messages = fixture(query, evidence)
    source = messages[4]["content"]
    spans = ex.split_spans(source)
    ranking = ex.rank_spans(spans, query)
    pool = ex.candidate_pool(spans, ranking)
    pool_ids = {s.id for s in pool}
    targets = [s.id for s in spans if evidence in s.text]
    bm25_ids = ranking[:ex.MAX_EXCERPTS]
    rec = {
        "case": name,
        "query": query,
        "evidence_label": evidence,
        "span_count": len(spans),
        "pool_size": len(pool),
        "offered_ids": sorted(pool_ids),
        "target_span_ids": targets,
        "bm25_ids": bm25_ids,
        "bm25_hit": any(i in targets for i in bm25_ids),
        "qwen_ids": None,
        "qwen_valid": False,
        "qwen_hit": False,
        "evidence_omitted_by_qwen": True,
        "error": None,
    }
    t0 = time.perf_counter()
    try:
        ids = selector(query, tuple(pool))
        rec["qwen_ids"] = list(ids)
        rec["qwen_valid"] = (
            isinstance(ids, list) and len(ids) <= ex.MAX_EXCERPTS
            and all(type(i) is int and i in pool_ids for i in ids)
            and len(set(ids)) == len(ids)
        )
        rec["qwen_hit"] = any(i in targets for i in ids)
        rec["evidence_omitted_by_qwen"] = not rec["qwen_hit"]
        rec["qwen_raw_response"] = telemetry[-1]["raw_content"] if telemetry else None
    except Exception as exc:
        rec["error"] = f"{type(exc).__name__}: {exc}"
    rec["wall_s"] = round(time.perf_counter() - t0, 3)
    report["cases"].append(rec)
    print(name, "valid", rec["qwen_valid"], "bm25_hit", rec["bm25_hit"],
          "qwen_hit", rec["qwen_hit"], "ids", rec["qwen_ids"], "err", rec["error"], flush=True)

# Repeated selection on the revocation case: stability and validity across calls.
query, evidence = "What is the current permission?", "current permission: the prior approval has been revoked."
messages = fixture(query, evidence)
spans = ex.split_spans(messages[4]["content"])
ranking = ex.rank_spans(spans, query)
pool = ex.candidate_pool(spans, ranking)
for i in range(3):
    t0 = time.perf_counter()
    entry = {"attempt": i + 1, "pool_size": len(pool)}
    try:
        ids = list(selector(query, tuple(pool)))
        entry.update(ids=ids, valid=all(type(x) is int and x in {s.id for s in pool} for x in ids),
                     seconds=round(time.perf_counter() - t0, 3))
    except Exception as exc:
        entry.update(error=f"{type(exc).__name__}: {exc}", seconds=round(time.perf_counter() - t0, 3))
    report["repetitions"].append(entry)
    print("repeat", entry, flush=True)

report["provider_telemetry"] = telemetry
bm25_hits = sum(1 for c in report["cases"] if c["bm25_hit"])
qwen_hits = sum(1 for c in report["cases"] if c["qwen_hit"])
qwen_valid = sum(1 for c in report["cases"] if c["qwen_valid"] and not c["error"])
report["summary"] = {
    "cases": len(report["cases"]),
    "bm25_hits": bm25_hits,
    "qwen_hits": qwen_hits,
    "qwen_valid_responses": qwen_valid,
    "bm25_hit_rate": round(bm25_hits / len(report["cases"]), 3),
    "qwen_hit_rate": round(qwen_hits / len(report["cases"]), 3),
    "total_prompt_tokens": sum(t["prompt_eval_count"] for t in telemetry),
    "total_completion_tokens": sum(t["eval_count"] for t in telemetry),
    "total_wall_s": round(sum(t["duration_s"] for t in telemetry), 3),
    "mean_wall_s": round(sum(t["duration_s"] for t in telemetry) / max(1, len(telemetry)), 3),
}
(E / "EXTRACTIVE_MODEL_BENCHMARK.json").write_text(
    json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print("SUMMARY", report["summary"])
