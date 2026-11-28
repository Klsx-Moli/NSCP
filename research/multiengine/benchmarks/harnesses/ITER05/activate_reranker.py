"""ITER05 phase 4: real Qwen3-Reranker-0.6B scores via isolated llama-server /rerank endpoint."""
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
MODEL = r"<MODELS_DIR>\qwen3-reranker-0.6b-q8_0.gguf"
PORT = 18085


def free():
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", PORT))
            return True
        except OSError:
            return False


def post(path, payload, timeout=180):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}" + path,
                                 data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def to_scores(items):
    vals = []
    for x in items:
        if isinstance(x, dict):
            v = x.get("relevance_score", x.get("score"))
        else:
            v = x
        vals.append(float(v))
    return vals


def main():
    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "model": MODEL,
           "runtime": "llama.cpp b9947 --rerank --pooling rank", "classification": "EVIDENCE_PENDING",
           "endpoint_attempts": [], "cases": {}, "scaling": {}, "errors": []}
    if not free():
        out["errors"].append(f"port {PORT} occupied")
        (E / "RERANKER_BENCHMARK.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print("BLOCKED port")
        return
    env = os.environ.copy()
    env["PATH"] = str(pathlib.Path(SERVER).parent) + ";" + r"C:\Windows\System32;C:\Windows"
    for k in list(env):
        if k.startswith("LLAMA_ARG_"):
            env.pop(k, None)
    cmd = [SERVER, "--host", "127.0.0.1", "--port", str(PORT), "-m", MODEL,
           "--rerank", "--pooling", "rank", "--ctx-size", "4096", "-t", "2", "-tb", "2",
           "-ngl", "0", "--no-webui"]
    out["command"] = cmd
    log = (E / "logs" / "reranker-server.txt").open("w", encoding="utf-8")
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
        if not ok:
            out["server_log_tail"] = (E / "logs" / "reranker-server.txt").read_text(encoding="utf-8", errors="replace")[-3000:]
        else:
            query = "¿Quién autorizó la fusión?"
            docs = ["moli autorizó la fusión", "moli revocó la autorización", "el gato duerme en el sofá"]
            endpoint = None
            for path, payload in (
                ("/rerank", {"query": query, "documents": docs}),
                ("/v1/rerank", {"model": "x", "query": query, "documents": docs}),
                ("/rerank", {"query": query, "passages": docs}),
            ):
                try:
                    resp = post(path, payload, timeout=60)
                    out["endpoint_attempts"].append({"path": path, "keys": list(payload), "ok": True,
                                                     "response_keys": list(resp) if isinstance(resp, dict) else type(resp).__name__})
                    endpoint = (path, tuple(payload))
                    out["first_response"] = json.dumps(resp, ensure_ascii=False)[:600]
                    break
                except Exception as exc:
                    out["endpoint_attempts"].append({"path": path, "keys": list(payload), "ok": False,
                                                     "error": f"{type(exc).__name__}: {str(exc)[:160]}"})
            if endpoint is None:
                out["errors"].append("no working rerank endpoint")
            else:
                path, keys = endpoint

                def rank(q, ds):
                    payload = {"query": q, "documents" if "documents" in keys else "passages": ds}
                    if path == "/v1/rerank":
                        payload["model"] = "x"
                    r = post(path, payload, timeout=180)
                    if isinstance(r, list):
                        return r
                    for k in ("results", "scores", "data"):
                        if k in r:
                            return r[k]
                    return r

                cases = {
                    "authorization": ("¿Quién autorizó la fusión?", [
                        "moli autorizó la fusión", "moli revocó la autorización", "el gato duerme en el sofá"]),
                    "negation": ("el servidor está apagado", [
                        "el servidor está apagado", "el servidor no está apagado", "se instaló Python 3.12"]),
                    "cross_lingual": ("permiso revocado para hacer push", [
                        "push permission was revoked", "push permission is still valid", "the cat sleeps"]),
                    "code_context": ("¿qué error aparece en el test?", [
                        "tests/test_agent_context.py: file or directory not found",
                        "535 passed, 1 skipped", "python -m ruff check PASS"]),
                }
                for name, (q, ds) in cases.items():
                    t0 = time.monotonic()
                    r1 = rank(q, ds)
                    lat = round(time.monotonic() - t0, 3)
                    r2 = rank(q, ds)
                    scores1 = to_scores(r1)
                    scores2 = to_scores(r2)
                    out["cases"][name] = {
                        "query": q, "documents": ds,
                        "scores": [round(s, 6) for s in scores1],
                        "scores_second": [round(s, 6) for s in scores2],
                        "finite": all(math.isfinite(s) for s in scores1 + scores2),
                        "repeat_identical": scores1 == scores2,
                        "max_repeat_diff": max(abs(a - b) for a, b in zip(scores1, scores2)),
                        "best_index": max(range(len(scores1)), key=lambda i: scores1[i]),
                        "latency_s": lat,
                        "raw_first": json.dumps(r1, ensure_ascii=False)[:400],
                    }
                for n in (4, 8, 16, 32, 64):
                    ds = [f"candidato {i}: {'permiso autorizado' if i == n - 1 else 'texto irrelevante'}" for i in range(n)]
                    t0 = time.monotonic()
                    r = rank("permiso autorizado", ds)
                    scores = to_scores(r)
                    out["scaling"][str(n)] = {
                        "latency_s": round(time.monotonic() - t0, 3), "count": len(scores),
                        "finite": all(math.isfinite(s) for s in scores),
                        "best_index": max(range(len(scores)), key=lambda i: scores[i]) if scores else None,
                    }
                good = (out["cases"].get("authorization", {}).get("best_index") == 0
                        and out["cases"].get("negation", {}).get("best_index") == 0
                        and all(c["finite"] for c in out["cases"].values()))
                out["classification"] = "VERIFIED_BY_ME" if good else "EVIDENCE_PENDING"
    except Exception as exc:
        out["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        out["final_exit_code"] = proc.poll()
        log.close()
    (E / "RERANKER_BENCHMARK.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"healthy": out.get("healthy"), "endpoints": out["endpoint_attempts"],
                      "cases": {k: {"scores": v["scores"], "best": v["best_index"],
                                    "repeat": v["repeat_identical"]} for k, v in out["cases"].items()},
                      "scaling": out["scaling"], "errors": out["errors"]}, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main()
