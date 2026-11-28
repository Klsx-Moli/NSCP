"""Run bounded sequential local embedding/reranker evaluation.

Synthetic corpus only. Never uses a real session, external provider or
Ollama store. Explicit llama-server executable and model resource root.
Reports incomplete runs without converting transport failures into scores.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import socket
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from extractive_context import Span, rank_spans
from nscp_resources import file_hash, model_files, root_path
from semantic_memory import _vector
from semantic_ranking import rerank_results, retrieval_metrics

# Each case has a different target fact. No expected IDs are sent to engines.
# Synthetic and publicly visible: development benchmark, not sealed holdout.
DOCS = {
    "d01": "La autorización para publicar en producción quedó revocada.",
    "d02": "El despliegue en pruebas sigue permitido.",
    "d03": "The worker was terminated because the memory limit was exceeded.",
    "d04": "A network request was cancelled after the service stopped responding.",
    "d05": "El archivo de configuración contiene una clave duplicada.",
    "d06": "La lectura del fichero falló porque no existía en disco.",
    "d07": "The previous successful test result was invalidated by a later regression.",
    "d08": "The current unit test suite passed after the latest repair.",
    "d09": "Los datos originales permanecen intactos en un archivo recuperable.",
    "d10": "El resumen perdió una restricción y no debe usarse como fuente primaria.",
    "d11": "The vector index was rebuilt after the embedding model revision changed.",
    "d12": "The old cache was retained only for historical comparison.",
    "d13": "Se concedió acceso de lectura, pero no permiso de escritura.",
    "d14": "El administrador confirmó una copia de seguridad independiente.",
    "d15": "The background task is queued; no execution has been observed yet.",
    "d16": "A completed task has a recorded exit status and output.",
    "d17": "El servidor local escucha exclusivamente en la interfaz de loopback.",
    "d18": "The reranker considers a negated statement highly relevant as well.",
    "d19": "La transacción se revirtió tras detectar una referencia huérfana.",
    "d20": "A model file has a matching digest but has not been loaded.",
    "d21": "The repository was inspected without changing the stable branch.",
    "d22": "El generador produjo un resultado truncado por el límite de salida.",
    "d23": "La sesión se restauró con el mismo identificador tras reiniciar.",
    "d24": "The new tokenizer changed the number of tokens in the prompt.",
}
CASES = (
    ("c01", "May we still release to production?", ("d01",)),
    ("c02", "¿Qué ocasionó que el proceso fuese eliminado por consumo de recursos?", ("d03",)),
    ("c03", "Which settings file problem involves repeated fields?", ("d05",)),
    ("c04", "¿Por qué dejó de ser válida la comprobación anterior?", ("d07",)),
    ("c05", "Can we recover the unmodified material?", ("d09",)),
    ("c06", "¿Qué ocurrió cuando cambiaron los pesos de representación semántica?", ("d11",)),
    ("c07", "Can the actor edit content, or only view it?", ("d13",)),
    ("c08", "¿Se ha llegado a ejecutar el trabajo en espera?", ("d15",)),
    ("c09", "Can another machine reach the listening service?", ("d17",)),
    ("c10", "¿Qué pasó al encontrar un vínculo sin fuente?", ("d19",)),
    ("c11", "¿Se alteró la rama estable durante la inspección?", ("d21",)),
    ("c12", "Did the conversation identity survive a restart?", ("d23",)),
    ("c13", "Which statements show that checking a digest or a queue is not execution?", ("d15", "d20")),
    ("c14", "What is the user's bank account number?", ()),
    ("c15", "¿Qué versión exacta del kernel Linux se ejecutó?", ()),
)
KS = (4, 8, 16)


def dataset_digest():
    data = json.dumps({"docs": DOCS, "cases": CASES, "ks": KS},
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Unexpected local redirect")


def request(port, path, payload=None, timeout=90):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"http://127.0.0.1:{port}" + path, data=body,
                                 headers={"Content-Type": "application/json"})
    with opener.open(req, timeout=timeout) as response:
        data = response.read(16 * 1024 * 1024 + 1)
    if len(data) > 16 * 1024 * 1024:
        raise ValueError("Response too large")
    result = json.loads(data)
    if not isinstance(result, dict) or result.get("error"):
        raise ValueError("Invalid response")
    return result


def embedding_results(response, count, dimension):
    if not isinstance(response, dict) or not isinstance(response.get("data"), list):
        raise ValueError("Missing embedding data")
    if len(response["data"]) != count:
        raise ValueError("Incomplete embedding response")
    out = {}
    for item in response["data"]:
        if not isinstance(item, dict):
            raise ValueError("Invalid embedding item")
        i = item.get("index")
        if type(i) is not int or not 0 <= i < count or i in out:
            raise ValueError("Invalid embedding index")
        out[i] = _vector(item.get("embedding"), dimension)
    return [out[i] for i in range(count)]


def lexical(query):
    ids = list(DOCS)
    spans = [Span(i, 0, len(DOCS[d]), DOCS[d]) for i, d in enumerate(ids)]
    return [ids[i] for i in rank_spans(spans, query)]


def fuse(a, b, *, limit):
    scores = {}
    for ranking in (a, b):
        for rank, key in enumerate(ranking, 1):
            scores[key] = scores.get(key, 0.0) + 1 / (60 + rank)
    return sorted(scores, key=lambda key: (-scores[key], key))[:limit]


def evaluate_rankings(vectors, queries):
    ids = list(DOCS)
    out = {}
    for (qid, query, _), vector in zip(CASES, queries):
        embedding = sorted(ids, key=lambda d: (-math.fsum(
            a * b for a, b in zip(vectors[ids.index(d)], vector)), d))
        bm = lexical(query)
        out[qid] = {"bm25": bm, "embedding": embedding,
                    "rrf": fuse(bm[:16], embedding[:16], limit=16)}
    return out


def summary(rows):
    """All expected cases count. Missing/failed cases are not measured hits."""
    result = {}
    for route in ("bm25", "embedding", "rrf", "bm25_rerank", "embedding_rerank", "rrf_rerank"):
        for k in KS:
            relevant_cases = [(qid, gold) for qid, _, gold in CASES if gold]
            expected = len(relevant_cases)
            observed = [rows.get(qid, {}).get(route, {}).get(str(k)) for qid, _ in relevant_cases]
            valid = [r["metrics"] for r in observed if r and r["status"] == "ok"]
            result[f"{route}@{k}"] = {
                "expected_answerable_cases": expected, "measured_answerable_cases": len(valid),
                "complete": len(valid) == expected,
                "recall_at_k": sum(m["recall_at_k"] for m in valid) / expected if len(valid) == expected else None,
                "top1_accuracy": sum(m["top1_hit"] for m in valid) / expected if len(valid) == expected else None,
                "mrr_at_k": sum(m["mrr_at_k"] for m in valid) / expected if len(valid) == expected else None,
                "observed_hits": sum(m["top1_hit"] for m in valid),
                "no_answer_cases": len(CASES) - expected,
            }
    return result


@contextmanager
def server(executable, model, out, name, args, telemetry):
    # The data is synthetic; we still avoid proxy/redirect and verify child
    # process liveness. Port release before spawn has a small TOCTOU window.
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    command = [str(executable), "--host", "127.0.0.1", "--port", str(port),
               "-m", str(model), "--ctx-size", "2048", "-t", "2", "-tb", "2",
               "--no-webui", *args]
    env = os.environ.copy()
    if os.name == "nt":
        win = Path(env.get("SystemRoot", r"C:\Windows"))
        env["PATH"] = os.pathsep.join([str(executable.parent), str(win / "System32"), str(win)])
    model_digest = file_hash(model)
    started = time.monotonic()
    with (out / (name + ".log")).open("x", encoding="utf-8") as log:
        proc = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
        info = telemetry[name] = {"pid": proc.pid, "port": port, "arguments": command,
                                  "model_sha256": model_digest}
        try:
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise RuntimeError("Server exited during startup")
                try:
                    health = request(port, "/health", timeout=2)
                    if health.get("status") == "ok":
                        break
                except (OSError, ValueError):
                    pass
                time.sleep(1)
            else:
                raise TimeoutError("Server startup timeout")
            info["startup_s"] = round(time.monotonic() - started, 3)
            yield port
        finally:
            info["exit_before_cleanup"] = proc.poll()
            if proc.poll() is None:
                info["termination_requested"] = True
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            info["exit_after_cleanup"] = proc.returncode


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True)
    p.add_argument("--server", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--ngl", type=int, choices=(0, 99), default=0)
    p.add_argument("--query-prefix", default="")
    args = p.parse_args(argv)
    root = root_path(args.root)
    executable = args.server.resolve(strict=True)
    if not executable.is_file():
        p.error("Expected llama-server executable")
    emb = root.joinpath(*model_files("qwen3-embedding-0.6b-q8")[0])
    rer = root.joinpath(*model_files("qwen3-reranker-0.6b-q8")[0])
    if not emb.is_file() or not rer.is_file():
        p.error("Import both local models first")
    args.out.mkdir(parents=True, exist_ok=False)
    report = {"schema": "nscp/specialized-retrieval-benchmark/v1",
              "dataset_sha256": dataset_digest(), "data_origin": "synthetic_development",
              "independent_cases": len(CASES), "case_ids": [c[0] for c in CASES],
              "query_prefix": args.query_prefix, "ngl_requested": args.ngl,
              "servers": {}, "errors": [], "rows": {}, "complete": False}
    (args.out / "dataset.json").write_text(json.dumps(
        {"docs": DOCS, "cases": CASES, "ks": KS}, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = report["rows"]

    def save():
        report["summary"] = summary(rows)
        tmp = args.out / "results.partial.json"
        tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        os.replace(tmp, args.out / "results.json")

    def record(qid, gold, route, k, ranked, **extra):
        rows.setdefault(qid, {}).setdefault(route, {})[str(k)] = {
            "status": "ok", "ranked": ranked, "metrics": retrieval_metrics(ranked, gold, k=k), **extra}

    try:
        for qid, query, gold in CASES:
            for k in KS:
                record(qid, gold, "bm25", k, lexical(query)[:k])
        save()
        with server(executable, emb, args.out, "embedding", ["--embedding", "-ngl", str(args.ngl)],
                    report["servers"]) as port:
            inputs = list(DOCS.values()) + [args.query_prefix + q for _, q, _ in CASES]
            vectors = []
            for start in range(0, len(inputs), 4):
                batch = inputs[start:start+4]
                result = request(port, "/v1/embeddings", {"input": batch})
                vectors.extend(embedding_results(result, len(batch), 1024))
        rankings = evaluate_rankings(vectors[:len(DOCS)], vectors[len(DOCS):])
        for qid, _, gold in CASES:
            for route in ("embedding", "rrf"):
                for k in KS:
                    record(qid, gold, route, k, rankings[qid][route][:k])
        save()
        with server(executable, rer, args.out, "reranker",
                    ["--rerank", "--pooling", "rank", "-ngl", str(args.ngl)], report["servers"]) as port:
            for qid, query, gold in CASES:
                for route in ("bm25", "embedding", "rrf"):
                    pool = rankings[qid][route][:max(KS)]
                    try:
                        start = time.monotonic()
                        response = request(port, "/rerank", {"query": query, "documents": [DOCS[d] for d in pool]}) if pool else {"results": []}
                        ranked = rerank_results(pool, response)
                        for k in KS:
                            record(qid, gold, route + "_rerank", k, [d for d, _ in ranked[:k]],
                                   candidate_ids=pool, raw_results=response["results"],
                                   latency_s=round(time.monotonic() - start, 3))
                    except (OSError, ValueError, KeyError) as exc:
                        report["errors"].append({"case": qid, "route": route, "error": type(exc).__name__})
                    save()
        report["complete"] = not report["errors"]
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        report["errors"].append({"stage": "runtime", "error": type(exc).__name__, "detail": str(exc)})
    finally:
        save()
    print(json.dumps({"complete": report["complete"], "results": str(args.out / "results.json")}))
    return 0 if report["complete"] else 2


if __name__ == "__main__":
    sys.exit(main())
