"""ITER09: replay the real embedding route and exercise persistent memory.

Sequential local inference; synthetic event data; no downloads, no Hermes
activation, no provider calls, and no Git writes. No model-quality claim.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from benchmark_specialized_engines import server
from run_iter08_local import _fixture, _check_preview
from agent_context import verify_request_plan
from extractive_context import plan_extractive_request
from local_retrieval import RetrievalConfig, SemanticSpanSelector
from memory_index import index_source
from nscp_resources import file_hash, model_files, root_path
from semantic_memory import SemanticMemory


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True)
    p.add_argument("--server", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--ngl", type=int, choices=(0, 99), default=99)
    args = p.parse_args(argv)
    root = root_path(args.root)
    exe = args.server.resolve(strict=True)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {"schema": "nscp/iter09-local/v1", "complete": False, "server": {}, "tasks": {}}
    model = root.joinpath(*model_files("qwen3-embedding-0.6b-q8")[0])
    try:
        model_identity = file_hash(model) + ":llama.cpp:" + file_hash(exe) + ":raw-v1"
        rows = _fixture()
        with server(exe, model, out, "embedding", ["--embedding", "-ngl", str(args.ngl)],
                    report["server"]) as port:
            selector = SemanticSpanSelector(RetrievalConfig(port))
            plan = plan_extractive_request(rows, rows, 1300, keep_recent=1, selector=selector,
                                           selector_route="embedding", selector_pool="bounded_all")
            plan.report["verification"] = verify_request_plan(rows, rows, plan, 1300, keep_recent=1)
            report["tasks"]["preview"] = _check_preview(rows, plan)
            report["tasks"]["preview"]["http_requests"] = selector.requests
            # Use actual original event text; do not pass answer key into engine.
            source = {"episode": "synthetic", "message": "log", "role": "tool",
                      "tool_call": "synthetic", "content": rows[4]["content"]}
            database = out / "synthetic-memory.sqlite"
            embed = SemanticSpanSelector(RetrievalConfig(port))
            with SemanticMemory(database, session_id="s1", embedding_id=model_identity, dimension=1024) as m:
                first = index_source(m, embed.embed, **source)
                first_calls = embed.requests
            replay = SemanticSpanSelector(RetrievalConfig(port))
            with SemanticMemory(database, session_id="s1", embedding_id=model_identity, dimension=1024) as m:
                second = index_source(m, replay.embed, **source)
                replay_calls = replay.requests
                vector = replay.embed(["What obligations remain applicable?"])[0]
                hits = m.search(vector, k=8)
                exact = m.recall(episode="synthetic", message="log", limit=12000)["content"] == source["content"]
            with SemanticMemory(database, session_id="s2", embedding_id=model_identity, dimension=1024) as m:
                isolation = m.search(vector) == [] and m.recall(episode="synthetic", message="log") is None
            report["tasks"]["memory"] = {"first": first, "replay": second,
                "first_http_requests": first_calls, "replay_http_requests": replay_calls,
                "exact_recall": exact, "session_isolation": isolation,
                "hits": hits, "semantic_equivalence": "not_verified"}
            report["complete"] = bool(report["tasks"]["preview"]["expected_evidence_visible"]
                and first["inserted"] > 0 and second["inserted"] == 0 and replay_calls == 0 and exact and isolation)
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)
    tmp = out / "checkpoint.partial.json"
    tmp.write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
    os.replace(tmp, out / "checkpoint.json")
    return 0 if report["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
