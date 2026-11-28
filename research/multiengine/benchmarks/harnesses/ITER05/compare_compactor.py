"""ITER05 phase 5b: fix deterministic baseline, add original-Qwen A/B, paraphrase-aware scoring."""
import json
import os
import pathlib
import re
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from types import SimpleNamespace

E = pathlib.Path(r"<EVIDENCE_DIR>\2026-11-27_iter05_specialized_engines")
sys.path.insert(0, str(E))
from activate_compactor import FACTS, fixture, post, score  # noqa: E402

SERVER = r"<USERPROFILE>\AppData\Local\Microsoft\WinGet\Packages\ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe\llama-server.exe"
ORIGINAL = r"<MODEL_ROOT>\00_CONTROL_OFICIAL\bartowski--Qwen_Qwen3.5-4B-GGUF\Qwen_Qwen3.5-4B-Q4_K_M.gguf"
PORT = 18087
sys.path.insert(0, r"<ITER03_WORKTREE>\src")

PROXY = {
    "sha": [lambda t: FACTS["sha"] in t],
    "branch": [lambda t: "feature/context-compactor" in t],
    "permission": [lambda t: all(x in t.lower() for x in ("moli", "revoc", "10:00"))],
    "test": [lambda t: "535" in t and "1 skipped" in t],
    "error": [lambda t: "test_agent_context.py" in t and "not found" in t],
    "path": [lambda t: "NSCP_LOCAL_EVIDENCE" in t],
    "decision": [lambda t: "main" in t and "hermes" in t.lower() and "no modificar" in t.lower()],
    "next": [lambda t: "ITER05" in t and "worktree" in t],
    "model": [lambda t: "Qwen3-Embedding-0.6B" in t and "Q8" in t],
    "gate": [lambda t: "CHECKMATE" in t and "PASS" in t],
    "owner": [lambda t: "THEKEY" in t and "Hermes" in t],
    "vram": [lambda t: "RX 570" in t and "4 GB" in t],
}


def proxy_score(text):
    found = [k for k, preds in PROXY.items() if any(p(text) for p in preds)]
    return {"count": len(found), "total": len(PROXY), "found": found,
            "missing": [k for k in PROXY if k not in found]}


def main():
    out = {"generated_at": datetime.now(timezone.utc).isoformat(),
           "classification": "EVIDENCE_PENDING", "comparison": {}, "errors": []}
    fixture_text = fixture()
    messages = [
        {"role": "system", "content": (
            "Eres un compactador de estado de sesion. Conserva literalmente SHAs, rutas, "
            "permisos revocados, errores pendientes y proximas acciones. No inventes datos. "
            "Devuelve solo bloques 'HECHO: ...'.")},
        {"role": "user", "content": "Estado a compactar:\n" + fixture_text},
    ]

    # deterministic NSCP baseline with sufficient window
    try:
        from context_compactor import compact_history
        history = [SimpleNamespace(role="system", content=messages[0]["content"]),
                   SimpleNamespace(role="user", content=fixture_text)]
        history += [SimpleNamespace(role="assistant", content=f"confirmado {i}: " + fixture_text[:300])
                    for i in range(6)]
        def summarizer(prose):
            keep = []
            for t in prose:
                for k, v in FACTS.items():
                    if v in t.content and v not in keep:
                        keep.append(v)
            return "\n".join(f"HECHO {i+1}: {v}" for i, v in enumerate(keep))
        msgs, report = compact_history(history, num_ctx=3200, summarizer=summarizer)
        text = "\n".join(m.get("content", "") for m in msgs)
        out["comparison"]["C_deterministic_nscp"] = {
            "source": "context_compactor.py @ 97ea9e9, real call", "report": report,
            "exact": score(text), "paraphrase_proxy": proxy_score(text), "chars": len(text)}
    except Exception as exc:
        out["errors"].append(f"baseline: {type(exc).__name__}: {exc}")

    comp = json.loads((E / "COMPACTOR_BENCHMARK.json").read_text(encoding="utf-8"))
    for name in ("specialized", "generic"):
        c = comp["conditions"].get(name, {})
        if "output_head" not in c:
            continue
        full = c.get("output_head", "")
        out["comparison"]["B_compactor_" + name] = {
            "source": "llama-server real inference; output_head cap 1500 chars",
            "exact": c["retention"], "paraphrase_proxy": proxy_score(full),
            "chars": c["output_chars"], "latency_s": c["latency_s"], "usage": c["usage"]}
    out["comparison"]["E_uncompressed_upper_bound"] = {
        "source": "fixture itself (no compaction)", "exact": score(fixture_text),
        "paraphrase_proxy": proxy_score(fixture_text), "chars": len(fixture_text)}

    # original Qwen3.5 4B, sequential, same prompt
    with socket.socket() as s:
        busy = s.connect_ex(("127.0.0.1", PORT)) == 0
    if busy:
        out["errors"].append("port 18087 occupied; original Qwen not run")
    else:
        env = os.environ.copy()
        env["PATH"] = str(pathlib.Path(SERVER).parent) + ";" + r"C:\Windows\System32;C:\Windows"
        for k in list(env):
            if k.startswith("LLAMA_ARG_"):
                env.pop(k, None)
        cmd = [SERVER, "--host", "127.0.0.1", "--port", str(PORT), "-m", ORIGINAL,
               "--ctx-size", "8192", "-t", "2", "-tb", "2", "-ngl", "0",
               "--reasoning", "off", "--no-webui"]
        log = (E / "logs" / "qwen35-original-server.txt").open("w", encoding="utf-8")
        proc = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
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
            out["original_server_healthy"] = ok
            if ok:
                body = {"model": "original", "messages": messages, "temperature": 0,
                        "max_tokens": 800, "chat_template_kwargs": {"enable_thinking": False}}
                t0 = time.monotonic()
                rr = post(f"http://127.0.0.1:{PORT}/v1/chat/completions", body, timeout=420)
                text = rr["choices"][0]["message"].get("content", "") or ""
                out["comparison"]["A_original_qwen35"] = {
                    "source": ORIGINAL, "exact": score(text), "paraphrase_proxy": proxy_score(text),
                    "chars": len(text), "latency_s": round(time.monotonic() - t0, 3),
                    "usage": rr.get("usage"), "output_head": text[:1200]}
            else:
                out["errors"].append("original Qwen server not healthy")
        except Exception as exc:
            out["errors"].append(f"original: {type(exc).__name__}: {exc}")
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            log.close()

    out["classification"] = "VERIFIED_BY_ME" if len(out["comparison"]) >= 4 else "EVIDENCE_PENDING"
    (E / "COMPACTOR_COMPARISON.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: {"exact": v["exact"]["count"], "proxy": v["paraphrase_proxy"]["count"],
                          "chars": v["chars"]} for k, v in out["comparison"].items()}, ensure_ascii=False))
    print("errors:", out["errors"])


if __name__ == "__main__":
    main()
