"""ITER05 phase 3b: embedding determinism, semantic contrast, batch scaling, CPU vs Vulkan."""
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


def free(port):
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def post(port, path, payload, timeout=120):
    req = urllib.request.Request(f"http://127.0.0.1:{port}" + path,
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def start(port, gpu, logname):
    env = os.environ.copy()
    env["PATH"] = str(pathlib.Path(SERVER).parent) + ";" + r"C:\Windows\System32;C:\Windows"
    for k in list(env):
        if k.startswith("LLAMA_ARG_"):
            env.pop(k, None)
    cmd = [SERVER, "--host", "127.0.0.1", "--port", str(port), "-m", MODEL,
           "--embedding", "--ctx-size", "512", "-t", "2", "-tb", "2",
           "-ngl", "99" if gpu else "0", "--no-webui"]
    log = E / "logs" / logname
    fh = log.open("w", encoding="utf-8")
    proc = subprocess.Popen(cmd, env=env, stdout=fh, stderr=subprocess.STDOUT)
    t0 = time.monotonic()
    ok = False
    for _ in range(120):
        if proc.poll() is not None:
            break
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as r:
                if r.status == 200:
                    ok = True
                    break
        except Exception:
            time.sleep(1)
    return proc, fh, cmd, round(time.monotonic() - t0, 2), ok


def stop(proc, fh):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    fh.close()


def cos(a, b):
    return sum(x * y for x, y in zip(a, b))


def maxdiff(a, b):
    return max(abs(x - y) for x, y in zip(a, b))


def main():
    out = {"generated_at": datetime.now(timezone.utc).isoformat(),
           "model": MODEL, "classification": "EVIDENCE_PENDING",
           "pairs": {}, "determinism": {}, "scaling": {}, "vulkan": {}, "errors": []}

    if free(18082):
        proc, fh, cmd, boot, ok = start(18082, False, "embedding-deep-cpu.txt")
        out["cpu_boot_s"] = boot
        try:
            if not ok:
                out["errors"].append("CPU server not healthy")
            else:
                single = "el gato duerme"
                vs = []
                for _ in range(3):
                    r = post(18082, "/v1/embeddings", {"model": "x", "input": [single]})
                    vs.append(r["data"][0]["embedding"])
                out["determinism"]["single_request_maxdiff_01"] = maxdiff(vs[0], vs[1])
                out["determinism"]["single_request_maxdiff_02"] = maxdiff(vs[1], vs[2])
                out["determinism"]["single_request_cos_01"] = round(cos(vs[0], vs[1]), 8)
                out["determinism"]["single_request_identical"] = vs[0] == vs[1] == vs[2]

                texts = [
                    "el gato duerme", "un felino duerme", "la compresion semanticura de contexto",
                    "the cat sleeps", "el permiso fue revocado a las 10:00",
                    "el permiso sigue vigente", "ñandú y pingüino", "quantum chromodynamics",
                    "SHA 97ea9e987656bf64234cfc56ee3a89196a3b579d", "error en tests/test_agent_context.py",
                ]
                pairs = [(0, 1, "sinonimos_es"), (0, 3, "es_en_gato"), (0, 7, "unrelated"),
                         (4, 5, "revocado_vs_vigente"), (8, 9, "sha_vs_error")]
                for n in (1, 4, 16, 32):
                    batch = (texts * ((n // len(texts)) + 1))[:n]
                    t0 = time.monotonic()
                    r = post(18082, "/v1/embeddings", {"model": "x", "input": batch})
                    dt = round(time.monotonic() - t0, 3)
                    v = [d["embedding"] for d in sorted(r["data"], key=lambda d: d["index"])]
                    out["scaling"][str(n)] = {"latency_s": dt, "count": len(v),
                                              "dim": len(v[0]) if v else None,
                                              "finite": all(math.isfinite(x) for z in v for x in z)}
                    if n == 16:
                        for i, j, name in pairs:
                            out["pairs"][name] = round(cos(v[i], v[j]), 6)
                        out["determinism"]["batch_vs_single_maxdiff"] = maxdiff(v[0], vs[0])
                        out["determinism"]["batch_vs_single_cos"] = round(cos(v[0], vs[0]), 8)
        finally:
            stop(proc, fh)
    else:
        out["errors"].append("port 18082 occupied")

    if free(18083):
        proc, fh, cmd, boot, ok = start(18083, True, "embedding-deep-vulkan.txt")
        out["vulkan"] = {"boot_s": boot, "healthy": ok, "argv": cmd}
        try:
            if ok:
                t0 = time.monotonic()
                r = post(18083, "/v1/embeddings", {"model": "x", "input": ["vulkan probe"]})
                v = r["data"][0]["embedding"]
                out["vulkan"].update({"latency_s": round(time.monotonic() - t0, 3),
                                      "dim": len(v), "finite": all(math.isfinite(x) for x in v),
                                      "norm": round(math.sqrt(cos(v, v)), 6)})
        except Exception as exc:
            out["vulkan"]["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            stop(proc, fh)
    else:
        out["vulkan"]["error"] = "port 18083 occupied"

    out["classification"] = "VERIFIED_BY_ME" if out["pairs"] and not out["errors"] else "EVIDENCE_PENDING"
    (E / "EMBEDDING_BENCHMARK_DEEP.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("determinism", "pairs", "scaling", "vulkan")}, ensure_ascii=False)[:2500])


if __name__ == "__main__":
    main()
