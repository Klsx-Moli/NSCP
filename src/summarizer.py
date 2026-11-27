"""Resumen de turnos via Ollama local con fallback determinista."""

from __future__ import annotations

import json
import urllib.request

DEFAULT_MODEL = "hermes3:8b"
DEFAULT_HOST = "http://localhost:11434"
DEFAULT_TIMEOUT = 120.0
_SYSTEM = "Eres un resumidor tecnico extremadamente conciso. Responde solo con las secciones pedidas."
_PROMPT = ("Resume el historial en estas secciones exactas:\n- OBJETIVO VIGENTE\n- DECISIONES TOMADAS\n"
           "- ARCHIVOS/SISTEMAS TOCADOS\n- RESTRICCIONES DEL USUARIO\n- PENDIENTES\n\nHISTORIAL:\n")


def _fallback_summary(turns):
    lines = ["RESUMEN AUTOMATICO (sin modelo; truncado determinista):"]
    for t in turns:
        text = (t.content or "").strip()
        first = text.splitlines()[0][:160] if text else "(turno vacio)"
        lines.append(f"- [{t.role}] {first}")
    return "\n".join(lines)


def summarize_turns(turns, model=DEFAULT_MODEL, host=DEFAULT_HOST, timeout=DEFAULT_TIMEOUT):
    if not turns:
        return ""
    text = "\n\n".join(f"[{t.role}] {t.content}" for t in turns)
    payload = {"model": model, "stream": False, "messages": [
        {"role": "system", "content": _SYSTEM}, {"role": "user", "content": _PROMPT + text[:24000]}]}
    try:
        req = urllib.request.Request(host + "/api/chat", data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = ((data.get("message") or {}).get("content") or "").strip()
        return content or _fallback_summary(turns)
    except Exception:
        return _fallback_summary(turns)
