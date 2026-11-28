"""ITER05 phase 5: real Compactor-Qwen3.5-4B inference + deterministic NSCP baseline."""
import json
import os
import pathlib
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from types import SimpleNamespace

E = pathlib.Path(r"<EVIDENCE_DIR>\2026-11-27_iter05_specialized_engines")
SERVER = r"<USERPROFILE>\AppData\Local\Microsoft\WinGet\Packages\ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe\llama-server.exe"
MODEL = r"<MODELS_DIR>\Compactor-Qwen3.5-4B.Q4_K_M.gguf"
PORT = 18086
SRC = r"<ITER03_WORKTREE>\src"
sys.path.insert(0, SRC)

FACTS = {
    "sha": "97ea9e987656bf64234cfc56ee3a89196a3b579d",
    "branch": "feature/context-compactor",
    "permission": "moli revoco el permiso de push a las 10:00",
    "test": "535 passed, 1 skipped",
    "error": "tests/test_agent_context.py file or directory not found",
    "path": "<EVIDENCE_DIR>",
    "decision": "no modificar main ni Hermes activo",
    "next": "ejecutar ITER05 en worktree aislado",
    "model": "Qwen3-Embedding-0.6B Q8_0",
    "gate": "CHECKMATE exige gates PASS",
    "owner": "THEKEY gobierna, Hermes implementa",
    "vram": "RX 570 4 GB reportados",
}
DISTRACTORS = [
    "El informe anterior afirmaba erroneamente que el permiso de push seguia vigente.",
    "Un resumen viejo indicaba 591 tests passed; dato no reproducible localmente.",
]


def fixture():
    lines = [f"{k}: {v}" for k, v in FACTS.items()] + DISTRACTORS
    lines += [f"nota de seguimiento {i}: se reviso el estado {i} sin cambios relevantes" for i in range(20)]
    return "\n".join(lines)


def post(path, payload, timeout=300):
    req = urllib.request.Request(path, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def score(text):
    found = [k for k, v in FACTS.items() if v in text]
    shas = set(re.findall(r"\b[0-9a-f]{40}\b", text))
    return {"found": found, "missing": [k for k in FACTS if k not in found],
            "count": len(found), "total": len(FACTS),
            "invented_shas": sorted(s for s in shas if s != FACTS["sha"]),
            "chars": len(text)}


def main():
    out = {"generated_at": datetime.now(timezone.utc).isoformat(),
           "model": MODEL, "classification": "EVIDENCE_PENDING",
           "conditions": {}, "baseline": {}, "ollama": {}, "errors": [],
           "fixture_facts": FACTS, "note": "retention by exact substring; no semantic paraphrase credit"}
    fixture_text = fixture()
    out["fixture_chars"] = len(fixture_text)

    # --- deterministic NSCP baseline from validated iter03 source ---
    try:
        from context_compactor import compact_history
        history = [SimpleNamespace(role="system", content="Conserva SHAs, permisos revocados y errores pendientes.")]
        history += [SimpleNamespace(role="user", content=fixture_text)]
        history += [SimpleNamespace(role="assistant", content=f"confirmado %d\n%s" % (i, fixture_text[:400]))
                    for i in range(12)]
        def summarizer(prose):
            keep = []
            for t in prose:
                for k, v in FACTS.items():
                    if v in t.content and v not in keep:
                        keep.append(v)
            return "\n".join(f"HECHO {i+1}: {v}" for i, v in enumerate(keep))
        msgs, report = compact_history(history, num_ctx=700, summarizer=summarizer)
        result_text = "\n".join(m.get("content", "") for m in msgs)
        out["baseline"] = {"module": "context_compactor.py @ 97ea9e9", "report": report,
                           "retention": score(result_text), "result_chars": len(result_text)}
    except Exception as exc:
        out["errors"].append(f"NSCP baseline: {type(exc).__name__}: {exc}")

    # --- specialized compactor via isolated llama-server ---
    if not socket.socket().connect_ex(("127.0.0.1", PORT)) == 0:
        env = os.environ.copy()
        env["PATH"] = str(pathlib.Path(SERVER).parent) + ";" + r"C:\Windows\System32;C:\Windows"
        for k in list(env):
            if k.startswith("LLAMA_ARG_"):
                env.pop(k, None)
        cmd = [SERVER, "--host", "127.0.0.1", "--port", str(PORT), "-m", MODEL,
               "--ctx-size", "8192", "-t", "2", "-tb", "2", "-ngl", "0",
               "--reasoning", "off", "--no-webui"]
        out["command"] = cmd
        log = (E / "logs" / "compactor-server.txt").open("w", encoding="utf-8")
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
            out["server_healthy"] = ok
            if not ok:
                out["server_log_tail"] = (E / "logs" / "compactor-server.txt").read_text(encoding="utf-8", errors="replace")[-2000:]
            else:
                specialized = {
                    "messages": [
                        {"role": "system", "content": (
                            "Eres un compactador de estado de sesion. Conserva literalmente SHAs, rutas, "
                            "permisos revocados, errores pendientes y proximas acciones. No inventes datos. "
                            "Devuelve solo bloques 'HECHO: ...'.")},
                        {"role": "user", "content": "Estado a compactar:\n" + fixture_text},
                    ],
                    "temperature": 0, "max_tokens": 800,
                    "chat_template_kwargs": {"enable_thinking": False},
                }
                generic = {"messages": [{"role": "user", "content": "Resume este estado:\n" + fixture_text}],
                           "temperature": 0, "max_tokens": 800,
                           "chat_template_kwargs": {"enable_thinking": False}}
                for name, payload in (("specialized", specialized), ("generic", generic)):
                    body = dict(payload)
                    body["model"] = "compactor"
                    try:
                        t0 = time.monotonic()
                        rr = post(f"http://127.0.0.1:{PORT}/v1/chat/completions", body, timeout=420)
                        text = rr["choices"][0]["message"].get("content", "") or ""
                        out["conditions"][name] = {
                            "latency_s": round(time.monotonic() - t0, 3),
                            "usage": rr.get("usage"),
                            "retention": score(text),
                            "output_chars": len(text),
                            "output_head": text[:1500],
                            "reasoning_content": (rr["choices"][0]["message"].get("reasoning_content") or "")[:300],
                        }
                    except Exception as exc:
                        out["conditions"][name] = {"error": f"{type(exc).__name__}: {exc}"}
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            log.close()
    else:
        out["errors"].append("port 18086 occupied; compactor not executed")

    # --- Ollama original Qwen3.5 4B (sequential, existing service, no config changes) ---
    try:
        tags = post("http://127.0.0.1:11434/api/tags", {}, timeout=20)
        names = [m.get("name") for m in tags.get("models", [])]
        out["ollama"]["available_models"] = names
        target = next((n for n in names if n and n.startswith("qwen3.5:4b")), None)
        if target:
            t0 = time.monotonic()
            rr = post("http://127.0.0.1:11434/api/chat", {
                "model": target,
                "messages": specialized["messages"],
                "stream": False, "options": {"temperature": 0, "num_predict": 800}}, timeout=420)
            text = rr.get("message", {}).get("content", "")
            out["ollama"] = {"model": target, "latency_s": round(time.monotonic() - t0, 3),
                             "retention": score(text), "output_chars": len(text), "output_head": text[:1500]}
        else:
            out["ollama"]["error"] = "qwen3.5:4b not in /api/tags"
    except Exception as exc:
        out["ollama"]["error"] = f"{type(exc).__name__}: {exc}"

    good = bool(out["conditions"].get("specialized", {}).get("retention", {}).get("count", 0) >= 8)
    out["classification"] = "VERIFIED_BY_ME" if good else "EVIDENCE_PENDING"
    (E / "COMPACTOR_BENCHMARK.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"baseline": out["baseline"].get("retention"),
                      "specialized": out["conditions"].get("specialized", {}).get("retention"),
                      "generic": out["conditions"].get("generic", {}).get("retention"),
                      "ollama": out["ollama"].get("retention", out["ollama"].get("error")),
                      "errors": out["errors"]}, ensure_ascii=False)[:2500])


if __name__ == "__main__":
    main()
