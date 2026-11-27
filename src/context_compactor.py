"""Compactor de contexto conversacional para objetivos Hermes (NSCP).

Reglas duras: el historial original jamas se modifica; los turnos con bloques
de codigo nunca se offloadean; los turnos system y pinned entran siempre.
Limitacion v1: el resumen SI puede incluir turnos con codigo (ver docs).
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Callable, Sequence

from compression_policy import CompressionPolicy, get_policy

HERMES_WRAPPER = (
    "# Contexto compactado (NSCP)\n"
    "La historia previa se compacto para caber en la ventana. Las instrucciones "
    "fijadas se conservan integras; los turnos intermedios estan resumidos o "
    "referenciados en archivos locales.\n"
    "Ejecucion por fases con informes y fallbacks explicitos. No inferir ni "
    "inventar el contenido de archivos referenciados; pedirlo si se necesita."
)
SUMMARY_INTRO = ("## Resumen de turnos intermedios\n"
                 "Generado por compresion. La historia integra esta preservada fuera de esta ventana.")
_VALID_ROLES = ("system", "user", "assistant", "tool")


@dataclass
class TurnView:
    role: str
    content: str
    token_count: int = 0
    pinned: bool = False


def estimate_tokens(text):
    return max(1, (len(text) + 3) // 4)


def tokens_of(text, tokenizer=None):
    return tokenizer(text) if tokenizer else estimate_tokens(text)


def to_view(turn, tokenizer=None):
    content = getattr(turn, "content", "") or ""
    tok = getattr(turn, "token_count", 0) or tokens_of(content, tokenizer)
    return TurnView(getattr(turn, "role", "user") or "user", content, tok,
                    bool(getattr(turn, "pinned", False)))


def partition_turns(views, keep_recent):
    pinned = [v for v in views if v.pinned or v.role == "system"]
    rest = [v for v in views if not (v.pinned or v.role == "system")]
    recent = rest[-keep_recent:] if keep_recent > 0 else []
    middle = rest[: len(rest) - len(recent)]
    return pinned, middle, recent


def offload_large_blocks(middle, storage_dir, max_inline_tokens, tokenizer=None):
    os.makedirs(storage_dir, exist_ok=True)
    out, count = [], 0
    for v in middle:
        if v.token_count > max_inline_tokens and "```" not in v.content:
            digest = hashlib.sha1(v.content.encode("utf-8")).hexdigest()[:12]
            filename = f"offloaded-{digest}.txt"
            path = os.path.join(storage_dir, filename)
            if not os.path.exists(path):
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(v.content)
            pointer = f"[turno ({v.role}, {v.token_count} tokens) movido a archivo local '{filename}']"
            out.append(TurnView(v.role, pointer, tokens_of(pointer, tokenizer), v.pinned))
            count += 1
        else:
            out.append(v)
    return out, count


def assemble_context(pinned, summary, middle, recent):
    head = [v.content for v in pinned] + [HERMES_WRAPPER]
    if summary:
        head.append(SUMMARY_INTRO + "\n\n" + summary)
    messages = [{"role": "system", "content": "\n\n".join(head)}]
    for v in list(middle) + list(recent):
        role = v.role if v.role in _VALID_ROLES else "user"
        if role == "system":
            role = "user"
        messages.append({"role": role, "content": v.content})
    return messages


def _report(policy, num_ctx, before, after, triggered, actions):
    return {
        "schema": "neuroprompt/compaction-result/v1",
        "level": policy.level, "num_ctx": num_ctx, "trigger_ratio": policy.trigger_ratio,
        "triggered": triggered, "tokens_before": before, "tokens_after": after,
        "compression_ratio": round(before / after, 2) if after else 0.0,
        "actions": actions,
        "verification": {"status": "structural_only"},
    }


def compact_history(history: Sequence, num_ctx: int, level=None,
                    summarizer: Callable | None = None, storage_dir=None, tokenizer=None):
    policy = get_policy(level)
    views = [to_view(t, tokenizer) for t in history]
    before = sum(v.token_count for v in views)
    if before < policy.triggers_at(num_ctx):
        msgs = [{"role": v.role if v.role in _VALID_ROLES else "user", "content": v.content} for v in views]
        return msgs, _report(policy, num_ctx, before, before, False, {})

    pinned, middle, recent = partition_turns(views, policy.keep_recent_turns)
    offloaded = 0
    if storage_dir and policy.offload_enabled and middle:
        middle, offloaded = offload_large_blocks(middle, storage_dir, policy.offload_max_inline_tokens, tokenizer)

    budget = (num_ctx - sum(v.token_count for v in pinned) - sum(v.token_count for v in recent)
              - tokens_of(HERMES_WRAPPER, tokenizer))
    if budget < 100:
        raise ValueError("Ventana insuficiente: instrucciones fijadas + turnos recientes no caben en num_ctx.")

    summary, summarized, dropped = None, 0, 0
    middle_kept = list(middle)
    if middle and sum(v.token_count for v in middle) > budget:
        if summarizer:
            summary = summarizer(middle)
            summarized = len(middle)
            middle_kept = []
            if tokens_of(summary, tokenizer) > budget:
                summary = summary[: max(budget * 4 - 48, 64)] + "\n[...resumen truncado por presupuesto]"
        else:
            middle_kept, used = [], 0
            for v in reversed(middle):
                if used + v.token_count <= budget:
                    middle_kept.append(v)
                    used += v.token_count
                else:
                    dropped += 1
            middle_kept.reverse()

    messages = assemble_context(pinned, summary, middle_kept, recent)
    after = sum(tokens_of(m["content"], tokenizer) for m in messages)
    actions = {"offloaded": offloaded, "summarized_turns": summarized, "dropped_turns": dropped,
               "kept_recent": len(recent), "pinned": len(pinned), "middle_kept": len(middle_kept)}
    return messages, _report(policy, num_ctx, before, after, True, actions)
