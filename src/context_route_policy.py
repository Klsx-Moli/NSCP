"""Fail-closed route *planning*, not execution or a quality certificate.

A ready engine is explicitly available and healthy. No model or tool call
is performed here. Every non-passthrough route requires later verification.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

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


_RESOURCE_KEYS = frozenset({"ram_bytes", "vram_bytes"})


def _resource_pair(value, *, unknown=False):
    if not isinstance(value, dict) or set(value) != _RESOURCE_KEYS:
        raise ValueError("Expected RAM and VRAM byte fields")
    if any(not (unknown and v is None) and (type(v) is not int or v < 0)
           for v in value.values()):
        raise ValueError("Invalid resource byte count")
    return dict(value)


def plan_resource_route(*, capacity, reserve, costs, **policy):
    """Admit only routes whose additional peak demand fits explicit estimates.

    Capacity is currently available memory, not installed hardware size.
    Costs are caller-provided conservative incremental peak bounds, including
    runtime overhead; weights on disk are not a memory estimate. No allocation,
    measurement, process management, reservation lock or inference occurs here.
    """
    capacity = _resource_pair(capacity, unknown=True)
    reserve = _resource_pair(reserve)
    if not isinstance(costs, dict) or set(costs) - ENGINES:
        raise ValueError("Invalid engine resource estimates")
    costs = {engine: _resource_pair(value) for engine, value in costs.items()}
    original = choose_route(**policy)  # validate the original routing contract
    health = dict(policy["health"])
    exclusions = {}

    def admission(engines):
        if any(engine not in costs for engine in engines):
            return "cost_unknown", None
        demand = {key: sum(costs[engine][key] for engine in engines)
                  for key in sorted(_RESOURCE_KEYS)}
        for key, required in demand.items():
            # Zero incremental use with no reserve needs no observation of
            # that memory class (e.g. an explicitly CPU-only route).
            if required == 0 and reserve[key] == 0:
                continue
            if capacity[key] is None:
                return "capacity_unknown:" + key, demand
            if required + reserve[key] > capacity[key]:
                return "capacity_insufficient:" + key, demand
        return "fits_estimates", demand

    for engine, state in sorted(health.items()):
        if state == "ready":
            reason, _ = admission((engine,))
            if reason != "fits_estimates":
                exclusions[engine] = reason
                health[engine] = "unavailable"
    decision = choose_route(**{**policy, "health": health})
    # Individually feasible engines can exceed the shared envelope together.
    # Reranking is optional; never substitute BM25 for a semantic requirement.
    if decision.route == "EMBEDDING_RERANK":
        reason, _ = admission(decision.engines)
        if reason != "fits_estimates":
            exclusions["reranker"] = "combined:" + reason
            health["reranker"] = "unavailable"
            decision = choose_route(**{**policy, "health": health})
    reason, demand = admission(decision.engines) if decision.engines else ("no_engine_selected", None)
    if decision.engines and reason != "fits_estimates":
        raise RuntimeError("Resource admission invariant failed")
    return {"schema": "nscp/resource-route/v1", "original_route": original.route,
            "decision": asdict(decision), "capacity": capacity, "reserve": reserve,
            "selected_additional_peak_bytes": demand, "resource_status": reason,
            "resource_exclusions": exclusions, "effective_health": health,
            "execution": "not_executed", "capacity_measurement": "caller_supplied",
            "semantic_equivalence": "not_verified"}
