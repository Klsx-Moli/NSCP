"""Offline preview and exact recall for request-only agent compaction."""
import argparse
import json
from pathlib import Path

from agent_context import STRATEGIES, plan_request, recall


def _messages(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("messages")
    if not isinstance(data, list):
        raise ValueError("Expected a message list")
    return data


def run_cli(argv=None):
    parser = argparse.ArgumentParser(prog="npsc-agent-context")
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--input", required=True)
    plan.add_argument("--transcript", required=True)
    plan.add_argument("--budget", type=int, required=True)
    plan.add_argument("--keep-recent", type=int, default=8)
    plan.add_argument("--strategy", choices=STRATEGIES, default="adaptive")
    plan.add_argument("--focus", action="append", default=None, help="Explicit protected identifier (repeatable)")
    plan.add_argument("--excerpts", choices=["bm25", "ollama", "embedding", "embedding-rerank"],
                      help="Opt-in exact source previews; ollama sends data only to the local model")
    plan.add_argument("--preview-reserve", type=int, default=0)
    plan.add_argument("--max-model-calls", type=int, default=4)
    plan.add_argument("--local-num-ctx", type=int, default=8192)
    plan.add_argument("--local-model", default="qwen3.5:4b-q4_K_M")
    plan.add_argument("--embedding-port", type=int)
    plan.add_argument("--reranker-port", type=int)
    plan.add_argument("--max-local-requests", type=int, default=24)
    recover = sub.add_parser("recall")
    recover.add_argument("--transcript", required=True)
    recover.add_argument("--reference", required=True)
    recover.add_argument("--offset", type=int, default=0)
    recover.add_argument("--limit", type=int, default=4000)
    args = parser.parse_args(argv)
    try:
        source = _messages(args.transcript)
        if args.command == "plan":
            kwargs = dict(keep_recent=args.keep_recent, strategy=args.strategy,
                          focus_terms=args.focus)
            if args.excerpts:
                from extractive_context import OllamaSpanSelector, plan_extractive_request
                from local_summary import LocalSummaryConfig
                selector = (OllamaSpanSelector(LocalSummaryConfig(
                    model=args.local_model, num_ctx=args.local_num_ctx, num_predict=128))
                    if args.excerpts == "ollama" else None)
                route, pool = "local_ids", "sampled"
                if args.excerpts in ("embedding", "embedding-rerank"):
                    from local_retrieval import RetrievalConfig, SemanticSpanSelector
                    if args.embedding_port is None or (
                            args.excerpts == "embedding-rerank" and args.reranker_port is None):
                        raise ValueError("Explicit loopback retrieval ports required")
                    selector = SemanticSpanSelector(RetrievalConfig(
                        embedding_port=args.embedding_port,
                        reranker_port=args.reranker_port if args.excerpts == "embedding-rerank" else None,
                        max_requests=args.max_local_requests))
                    route = args.excerpts.replace("-", "_")
                    pool = "bounded_all"
                result = plan_extractive_request(
                    _messages(args.input), source, args.budget, **kwargs,
                    preview_reserve=args.preview_reserve, selector=selector,
                    max_model_calls=args.max_model_calls, selector_route=route,
                    selector_pool=pool)
                if pool == "bounded_all":
                    result.report["local_http_requests"] = selector.requests
            else:
                if args.preview_reserve:
                    raise ValueError("--preview-reserve requires --excerpts")
                result = plan_request(_messages(args.input), source, args.budget, **kwargs)
            payload = {"messages": result.messages, "report": result.report}
            code = 0 if result.report["fits_metered_budget"] else 2
        else:
            payload = recall(source, args.reference, offset=args.offset, limit=args.limit)
            code = 2 if "error" in payload else 0
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(1, f"Invalid input: {exc}\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(run_cli())
