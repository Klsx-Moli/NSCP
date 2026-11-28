"""Capture raw Ollama /api/chat response for one selector call."""
import json
import sys
from pathlib import Path
import urllib.request

E = Path(__file__).parent
W = "<ITER03_WORKTREE>"
sys.path[:0] = [W + "/src", W + "/tools"]
import extractive_context as ex
from local_summary import LocalSummaryConfig
from benchmark_extractive_context import CASES, fixture

name, query, evidence = CASES[0]
messages = fixture(query, evidence)
spans = ex.split_spans(messages[4]["content"])
pool = ex.candidate_pool(spans, ex.rank_spans(spans, query))
cfg = LocalSummaryConfig(model="qwen3.5:4b-q4_K_M", num_ctx=8192, num_predict=128, timeout=90)

wire = [{"role": "system", "content": ex._SYSTEM},
        {"role": "user", "content": ex._json({"query": query, "max_ids": 6,
                                              "candidates": ex._payload(pool)})}]
print("WIRE_BYTES", len(ex._json(wire).encode("utf-8")), "POOL", len(pool), flush=True)
payload = {"model": cfg.model, "messages": wire, "stream": False, "think": False,
           "truncate": False, "shift": False,
           "options": {"num_ctx": cfg.num_ctx, "num_predict": cfg.num_predict, "temperature": 0}}
req = urllib.request.Request("http://127.0.0.1:11434/api/chat",
                             data=json.dumps(payload).encode("utf-8"),
                             headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=120) as r:
    body = json.loads(r.read().decode("utf-8"))
msg = body.get("message", {})
out = {"done": body.get("done"), "done_reason": body.get("done_reason"),
       "model": body.get("model"), "remote_host": body.get("remote_host"),
       "prompt_eval_count": body.get("prompt_eval_count"), "eval_count": body.get("eval_count"),
       "content": msg.get("content"), "thinking_len": len(msg.get("thinking") or ""),
       "tool_calls": msg.get("tool_calls")}
(E / "selector_raw_response.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False)[:1200])
