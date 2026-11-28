# Compactor de contexto conversacional (Hermes)

> Estado: **v1** en `feature/context-compactor`. Complementario a NSCP: NSCP comprime la peticion (hacia adentro); este modulo comprime la historia acumulada de una conversacion con Hermes (hacia atras).

## Problema

Hermes 3 declara hasta 131 072 tokens de contexto nativo, pero el limite practico local lo fijan el runtime y la VRAM: Ollama recorta la ventana segun `num_ctx` y en GPUs de 8 GB la cache KV limita ventanas grandes. El compactor mantiene conversaciones largas dentro de la ventana efectiva **sin destruir el historial**.

## Pipeline

```text
historial raw (ConversationStore, integro, nunca destructivo)
  -> tokens (estimate_tokens o tokenizer inyectado)
  -> trigger: tokens >= num_ctx * trigger_ratio
  -> partition: pinned (system + pinned) / middle / recent
  -> offload: turnos grandes SIN codigo -> archivo local + puntero
  -> summarize (opcional, Ollama local, fallback determinista)
     o drop de los middle mas antiguos si no caben
  -> assemble: system(pinned + wrapper + resumen) + middle + recent
  -> report (schema neuroprompt/compaction-result/v1)
```

## Reglas duras

- El historial original jamas se modifica ni se borra.
- Los turnos que contienen bloques de codigo (```) **nunca se offloadean**.
- Limitacion v1 conocida: si no caben, los turnos intermedios con codigo **si pueden resumirse o descartarse** (el resumen los incluye como texto). La proteccion total del codigo en el resumen esta prevista para v2.
- Los turnos `system` y `pinned` entran siempre.
- Sin dependencias externas (sqlite3, urllib, hashlib).
- `summarize_turns` nunca lanza excepciones: ante cualquier fallo devuelve un resumen determinista.

## Politicas

| Nivel | Dispara al % de num_ctx | Turnos recientes | Resumen max. | Offload > tok |
|---|---|---|---|---|
| safe (defecto; requerido para Hermes) | 70 % | 8 | 600 | 600 |
| balanced | 80 % | 5 | 400 | 400 |
| aggressive (solo prosa) | 88 % | 3 | 250 | 250 |

El perfil `hermes` de `configs/model_profiles.json` declara `compression_tolerance: low` y `best_level: safe`; por eso el nivel por defecto es `safe`.

## Uso

```python
import sys; sys.path.insert(0, "src")
from context_compactor import compact_history
from conversation_store import ConversationStore, Turn
from summarizer import summarize_turns

store = ConversationStore("hist.db")
history = store.load("mi-conversacion")
messages, report = compact_history(history, num_ctx=8192, level="safe",
                                   summarizer=summarize_turns, storage_dir=".offload")
```

## Verificacion local (a ejecutar por el usuario)

```bash
ollama show hermes3:8b
python -m pytest tests/test_compression_policy.py tests/test_context_compactor.py \
    tests/test_conversation_store.py tests/test_summarizer.py -q
python -m pytest tests/ -q
```

Estado de verificacion previa a la PR: los 26 tests de estas 4 suites pasaron en un entorno aislado del asistente (Python 3.12, pytest 8.3). No sustituye a tu ejecucion local sobre el repositorio completo.

## Riesgos (v1)

- **GREEN**: store SQLite y archivos offload solo anaden datos; reversibles borrando el directorio.
- **YELLOW**: el resumen consume una generacion extra del modelo local por evento de compresion.
- **YELLOW**: `aggressive` o resumir prosa critica puede degradar el seguimiento de instrucciones; Hermes debe quedarse en `safe` hasta la verificacion semantica de v2.
- **UNRESOLVED**: el `num_ctx` real se fija tras el diagnostico local (`ollama show`).

## Roadmap

- v2: integrar `context_loss_verifier` y el modo `--strict` como puerta de la compresion; proteger codigo tambien en el resumen; CLI `npsc compact`.
- v3: proxy compatible con la API de Ollama en `localhost:11435` (cabecera `X-NSCP-Compaction`); pestana GUI.
- v4: plugin opcional LLMLingua-2 para prosa larga (nunca codigo).
