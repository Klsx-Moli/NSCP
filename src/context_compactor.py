"""Compactor de contexto conversacional para objetivos Hermes (NSCP).

Reglas duras: el historial original jamas se modifica; los turnos con bloques
de codigo (```) nunca se offloadean ni se resumen: se conservan verbatim o, si
no caben, se descartan de forma EXPLICITA (actions.code_turns_dropped) y el
verificador lo marca como perdida critica. Los turnos system/pinned entran siempre.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Callable, Sequence

from compression_policy import get_policy

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
    count = tokenizer(text) if tokenizer else estimate_tokens(text)
    if type(count) is not int or count < 0 or (text and count == 0):
        raise ValueError("Conteo de tokens invalido")
    return count


def has_code(v):
    return "```" in v.content


def to_view(turn, tokenizer=None):
    content = getattr(turn, "content", None)
    role = getattr(turn, "role", None)
    if not isinstance(content, str) or role not in _VALID_ROLES:
        raise ValueError("Turno invalido")
    # Cached counts are not authoritative for the selected target tokenizer.
    tok = tokens_of(content, tokenizer)
    return TurnView(role, content, tok, bool(getattr(turn, "pinned", False)))


def partition_turns(views, keep_recent):
    pinned = [v for v in views if v.pinned or v.role == "system"]
    rest = [v for v in views if not (v.pinned or v.role == "system")]
    recent = rest[-keep_recent:] if keep_recent > 0 else []
    middle = rest[: len(rest) - len(recent)]
    return pinned, middle, recent


def offload_large_blocks(middle, storage_dir, max_inline_tokens, tokenizer=None, *, protect_users=False):
    os.makedirs(storage_dir, exist_ok=True)
    out, count = [], 0
    for v in middle:
        if (v.token_count > max_inline_tokens and not has_code(v)
                and not (protect_users and v.role == "user")):
            raw = v.content.encode("utf-8")
            digest = hashlib.sha256(raw).hexdigest()
            filename = f"offloaded-{digest}.txt"
            path = os.path.join(storage_dir, filename)
            if os.path.islink(path):
                raise ValueError("Referencia local no puede ser un enlace simbolico")
            try:
                with open(path, "xb") as fh:
                    fh.write(raw)
                    fh.flush()
                    os.fsync(fh.fileno())
            except FileExistsError:
                pass
            if not os.path.isfile(path) or os.path.islink(path):
                raise ValueError("Referencia local no es un archivo regular")
            with open(path, "rb") as fh:
                if fh.read() != raw:
                    raise ValueError("Referencia local corrupta; no se sobrescribe")
            pointer = f"[turno ({v.role}, {v.token_count} tokens) movido a archivo local '{filename}']"
            out.append(TurnView(v.role, pointer, tokens_of(pointer, tokenizer), v.pinned))
            count += 1
        else:
            out.append(v)
    return out, count


def assemble_context(pinned, summary, middle, recent):
    if any(v.role != "system" for v in pinned):
        raise ValueError("El compactador legacy no puede reordenar turnos fijados no-system")
    head = [v.content for v in pinned] + [HERMES_WRAPPER]
    messages = [{"role": "system", "content": "\n\n".join(head)}]
    if summary:
        # Generated historical text is data, never a system instruction.
        messages.append({"role": "assistant", "content": SUMMARY_INTRO + "\n\n" + summary})
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
        "token_accounting": "content_only_estimate",
        "verification": {"status": "not_verified"},
    }


def compact_history(history: Sequence, num_ctx: int, level=None,
                    summarizer: Callable | None = None, storage_dir=None, tokenizer=None,
                    *, protect_users=False):
    if type(num_ctx) is not int or num_ctx <= 0:
        raise ValueError("num_ctx debe ser un entero positivo")
    policy = get_policy(level)
    views = [to_view(t, tokenizer) for t in history]
    if any(v.role == "tool" for v in views):
        raise ValueError("El compactador legacy no conserva el protocolo de herramientas")
    before = sum(v.token_count for v in views)
    if before < policy.triggers_at(num_ctx):
        msgs = [{"role": v.role if v.role in _VALID_ROLES else "user", "content": v.content} for v in views]
        return msgs, _report(policy, num_ctx, before, before, False, {})

    pinned, middle, recent = partition_turns(views, policy.keep_recent_turns)
    offloaded = 0
    if storage_dir and policy.offload_enabled and middle:
        middle, offloaded = offload_large_blocks(middle, storage_dir, policy.offload_max_inline_tokens, tokenizer,
                                                 protect_users=protect_users)

    # reserva: wrapper + encabezado del resumen + separadores del mensaje system
    overhead = tokens_of(HERMES_WRAPPER, tokenizer) + tokens_of(SUMMARY_INTRO, tokenizer) + 4
    budget = num_ctx - sum(v.token_count for v in pinned) - sum(v.token_count for v in recent) - overhead
    if budget < 100:
        raise ValueError("Ventana insuficiente: instrucciones fijadas + turnos recientes no caben en num_ctx.")

    summary, summarized, dropped, code_kept, code_dropped = None, 0, 0, 0, 0
    middle_kept = list(middle)
    if middle and sum(v.token_count for v in middle) > budget:
        code_idx = [i for i, v in enumerate(middle) if has_code(v)]
        mandatory = [i for i, v in enumerate(middle)
                     if has_code(v) or (protect_users and v.role == "user")]
        mandatory_set = set(mandatory)
        prose_idx = [i for i in range(len(middle)) if i not in mandatory_set]
        reserve = min(policy.max_summary_tokens, budget // 3) if (summarizer and prose_idx) else 0
        if protect_users:
            reserve = min(reserve, max(0, budget - sum(middle[i].token_count for i in mandatory)))
        keep, used = set(), 0
        for i in reversed(mandatory):
            t = middle[i].token_count
            if used + t <= budget - reserve:
                keep.add(i)
                used += t
            elif i in code_idx:
                code_dropped += 1
            else:
                dropped += 1
        code_kept = sum(i in keep for i in code_idx)
        remaining = budget - used
        prose = [middle[i] for i in prose_idx]
        if summarizer and prose and remaining > 0 and (not protect_users or reserve > 0):
            summary = summarizer(prose)
            summarized = len(prose)
            limit = min(remaining, policy.max_summary_tokens)
            if not isinstance(summary, str) or tokens_of(summary, tokenizer) > limit:
                raise ValueError("Resumen excede presupuesto; no se trunca silenciosamente")
        else:
            u = 0
            for i in reversed(prose_idx):
                t = middle[i].token_count
                if u + t <= remaining:
                    keep.add(i)
                    u += t
                else:
                    dropped += 1
        middle_kept = [middle[i] for i in range(len(middle)) if i in keep]

    messages = assemble_context(pinned, summary, middle_kept, recent)
    after = sum(tokens_of(m["content"], tokenizer) for m in messages)
    if after > num_ctx:
        raise ValueError("Contexto ensamblado excede el presupuesto")
    actions = {"offloaded": offloaded, "summarized_turns": summarized, "dropped_turns": dropped,
               "kept_recent": len(recent), "pinned": len(pinned), "middle_kept": len(middle_kept),
               "code_turns_kept": code_kept, "code_turns_dropped": code_dropped}
    return messages, _report(policy, num_ctx, before, after, True, actions)
