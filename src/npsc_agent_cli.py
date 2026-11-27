"""Offline preview and exact recall for request-only agent compaction."""
import argparse
import json
from pathlib import Path

from agent_context import plan_request, recall


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
    recover = sub.add_parser("recall")
    recover.add_argument("--transcript", required=True)
    recover.add_argument("--reference", required=True)
    recover.add_argument("--offset", type=int, default=0)
    recover.add_argument("--limit", type=int, default=4000)
    args = parser.parse_args(argv)
    try:
        source = _messages(args.transcript)
        if args.command == "plan":
            result = plan_request(_messages(args.input), source, args.budget,
                                  keep_recent=args.keep_recent)
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
