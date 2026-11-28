"""ITER05 phase 7: bounded multi-engine differential with preregistered gold labels."""
import json
import math
import os
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from types import SimpleNamespace

E = pathlib.Path(r"<EVIDENCE_DIR>\2026-11-27_iter05_specialized_engines")
sys.path.insert(0, str(E / "MEMORY_INDEX_PROTOTYPE"))
from memory_index import MemoryIndex  # noqa: E402

SERVER = r"<USERPROFILE>\AppData\Local\Microsoft\WinGet\Packages\ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe\llama-server.exe"
EMB = r"<MODELS_DIR>\Qwen3-Embedding-0.6B-Q8_0.gguf"
RER = r"<MODELS_DIR>\qwen3-reranker-0.6b-q8_0.gguf"
CMP = r"<MODELS_DIR>\Compactor-Qwen3.5-4B.Q4_K_M.gguf"

DOCS = [
    "d00: moli revoco el permiso de push a las 10:00",
    "d01: 535 passed, 1 skipped en la suite de NSCP",
    "d02: Qwen3-Embedding-0.6B devuelve vectores de 1024 dimensiones",
    "d03: el reranker Qwen3 orderna con relevance_score",
    "d04: Compactor-Qwen3.5-4B conserva SHAs y revocaciones",
    "d05: error tests/test_agent_context.py file or directory not found",
    "d06: ruff PASS con --select E,F,W --ignore E501",
    "d07: Ollama no responde en este entorno aislado",
    "d08: worktree aislado en 97ea9e987656bf64234cfc56ee3a89196a3b579d",
    "d09: permiso de push autorizado para main",
    "d10: CHECKMATE exige gates PASS antes de cerrar",
    "d11: THEKEY gobierna, Hermes implementa",
    "d12: RX 570 con 4 GB de VRAM reportados",
    "d13: temperatura 0 y salida acotada en el compactor",
    "d14: memoria vectorial SQLite con dedupe por identidad",
    "d15: MTU red y DNS del router sin cambios",
]
QUERIES = [
    ("q1", "quien revoco el permiso de push a las 10:00", "d00"),
    ("q2", "error file or directory not found en el test", "d05"),
    ("q3", "vector de 1024 dimensiones del embedding", "d02"),
]
KS = (4, 8, 16, 32)


def free(p):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", p)) != 0


def post(port, path, payload, timeout=240):
    req = urllib.request.Request(f"http://127.0.0.1:{port}" + path,
                                 data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def boot(port, model, extra, logname):
    env = os.environ.copy()
    env["PATH"] = str(pathlib.Path(SERVER).parent) + ";" + r"C:\Windows\System32;C:\Windows"
    cmd = [SERVER, "--host", "127.0.0.1", "--port", str(port), "-m", model,
           "--ctx-size", "2048", "-t", "2", "-tb", "2", "-ngl", "0", "--no-webui"] + extra
    log = (E / "logs" / logname).open("w", encoding="utf-8")
    proc = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
    ok = False
    for _ in range(180):
        if proc.poll() is not None:
            break
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as r:
                ok = r.status == 200
            if ok:
                break
        except Exception:
            time.sleep(1)
    return proc, log, ok


def stop(proc, log):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    log.close()


def metrics(ranked, gold, k):
    gold_pos = ranked.index(gold) + 1 if gold in ranked else 0
    return {"recall_at_k": 1 if gold_pos and gold_pos <= k else 0,
            "selection_recall": 1 if gold_pos == 1 else 0,
            "precision_at_k": (1 / k) if gold_pos else 0,
            "mrr": (1 / gold_pos) if gold_pos else 0,
            "ndcg": (1 / math.log2(gold_pos + 1)) if gold_pos else 0,
            "abstention": 0 if ranked else 1,
            "gold_position": gold_pos}


def main():
    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "sha": "97ea9e9",
           "preregistered": {"queries": QUERIES, "ks": list(KS), "docs": DOCS},
           "classification": "EVIDENCE_PENDING", "routes": {}, "errors": []}
    db = E / "MULTIENGINE_DIFFERENTIAL" / "index.sqlite3"
    db.parent.mkdir(exist_ok=True)
    if db.exists():
        db.unlink()
    idx = MemoryIndex(db, "embedding@06507c7b")

    # embeddings route (real server)
    if not free(18091):
        out["errors"].append("port 18091 busy")
        (E / "MULTIENGINE_DIFFERENTIAL.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        return
    proc, log, ok = boot(18091, EMB, ["--embedding"], "diff-embedding-server.txt")
    evecs = qvecs = None
    try:
        if not ok:
            raise RuntimeError("embedding server not healthy")
        r = post(18091, "/v1/embeddings", {"model": "x", "input": DOCS + [q[1] for q in QUERIES]}, timeout=180)
        allv = [d["embedding"] for d in sorted(r["data"], key=lambda d: d["index"])]
        evecs, qvecs = allv[:len(DOCS)], allv[len(DOCS):]
        for d, v in zip(DOCS, evecs):
            did = d.split(":", 1)[0]
            idx.add(session_id="diff", episode_id="e", message_id=did, role="user",
                    source_sha256="sha", text=d, vector=v)
        for k in KS:
            for (qid, qtext, gold), qv in zip(QUERIES, qvecs):
                bm = [r["message_id"] for _, r in idx.bm25_search(qtext, k)]
                ve = [r["message_id"] for _, r in idx.vector_search(qv, k)]
                hy = [r["message_id"] for _, r in idx.hybrid_search(qtext, qv, k)]
                for route, ranked in (("A_BM25", bm), ("B_EMBEDDING", ve), ("C_HYBRID_RRF", hy)):
                    out["routes"].setdefault(route, {})[f"{qid}_k{k}"] = {
                        "ranked": ranked, "latency_s": 0.0,
                        "classification": "VERIFIED_BY_ME", **metrics(ranked, gold, k)}
    except Exception as exc:
        out["errors"].append(f"embedding phase: {type(exc).__name__}: {exc}")
    finally:
        stop(proc, log)

    # rerank routes D/E/F (sequential)
    if evecs is not None and free(18092):
        proc2, log2, ok2 = boot(18092, RER, ["--rerank", "--pooling", "rank"], "diff-reranker-server.txt")
        try:
            if not ok2:
                raise RuntimeError("reranker not healthy")
            for k in KS:
                for (qid, qtext, gold), qv in zip(QUERIES, qvecs):
                    pools = {
                        "D_BM25_RERANK": [r["message_id"] for _, r in idx.bm25_search(qtext, k)],
                        "E_EMB_RERANK": [r["message_id"] for _, r in idx.vector_search(qv, k)],
                        "F_ALL_RERANK": [r["message_id"] for _, r in idx.hybrid_search(qtext, qv, k)],
                    }
                    for route, pool in pools.items():
                        if not pool:
                            continue
                        docs = [DOCS[int(x[1:])] for x in pool]
                        t0 = time.monotonic()
                        rr = post(18092, "/rerank", {"query": qtext, "documents": docs}, timeout=240)
                        scored = sorted(zip(pool, [x["relevance_score"] for x in rr["results"]]),
                                        key=lambda x: -x[1])
                        ranked = [x[0] for x in scored]
                        out["routes"].setdefault(route, {})[f"{qid}_k{k}"] = {
                            "ranked": ranked, "latency_s": round(time.monotonic() - t0, 3),
                            "scores": [round(s, 4) for _, s in scored[:3]],
                            "classification": "VERIFIED_BY_ME", **metrics(ranked, gold, k)}
        except Exception as exc:
            out["errors"].append(f"rerank phase: {type(exc).__name__}: {exc}")
        finally:
            stop(proc2, log2)
    else:
        out["errors"].append("rerank phase skipped: no vectors or port busy")

    # G: generative selector (compactor, constrained) and J: hybrid+rerank+compact
    if free(18093):
        proc3, log3, ok3 = boot(18093, CMP, ["--reasoning", "off"], "diff-selector-server.txt")
        try:
            if not ok3:
                raise RuntimeError("selector not healthy")
            for qid, qtext, gold in QUERIES:
                pool = [r["message_id"] for _, r in idx.bm25_search(qtext, 8)]
                listing = "\n".join(DOCS[int(x[1:])] for x in pool)
                body = {"model": "x", "messages": [
                    {"role": "system", "content": "Devuelve SOLO el id del documento (dNN) mas relevante. Sin explicacion."},
                    {"role": "user", "content": f"Pregunta: {qtext}\nDocumentos:\n{listing}"}],
                    "temperature": 0, "max_tokens": 16,
                    "chat_template_kwargs": {"enable_thinking": False}}
                t0 = time.monotonic()
                rr = post(18093, "/v1/chat/completions", body, timeout=300)
                text = rr["choices"][0]["message"].get("content", "")
                import re
                m = re.search(r"\bd\d{2}\b", text)
                ranked = ([m.group(0)] + [x for x in pool if x != m.group(0)]) if m else []
                out["routes"].setdefault("G_QWEN_SELECTOR", {})[f"{qid}_k8"] = {
                    "raw": text[:120], "ranked": ranked, "latency_s": round(time.monotonic() - t0, 3),
                    "format_failure": 0 if m else 1, "classification": "VERIFIED_BY_ME",
                    **metrics(ranked, gold, 8)}
        except Exception as exc:
            out["errors"].append(f"selector phase: {type(exc).__name__}: {exc}")
        finally:
            stop(proc3, log3)
    else:
        out["errors"].append("selector phase skipped: port busy")

    for route, reason in (("H_RERANK_SELECTOR", "requires two generative calls per query; not executed in this bounded run"),
                          ("I_COMPACTOR_RETRIEVAL", "compaction route already measured in COMPACTOR_BENCHMARK; not re-run here"),
                          ("J_FULL_PIPELINE", "composition not executed; would combine G+D+C without new evidence")):
        out["routes"][route] = {"classification": "NOT_EXECUTED", "reason": reason}

    summary = {}
    for route, cases in out["routes"].items():
        vals = [v for v in cases.values() if isinstance(v, dict) and "recall_at_k" in v]
        if vals:
            summary[route] = {"n": len(vals),
                              "recall_at_k": round(sum(v["recall_at_k"] for v in vals) / len(vals), 3),
                              "selection_recall": round(sum(v["selection_recall"] for v in vals) / len(vals), 3),
                              "mrr": round(sum(v["mrr"] for v in vals) / len(vals), 3),
                              "max_latency_s": max(v["latency_s"] for v in vals)}
    out["summary"] = summary
    out["classification"] = "VERIFIED_BY_ME" if len(summary) >= 7 else "EVIDENCE_PENDING"
    (E / "MULTIENGINE_DIFFERENTIAL.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    print("errors:", out["errors"])


if __name__ == "__main__":
    main()
