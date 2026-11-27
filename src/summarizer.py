"""Resumen de turnos intermedios vía Ollama local (objetivo Hermes).

Sin dependencias externas: urllib de la biblioteca estándar contra el
endpoint /api/chat de Ollama en localhost. Si Ollama no responde, no
hay modelo o cualquier error ocurre, se devuelve un resumen
DETERMINISTA por truncado estructurado: el compactor nunca se queda
sin salida.
"""

from __future__ import annotations

import json
import urllib.request

DEFAULT_MODEL = "hermes3:8b"
DEFAULT_HOST = "http://localhost:11434"
DEFAULT_TIMEOUT = 120.0

_SYSTEM = (
    "Eres un resumidor técnico extremadamente conciso. Responde solo"
    " con las secciones pedidas, sin comentarios ni adornos."
)

_PROMPT = (
    "Resume el historial siguiente en las secciones exactas indicadas:\n"
    "- OBJETIVO VIGENTE\n"
    "- DECISIONES TOMADAS\n"
    "- ARCHIVOS/SISTEMAS TOCADOS\n"
    "- RESTRICCIONES DEL USUARIO\n"
    "- PENDIENTES / PRÓXIMOS PASOS\n\n"
    "HISTORIAL:\n"
)


def _fallback_summary(turns) -> str:
    """Resumen determinista: primera línea de cada turno, truncada."""
    lines = ["RESUMEN AUTOMÁTICO (sin modelo; truncado determinista):"]
    for t in turns:
        text = (t.content or "").strip()
        first = text.splitlines()[0][:160] if text else "(turno vacío)"
        lines.append(f"- [{t.role}] {first}")
    return "\n".join(lines)


def summarize_turns(turns,
                    model: str = DEFAULT_MODEL,
                    host: str = DEFAULT_HOST,
                    timeout: float = DEFAULT_TIMEOUT) -> str:
    """Resume los turnos intermedios con el modelo local indicado.

    Nunca lanza excepción: ante cualquier fallo devuelve el fallback
    determinista, de modo que el compactor siempre produce salida.
    """
    if not turns:
        return ""
    text = "\n\n".join(f"[{t.role}] {t.content}" for t in turns)
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _PROMPT + text[:24000]},
        ],
    }
    try:
        req = urllib.request.Request(
            host + "/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = ((data.get("message") or {}).get("content") or "").strip()
        return content or _fallback_summary(turns)
    except Exception:
        return _fallback_summary(turns)
