from copy import deepcopy

import pytest

from agent_context import MARKER, plan_request, recall


def transcript():
    return [
        {"role": "system", "content": "Never modify main."},
        {"role": "user", "content": "Inspect repository."},
        {"role": "assistant", "content": "I will inspect."},
        {"role": "assistant", "content": None,
         "tool_calls": [{"id": "call_1", "type": "function",
                         "function": {"name": "terminal", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "call_1", "content": "old log " * 1500,
         "message_uid": "tool-uid", "_tool_call_uid": "occurrence-1"},
        {"role": "assistant", "content": "Old inspection complete."},
        {"role": "user", "content": "Continue. Do not push."},
        {"role": "assistant", "content": None,
         "tool_calls": [{"id": "call_1", "type": "function",
                         "function": {"name": "terminal", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "call_1", "content": "active log " * 1500},
    ]


def test_request_only_and_protocol_preserved():
    source = transcript()
    before = deepcopy(source)
    result = plan_request(source, source, 6000, keep_recent=1)
    assert source == before
    assert len(result.messages) == len(source)
    assert result.report["references"]
    assert result.messages[4]["content"].startswith(MARKER)
    for i in range(len(source)):
        if i != 4:
            assert result.messages[i] == source[i]
    assert {k: v for k, v in result.messages[4].items() if k != "content"} == {
        k: v for k, v in source[4].items() if k != "content"}
    assert result.report["tokens_after"] < result.report["tokens_before"]


def test_recall_exact_pagination_and_isolation():
    source = transcript()
    result = plan_request(source, source, 6000, keep_recent=1)
    ref = result.report["references"][0]
    pieces, offset = [], 0
    while offset is not None:
        part = recall(source, ref, offset=offset, limit=997)
        pieces.append(part["content"])
        offset = part["next_offset"]
    assert "".join(pieces) == source[4]["content"]
    assert "error" in recall(source[5:], ref)
    with pytest.raises(ValueError):
        recall(source, "../private")
    with pytest.raises(ValueError):
        recall(source, ref, limit=12001)


def test_missing_original_never_creates_unrecoverable_reference():
    source = transcript()
    result = plan_request(source, source[5:], 100, keep_recent=1)
    assert result.messages == source
    assert not result.report["fits_metered_budget"]
    assert not result.report["references"]


def test_missing_or_ambiguous_tool_result_preserved():
    source = transcript()
    source[3]["tool_calls"].append({"id": "missing"})
    assert plan_request(source, source, 100, keep_recent=1).messages == source
    source = transcript()
    source[3]["tool_calls"].append({"id": "call_1"})
    assert plan_request(source, source, 100, keep_recent=1).messages == source


def test_replay_stable_and_no_recursive_reference():
    source = transcript()
    a = plan_request(source, source, 100, keep_recent=1)
    b = plan_request(source, source, 100, keep_recent=1)
    c = plan_request(a.messages, source, 100, keep_recent=1)
    assert a == b and c.messages == a.messages
    assert not c.report["references"]


def test_pinned_and_multimodal_results_are_protected():
    source = transcript()
    source[4]["pinned"] = True
    assert plan_request(source, source, 100, keep_recent=1).messages == source
    source[4]["pinned"] = False
    source[4]["content"] = [{"type": "text", "text": "x" * 10000}]
    assert plan_request(source, source, 100, keep_recent=1).messages == source


def test_meter_no_reduction_does_not_rewrite():
    source = transcript()
    result = plan_request(source, source, 100, keep_recent=1, count=lambda _: 1000)
    assert result.messages == source
    assert not result.report["references"]


def test_invalid_budget_and_meter():
    source = transcript()
    for value in (0, -1, True, float("nan")):
        with pytest.raises(ValueError):
            plan_request(source, source, value)
    with pytest.raises(ValueError):
        plan_request(source, source, 100, count=lambda _: -1)


def multi_history():
    source = transcript()[:3]
    for i, size in enumerate((2500, 3000, 9000)):
        source.extend([
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": str(i), "type": "function", "function": {"name": "read", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": str(i), "content": chr(97 + i) * size},
            {"role": "assistant", "content": "done"},
        ])
    source.append({"role": "user", "content": "continue"})
    return source


def test_cache_prefix_prefers_newest_eligible_result():
    source = multi_history()
    from agent_context import _estimate
    budget = _estimate(source) - 500
    old = plan_request(source, source, budget, strategy="oldest", keep_recent=1)
    new = plan_request(source, source, budget, strategy="cache_prefix", keep_recent=1)
    assert old.report["fits_metered_budget"] and new.report["fits_metered_budget"]
    assert new.report["unchanged_prefix_messages"] > old.report["unchanged_prefix_messages"]
    assert new.report["unchanged_prefix_messages"] == 10


def test_focus_path_and_sidecar_protected_in_every_strategy():
    source = multi_history()
    source[4]["content"] += " src/core.py"
    source[7]["api_content"] = [{"type": "text", "text": "provider-specific"}]
    source[-1]["content"] = "Investigate src/core.py"
    for strategy in ("oldest", "cache_prefix", "relevance", "adaptive"):
        plan = plan_request(source, source, 1, strategy=strategy, keep_recent=1)
        assert plan.messages[4] == source[4]
        assert plan.messages[7] == source[7]
        assert plan.messages[10]["content"].startswith(MARKER)
        assert plan.report["focus_protected"] == 1
        assert plan.report["sidecar_protected"] == 1


def test_incremental_estimate_matches_full_unicode_and_custom_meter():
    from agent_context import _estimate
    source = multi_history()
    source[4]["content"] = "ñ😀漢字\n" * 3000
    a = plan_request(source, source, 100, keep_recent=1)
    b = plan_request(source, source, 100, keep_recent=1, count=_estimate)
    assert a.messages == b.messages
    assert a.report["tokens_after"] == b.report["tokens_after"] == _estimate(a.messages)


def test_adaptive_selects_route_by_pressure():
    from agent_context import _estimate
    source = multi_history()
    near = plan_request(source, source, _estimate(source) - 100, strategy="adaptive", keep_recent=1)
    far = plan_request(source, source, 1, strategy="adaptive", keep_recent=1)
    assert near.report["selected_strategy"] == "cache_prefix"
    assert far.report["selected_strategy"] == "relevance"
    with pytest.raises(ValueError):
        plan_request(source, source, 10, strategy="invented")
    with pytest.raises(ValueError):
        plan_request(source, source, 10, focus_terms=[""])


def test_output_metadata_is_independently_owned():
    source = multi_history()
    source[4]["metadata"] = {"nested": {"values": [1]}}
    plan = plan_request(source, source, 1, keep_recent=1)
    assert plan.messages[4]["content"].startswith(MARKER)
    plan.messages[4]["metadata"]["nested"]["values"].append(2)
    assert source[4]["metadata"]["nested"]["values"] == [1]


def test_parent_pin_and_recall_results_are_not_elided():
    source = multi_history()
    source[3]["pinned"] = True
    source[6]["tool_calls"][0]["function"]["name"] = "nscp_recall"
    result = plan_request(source, source, 1, keep_recent=1, strategy="adaptive")
    assert result.messages[4] == source[4]
    assert result.messages[7] == source[7]
    assert result.messages[10]["content"].startswith(MARKER)
    assert result.report["lineage_protected"] == 2


def test_focus_can_match_tool_arguments_without_matching_output():
    source = multi_history()
    source[3]["tool_calls"][0]["function"]["arguments"] = '{"path":"src/important.py"}'
    source[-1]["content"] = "Review src/important.py"
    result = plan_request(source, source, 1, keep_recent=1, strategy="adaptive")
    assert result.messages[4] == source[4]
    assert result.report["focus_protected"] == 1


def test_protect_first_does_not_split_protected_parent_from_result():
    source = multi_history()
    result = plan_request(source, source, 1, keep_recent=1, protect_first=4)
    assert result.messages[4] == source[4]
    assert result.report["lineage_protected"] == 1



def test_independent_gate_detects_tampering_and_source_loss():
    from copy import deepcopy
    from agent_context import RequestPlan, _estimate, verify_request_plan
    rows = transcript()
    plan = plan_request(rows, rows, 4500, keep_recent=1)
    assert plan.report["references"]
    assert verify_request_plan(rows, rows, plan, 4500, keep_recent=1)["status"] == "structurally_verified"
    with pytest.raises(ValueError, match="canonical source"):
        verify_request_plan(rows, [], plan, 4500, keep_recent=1)
    for mode in ("role", "marker", "reference", "recent"):
        new = deepcopy(plan.messages)
        report = deepcopy(plan.report)
        idx = next(i for i, (a, b) in enumerate(zip(rows, new)) if a != b)
        if mode == "role":
            new[idx]["role"] = "assistant"
        elif mode == "marker":
            new[idx]["content"] += " fabricated"
        elif mode == "reference":
            report["references"] = ["0" * 64]
        else:
            new[-1]["content"] = "tampered"
        report["tokens_after"] = _estimate(new)
        report["fits_metered_budget"] = report["tokens_after"] <= 4500
        with pytest.raises(ValueError):
            verify_request_plan(rows, rows, RequestPlan(new, report), 4500, keep_recent=1)



def test_context_envelope_reserves_and_rejects_nonpositive_input():
    from agent_context import available_request_budget
    assert available_request_budget(8192, output=1024, tools=512, framing=128) == 6528
    for kwargs in ({"output": 8192}, {"output": True}, {"output": 0}, {"output": 1, "tools": -1}):
        with pytest.raises(ValueError):
            available_request_budget(8192, **kwargs)
