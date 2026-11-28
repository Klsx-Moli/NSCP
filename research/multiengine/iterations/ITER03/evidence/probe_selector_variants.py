"""Variant matrix for the selector wire request (synthetic, direct /api/chat)."""
import json
import time
import urllib.request
from pathlib import Path

E = Path(__file__).parent
W = "<ITER03_WORKTREE>"
import sys
sys.path[:0] = [W + "/src", W + "/tools"]
import extractive_context as ex
from benchmark_extractive_context import CASES, fixture

name, query, evidence = CASES[0]
messages = fixture(query, evidence)
spans = ex.split_spans(messages[4]["content"])
pool = ex.candidate_pool(spans, ex.rank_spans(spans, query))
wire = [{"role": "system", "content": ex._SYSTEM},
        {"role": "user", "content": ex._json({"query": query, "max_ids": 6,
                                              "candidates": ex._payload(pool)})}]
rows = []
for ctx, predict in ((4096, 128), (4096, 256), (8192, 128), (8192, 256), (16384, 128)):
    payload = {"model": "qwen3.5:4b-q4_K_M", "messages": wire, "stream": False,
               "think": False, "truncate": False, "shift": False,
               "options": {"num_ctx": ctx, "num_predict": predict, "temperature": 0}}
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/chat",
                                     data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=150) as r:
            body = json.loads(r.read().decode("utf-8"))
        msg = body.get("message", {})
        rows.append({"ctx": ctx, "predict": predict, "done": body.get("done"),
                     "reason": body.get("done_reason"), "prompt": body.get("prompt_eval_count"),
                     "eval": body.get("eval_count"), "content": (msg.get("content") or "")[:160],
                     "thinking_len": len(msg.get("thinking") or ""),
                     "seconds": round(time.perf_counter() - t0, 2)})
    except Exception as exc:
        rows.append({"ctx": ctx, "predict": predict, "error": f"{type(exc).__name__}: {exc}"})
    print(rows[-1], flush=True)
(E / "selector_context_variants.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
