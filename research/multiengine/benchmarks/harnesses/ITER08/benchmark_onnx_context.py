"""Synthetic, local-only ONNX evidence preservation comparison.

No model files, tokenizer data, real sessions or remote calls are produced.
Raw CTXPrune scoring is not a benchmark of the full CTXPrune package.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path

from local_onnx import LocalOnnxScorer, TokenScore, plan_log_preview

CASES = (
    ("error", "ERROR tests/test_agent_context.py missing"),
    ("negation", "Permission was revoked; never publish to production."),
    ("spanish", "Autorización anulada: no publicar fuera de la rama aislada."),
    ("id", "Verified commit 97ea9e987656bf64234cfc56ee3a89196a3b579d"),
    ("unicode", "Resultado especial: ñandú y pingüino 日本語 😀"),
    ("semantic", "The old checkpoint became obsolete following the latest regression."),
)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--kind", choices=("kompress", "ctxprune"), required=True)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--tokenizer", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)
    if args.out.exists():
        p.error("Output already exists")
    scorer = LocalOnnxScorer(args.kind, args.model, args.tokenizer)
    report = {"schema": "nscp/onnx-log-benchmark/v1", "engine": scorer.identity,
              "data_origin": "synthetic_development", "cases": [],
              "provider_tokens": None, "semantic_task_success": None}
    for case, expected in CASES:
        text = ("INFO routine diagnostic completed successfully\n" * 14
                + expected + "\n" + "INFO routine cleanup completed successfully\n" * 14)
        row = {"case": case, "source_sha256": hashlib.sha256(text.encode()).hexdigest(),
               "expected": expected, "routes": []}
        for kind in ("deterministic_equal_scores", args.kind):
            started = time.monotonic()
            try:
                scores = ([TokenScore(0, len(text), 0.5)] if kind == "deterministic_equal_scores"
                          else scorer.score(text))
                plan = plan_log_preview(text, scores, 650)
                preview = plan["preview"]
                visible = ([preview] if isinstance(preview, str) else
                           [s["text"] for s in preview["spans"]] if preview else [])
                if isinstance(preview, dict):
                    assert all(s["text"] == text[s["start"]:s["end"]] for s in preview["spans"])
                row["routes"].append({"route": kind, "status": plan["status"],
                                      "source_bytes": plan["source_bytes"],
                                      "preview_bytes": plan["preview_bytes"],
                                      "protected_lines": plan["protected_lines"],
                                      "expected_visible": any(expected in s for s in visible),
                                      "preview": preview, "seconds": time.monotonic() - started})
            except Exception as exc:
                row["routes"].append({"route": kind, "status": "error",
                                      "error_type": type(exc).__name__})
        report["cases"].append(row)
    with args.out.open("x", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, allow_nan=False)
    return 2 if any(r["status"] == "error" for c in report["cases"] for r in c["routes"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
