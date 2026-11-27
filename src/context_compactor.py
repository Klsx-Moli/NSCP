"""Compresión del contexto conversacional para objetivos Hermes.

Opera "hacia atrás": decide, en cada turno, qué parte del historial
acumulado entra en la ventana efectiva (num_ctx) y qué parte se
resume, referencia en disco o se omite. Complementario a NSCP: NSCP
comprime la petición (hacia adentro); este módulo comprime la
historia acumulada (hacia atrás).

Reglas duras (coherentes con el perfil hermes de
configs/model_profiles.json: "strong boundary and non-destructive
constraints required"):

- El historial original jamás se modifica ni se borra; solo se
  reconstruye lo que se envía al modelo.
- Nunca se offloadea contenido que contenga bloques de código (```):
  la compresión de estructura de código es de alto riesgo.
- Los turnos ``system`` y los marcados ``pinned`` entran siempre.
- Sin dependencias externas; el tokenizer es inyectable (fallo a una
  estimación de ~4 caracteres por token si no se suministra).

API pública: ``compact_history``. Uso típico::

    from summarizer import summarize_turns
    messages, report = compact_history(
        history, num_ctx=8192, level="safe",
        summarizer=summarize_turns, storage_dir=".offload",
    )
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Callable, Sequence

from compression_policy import CompressionPolicy, get_policy

Tokenizer = Optional = Callable[[str], int]

HERMES_WRAPPER = (
    "# Contexto compactado (NSCP)\n"
    "La historia previa se compactó para caber en la ventana. Las "
    "instrucciones fijadas se conservan íntegras; los turnos "
    "intermedios están resumidos o referenciados en archivos "
    "locales.\n"
    "Ejecución por fases con informes y fallbacks explícitos. No "
    "inferir ni inventar el contenido de archivos referenciados; "
    "pedirlo explícitamente si se necesita."
)

SUMMARY_INTRO = (
    "## Resumen de turnos intermedios\n"
    "Generado por compresión. La historia íntegra está preservada "
    "fuera de esta ventana."
)

_VALID_ROLES = ("system", "user", "assistant", "tool")


@dataclass
class TurnView:
    """Vista ligera de un turno con la que trabaja el compactor."""

    role: str
    content: str
    token_count: int = 0
    pinned: bool = False


def estimate_tokens(text: str) -> int:
    """Estimación sin tokenizer real: ~4 caracteres por token."""
    return max(1, (len(text) + 3) // 4)


def tokens_of(text: str, tokenizer=None) -> int:
    return tokenizer(text) if tokenizer else estimate_tokens(text)


def to_view(turn, tokenizer=None) -> TurnView:
    """Admite objetos duck-typed (Turn, dict-like de atributos)."""
    content = getattr(turn, "content", "") or ""
    tok = getattr(turn, "token_count", 0) or tokens_of(content, tokenizer)
    return TurnView(
        role=getattr(turn, "role", "user") or "user",
        content=content,
        token_count=tok,
        pinned=bool(getattr(turn, "pinned", False)),
    )


def partition_turns(views: list[TurnView],
                    keep_recent: int) -> tuple[list, list, list]:
    """Parte el historial en (pinned, middle, recent).

    pinned  -> turnos ``system`` o marcados pinned; entran siempre.
    recent  -> los últimos ``keep_recent``; entran íntegros.
    middle  -> el resto: candidatos a offload, resumen u omisión.
    """
    pinned = [v for v in views if v.pinned or v.role == "system"]
    rest = [v for v in views if not (v.pinned or v.role == "system")]
    recent = rest[-keep_recent:] if keep_recent > 0 else []
    middle = rest[: len(rest) - len(recent)]
    return pinned, middle, recent


def offload_large_blocks(middle: list[TurnView],
                         storage_dir: str,
                         max_inline_tokens: int,
                         tokenizer=None) -> tuple[list[TurnView], int]:
    """Mueve a disco turnos grandes SIN código; devuelve (turnos, n)."""
    os.makedirs(storage_dir, exist_ok=True)
    out: list[TurnView] = []
    count = 0
    for v in middle:
        if (
            v.token_count > max_inline_tokens
            and "```" not in v.content
        ):
            digest = hashlib.sha1(v.content.encode("utf-8")).hexdigest()[:12]
            filename = f"offloaded-{digest}.txt"
            path = os.path.join(storage_dir, filename)
            if not os.path.exists(path):
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(v.content)
            pointer = (
                f"[turno ({v.role}, {v.token_count} tokens) movido a "
                f"archivo local '{filename}']"
            )
            out.append(TurnView(role=v.role, content=pointer,
                                token_count=tokens_of(pointer, tokenizer),
                                pinned=v.pinned))
            count += 1
        else:
            out.append(v)
    return out, count


def assemble_context(pinned: list[TurnView],
                     summary: str | None,
                     middle: list[TurnView],
                     recent: list[TurnView]) -> list[dict]:
    """Reconstruye mensajes en formato /api/chat de Ollama.

    Orden: [system: pinned + wrapper + resumen] + middle + recent.
    """
    head = [v.content for v in pinned] + [HERMES_WRAPPER]
    if summary:
        head.append(SUMMARY_INTRO + "\n\n" + summary)
    messages = [{"role": "system", "content": "\n\n".join(head)}]
    for v in list(middle) + list(recent):
        role = v.role if v.role in _VALID_ROLES else "user"
        if role == "system":  # los system externos no pueden repetirse tarde
            role = "user"
        messages.append({"role": role, "content": v.content})
    return messages


def _report(policy: CompressionPolicy, num_ctx: int,
            tokens_before: int, tokens_after: int,
            triggered: bool, actions: dict) -> dict:
    ratio = round(tokens_before / tokens_after, 2) if tokens_after else 0.0
    return {
        "schema": "neuroprompt/compaction-result/v1",
        "level": policy.level,
        "num_ctx": num_ctx,
        "trigger_ratio": policy.trigger_ratio,
        "triggered": triggered,
        "tokens_before": tokens_before,
        "tokens_after": tokens_after,
        "compression_ratio": ratio,
        "actions": actions,
        "verification": {
            "status": "structural_only",
            "note": (
                "v1 asegura reglas estructurales (pinned conservados, "
                "código nunca offloaded, orden preservado). La "
                "verificación semántica con context_loss_verifier y el "
                "modo --strict están previstos para v2."
            ),
        },
    }


def compact_history(history: Sequence,
                    num_ctx: int,
                    level: str | None = None,
                    summarizer: Callable[[list[TurnView]], str] | None = None,
                    storage_dir: str | None = None,
                    tokenizer=None) -> tuple[list[dict], dict]:
    """Compacta un historial para caber en ``num_ctx`` tokens.

    Devuelve (messages, report). ``messages`` va directo al payload
    /api/chat de Ollama; ``report`` es persistible/auditable.
    """
    policy = get_policy(level)
    views = [to_view(t, tokenizer) for t in history]
    tokens_before = sum(v.token_count for v in views)
    threshold = policy.triggers_at(num_ctx)

    if tokens_before < threshold:
        messages = [
            {"role": v.role if v.role in _VALID_ROLES else "user",
             "content": v.content}
            for v in views
        ]
        return messages, _report(policy, num_ctx, tokens_before,
                                 tokens_before, False, {})

    pinned, middle, recent = partition_turns(views, policy.keep_recent_turns)

    offloaded = 0
    if storage_dir and policy.offload_enabled and middle:
        middle, offloaded = offload_large_blocks(
            middle, storage_dir, policy.offload_max_inline_tokens, tokenizer)

    pinned_tokens = sum(v.token_count for v in pinned)
    recent_tokens = sum(v.token_count for v in recent)
    wrapper_tokens = tokens_of(HERMES_WRAPPER, tokenizer)
    budget = num_ctx - pinned_tokens - recent_tokens - wrapper_tokens
    if budget < 100:
        raise ValueError(
            "Ventana insuficiente: instrucciones fijadas + turnos recientes"
            " no caben en num_ctx. Sube num_ctx, reduce keep_recent_turns"
            " o desfija contenido."
        )

    summary = None
    summarized = 0
    dropped = 0
    middle_tokens = sum(v.token_count for v in middle)

    if middle and middle_tokens > budget:
        if summarizer:
            summary = summarizer(middle)
            summarized = len(middle)
            middle_kept: list[TurnView] = []
            if tokens_of(summary, tokenizer) > budget:
                max_chars = max(budget * 4 - 48, 64)
                summary = summary[:max_chars] + "\n[...resumen truncado por presupuesto]"
        else:
            middle_kept, used = [], 0
            for v in reversed(middle):
                if used + v.token_count <= budget:
                    middle_kept.append(v)
                    used += v.token_count
                else:
                    dropped += 1
            middle_kept.reverse()
    else:
        middle_kept = list(middle)

    messages = assemble_context(pinned, summary, middle_kept, recent)
    tokens_after = sum(tokens_of(m["content"], tokenizer) for m in messages)

    actions = {
        "offloaded": offloaded,
        "summarized_turns": summarized,
        "dropped_turns": dropped,
        "kept_recent": len(recent),
        "pinned": len(pinned),
        "middle_kept": len(middle_kept),
    }
    return messages, _report(policy, num_ctx, tokens_before, tokens_after,
                             True, actions)
