import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pytest
import summarizer as sm
import local_summary as ls
from context_compactor import TurnView


def _response(content="RESUMEN OK", **changes):
    return dict({"model": ls.DEFAULT_MODEL, "done": True, "done_reason": "stop",
                 "prompt_eval_count": 100, "eval_count": 20,
                 "message": {"role": "assistant", "content": content}}, **changes)


def _mock_transport(monkeypatch, respond):
    def post(base, path, payload, timeout):
        if path == "/api/show":
            return {"model_info": {"general.architecture": "qwen"}, "details": {"format": "gguf"}}
        assert path == "/api/chat"
        return respond(payload)
    monkeypatch.setattr(ls, "_post", post)


def turns():
    return [TurnView("user", "primera linea\nsegunda"), TurnView("assistant", "respuesta")]


def test_empty_turns_returns_empty():
    assert sm.summarize_turns([]) == ""


def test_success_returns_model_content(monkeypatch):
    _mock_transport(monkeypatch, lambda payload: _response("  RESUMEN OK  "))
    assert sm.summarize_turns(turns()) == "RESUMEN OK"


def test_connection_error_falls_back(monkeypatch):
    def boom(*a, **k):
        raise OSError("sin ollama")
    monkeypatch.setattr(ls, "_post", boom)
    out = sm.summarize_turns(turns())
    assert out.startswith("RESUMEN AUTOMATICO") and "[user] primera linea" in out and "segunda" not in out


def test_empty_model_content_falls_back(monkeypatch):
    _mock_transport(monkeypatch, lambda payload: _response("   "))
    assert sm.summarize_turns(turns()).startswith("RESUMEN AUTOMATICO")


def test_invalid_json_falls_back(monkeypatch):
    def invalid(*args):
        raise ValueError("invalid JSON")
    monkeypatch.setattr(ls, "_post", invalid)
    assert sm.summarize_turns(turns()).startswith("RESUMEN AUTOMATICO")


def test_fallback_is_extractive_and_prioritizes_constraints():
    ts = [TurnView("user", "relleno " * 50 + ". Nunca uses sudo en este servidor. Ver src/a/b.py puerto 11435"),
          TurnView("assistant", "otro " * 80)]
    out = sm._fallback_summary(ts, max_chars=400)
    assert "RESTRICCIONES:" in out and "nunca uses sudo en este servidor" in out
    assert "src/a/b.py" in out and "11435" in out and len(out) <= 400 + 60


def test_fallback_is_deterministic_and_respects_budget():
    ts = [TurnView("user", f"Nunca uses opcion {i} en el paso {i}. src/m{i}/f{i}.py") for i in range(200)]
    a, b = sm._fallback_summary(ts, 1000), sm._fallback_summary(ts, 1000)
    assert a == b and len(a) <= 1000 + 80


def test_long_history_includes_tail_and_consolidates(monkeypatch):
    seen = []

    def respond(payload):
        seen.append(payload["messages"][1]["content"])
        assert payload["options"]["temperature"] == 0
        assert payload["think"] is False
        assert payload["truncate"] is False and payload["shift"] is False
        return _response("estado conciso")

    _mock_transport(monkeypatch, respond)
    out = sm.summarize_turns([TurnView("user", "a" * 30000 + " FINAL_SENTINEL")],
                             strict=True)
    assert out == "estado conciso"
    assert len(seen) > 2 and any("FINAL_SENTINEL" in v for v in seen)


def test_strict_rejects_truncated_output(monkeypatch):
    _mock_transport(monkeypatch, lambda payload: _response("parcial", done_reason="length"))
    with pytest.raises(sm.SummaryUnavailable):
        sm.summarize_turns(turns(), strict=True)


def test_nonlocal_endpoint_rejected_before_request(monkeypatch):
    def never(*a, **k):
        pytest.fail("remote request attempted")
    monkeypatch.setattr(ls, "_post", never)
    for host in ("https://example.com", "http://127.0.0.1@evil.test", "http://localhost/x"):
        with pytest.raises(ValueError):
            sm.summarize_turns(turns(), host=host)


def test_chunks_preserve_unicode():
    raw = "á😀漢字" * 100
    pieces = list(sm._chunks(raw, 19))
    assert "".join(pieces) == raw
    assert all(len(p.encode("utf-8")) <= 19 for p in pieces)


def test_legacy_uses_same_strict_response_validation(monkeypatch):
    _mock_transport(monkeypatch, lambda payload: _response(
        message={"role": "assistant", "content": "", "thinking": "not a completed summary"},
        done_reason="length"))
    with pytest.raises(sm.SummaryUnavailable):
        sm.summarize_turns(turns(), strict=True)


def test_legacy_json_escaping_never_exceeds_transport_bound(monkeypatch):
    import json
    seen = []
    def respond(payload):
        wire = json.dumps(payload["messages"], ensure_ascii=False, separators=(",", ":"))
        options = payload["options"]
        assert len(wire.encode("utf-8")) + 512 + 32 * len(payload["messages"]) <= (
            options["num_ctx"] - options["num_predict"])
        seen.append(payload["messages"][1]["content"].removeprefix(sm._PROMPT))
        return _response("compact state")
    _mock_transport(monkeypatch, respond)
    raw = 'quote" slash\\ newline\n null\x00 😀 ' * 1500
    assert sm.summarize_turns([TurnView("user", raw)], strict=True) == "compact state"
    assert "".join(seen[:next(i for i, text in enumerate(seen) if text.startswith("compact state"))]) == "[user] " + raw


def test_legacy_refuses_cloud_metadata_without_sending_history(monkeypatch):
    calls = []
    def post(base, path, payload, timeout):
        calls.append(path)
        return {"remote_host": "https://example.invalid"}
    monkeypatch.setattr(ls, "_post", post)
    with pytest.raises(sm.SummaryUnavailable):
        sm.summarize_turns(turns(), strict=True)
    assert calls == ["/api/show"]
