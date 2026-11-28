"""ITER06 T006: empirical all-layers-offload probe for three models, sequential."""
import json
import math
import os
import pathlib
import re
import socket
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timezone

SERVER = r"<USERPROFILE>\AppData\Local\Microsoft\WinGet\Packages\ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe\llama-server.exe"
MODELS = {
    "embedding": (r"<MODELS_DIR>\Qwen3-Embedding-0.6B-Q8_0.gguf", ["--embedding"]),
    "reranker": (r"<MODELS_DIR>\qwen3-reranker-0.6b-q8_0.gguf", ["--rerank", "--pooling", "rank"]),
    "compactor": (r"<MODELS_DIR>\Compactor-Qwen3.5-4B.Q4_K_M.gguf", ["--reasoning", "off"]),
}
OUT = pathlib.Path(r"<HERMES_ROOT>\cache\scratch\vram_proxy_results.json")


def free(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def rss_mb():
    try:
        text = subprocess.run(["tasklist", "/FI", "IMAGENAME eq llama-server.exe", "/FO", "CSV", "/NH"],
                              capture_output=True, text=True, timeout=5).stdout
        total = 0
        for line in text.splitlines():
            parts = [p.strip().strip('"') for p in line.split('","')]
            if len(parts) >= 5 and parts[0].lower().startswith("llama-server"):
                digits = re.sub(r"[^0-9]", "", parts[4])
                if digits:
                    total += int(digits) / 1024
        return round(total, 1)
    except Exception:
        return None


def post(port, path, payload):
    req = urllib.request.Request(f"http://127.0.0.1:{port}" + path,
                                 data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.loads(r.read().decode("utf-8"))


def probe(name, path, extra, port):
    result = {"model": pathlib.Path(path).name, "offload_layers": 99, "status": "EVIDENCE_PENDING"}
    env = os.environ.copy()
    env["PATH"] = str(pathlib.Path(SERVER).parent) + ";" + r"C:\Windows\System32;C:\Windows"
    cmd = [SERVER, "--host", "127.0.0.1", "--port", str(port), "-m", path,
           "--ctx-size", "2048", "-t", "2", "-tb", "2", "-ngl", "99", "--no-webui"] + extra
    result["argv"] = cmd
    peaks = [0.0]
    stop = threading.Event()

    def sample():
        while not stop.is_set():
            v = rss_mb()
            if v and v > peaks[0]:
                peaks[0] = v
            stop.wait(0.5)

    th = threading.Thread(target=sample, daemon=True)
    th.start()
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        t0 = time.monotonic()
        healthy = False
        for _ in range(120):
            if proc.poll() is not None:
                break
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as r:
                    healthy = r.status == 200
                if healthy:
                    break
            except Exception:
                time.sleep(1)
        result["load_s"] = round(time.monotonic() - t0, 2)
        result["healthy_all_layers_offload"] = healthy
        if healthy:
            t1 = time.monotonic()
            if name == "embedding":
                rr = post(port, "/v1/embeddings", {"model": "x", "input": ["vram probe"]})
                v = rr["data"][0]["embedding"]
                result["inference_ok"] = len(v) == 1024 and all(math.isfinite(x) for x in v)
            elif name == "reranker":
                rr = post(port, "/rerank", {"query": "permiso", "documents": ["permiso autorizado", "gato"]})
                vals = [x["relevance_score"] for x in rr["results"]]
                result["inference_ok"] = len(vals) == 2 and all(math.isfinite(x) for x in vals)
            else:
                rr = post(port, "/v1/chat/completions", {"model": "x", "messages": [
                    {"role": "user", "content": "Devuelve SHA 97ea9e987656bf64234cfc56ee3a89196a3b579d"}],
                    "temperature": 0, "max_tokens": 16})
                result["inference_ok"] = bool(rr.get("choices"))
            result["inference_s"] = round(time.monotonic() - t1, 3)
        result["peak_system_rss_mb"] = peaks[0]
        result["status"] = "VERIFIED_BY_EXECUTOR" if healthy and result.get("inference_ok") else "EVIDENCE_PENDING"
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        stop.set()
        th.join(timeout=2)
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        result["exit_code"] = proc.poll()
    return result


def main():
    gpu = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM | ConvertTo-Json -Compress"],
                         capture_output=True, text=True, timeout=60).stdout
    out = {"generated_at": datetime.now(timezone.utc).isoformat(),
           "classification": "EVIDENCE_PENDING",
           "gpu_cim": gpu.strip()[:1500],
           "vram_telemetry": "NOT_ACCESSIBLE: no per-process VRAM counter for AMD RX 570 in this environment",
           "proxy_definition": "all-layers-offload load + real inference; system RSS measured separately",
           "models": {}}
    for i, (name, (path, extra)) in enumerate(MODELS.items(), 1):
        port = 18100 + i
        if free(port):
            out["models"][name] = probe(name, path, extra, port)
        else:
            out["models"][name] = {"status": "BLOCKED", "reason": "port occupied"}
        print(name, out["models"][name].get("status"), out["models"][name].get("load_s"),
              out["models"][name].get("peak_system_rss_mb"), flush=True)
    out["classification"] = "VERIFIED_BY_EXECUTOR_PROXY" if all(
        m.get("status") == "VERIFIED_BY_EXECUTOR" for m in out["models"].values()) else "EVIDENCE_PENDING"
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("saved", OUT)


if __name__ == "__main__":
    main()
