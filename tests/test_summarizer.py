import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import io
import json
import pytest
import summarizer as sm
from context_compactor import TurnView


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def turns():
    return [TurnView("user", "primera linea\nsegunda"), TurnView("assistant", "respuesta")]


def test_empty_turns_returns_empty():
    assert sm.summarize_turns([]) == ""


def test_success_returns_model_content(monkeypatch):
    body = json.dumps({"message": {"content": "  RESUMEN OK  "}}).encode()
    monkeypatch.setattr(sm, "_open_local", lambda *a, **k: _Resp(body))
    assert sm.summarize_turns(turns()) == "RESUMEN OK"


def test_connection_error_falls_back(monkeypatch):
    def boom(*a, **k):
        raise OSError("sin ollama")
    monkeypatch.setattr(sm, "_open_local", boom)
    out = sm.summarize_turns(turns())
    assert out.startswith("RESUMEN AUTOMATICO") and "[user] primera linea" in out and "segunda" not in out


def test_empty_model_content_falls_back(monkeypatch):
    body = json.dumps({"message": {"content": "   "}}).encode()
    monkeypatch.setattr(sm, "_open_local", lambda *a, **k: _Resp(body))
    assert sm.summarize_turns(turns()).startswith("RESUMEN AUTOMATICO")


def test_invalid_json_falls_back(monkeypatch):
    monkeypatch.setattr(sm, "_open_local", lambda *a, **k: _Resp(b"no-json"))
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

    def respond(req, timeout):
        payload = json.loads(req.data)
        seen.append(payload["messages"][1]["content"])
        assert payload["options"]["temperature"] == 0
        assert payload["think"] is False
        return _Resp(json.dumps({"message": {"content": "estado conciso"}}).encode())

    monkeypatch.setattr(sm, "_open_local", respond)
    out = sm.summarize_turns([TurnView("user", "a" * 30000 + " FINAL_SENTINEL")],
                             strict=True)
    assert out == "estado conciso"
    assert len(seen) > 2 and any("FINAL_SENTINEL" in v for v in seen)


def test_strict_rejects_truncated_output(monkeypatch):
    body = json.dumps({"done_reason": "length", "message": {"content": "parcial"}}).encode()
    monkeypatch.setattr(sm, "_open_local", lambda *a, **k: _Resp(body))
    with pytest.raises(sm.SummaryUnavailable):
        sm.summarize_turns(turns(), strict=True)


def test_nonlocal_endpoint_rejected_before_request(monkeypatch):
    def never(*a, **k):
        pytest.fail("remote request attempted")
    monkeypatch.setattr(sm, "_open_local", never)
    for host in ("https://example.com", "http://127.0.0.1@evil.test", "http://localhost/x"):
        with pytest.raises(ValueError):
            sm.summarize_turns(turns(), host=host)


def test_chunks_preserve_unicode():
    raw = "á😀漢字" * 100
    pieces = list(sm._chunks(raw, 19))
    assert "".join(pieces) == raw
    assert all(len(p.encode("utf-8")) <= 19 for p in pieces)
