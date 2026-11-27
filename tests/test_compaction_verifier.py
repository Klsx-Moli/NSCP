import os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import random
import context_compactor as cc
import compaction_verifier as cv
sys.path.insert(0, os.path.dirname(__file__))
from compaction_helpers import build, fake_summarizer


def hist_with_facts(n=40):
    h = [cc.TurnView("system", "REGLA FIJA", pinned=True)]
    for i in range(n):
        txt = f"t{i} relleno " * 15
        if i == 2:
            txt += " Nunca uses sudo en el servidor. El puerto es 11435 y el archivo src/ollama_proxy.py."
        h.append(cc.TurnView("user" if i % 2 == 0 else "assistant", txt))
    return [cc.TurnView(v.role, v.content, cc.estimate_tokens(v.content), v.pinned) for v in h]


def test_extract_facts_kinds():
    f = cv.extract_facts("Nunca uses sudo. Ver src/a/b.py y https://x.org/p, puerto 11435, num_ctx=8192.")
    kinds = {k for k, _ in f}
    assert {"constraint", "path", "url", "number", "identifier"} <= kinds


def test_passthrough_scores_100():
    h = hist_with_facts(3)
    msgs, rep = cc.compact_history(h, 8192)
    assert cv.verify_compaction(h, msgs, rep)["score"] == 100


def test_lost_fact_lowers_score_and_reports_counts():
    h = hist_with_facts()
    msgs, rep = cc.compact_history(h, 1500)
    v = cv.verify_compaction(h, msgs, rep)
    assert v["facts_total"] >= 3 and v["facts_lost"] >= 1 and v["score"] < 100


def test_missing_code_block_is_critical():
    h = build(random.Random(3), 60, 1)
    msgs, rep = cc.compact_history(h, 1500)
    v = cv.verify_compaction(h, msgs, rep)
    assert "missing_code_block" in v["critical_losses"] and v["code_blocks_lost"] > 0


def test_tampered_recent_detected():
    h = hist_with_facts()
    msgs, rep = cc.compact_history(h, 1500)
    msgs[-1] = {"role": "user", "content": "adulterado"}
    assert "missing_recent" in cv.verify_compaction(h, msgs, rep)["critical_losses"]


def test_missing_pinned_detected():
    h = hist_with_facts()
    msgs, rep = cc.compact_history(h, 1500)
    msgs[0] = {"role": "system", "content": "sin reglas"}
    assert "missing_pinned" in cv.verify_compaction(h, msgs, rep)["critical_losses"]


def test_offloaded_facts_count_as_recoverable(tmp_path):
    h = hist_with_facts()
    h[3] = cc.TurnView("user", "Nunca uses sudo. Puerto 11435. " + "z" * 3000, 800)
    msgs, rep = cc.compact_history(h, 2048, storage_dir=str(tmp_path))
    v = cv.verify_compaction(h, msgs, rep, storage_dir=str(tmp_path))
    assert rep["actions"]["offloaded"] == 1 and v["facts_recoverable_only"] >= 1


def test_gate_pass_and_fail_reasons():
    ok, r = cv.evaluate_gate({"score": 90, "critical_losses": []})
    assert ok and r == []
    ok, r = cv.evaluate_gate({"score": 70, "critical_losses": ["missing_code_block"]})
    assert not ok and any(x.startswith("score_below_min") for x in r) and any(x.startswith("critical_losses_exceeded") for x in r)


def test_strict_blocks_when_gate_fails():
    h = build(random.Random(3), 60, 1)
    with pytest.raises(cv.CompactionBlocked) as e:
        cv.compact_with_gate(h, 1500, strict=True)
    assert "critical_losses_exceeded:1>0" in e.value.reasons


def test_non_strict_is_advisory():
    h = build(random.Random(3), 60, 1)
    msgs, rep = cv.compact_with_gate(h, 1500, strict=False)
    assert rep["verification"]["status"] == "advisory" and rep["verification"]["gate_reasons"]


def test_fallback_truncation_runs_when_summarizer_attempt_fails(monkeypatch):
    real = cv.verify_compaction
    state = {"n": 0}

    def flaky(*a, **k):
        state["n"] += 1
        v = real(*a, **k)
        if state["n"] == 1:
            v["critical_losses"] = ["missing_code_block"]
        return v
    monkeypatch.setattr(cv, "verify_compaction", flaky)
    h = hist_with_facts(60)
    msgs, rep = cv.compact_with_gate(h, 2048, summarizer=fake_summarizer, strict=True,
                                     policy={"min_score": 0, "max_critical_losses": 0})
    assert rep["triggered"] and state["n"] == 2
    assert rep["verification"]["status"] == "pass_after_fallback_truncation"
    assert rep["verification"]["first_attempt_reasons"]
    assert rep["actions"]["summarized_turns"] == 0


def test_blocked_after_fallback_raises(monkeypatch):
    def always_bad(*a, **k):
        return {"score": 10, "critical_losses": ["missing_code_block"], "profile_failures": []}
    monkeypatch.setattr(cv, "verify_compaction", always_bad)
    with pytest.raises(cv.CompactionBlocked):
        cv.compact_with_gate(hist_with_facts(60), 2048, summarizer=fake_summarizer, strict=True)


def test_report_compatible_with_npsc_evaluate_strict():
    ns = pytest.importorskip("npsc_service")
    h = build(random.Random(3), 60, 1)
    msgs, rep = cc.compact_history(h, 1500)
    v = cv.verify_compaction(h, msgs, rep)
    pol = {"min_score": 80, "max_critical_losses": 0, "fail_on_missing_safety": True, "fail_on_missing_goal": True}
    assert ns.evaluate_strict(v, pol)[0] == cv.evaluate_gate(v, pol)[0]
    h2 = hist_with_facts(3)
    m2, r2 = cc.compact_history(h2, 8192)
    v2 = cv.verify_compaction(h2, m2, r2)
    assert ns.evaluate_strict(v2, pol)[0] is True and cv.evaluate_gate(v2, pol)[0] is True
