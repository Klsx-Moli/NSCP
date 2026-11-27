"""CLI `npsc compact` (archivo nuevo; no modifica npsc_cli.py).

Entrada JSON: lista de {role, content, pinned?} o {"messages": [...]}.
Salida JSON: {"messages": [...], "report": {...}}. Codigos de salida: 0 ok,
1 error de entrada, 2 bloqueado por --strict.
"""

from __future__ import annotations

import argparse
import functools
import json
import sys
from pathlib import Path

from compaction_verifier import DEFAULT_GATE_POLICY, CompactionBlocked, compact_with_gate
from context_compactor import TurnView, estimate_tokens

VALID_ROLES = ("system", "user", "assistant", "tool")


def load_gate_policy():
    path = Path(__file__).resolve().parents[1] / "configs" / "compiler_defaults.json"
    try:
        sp = json.loads(path.read_text(encoding="utf-8")).get("strict_policy") or {}
        pol = {k: sp[k] for k in ("min_score", "max_critical_losses") if k in sp}
        return pol or dict(DEFAULT_GATE_POLICY)
    except (OSError, ValueError):
        return dict(DEFAULT_GATE_POLICY)


def load_history(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data.get("messages") if isinstance(data, dict) else data
    if not isinstance(items, list) or not items:
        raise ValueError("el JSON debe ser una lista no vacia de mensajes o {'messages': [...]}")
    out = []
    for i, m in enumerate(items):
        if not isinstance(m, dict) or m.get("role") not in VALID_ROLES or not isinstance(m.get("content"), str):
            raise ValueError(f"mensaje {i} invalido: requiere role en {VALID_ROLES} y content str")
        out.append(TurnView(m["role"], m["content"], estimate_tokens(m["content"]), bool(m.get("pinned", False))))
    return out


def _parser():
    p = argparse.ArgumentParser(prog="npsc compact", description="Compacta un historial para Hermes/Ollama")
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True, help="ruta JSON de salida, o '-' para stdout")
    p.add_argument("--num-ctx", type=int, required=True)
    p.add_argument("--level", choices=["safe", "balanced", "aggressive"], default="safe")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--offload-dir")
    p.add_argument("--summarizer", choices=["none", "ollama"], default="none")
    p.add_argument("--model", default="qwen3.5:4b-q4_K_M")
    p.add_argument("--summarizer-num-ctx", type=int, default=8192)
    p.add_argument("--summarizer-num-predict", type=int, default=1024)
    p.add_argument("--summarizer-timeout", type=float, default=120.0)
    p.add_argument("--host", default="http://localhost:11434")
    return p


def run_cli(argv=None):
    args = _parser().parse_args(argv)
    try:
        history = load_history(args.input)
    except (OSError, ValueError) as exc:
        print(f"[npsc compact] entrada invalida: {exc}", file=sys.stderr)
        return 1
    summarizer = None
    if args.summarizer == "ollama":
        from summarizer import summarize_turns
        summarizer = functools.partial(summarize_turns, model=args.model, host=args.host,
                                       num_ctx=args.summarizer_num_ctx,
                                       num_predict=args.summarizer_num_predict,
                                       timeout=args.summarizer_timeout, strict=args.strict)
    code, payload = 0, None
    try:
        msgs, rep = compact_with_gate(history, args.num_ctx, args.level, summarizer,
                                                      args.offload_dir, None, args.strict, load_gate_policy())
        payload = {"messages": msgs, "report": rep}
    except CompactionBlocked as exc:
        payload = {"messages": [], "report": exc.report, "blocked": True, "reasons": exc.reasons}
        code = 2
    except ValueError as exc:
        print(f"[npsc compact] {exc}", file=sys.stderr)
        return 1
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.out == "-":
        print(text)
    else:
        Path(args.out).write_text(text, encoding="utf-8")
    if code:
        print("[npsc compact] bloqueado por --strict: " + ",".join(payload["reasons"]), file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(run_cli())
