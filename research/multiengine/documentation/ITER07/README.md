ITER07 — LOCAL EXECUTION & RESOURCE CONSOLIDATION
Base SHA: 7835e7c746bed1429b993d2f7a21ae380dfd37c3
Executed: 2026-11-28T05:28:56.834521+00:00

RESULTADOS REALES
- tests: 41 passed, 1 skipped (pytest --basetemp local; primer intento falló por temp dir del sistema).
- recursos: 4 modelos gestionados PRESENT (8 archivos con SHA256 verificados).
- benchmark corregido: complete=true, 15 casos, sin errores, --ngl 99 solicitado.
  bm25@4 recall 0.077; embedding@4 recall 1.000;
  rrf@4 recall 0.308; embedding_rerank@4 top1 0.923;
  rrf_rerank@4 recall 1.000.
- smoke: Kompress, CTXPrune, NLI y SQLite-vec ejecutaron inferencia/consulta real.
- NLI acierto 3/6 en pares ES/EN; no afirmar capacidad semántica validada.

LIMITACIONES
- --ngl 99 es offload solicitado, no medición de VRAM.
- ITER05 score attribution no reutilizado; estas métricas provienen del evaluador nuevo.
- LLMLingua-2 no descargado (sin ONNX upstream, PyTorch no instalado, no necesario para smoke).
- Rutas privadas y planes de importación NO publicados.
