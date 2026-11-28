ITER08 — LOCAL VALIDATION (NO NEW CAMPAIGN)
Development SHA: 5fbdd030ec5571039159534a413ff8b44fe3dc45
Research base: c997ab3004913bdc70ab402abfdc07d02f221d67
Executed: 2026-11-28T06:19:50.317157+00:00

RESULTADOS REALES
- tests: 51 passed, 1 skipped.
- recursos: 6 modelos gestionados PRESENT; CTXPrune y NLI importados desde los bundles de ITER07, sin nuevas descargas.
- runner: complete=true; kompress/ctxprune/nli ejecutados; semantic_preview status=inference_path_observed.
- preview semántico: baseline determinista expected_evidence_visible=False,
  ruta embedding expected_evidence_visible=True,
  tokens_before=3808, tokens_after=1242.
- NLI: 21/21 medidos, 15 aciertos; ES 6/9, EN 7/9, cross 2/3.
  calibrated=False, authority=none, semantic_gate=not_validated.
- Kompress y CTXPrune: 6 casos cada uno; 4 con expected_visible=true y 2 (unicode/semantic) en false.

LIMITACIONES / RESULTADOS NEGATIVOS CONSERVADOS
- No se afirma competencia semántica: NLI no validado y casos unicode/semantic no visibles.
- --ngl 99 es offload solicitado, no medición de VRAM.
- Logs kompress/ctxprune/nli quedaron vacíos (0 bytes); resultados JSON conservados.
- Sin descargas nuevas, sin cambios en componentes remotos, main ni feature/context-compactor.
