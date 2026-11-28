"""Sample Ollama VRAM while a real synthetic inference is in flight."""
import json
import threading
import time
import urllib.request
from pathlib import Path

E = Path(__file__).parent
payload = {
    "model": "qwen3.5:4b-q4_K_M", "stream": False, "think": False,
    "messages": [{"role": "user", "content": "Explica en 80 palabras por qué la VRAM dedicada importa para inferencia local."}],
    "options": {"num_ctx": 4096, "num_predict": 128, "temperature": 0},
}
result = {}


def infer():
    req = urllib.request.Request("http://127.0.0.1:11434/api/chat",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as r:
        result["body"] = json.loads(r.read().decode())
    result["seconds"] = round(time.perf_counter() - t0, 2)


samples = []
t = threading.Thread(target=infer)
t.start()
while t.is_alive():
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/ps", timeout=3) as r:
            ps = json.loads(r.read().decode())
        samples.append({"t": round(time.perf_counter(), 2),
                        "vram_bytes": [(m["name"], m.get("size_vram"), m.get("context_length"))
                                       for m in ps.get("models", [])]})
    except Exception as exc:
        samples.append({"error": type(exc).__name__})
    time.sleep(0.4)
t.join()
body = result.get("body", {})
out = {
    "samples": samples,
    "inference_seconds": result.get("seconds"),
    "done_reason": body.get("done_reason"),
    "content_len": len((body.get("message") or {}).get("content") or ""),
}
(E / "vram_during_inference.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
print("samples", len(samples), "vram", samples[-1] if samples else None,
      "done_reason", out["done_reason"], "seconds", out["inference_seconds"])
