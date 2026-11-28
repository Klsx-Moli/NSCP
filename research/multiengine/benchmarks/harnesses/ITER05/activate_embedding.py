"""ITER05 phase 3: real embedding vectors from Qwen3-Embedding-0.6B Q8_0 via isolated llama-server.

One model at a time. All env changes are process-local. Server is always terminated.
"""
import json
import math
import os
import pathlib
import socket
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

E = pathlib.Path(r"<EVIDENCE_DIR>\2026-11-27_iter05_specialized_engines")
SERVER = r"<USERPROFILE>\AppData\Local\Microsoft\WinGet\Packages\ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe\llama-server.exe"
MODEL = r"<MODELS_DIR>\Qwen3-Embedding-0.6B-Q8_0.gguf"
PORT = 18081
BASE = f"http://127.0.0.1:{PORT}"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", PORT))
        return True


def post(path, payload, timeout=60):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def get(path, timeout=10):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "replace")[:200]


def cos(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def main():
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_path": MODEL,
        "runtime": "llama.cpp b9947 (3de7dd4c8) WinGet ggml.llamacpp",
        "port": PORT,
        "isolation": "process-local PATH override; no global env/PATH/Ollama/Hermes changes",
        "classification": "EVIDENCE_PENDING",
        "server": {},
        "checks": {},
        "errors": [],
    }
    if not free_port():
        result["errors"].append(f"port {PORT} already in use; refusing to start another server")
        (E / "EMBEDDING_BENCHMARK.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print("BLOCKED: port in use")
        return
    env = os.environ.copy()
    env["PATH"] = str(pathlib.Path(SERVER).parent) + ";" + r"C:\Windows\System32;C:\Windows"
    for k in list(env):
        if k.startswith("LLAMA_ARG_"):
            env.pop(k, None)
    cmd = [SERVER, "--host", "127.0.0.1", "--port", str(PORT),
           "-m", MODEL, "--embedding", "--ctx-size", "512",
           "-t", "2", "-tb", "2", "-ngl", "0", "--no-webui"]
    result["server"]["command"] = cmd
    log_path = E / "logs" / "embedding-server.txt"
    proc = None
    try:
        with log_path.open("w", encoding="utf-8") as log:
            t0 = time.monotonic()
            proc = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
            result["server"]["pid"] = proc.pid
            healthy = False
            for _ in range(120):
                if proc.poll() is not None:
                    break
                try:
                    status, _ = get("/health", timeout=3)
                    if status == 200:
                        healthy = True
                        break
                except Exception:
                    time.sleep(1)
            result["server"]["startup_s"] = round(time.monotonic() - t0, 2)
            result["server"]["healthy"] = healthy
            result["server"]["exit_code_during_startup"] = proc.poll()
            if not healthy:
                tail = log_path.read_text(encoding="utf-8", errors="replace")[-3000:]
                result["errors"].append("server did not become healthy; log tail saved")
                result["server"]["log_tail"] = tail
                print("SERVER NOT HEALTHY", tail[-500:])
                return
            texts = [
                "el gato duerme", "un felino duerme", "la dirección exacta del archivo es <REPO_ROOT>",
                "the cat sleeps", "ñandú y pingüino", "quantum chromodynamics",
                "el gato duerme",
            ]
            payload = {"model": "iter05-embed", "input": texts}
            t1 = time.monotonic()
            resp = post("/v1/embeddings", payload, timeout=120)
            latency = round(time.monotonic() - t1, 3)
            data = sorted(resp.get("data", []), key=lambda x: x.get("index", 0))
            vectors = [d["embedding"] for d in data]
            result["checks"]["endpoint"] = "/v1/embeddings"
            result["checks"]["latency_s"] = latency
            result["checks"]["usage"] = resp.get("usage")
            result["checks"]["count"] = len(vectors)
            result["checks"]["dimension"] = len(vectors[0]) if vectors else None
            result["checks"]["all_finite"] = all(math.isfinite(x) for v in vectors for x in v) if vectors else False
            result["checks"]["all_nonempty"] = all(len(v) > 0 for v in vectors) if vectors else False
            result["checks"]["norms"] = [round(math.sqrt(sum(x * x for x in v)), 6) for v in vectors]
            result["checks"]["repeat_identical"] = (vectors[0] == vectors[-1]) if len(vectors) == len(texts) else None
            result["checks"]["cos_synonyms_es"] = round(cos(vectors[0], vectors[1]), 6) if len(vectors) > 1 else None
            result["checks"]["cos_cat_en"] = round(cos(vectors[0], vectors[3]), 6) if len(vectors) > 3 else None
            result["checks"]["cos_unrelated"] = round(cos(vectors[0], vectors[5]), 6) if len(vectors) > 5 else None
            result["checks"]["cos_unicode"] = round(cos(vectors[4], vectors[5]), 6) if len(vectors) > 5 else None
            result["checks"]["texts"] = texts
            # vector values are not saved in full; only aggregate statistics
            result["checks"]["first_vector_sample"] = [round(x, 6) for x in vectors[0][:8]] if vectors else []
            ok = (result["checks"]["all_finite"] and result["checks"]["all_nonempty"]
                  and result["checks"]["count"] == len(texts) and result["checks"]["repeat_identical"])
            result["classification"] = "VERIFIED_BY_ME" if ok else "EVIDENCE_PENDING"
            result["verdict"] = "REAL_VECTORS" if ok else "INCOMPLETE"
            print(json.dumps({k: result["checks"][k] for k in
                              ("count", "dimension", "all_finite", "repeat_identical", "norms",
                               "cos_synonyms_es", "cos_cat_en", "cos_unrelated", "latency_s")}, ensure_ascii=False))
    except Exception as exc:
        result["errors"].append(f"{type(exc).__name__}: {exc}")
        print("ERROR", type(exc).__name__, str(exc)[:300])
    finally:
        if proc is not None:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            result["server"]["final_exit_code"] = proc.poll()
        (E / "EMBEDDING_BENCHMARK.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
