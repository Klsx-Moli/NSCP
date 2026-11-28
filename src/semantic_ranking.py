"""Strict response attribution and retrieval metrics for local engine adapters.

This module is transport-independent: validated response data only, never a
claim that a model has actually executed. No network access.
"""
from __future__ import annotations

import math


def _number(value):
    if type(value) not in (int, float):
        raise ValueError("Expected numeric score")
    try:
        if math.isfinite(value):
            return float(value)
    except OverflowError:
        pass
    raise ValueError("Expected finite numeric score")


def _unique_ids(ids):
    if (not isinstance(ids, (tuple, list)) or any(not isinstance(i, str) or not i for i in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError("Invalid or duplicate document identities")


def rerank_results(candidate_ids, response):
    """Map server results by explicit index, not by response order.

    Full-pool responses only. If a runtime intentionally returns top_n, the
    caller must use a different explicitly bounded contract.
    """
    _unique_ids(candidate_ids)
    if not isinstance(response, dict) or not isinstance(response.get("results"), list):
        raise ValueError("Missing rerank results")
    results = response["results"]
    if len(results) != len(candidate_ids):
        raise ValueError("Incomplete rerank response")
    seen = set()
    scored = []
    for item in results:
        if not isinstance(item, dict):
            raise ValueError("Invalid result")
        i = item.get("index")
        if type(i) is not int or not 0 <= i < len(candidate_ids) or i in seen:
            raise ValueError("Invalid or duplicate rerank index")
        seen.add(i)
        scored.append((i, _number(item.get("relevance_score"))))
    return [(candidate_ids[i], score) for i, score in sorted(scored, key=lambda x: (-x[1], x[0]))]


def retrieval_metrics(ranked, gold, *, k):
    """Set-valued answer key, separate top-k retrieval and top-1 selection.

    None denotes undefined quantities for a no-answer case, not perfect recall.
    """
    _unique_ids(ranked)
    _unique_ids(gold)
    if type(k) is not int or k <= 0:
        raise ValueError("Invalid k")
    relevant = set(gold)
    selected = ranked[:k]
    matches = sum(x in relevant for x in selected)
    first = next((i for i, x in enumerate(selected, 1) if x in relevant), None)
    dcg = sum(1 / math.log2(i + 1) for i, x in enumerate(selected, 1) if x in relevant)
    ideal = sum(1 / math.log2(i + 1) for i in range(1, min(k, len(relevant)) + 1))
    precision = matches / k
    recall = matches / len(relevant) if relevant else None
    return {"recall_at_k": recall, "precision_at_k": precision,
            "top1_hit": (bool(selected and selected[0] in relevant) if relevant else None),
            "mrr_at_k": (1 / first if first else 0.0) if relevant else None,
            "ndcg_at_k": dcg / ideal if ideal else None,
            "abstained": not selected, "no_answer": not relevant,
            "false_answer": bool(selected) if not relevant else None}
