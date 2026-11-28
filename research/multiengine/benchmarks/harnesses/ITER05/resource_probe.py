"""ITER05 resource probe: real load time and working-set peak for the 4B compactor."""
import json
import os
import pathlib
import re
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timezone

E = pathlib.Path(r"<EVIDENCE_DIR>\2026-11-27_iter05_specialized_engines")
SERVER = r"<USERPROFILE>\AppData\Local\Microsoft\WinGet\Packages\ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe\llama-server.exe"
MODEL = r"<MODELS_DIR>\Compactor-Qwen3.5-4B.Q4_K_M.gguf"
PORT = 18090


def ws_mb():
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq llama-server.exe", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, timeout=5).stdout
        total = 0
        for line in out.splitlines():
            parts = [p.strip().strip('"') for p in line.split('","')]
            if len(parts) >= 5 and parts[0].lower().startswith("llama-server"):
                digits = re.sub(r"[^0-9]", "", parts[4])
                if digits:
                    total += int(digits) / 1024
        return round(total, 1)
    except Exception:
        return None


def main():
    out = {"generated_at": datetime.now(timezone.utc).isoformat(),
           "classification": "EVIDENCE_PENDING", "method": "tasklist WorkingSet polling every 0.5 s",
           "model": MODEL, "gpu_offload_layers": 0, "errors": []}
    env = os.environ.copy()
    env["PATH"] = str(pathlib.Path(SERVER).parent) + ";" + r"C:\Windows\System32;C:\Windows"
    cmd = [SERVER, "--host", "127.0.0.1", "--port", str(PORT), "-m", MODEL,
           "--ctx-size", "8192", "-t", "2", "-tb", "2", "-ngl", "0",
           "--reasoning", "off", "--no-webui"]
    log = (E / "logs" / "resource-compactor-server.txt").open("w", encoding="utf-8")
    proc = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
    peaks = {"load": 0.0, "inference": 0.0}
    stop_flag = threading.Event()

    def sampler(key):
        while not stop_flag.is_set():
            v = ws_mb()
            if v and v > peaks[key]:
                peaks[key] = v
            stop_flag.wait(0.5)

    t = threading.Thread(target=sampler, args=("load",), daemon=True)
    t.start()
    try:
        t0 = time.monotonic()
        ok = False
        for _ in range(180):
            if proc.poll() is not None:
                break
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=3) as r:
                    ok = r.status == 200
                if ok:
                    break
            except Exception:
                time.sleep(1)
        out["load_s"] = round(time.monotonic() - t0, 2)
        out["healthy"] = ok
        out["peak_rss_mb_load"] = peaks["load"]
        if ok:
            stop_flag.set()
            t.join(timeout=2)
            stop_flag.clear()
            t2 = threading.Thread(target=sampler, args=("inference",), daemon=True)
            t2.start()
            payload = json.dumps({"model": "x", "messages": [
                {"role": "system", "content": "Resume conservando SHAs."},
                {"role": "user", "content": "SHA 97ea9e987656bf64234cfc56ee3a89196a3b579d. Resumen breve."}],
                "temperature": 0, "max_tokens": 64}).encode()
            req = urllib.request.Request(f"http://127.0.0.1:{PORT}/v1/chat/completions", data=payload,
                                         headers={"Content-Type": "application/json"})
            t1 = time.monotonic()
            with urllib.request.urlopen(req, timeout=300) as r:
                rr = json.loads(r.read().decode())
            out["inference_s_64tok"] = round(time.monotonic() - t1, 3)
            out["usage"] = rr.get("usage")
            stop_flag.set()
            t2.join(timeout=2)
            out["peak_rss_mb_inference"] = peaks["inference"]
        out["classification"] = "VERIFIED_BY_ME" if ok and peaks["load"] > 0 else "EVIDENCE_PENDING"
    except Exception as exc:
        out["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        stop_flag.set()
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        log.close()
    (E / "RESOURCE_BENCHMARK.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False)[:900])


if __name__ == "__main__":
    main()
