# Compactor de contexto conversacional (Hermes)

> Estado: **v1** en `feature/context-compactor`. Complementario a NSCP:
> NSCP comprime la petición (hacia adentro); este módulo comprime la
> historia acumulada de una conversación con Hermes (hacia atrás).

## Problema

Los modelos Hermes 3 soportan hasta 131 072 tokens de contexto de forma
nativa, pero el límite práctico local lo fijan el runtime y la VRAM:
Ollama recorta la ventana según el `num_ctx` configurado, y en GPUs de
8 GB la caché KV impide ventanas grandes aunque el modelo las soporte.
Este módulo mantiene conversaciones largas dentro de la ventana
defectiva **sin destruir el historial**.

## Pipeline

```text
historial raw (ConversationStore, íntegro, nunca destructivo)
  -> tokens (estimate_tokens o tokenizer inyectado)
  -> trigger: tokens >= num_ctx * trigger_ratio
  -> offload: turnos grandes SIN código -> archivo local + puntero
  -> partition: pinned (system + pinned) / middle / recent
  -> summarize (opcional, Ollama local; fallback determinista)
     o drop de los middle más antiguos si no caben
  -> assemble: system(pinned + wrapper Hermes + resumen) + middle + recent
  -> report (JSON, schema neuroprompt/compaction-result/v1)
```

## Reglas duras

- El historial original jamás se modifica ni se borra.
- Los bloques de código (```) nunca se offloadean ni resumen en v1.
- Los turnos `system` y `pinned` entran siempre.
- Sin dependencias externas: stdlib (sqlite3, urllib, hashlib).
- `summarize_turns` nunca lanza excepciones: si Ollama falla, devuelve
  un resumen determinista por truncado.

## Archivos

| Archivo | Rol |
|---|---|
| `src/compression_policy.py` | Políticas safe/balanced/aggressive y umbrales |
| `src/conversation_store.py` | `Turn` + `ConversationStore` (SQLite) |
| `src/context_compactor.py` | Núcleo: partición, offload, ensamblado, `compact_history` |
| `src/summarizer.py` | `summarize_turns` vía Ollama localhost con fallback |
| `configs/context_window_profiles.json` | Supuestos de ventana por runtime |
| `tests/test_*.py` | Tres suites headless |

## Políticas

| Nivel | Dispara al % de num_ctx | Turnos recientes | Resumen máx. | Offload > tok |
|---|---|---|---|---|
| safe (defecto; requerido para Hermes) | 70 % | 8 | 600 | 600 |
| balanced | 80 % | 5 | 400 | 400 |
| aggressive (solo prosa) | 88 % | 3 | 250 | 250 |

El perfil `hermes` de `configs/model_profiles.json` declara
`compression_tolerance: low` y `best_level: safe`; por eso el
compactor fija `safe` como nivel por defecto.

## Uso

```python
import sys; sys.path.insert(0, "src")
from context_compactor import compact_history
from conversation_store import ConversationStore, Turn
from summarizer import summarize_turns

store = ConversationStore("~/.local/share/neuro-prompt-sc/hist.db")
# ... append de turnos reales ...
history = store.load("mi-conversacion")

messages, report = compact_history(
    history, num_ctx=8192, level="safe",
    summarizer=summarize_turns, storage_dir=".offload",
)
# messages -> payload /api/chat de Ollama; report -> auditable
```

## Esquema del informe

```json
{
  "schema": "neuroprompt/compaction-result/v1",
  "level": "safe", "num_ctx": 8192,
  "triggered": true,
  "tokens_before": 7430, "tokens_after": 3650,
  "compression_ratio": 2.04,
  "actions": {"offloaded": 2, "summarized_turns": 12,
              "dropped_turns": 0, "kept_recent": 8, "pinned": 1},
  "verification": {"status": "structural_only"}
}
```

## Verificación local (a ejecutar por el usuario, no automático)

```bash
# 1. Num_ctx real del modelo (diagnóstico local imprescindible)
ollama show hermes3:8b

# 2. Tests del módulo (headless)
python -m pytest tests/test_compression_policy.py \
    tests/test_context_compactor.py tests/test_conversation_store.py -q

# 3. Suite completa del proyecto (no romper lo existente)
python -m pytest tests/ -q
```

## Riesgos (v1)

- **GREEN**: el store SQLite y los archivos offload solo añaden datos;
  reversibles borrando el directorio.
- **YELLOW**: el resumen consume una generación extra del modelo local
  por evento de compresión (latencia adicional en hardware modesto);
  mitigado disparando solo al 70-88 % de la ventana.
- **YELLOW**: el nivel `aggressive` o resumir prosa crítica puede
  degradar el seguimiento de instrucciones; Hermes debe quedarse en
  `safe` hasta tener la verificación semántica de v2.
- **UNRESOLVED**: el `num_ctx` real y el ajuste fino del trigger se
  fijan tras verificar el diagnóstico local del punto anterior.

## Roadmap

- v2: integrar `verify_context_loss` existente (retention/utility/
  risk scores + modo --strict) como puerta de la compresión.
- v2: `npsc_service` CLI: `npsc compact --num-ctx 8192 --level safe`.
- v3: proxy Opcallame-compatible en `localhost:11435` delante de
  Ollama, cabecera `X-NSCP-Compaction` con el ratio aplicado.
- v3: pestaña «Compactor de contexto» en la GUI PySide6 (worker con
  señales, como el compilador).
- v4: plugin opcional LLMLingua-2 para prosa larga (nunca código).
