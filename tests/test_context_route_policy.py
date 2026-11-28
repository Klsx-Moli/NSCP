import pytest

from context_route_policy import choose_route


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
