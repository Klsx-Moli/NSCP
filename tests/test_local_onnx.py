import pytest

from local_onnx import TokenScore, bind_offsets, keep_scores, plan_log_preview


def test_ctxprune_softmax_not_sigmoid_and_shift_invariant():
    logits = [[[-100, -99], [100, 99], [1000, 1000]]]
    scores = keep_scores("ctxprune", logits, 3)
    assert scores[0] > 0.7 and scores[1] < 0.3 and scores[2] == 0.5
    shifted = [[[a + 500, b + 500] for a, b in logits[0]]]
    assert scores == keep_scores("ctxprune", shifted, 3)


@pytest.mark.parametrize("kind, output", [
    ("kompress", [[float("nan")]]), ("kompress", [[1.1]]),
    ("kompress", [[True]]), ("kompress", [[[0.3]]]),
    ("ctxprune", [[[1, 2, 3]]]), ("ctxprune", [[[float("inf"), 0]]]),
    ("ctxprune", [[0.5]]), ("ctxprune", [[]]),
])
def test_invalid_scores_rejected(kind, output):
    with pytest.raises(ValueError):
        keep_scores(kind, output, 1)


def test_exact_unicode_offsets_and_special_tokens():
    text = "ñ 😀"
    rows = bind_offsets(text, [(0, 0), (0, 1), (2, 3), (0, 0)],
                        [1, 0, 0, 1], [0.9, 0.4, 0.5, 0.9])
    assert [text[s.start:s.end] for s in rows] == ["ñ", "😀"]
    with pytest.raises(ValueError):
        bind_offsets(text, [(0, 4)], [0], [0.5])
    with pytest.raises(ValueError):
        bind_offsets(text, [(0, 0)], [0], [0.5])


def fixture():
    text = ("ordinary chatter line\n" * 80 + "ERROR tests/test_agent_context.py missing\n"
            + "permission revoked: never publish\n" + "información útil única 😀\n"
            + "ordinary chatter line\n" * 80)
    scores = [TokenScore(0, len(text), 0.1)]
    start = text.index("información")
    scores.append(TokenScore(start, start + len("información útil única 😀"), 0.99))
    return text, scores


def test_preview_preserves_critical_lines_and_exact_text():
    text, scores = fixture()
    p = plan_log_preview(text, scores, 650, protected_terms=["útil"])
    assert p["status"] == "preview" and p["preview_bytes"] <= 650
    assert p["semantic_equivalence"] == "not_verified"
    spans = p["preview"]["spans"]
    assert all(s["text"] == text[s["start"]:s["end"]] for s in spans)
    assert any("ERROR" in s["text"] for s in spans)
    assert any("never publish" in s["text"] for s in spans)
    assert any("información útil única 😀" in s["text"] for s in spans)


def test_protected_budget_failure_and_no_silent_empty_output():
    text, scores = fixture()
    p = plan_log_preview(text, scores, 100)
    assert p["status"] == "protected_budget_unmet" and p["preview"] is None
    assert plan_log_preview(text, [], 650)["status"] == "no_scores"
    assert plan_log_preview("short", [TokenScore(0, 5, 0.1)], 50)["status"] == "unchanged"


def test_unscored_nonempty_lines_are_not_dropped():
    text = "unscored first\n" + "long filler\n" * 50
    rows = [TokenScore(len("unscored first\n"), len(text), 1.0)]
    plan = plan_log_preview(text, rows, 400)
    assert plan["status"] == "preview"
    assert plan["protected_lines"] == 1
    assert plan["preview"]["spans"][0]["text"] == "unscored first\n"
