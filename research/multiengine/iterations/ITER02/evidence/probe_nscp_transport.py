"""Real-loopback integration of the unified 9e6646b strict transport."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from context_compactor import TurnView
import local_summary
import summarizer

out = {"sha": "9e6646b418a34d36d8ba09eb354bd81191caff69", "model": "qwen3.5:4b-q4_K_M"}
turns = [
    TurnView("user", "Decision: el servidor usa el puerto 11435 y el archivo config/service.py."),
    TurnView("assistant", "Entendido: puerto 11435, archivo config/service.py."),
]
for label, fn in (
    ("legacy_summarize_turns", lambda: summarizer.summarize_turns(turns, strict=True, num_predict=128)),
    ("strict_complete_summary", lambda: local_summary.complete_summary(
        [{"role": "user", "content": "Resume en una frase: usa el puerto 11435 y config/service.py."}])),
):
    t0 = time.perf_counter()
    try:
        value = fn()
        out[label] = {
            "status": "PASS",
            "result": value.content if hasattr(value, "content") else value,
            "seconds": round(time.perf_counter() - t0, 2),
        }
    except Exception as exc:
        out[label] = {"status": "FAIL", "error": f"{type(exc).__name__}: {exc}",
                      "seconds": round(time.perf_counter() - t0, 2)}
    print(label, out[label]["status"], str(out[label].get("result", out[label].get("error")))[:120], flush=True)

Path(sys.argv[2]).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
