HANDOFF research/multiengine
Updated: 2026-11-28T02:21:14.001253+00:00

REALIZADO
- Primera sincronizacion: fetch, HEADs verificados, worktree dedicado creado.
- Transferidos ITER01-ITER05: evidencias, logs, harnesses y prototipos ejecutables.
- ITER05: embeddings/reranker/compactor reales; diferencial facil y duro;
  prototipos de memoria (12/12) y router (17/17); mutaciones (8/8).

CAMBIADO
- Nueva rama local research/multiengine desde 97ea9e987656bf64234cfc56ee3a89196a3b579d; sin tocar main ni feature.

PROBADO
- Harnesses ejecutados en sesion anterior con llama.cpp b9947 y Python 3.12.
- JSON validados; secretos escaneados: 0 patrones candidatos en 2785 archivos de texto.

FALLIDO / LIMITADO
- ITER06 no existe localmente (NOT_ACCESSIBLE).
- Ollama no respondio; se uso GGUF original via llama-server.
- Negaciones del reranker casi empatadas; scores no calibrados.
- Embeddings no bitwise-idempotentes dentro de un batch.
- Rutas H/I/J NO EJECUTADAS.

PENDIENTE DE REVISION REMOTA
- Auditar codigo transferido y refutar metricas si procede.
- Validar etiquetas prerregistradas del banco duro.
- Decidir si T006/T007 merecen ejecucion.

DECISIONES QUE REQUIEREN AUTORIZACION
- Integracion en producto (no autorizada aqui).
- Cualquier merger a feature/context-compactor o main.

BLOQUE ADDICIONAL 2026-11-28T02:26:17.686557+00:00 — T006
- Ejecutado: probe de offload total (-ngl 99) para embedding, reranker y compactor.
- Resultado: los tres modelos cargaron e infirieron; RSS sistema 1098/1204/2785 MB.
- Limitacion: no existe contador de VRAM por proceso para RX 570; el resultado es
  un PROXY de compatibilidad, no una medicion de capacidad de VRAM.
- Pendiente: validacion remota del proxy; T005 (ITER06 externo) y T007 siguen abiertas.

BLOQUE ITER07 2026-11-28T05:28:56.834521+00:00
Realizado: sincronización desde 7835e7c746bed1429b993d2f7a21ae380dfd37c3; worktree aislado; 4 tests del agente remoto
ejecutados (41 passed, 1 skipped); catálogo local importado y verificado;
benchmark corregido ejecutado; smoke tests de Kompress/CTXPrune/NLI/SQLite-vec.
Cambiado: coordination TASKS/STATUS/CHECKPOINT/EVIDENCE_INDEX; nueva carpeta ITER07.
Fallido: primer pytest por permisos del temp dir del sistema (no código); NLI 3/6.
Pendiente revisión remota: atribución corregida de scores, instrucciones Kompress/CTXPrune,
interpretación de offload solicitado vs VRAM medida.
Autorización requerida: integración en producto (NO ejecutada).

REMOTE REVIEW 2026-11-28T05:52:00Z
- Read ITER07 original benchmark rows and scripts; independently recomputed ranks and metrics. T012 accepted within saved-evidence scope only.
- CTXPrune smoke applied sigmoid to the class-1 logit; upstream uses two-class softmax. New local_onnx adapter and benchmark are ready for real inference tests. NLI 3/6 is diagnostic only.
- New feature candidate 5fbdd030ec5571039159534a413ff8b44fe3dc45: ONNX exact previews, semantic local CLI excerpts, explicit authorization event resolver, NLI diagnostic, two additional model bundles and one local runner.
- T013: import existing CTXPrune/NLI bundles into extras. T014: run tools/run_iter08_local.py using isolated ONNX Python. Do not rewrite tests or launch new broad campaign. No downloads, main merge, production Hermes changes, or skills changes.

BLOQUE ITER08 2026-11-28T06:19:50.317157+00:00
Realizado: fetch y lectura de TASKS/HANDOFF remotos; worktree desde 5fbdd030ec5571039159534a413ff8b44fe3dc45; cinco tests ejecutados;
bundles CTXPrune/NLI importados al catálogo compartido; runner ITER08 ejecutado con Python ONNX aislado.
Cambiado: T013/T014 a TESTED; nueva evidencia ITER08; STATUS/CHECKPOINT/EVIDENCE_INDEX.
Fallido/negativo: NLI 15/21 sin calibración ni autoridad; casos unicode/semantic no visibles en Kompress/CTXPrune;
logs ONNX vacíos; baseline determinista no mostró la evidencia esperada.
Pendiente revisión remota: interpretación científica de NLI y del preview semántico.
Sin autorización para integración en producto.

REMOTE DEVELOPMENT 2026-11-28
- Feature 98f96fa9ec7a6dba7a46d26aeb8481597e9e0976: exact-span dedup, independent request verification, atomic private memory CLI, experimental Hermes hybrid semantic selection, GUI workbench, real host qualification script, strict llama.cpp compactor candidate with actual chat token meter, explicit context envelope and request/time limits.
- Use docs/ITER09_LOCAL_EXECUTION.md. Start/end synchronization is mandatory; read coordination/AGENT_SYNC.md. No downloads. T015 tests; T016 single embedding runner; T017 actual installed host source/interpreter in temporary home; T018 optional three-case compactor diagnostic. Publish sanitized evidence only in research/multiengine. No changes to main, feature, active Hermes or skills. Keep all original worktrees.
- Do not interpret schema discovery as actual tool dispatch. Actual host qualification is synthetic and does not authorize live activation. No calibrated abstention or semantic truth claims.
