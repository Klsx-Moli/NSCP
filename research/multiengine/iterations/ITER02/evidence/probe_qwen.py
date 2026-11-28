"""Direct synthetic probe of Ollama /api/chat for qwen3.5:4b-q4_K_M.

Usage: python probe_qwen.py matrix|sweep
Saves full request/response (synthetic data only) to probe_qwen_results.json.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

URL = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen3.5:4b-q4_K_M"
OUT = Path(__file__).with_name("probe_qwen_results.json")
mode = sys.argv[1] if len(sys.argv) > 1 else "matrix"

cases = []
if mode == "matrix":
    for think in (False, True, "absent"):
        cases.append((f"think_{think}_np128", think, 128))
elif mode == "sweep":
    for np_ in (256, 512, 1024, 2048):
        cases.append((f"think_false_np{np_}", False, np_))

results = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
for name, think, num_predict in cases:
    payload = {
        "model": MODEL,
        "stream": False,
        "think": think,
        "truncate": False,
        "shift": False,
        "messages": [{"role": "user", "content": "Responde exclusivamente con la palabra OK."}],
        "options": {"num_ctx": 4096, "num_predict": num_predict, "temperature": 0},
    }
    if think == "absent":
        payload.pop("think")
    req = urllib.request.Request(
        URL, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    t0 = time.perf_counter()
    entry = {"request": payload, "case": name}
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            entry["http_status"] = r.status
            body = json.loads(r.read().decode("utf-8"))
        msg = body.get("message", {})
        entry["response"] = {
            "content": msg.get("content"),
            "thinking_len": len(msg.get("thinking") or ""),
            "thinking_head": (msg.get("thinking") or "")[:200],
            "tool_calls": body.get("message", {}).get("tool_calls"),
            "done": body.get("done"),
            "done_reason": body.get("done_reason"),
            "eval_count": body.get("eval_count"),
            "prompt_eval_count": body.get("prompt_eval_count"),
        }
        entry["verdict"] = (
            "PASS" if (msg.get("content") or "").strip() and body.get("done_reason") == "stop"
            else "FAIL"
        )
    except Exception as exc:
        entry["error"] = f"{type(exc).__name__}: {exc}"
        entry["verdict"] = "ERROR"
    entry["duration_s"] = round(time.perf_counter() - t0, 2)
    results[name] = entry
    print(name, entry.get("verdict"), "content=", repr(entry.get("response", {}).get("content"))[:80],
          "done_reason=", entry.get("response", {}).get("done_reason"),
          "thinking_len=", entry.get("response", {}).get("thinking_len"),
          "seconds=", entry["duration_s"], flush=True)
    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
