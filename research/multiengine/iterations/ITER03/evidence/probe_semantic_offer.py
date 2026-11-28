"""Semantic-gap probe: force the target span into the offered candidate pool."""
import json
import sys
import time
from pathlib import Path

E = Path(__file__).parent
W = "<ITER03_WORKTREE>"
sys.path[:0] = [W + "/src", W + "/tools"]
import extractive_context as ex
from local_summary import LocalSummaryConfig
from benchmark_extractive_context import fixture

CASES = [
    ("semantic_gap", "Which obligations remain applicable?",
     "Never publish outside the isolated branch."),
    ("semantic_access", "¿Quién puede acceder ahora al servidor?",
     "La autorización anterior quedó anulada y no rige."),
]
cfg = LocalSummaryConfig(model="qwen3.5:4b-q4_K_M", num_ctx=8192, num_predict=128, timeout=90)
selector = ex.OllamaSpanSelector(cfg)
rows = []
for name, query, evidence in CASES:
    source = fixture(query, evidence)[4]["content"]
    spans = ex.split_spans(source)
    targets = [s for s in spans if evidence in s.text]
    distractors = [s for s in spans if s.id not in {t.id for t in targets}]
    step = max(1, len(distractors) // 7)
    pool = tuple([targets[0]] + distractors[::step][:7])
    t0 = time.perf_counter()
    row = {"case": name, "query": query, "target_ids": [t.id for t in targets],
           "offered_ids": [s.id for s in pool], "pool_size": len(pool)}
    try:
        ids = list(selector(query, pool))
        row.update(qwen_ids=ids, valid=all(type(i) is int and i in {s.id for s in pool} for i in ids),
                   hit=any(i in {t.id for t in targets} for i in ids))
    except Exception as exc:
        row.update(error=f"{type(exc).__name__}: {exc}", valid=False, hit=False)
    row["seconds"] = round(time.perf_counter() - t0, 3)
    rows.append(row)
    print(name, "hit", row.get("hit"), "ids", row.get("qwen_ids"), "err", row.get("error"), flush=True)
(E / "semantic_gap_forced_offer.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
