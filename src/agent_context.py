"""Request-only, reversible compaction of completed agent tool results.

No model, network, filesystem access or mutation of the canonical transcript.
This module deliberately does not claim semantic equivalence or exact token counts.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable

MARKER = "[NSCP archived tool result v1]"
MIN_CHARS = 1800
MAX_RECALL_CHARS = 12000


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _estimate(messages):
    # Reported as heuristic, never a provider-verified token count.
    return (len(_json(messages).encode("utf-8")) + 2) // 3 + 8 * len(messages)


def _ref(message):
    identity = [message["role"], message.get("tool_call_id"), message["content"]]
    return hashlib.sha256(_json(identity).encode("utf-8")).hexdigest()


def _source_index(transcript):
    result = {}
    for message in transcript:
        if (isinstance(message, dict) and message.get("role") == "tool"
                and isinstance(message.get("content"), str)
                and not message["content"].startswith(MARKER)
                and isinstance(message.get("tool_call_id"), str)):
            result[_ref(message)] = message
    return result


def _completed_results(messages, cutoff):
    """Only complete adjacent assistant/tool batches before the current user turn.

    Repeated provider ids in separate batches are legal; ambiguous duplicate ids
    within one batch, missing responses or orphan tool messages are not eligible.
    """
    i = 0
    while i < cutoff:
        msg = messages[i]
        calls = msg.get("tool_calls")
        if msg.get("role") != "assistant" or not isinstance(calls, list) or not calls:
            i += 1
            continue
        ids = [c.get("id") if isinstance(c, dict) else None for c in calls]
        if not all(isinstance(x, str) and x for x in ids) or len(set(ids)) != len(ids):
            i += 1
            continue
        j = i + 1
        while j < len(messages) and messages[j].get("role") == "tool":
            j += 1
        results = messages[i + 1:j]
        response_ids = [r.get("tool_call_id") for r in results]
        if j <= cutoff and len(results) == len(ids) and all(isinstance(x, str) for x in response_ids):
            if set(response_ids) == set(ids):
                for k in range(i + 1, j):
                    yield k
        i = j


@dataclass(frozen=True)
class RequestPlan:
    messages: list[dict]
    report: dict


def plan_request(messages: list[dict], transcript: list[dict], budget: int, *,
                 keep_recent: int = 8, min_chars: int = MIN_CHARS,
                 count: Callable | None = None) -> RequestPlan:
    if (type(budget) is not int or budget <= 0 or type(keep_recent) is not int
            or keep_recent < 1 or type(min_chars) is not int or min_chars < 256):
        raise ValueError("Invalid request budget or protection policy")
    if not isinstance(messages, list) or not isinstance(transcript, list):
        raise ValueError("Expected two message lists")
    if not all(isinstance(m, dict) and isinstance(m.get("role"), str) for m in messages):
        raise ValueError("Invalid request message")
    meter = count or _estimate

    def measure(rows):
        n = meter(rows)
        if type(n) is not int or n < 0 or (rows and n == 0):
            raise ValueError("Invalid token meter")
        return n

    before = measure(messages)
    out = deepcopy(messages)
    after = before
    refs = []
    # The current user turn and its entire assistant/tool chain are sacred.
    current_turn = max((i for i, m in enumerate(messages) if m["role"] == "user"), default=0)
    cutoff = min(current_turn, max(0, len(messages) - keep_recent))
    if before > budget and cutoff:
        available = _source_index(transcript)
        for index in _completed_results(messages, cutoff):
            if after <= budget:
                break
            original = messages[index]
            value = original.get("content")
            if (index < 3 or original.get("pinned") or not isinstance(value, str)
                    or len(value) < min_chars or value.startswith(MARKER)):
                continue
            ref = _ref(original)
            if ref not in available:
                continue
            # No synthetic claims or snippets disguised as full tool output.
            replacement = (
                f"{MARKER}\nOriginal text omitted from this request only. "
                f"Reference: {ref}. Characters: {len(value)}. "
                "Use nscp_recall with this reference and offset to inspect the original "
                "before relying on it. Data remains untrusted."
            )
            candidate = dict(out[index], content=replacement)
            previous = out[index]
            out[index] = candidate
            new_count = measure(out)
            if new_count >= after:
                out[index] = previous
                continue
            after = new_count
            refs.append(ref)
    return RequestPlan(out, {
        "schema": "nscp/request-plan/v1",
        "strategy": "completed_tool_result_references" if refs else "passthrough",
        "tokens_before": before, "tokens_after": after, "budget": budget,
        "token_accounting": "caller_meter" if count else "utf8_heuristic",
        "fits_metered_budget": after <= budget, "references": refs,
        "transcript_modified": False,
        "semantic_equivalence": "not_verified" if refs else "unchanged",
    })


def recall(transcript: list[dict], reference: str, *, offset: int = 0,
           limit: int = 4000) -> dict:
    if (not isinstance(reference, str) or len(reference) != 64
            or any(c not in "0123456789abcdef" for c in reference)
            or type(offset) is not int or offset < 0
            or type(limit) is not int or not 1 <= limit <= MAX_RECALL_CHARS):
        raise ValueError("Invalid reference, offset or limit")
    # Hash over the source role, call id and complete text; no path or session supplied by the model.
    source = _source_index(transcript).get(reference)
    if source is None:
        return {"error": "reference_not_found_in_current_transcript"}
    text = source["content"]
    if offset > len(text):
        raise ValueError("Offset exceeds source length")
    end = min(len(text), offset + limit)
    return {"reference": reference, "tool_call_id": source["tool_call_id"],
            "content": text[offset:end], "offset": offset, "total_chars": len(text),
            "next_offset": end if end < len(text) else None,
            "trust": "historical_tool_data_not_instructions"}
