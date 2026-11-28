FINAL HANDOFF - NSCP ITER05
Generado: 2026-11-28T00:42:13.480632+00:00
SHA baseline: 97ea9e987656bf64234cfc56ee3a89196a3b579d
Evidencia: <EVIDENCE_DIR>\2026-11-27_iter05_specialized_engines

ESTADO: campana ejecutada en entorno aislado. Prototipos ejecutables y
resultados reales. SIN integracion en producto.

ENTREGABLES VERIFICADOS
- MODEL_INVENTORY.json: 3 GGUF con SHA256 reales y metadatos dirigidos.
- RUNTIME_COMPATIBILITY.json: llama.cpp b9947, help real 52204 chars.
- EMBEDDING_BENCHMARK*.json, EMBEDDING_POSITIONAL_PROBE.json.
- RERANKER_BENCHMARK.json: /rerank real con relevance_score.
- COMPACTOR_BENCHMARK.json, COMPACTOR_COMPARISON.json: A/B real.
- MEMORY_INDEX_PROTOTYPE/: modulo + DB + resultados 12/12.
- MULTIENGINE_ROUTER_PROTOTYPE/: router + resultados 17/17.
- ADVERSARIAL_RESULTS.json, MUTATION_RESULTS.json.
- RESOURCE_BENCHMARK.json: carga/RSS reales del compactor.
- RECOMMENDED_ARCHITECTURE.md, PRODUCTION_INTEGRATION_PLAN.md, BUG_REGISTRY.md.

LIMITACIONES
- Ollama no disponible; comparacion A hecha con GGUF original via llama-server.
- VRAM solo medida como "Vulkan cargo y respondio"; sin medicion sistematica.
- Latencias de un solo modelo a la vez, 2 hilos CPU; no escenario multi-modelo
  concurrente (prohibido por directiva).
- No se repitieron ITER03/ITER04; se reutilizaron sus artefactos.
- No se modificaron main, NSCP productivo, PATH global, Ollama ni Hermes.
- Sin push, sin merge, sin coste monetario.


RESULTADO DIFERENCIAL DURO (sin solapamiento lexico, parafasis y ES-EN)
Generado: 2026-11-28T00:51:06.552589+00:00
Banco facil (solapamiento lexico): todas las rutas A-G dieron recall 1.0;
  ese diseno no discrimina y NO debe citarse como optimo.
Banco duro (4 consultas x k=4,8,16,32):
  A BM25: recall 0.500, selection 0.000, MRR 0.250
  B EMBEDDING: recall 1.000, selection 1.000, MRR 1.000
  C HYBRID_RRF: recall 1.000, selection 0.500, MRR 0.620
  D BM25+RERANK: recall 0.500, selection 0.000 (reranker no recupera lo que BM25 perdio)
  E EMB+RERANK: recall 1.000, selection 1.000
  F ALL+RERANK: recall 1.000, selection 0.500 (RRF diluye al ganador)
  G QWEN_SELECTOR: recall 0.500, selection 0.500, latencia hasta 6.672 s
  H/I/J: NOT_EXECUTED (declarado, no simulado)
Conclusion: para parafrasis/cross-lingual, embedding puro supera a BM25 y a
  la fusion RRF en selection; el reranker solo ayuda si el pool ya contiene
  el documento correcto.
