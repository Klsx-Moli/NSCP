"""Fail-closed route *planning*, not execution or a quality certificate.

A ready engine is explicitly available and healthy. No model or tool call
is performed here. Every non-passthrough route requires later verification.
"""
from __future__ import annotations

from dataclasses import dataclass

ENGINES = frozenset({"deterministic", "bm25", "embedding", "reranker", "extractive", "compactor"})
NEEDS = frozenset({"none", "literal", "semantic", "extractive"})
HEALTH = frozenset({"ready", "unhealthy", "unknown", "unavailable"})


@dataclass(frozen=True)
class RouteDecision:
    route: str
    engines: tuple[str, ...]
    reason: str
    requires_verification: bool
    unresolved_need: str | None = None


def choose_route(*, context_tokens, request_budget, need, health,
                 allow_generative=False, allow_rerank=False, critical_risk=False):
    """Select a candidate route; missing evidence never becomes readiness.

    request_budget must already reserve the output/tools budget. This planner
    does not estimate actual reduction, guarantee fit, or authorize actions.
    """
    if (type(context_tokens) is not int or context_tokens < 0
            or type(request_budget) is not int or request_budget <= 0):
        raise ValueError("Invalid measured context or budget")
    if not isinstance(need, str) or need not in NEEDS:
        raise ValueError("Invalid retrieval need")
    if not isinstance(health, dict) or any(
            not isinstance(k, str) or k not in ENGINES or not isinstance(v, str) or v not in HEALTH
            for k, v in health.items()):
        raise ValueError("Invalid health state")
    if any(type(x) is not bool for x in (allow_generative, allow_rerank, critical_risk)):
        raise ValueError("Expected explicit boolean policy")
    ready = {k for k, v in health.items() if v == "ready"}
    pressured = context_tokens > request_budget
    if critical_risk:
        return RouteDecision("ABORT", (), "critical_risk", True, need)
    if not pressured and need == "none":
        return RouteDecision("PASSTHROUGH", (), "within_measured_budget", False)
    if need == "semantic":
        if "embedding" not in ready:
            # Lexical recovery is not a demonstrated substitute for semantic
            # retrieval; expose unresolved need instead of claiming success.
            return RouteDecision("RECOVERY", (), "semantic_engine_not_ready", True, need)
        if allow_rerank and "reranker" in ready:
            return RouteDecision("EMBEDDING_RERANK", ("embedding", "reranker"),
                                 "explicit_rerank_opt_in", True)
        return RouteDecision("EMBEDDING", ("embedding",), "semantic_need", True)
    if need == "literal":
        if "bm25" in ready:
            return RouteDecision("BM25", ("bm25",), "literal_need", True)
        return RouteDecision("RECOVERY", (), "lexical_engine_not_ready", True, need)
    if need == "extractive":
        if "extractive" in ready:
            return RouteDecision("EXTRACTIVE", ("extractive",), "extractive_need", True)
        return RouteDecision("RECOVERY", (), "extractive_engine_not_ready", True, need)
    if "deterministic" in ready:
        return RouteDecision("DETERMINISTIC", ("deterministic",), "over_budget", True)
    if allow_generative and "compactor" in ready:
        return RouteDecision("COMPACTOR", ("compactor",), "explicit_generative_opt_in", True)
    return RouteDecision("ABORT", (), "no_ready_budget_reduction", True, "budget")
