"""Explicit local persistent source indexing and retrieval.

A session id is a caller-provided partition, not authentication. Store only
authorized text in a private database. No automatic transcript collection.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from extractive_context import split_spans
from local_retrieval import MAX_SPANS, RetrievalConfig, SemanticSpanSelector
from semantic_memory import SemanticMemory


def index_source(memory, embed, *, episode, message, role, content, tool_call=""):
    """Index missing offsets only; batch insertion is atomic after inference."""
    args = dict(episode=episode, message=message, role=role, content=content, tool_call=tool_call)
    spans = split_spans(content)
    existing = memory.indexed_offsets(**args)
    missing = [s for s in spans if (s.start, s.end) not in existing]
    if len(missing) > MAX_SPANS:
        raise ValueError("Source exceeds bounded indexing batch; split into explicit events")
    if not missing:
        return {"inserted": 0, "reused": len(spans), "source_spans": len(spans)}
    # Deduplicate inference, NOT source occurrences. Every offset is stored.
    unique = list(dict.fromkeys(s.text for s in missing))
    vectors = embed(unique)
    if not isinstance(vectors, list) or len(vectors) != len(unique):
        raise ValueError("Incomplete vector batch")
    by_text = dict(zip(unique, vectors))
    inserted = memory.add_many(**args, spans=[(s.start, s.end, by_text[s.text]) for s in missing])
    return {"inserted": inserted, "reused": len(spans) - inserted,
            "source_spans": len(spans), "embedded_unique_texts": len(unique)}


def run_cli(argv=None):
    p = argparse.ArgumentParser(prog="nscp-memory", description=__doc__)
    p.add_argument("--db", required=True, type=Path)
    p.add_argument("--session", required=True)
    p.add_argument("--embedding-id", required=True,
                   help="Identity including model revision, tokenizer, runtime and query policy")
    p.add_argument("--dimension", type=int, default=1024)
    sub = p.add_subparsers(dest="command", required=True)
    index = sub.add_parser("index")
    index.add_argument("--source", required=True, type=Path, help="Explicit JSON event file")
    search = sub.add_parser("search")
    search.add_argument("--query", required=True)
    search.add_argument("--k", type=int, default=8)
    for cmd in (index, search):
        cmd.add_argument("--embedding-port", required=True, type=int)
        cmd.add_argument("--query-prefix", default="")
    recall = sub.add_parser("recall")
    recall.add_argument("--episode", required=True)
    recall.add_argument("--message", required=True)
    recall.add_argument("--offset", type=int, default=0)
    recall.add_argument("--limit", type=int, default=4000)
    args = p.parse_args(argv)
    try:
        if args.command != "index" and not args.db.is_file():
            raise ValueError("Memory database does not exist")
        if args.db.is_symlink():
            raise ValueError("Linked memory database rejected")
        with SemanticMemory(args.db, session_id=args.session,
                            embedding_id=args.embedding_id, dimension=args.dimension) as mem:
            if args.command == "recall":
                result = mem.recall(episode=args.episode, message=args.message,
                                    offset=args.offset, limit=args.limit)
                if result is None:
                    print(json.dumps({"error": "source_not_found"}))
                    return 2
            else:
                selector = SemanticSpanSelector(RetrievalConfig(
                    args.embedding_port, dimension=args.dimension, query_prefix=args.query_prefix))
                if args.command == "index":
                    if args.source.stat().st_size > 1024 * 1024:
                        raise ValueError("Source event exceeds byte limit")
                    source = json.loads(args.source.read_text(encoding="utf-8"))
                    if not isinstance(source, dict) or set(source) - {
                            "episode", "message", "role", "content", "tool_call"}:
                        raise ValueError("Invalid source event fields")
                    result = index_source(mem, selector.embed, **source)
                else:
                    vector = selector.embed([args.query_prefix + args.query])[0]
                    result = {"hits": mem.search(vector, k=args.k),
                              "semantic_equivalence": "not_verified",
                              "answerability": "unknown"}
                result["local_http_requests"] = selector.requests
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, sqlite3.Error) as exc:
        print(json.dumps({"error": type(exc).__name__}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(run_cli())
