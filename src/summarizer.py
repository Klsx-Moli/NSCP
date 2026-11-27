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


def _fallback_summary(turns, max_chars=2400):
    """Resumen extractivo DETERMINISTA: restricciones, luego rutas/numeros/URLs/identificadores,
    y con el presupuesto sobrante la primera linea de cada turno. Sin modelo, sin inventar."""
    from compaction_verifier import extract_facts
    cons, other, seen = [], [], set()
    for t in turns:
        for kind, val in sorted(extract_facts(t.content or "", t.role)):
            if val not in seen:
                seen.add(val)
                (cons if kind == "constraint" else other).append(val)
    lines = ["RESUMEN AUTOMATICO (sin modelo; extractivo determinista):"]
    used = len(lines[0])

    def section(title, items):
        nonlocal used
        picked = []
        for it in items:
            if used + len(it) + 3 > max_chars:
                break
            picked.append(it)
            used += len(it) + 3
        if picked:
            lines.append(title)
            lines.extend(f"- {p}" for p in picked)
            used += len(title) + 1

    section("RESTRICCIONES:", cons)
    section("HECHOS (rutas, numeros, URLs):", other)
    heads = []
    for t in turns:
        text = (t.content or "").strip()
        heads.append(f"[{t.role}] " + (text.splitlines()[0][:160] if text else "(turno vacio)"))
    section("TURNOS (primera linea):", heads)
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
