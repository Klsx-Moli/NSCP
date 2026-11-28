"""Resolve the first-run duplicate-vector anomaly with the exact original 7-text batch."""
import json
import math
import os
import pathlib
import socket
import subprocess
import time
import urllib.request
from datetime import datetime, timezone

E = pathlib.Path(r"<EVIDENCE_DIR>\2026-11-27_iter05_specialized_engines")
SERVER = r"<USERPROFILE>\AppData\Local\Microsoft\WinGet\Packages\ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe\llama-server.exe"
MODEL = r"<MODELS_DIR>\Qwen3-Embedding-0.6B-Q8_0.gguf"
PORT = 18084
TEXTS = ["el gato duerme", "un felino duerme",
         "la dirección exacta del archivo es <REPO_ROOT>",
         "the cat sleeps", "ñandú y pingüino", "quantum chromodynamics", "el gato duerme"]


def post(path, payload):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}" + path,
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def main():
    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "classification": "EVIDENCE_PENDING"}
    env = os.environ.copy()
    env["PATH"] = str(pathlib.Path(SERVER).parent) + ";" + r"C:\Windows\System32;C:\Windows"
    cmd = [SERVER, "--host", "127.0.0.1", "--port", str(PORT), "-m", MODEL, "--embedding",
           "--ctx-size", "512", "-t", "2", "-tb", "2", "-ngl", "0", "--no-webui"]
    log = (E / "logs" / "embedding-positional-probe.txt").open("w", encoding="utf-8")
    proc = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        ok = False
        for _ in range(120):
            if proc.poll() is not None:
                break
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=3) as r:
                    ok = r.status == 200
                if ok:
                    break
            except Exception:
                time.sleep(1)
        out["healthy"] = ok
        if ok:
            v = [d["embedding"] for d in sorted(post("/v1/embeddings", {"model": "x", "input": TEXTS})["data"],
                                                key=lambda d: d["index"])]
            a, b = v[0], v[6]
            out["duplicate_at_0_and_6"] = {
                "max_abs_diff": max(abs(x - y) for x, y in zip(a, b)),
                "cosine": round(sum(x * y for x, y in zip(a, b)), 8),
                "identical": a == b,
            }
            v2 = [d["embedding"] for d in sorted(post("/v1/embeddings", {"model": "x", "input": ["el gato duerme", "el gato duerme"]})["data"],
                                                 key=lambda d: d["index"])]
            out["duplicate_only_two"] = {
                "max_abs_diff": max(abs(x - y) for x, y in zip(v2[0], v2[1])),
                "cosine": round(sum(x * y for x, y in zip(v2[0], v2[1])), 8),
                "identical": v2[0] == v2[1],
            }
            out["classification"] = "VERIFIED_BY_ME"
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        log.close()
    (E / "EMBEDDING_POSITIONAL_PROBE.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
