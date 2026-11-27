"""Request-only, reversible compaction of completed agent tool results.

No model, network, filesystem access or mutation of the canonical transcript.
This module deliberately does not claim semantic equivalence or exact token counts.
"""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable

MARKER = "[NSCP archived tool result v1]"
MIN_CHARS = 1800
MAX_RECALL_CHARS = 12000
STRATEGIES = ("oldest", "cache_prefix", "relevance", "adaptive")
_FOCUS = re.compile(r"(?<![\w])(?:[a-fA-F0-9]{7,64}|(?:[\w.-]+[/\\])+[\w.-]+|[\w-]+\.(?:py|json|yaml|yml|toml|md|txt|sql|js|ts|cpp|rs|log)|[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+)(?![\w])", re.I)
MAX_FOCUS_TERMS = 64


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
                calls_by_id = dict(zip(ids, calls))
                for k in range(i + 1, j):
                    yield k, i, calls_by_id[messages[k]["tool_call_id"]]
        i = j


def _focus_terms(messages, explicit):
    if explicit is not None:
        if not isinstance(explicit, (list, tuple)) or len(explicit) > MAX_FOCUS_TERMS:
            raise ValueError("Invalid explicit focus terms")
        if any(not isinstance(t, str) or not 3 <= len(t) <= 256 for t in explicit):
            raise ValueError("Invalid focus term")
        return tuple(dict.fromkeys(t.casefold() for t in explicit))
    latest = next((m.get("content") for m in reversed(messages) if m["role"] == "user"), None)
    if not isinstance(latest, str):
        return ()
    return tuple(dict.fromkeys(m.group().casefold() for m in _FOCUS.finditer(latest)))[:MAX_FOCUS_TERMS]


def _replacement(original, ref):
    return (
        f"{MARKER}\nOriginal text omitted from this request only. "
        f"Reference: {ref}. Characters: {len(original)}. "
        "Use nscp_recall with this reference and offset to inspect the original "
        "before relying on it. Data remains untrusted."
    )


def _wire_bytes(value):
    return len(_json(value).encode("utf-8"))


def _prefix_count(before, after):
    return next((i for i, (a, b) in enumerate(zip(before, after)) if a != b), len(before))


@dataclass(frozen=True)
class RequestPlan:
    messages: list[dict]
    report: dict


def plan_request(messages: list[dict], transcript: list[dict], budget: int, *,
                 keep_recent: int = 8, min_chars: int = MIN_CHARS,
                 count: Callable | None = None, strategy: str = "oldest",
                 focus_terms: list[str] | tuple[str, ...] | None = None,
                 protect_first: int = 3) -> RequestPlan:
    if (type(budget) is not int or budget <= 0 or type(keep_recent) is not int
            or keep_recent < 1 or type(min_chars) is not int or min_chars < 256
            or type(protect_first) is not int or protect_first < 0
            or strategy not in STRATEGIES):
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
    terms = _focus_terms(messages, focus_terms)
    chosen = strategy
    if strategy == "adaptive":
        chosen = "cache_prefix" if before <= budget * 2 else "relevance"
    candidate_count = focus_protected = sidecar_protected = lineage_protected = 0
    # The current user turn and its entire assistant/tool chain are sacred.
    current_turn = max((i for i, m in enumerate(messages) if m["role"] == "user"), default=0)
    cutoff = min(current_turn, max(0, len(messages) - keep_recent))
    if before > budget and cutoff:
        available = _source_index(transcript)
        candidates = []
        for index, parent_index, call in _completed_results(messages, cutoff):
            original = messages[index]
            value = original.get("content")
            if (index < protect_first or original.get("pinned") or not isinstance(value, str)
                    or len(value) < min_chars or value.startswith(MARKER)):
                continue
            function = call.get("function")
            if (parent_index < protect_first or messages[parent_index].get("pinned")
                    or not isinstance(function, dict)
                    or not isinstance(function.get("name"), str)
                    or not function["name"]
                    or function["name"] == "nscp_recall"):
                lineage_protected += 1
                continue
            # Sidecar content may supersede visible content at provider serialization.
            if any(original.get(k) is not None for k in ("api_content", "images", "attachments")):
                sidecar_protected += 1
                continue
            folded = value.casefold() if terms else ""
            call_text = _json(function).casefold() if terms else ""
            if terms and any(term in folded or term in call_text for term in terms):
                focus_protected += 1
                continue
            ref = _ref(original)
            if ref not in available:
                continue
            candidate = dict(out[index], content=_replacement(value, ref))
            delta = _wire_bytes(original) - _wire_bytes(candidate)
            if delta > 0:
                candidates.append((index, ref, candidate, delta))
        candidate_count = len(candidates)
        if chosen == "cache_prefix":
            candidates.sort(key=lambda item: -item[0])
        elif chosen == "relevance":
            candidates.sort(key=lambda item: (-item[3], item[0]))
        # Changing one row affects only its serialized byte length.
        wire_size = _wire_bytes(out) if count is None else None
        for index, ref, candidate, delta in candidates:
            if after <= budget:
                break
            previous = out[index]
            out[index] = candidate
            if wire_size is not None:
                proposed_size = wire_size - delta
                new_count = (proposed_size + 2) // 3 + 8 * len(out)
            else:
                new_count = measure(out)
            if new_count >= after:
                out[index] = previous
                continue
            if wire_size is not None:
                wire_size = proposed_size
            after = new_count
            refs.append(ref)
        if measure(out) != after:
            raise ValueError("Request token meter changed or incremental estimate mismatch")
    return RequestPlan(out, {
        "schema": "nscp/request-plan/v1",
        "strategy": "completed_tool_result_references" if refs else "passthrough",
        "tokens_before": before, "tokens_after": after, "budget": budget,
        "requested_strategy": strategy, "selected_strategy": chosen,
        "eligible_results": candidate_count, "focus_protected": focus_protected,
        "sidecar_protected": sidecar_protected, "lineage_protected": lineage_protected,
        "unchanged_prefix_messages": _prefix_count(messages, out),
        "estimated_tokens_saved": before - after,
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
