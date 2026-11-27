import os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import io
import json
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
    monkeypatch.setattr(sm.urllib.request, "urlopen", lambda *a, **k: _Resp(body))
    assert sm.summarize_turns(turns()) == "RESUMEN OK"


def test_connection_error_falls_back(monkeypatch):
    def boom(*a, **k):
        raise OSError("sin ollama")
    monkeypatch.setattr(sm.urllib.request, "urlopen", boom)
    out = sm.summarize_turns(turns())
    assert out.startswith("RESUMEN AUTOMATICO") and "[user] primera linea" in out and "segunda" not in out


def test_empty_model_content_falls_back(monkeypatch):
    body = json.dumps({"message": {"content": "   "}}).encode()
    monkeypatch.setattr(sm.urllib.request, "urlopen", lambda *a, **k: _Resp(body))
    assert sm.summarize_turns(turns()).startswith("RESUMEN AUTOMATICO")


def test_invalid_json_falls_back(monkeypatch):
    monkeypatch.setattr(sm.urllib.request, "urlopen", lambda *a, **k: _Resp(b"no-json"))
    assert sm.summarize_turns(turns()).startswith("RESUMEN AUTOMATICO")
