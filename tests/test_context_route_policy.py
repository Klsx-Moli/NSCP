import itertools

import pytest

from context_route_policy import choose_route, plan_resource_route


def route(**kwargs):
    params = dict(context_tokens=100, request_budget=100, need="none", health={})
    params.update(kwargs)
    return choose_route(**params)


def test_no_pressure_no_inference():
    assert route().route == "PASSTHROUGH"
    assert not route().requires_verification
    assert route(context_tokens=101).route == "ABORT"


@pytest.mark.parametrize("health", [{}, {"embedding": "unknown"}, {"embedding": "unhealthy"},
                                    {"bm25": "ready"}, {"reranker": "ready"}])
def test_semantic_need_not_promoted_to_satisfied(health):
    result = route(need="semantic", health=health)
    assert result.route == "RECOVERY"
    assert result.unresolved_need == "semantic"
    assert not result.engines


def test_no_implicit_rrf_or_reranker():
    health = {"embedding": "ready", "bm25": "ready", "reranker": "ready"}
    assert route(need="semantic", health=health).engines == ("embedding",)
    assert route(need="semantic", health=health, allow_rerank=True).engines == ("embedding", "reranker")
    health["reranker"] = "unhealthy"
    assert route(need="semantic", health=health, allow_rerank=True).engines == ("embedding",)


def test_deterministic_first_and_generative_explicit():
    health = {"deterministic": "ready", "compactor": "ready"}
    assert route(context_tokens=101, health=health, allow_generative=True).route == "DETERMINISTIC"
    assert route(context_tokens=101, health={"compactor": "ready"}).route == "ABORT"
    assert route(context_tokens=101, health={"compactor": "ready"}, allow_generative=True).route == "COMPACTOR"
    assert route(critical_risk=True, health=health).route == "ABORT"


@pytest.mark.parametrize("kwargs", [
    {"context_tokens": -1}, {"context_tokens": True}, {"request_budget": 0},
    {"request_budget": float("nan")}, {"need": "invented"}, {"health": {"embedding": True}},
    {"health": {"embedding": []}}, {"allow_rerank": "false"}, {"critical_risk": 1},
])
def test_invalid_policy_rejected(kwargs):
    with pytest.raises(ValueError):
        route(**kwargs)


def pair(ram, vram):
    return {"ram_bytes": ram, "vram_bytes": vram}


def resource_plan(**kwargs):
    params = dict(capacity=pair(10, 10), reserve=pair(2, 2),
                  costs={"embedding": pair(4, 4), "reranker": pair(5, 5), "bm25": pair(1, 0)},
                  context_tokens=101, request_budget=100, need="semantic",
                  health={"embedding": "ready", "reranker": "ready", "bm25": "ready"},
                  allow_rerank=True)
    params.update(kwargs)
    return plan_resource_route(**params)


def test_combined_admission_and_boundary():
    result = resource_plan()
    assert result["decision"]["route"] == "EMBEDDING"
    assert result["resource_exclusions"]["reranker"] == "combined:capacity_insufficient:ram_bytes"
    result = resource_plan(capacity=pair(11, 11))
    assert result["decision"]["route"] == "EMBEDDING_RERANK"
    assert result["selected_additional_peak_bytes"] == pair(9, 9)


def test_unknown_is_not_capacity_or_health():
    assert resource_plan(capacity=pair(10, None))["decision"]["route"] == "RECOVERY"
    assert resource_plan(costs={})["decision"]["unresolved_need"] == "semantic"
    assert resource_plan(health={"embedding": "unknown"})["decision"]["route"] == "RECOVERY"
    assert resource_plan(critical_risk=True)["decision"]["route"] == "ABORT"
    assert resource_plan(need="none", context_tokens=100, capacity=pair(None, None))["decision"]["route"] == "PASSTHROUGH"


def test_cpu_only_and_opt_in():
    result = resource_plan(need="literal", capacity=pair(10, None), reserve=pair(2, 0))
    assert result["decision"]["route"] == "BM25"
    result = resource_plan(need="none", health={"compactor": "ready"}, costs={"compactor": pair(1, 0)})
    assert result["decision"]["route"] == "ABORT"
    result = resource_plan(need="none", health={"compactor": "ready"}, costs={"compactor": pair(1, 0)}, allow_generative=True)
    assert result["decision"]["route"] == "COMPACTOR"


@pytest.mark.parametrize("kw", [
    {"capacity": pair(True, 10)}, {"capacity": pair(-1, 10)},
    {"reserve": pair(None, 0)}, {"costs": {"embedding": pair(1.0, 0)}},
    {"costs": {"unknown": pair(0, 0)}}, {"health": {"embedding": "invented"}},
    {"capacity": {"ram_bytes": 10}}, {"reserve": pair(0, float("nan"))},
])
def test_invalid_resource_inputs(kw):
    with pytest.raises(ValueError):
        resource_plan(**kw)


def test_admission_exhaustive_small_grid():
    for ram, vram, e, r in itertools.product(range(5), repeat=4):
        costs = {"embedding": pair(e, e), "reranker": pair(r, r)}
        result = resource_plan(capacity=pair(ram, vram), reserve=pair(1, 1), costs=costs)
        route = result["decision"]["route"]
        fits_embedding = e + 1 <= min(ram, vram)
        fits_both = e + r + 1 <= min(ram, vram)
        assert route == ("EMBEDDING_RERANK" if fits_both else "EMBEDDING" if fits_embedding else "RECOVERY")
        assert result["execution"] == "not_executed"
