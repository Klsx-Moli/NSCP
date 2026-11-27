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
