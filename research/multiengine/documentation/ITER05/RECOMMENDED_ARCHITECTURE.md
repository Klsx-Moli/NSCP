ARQUITECTURA MULTIMOTOR RECOMENDADA - ITER05
Generado: 2026-11-28T00:42:13.421796+00:00
Estado: propuesta experimental; NO integrada en NSCP productivo.

1. HECHOS MEDIDOS (no estimaciones)
- Embedding Qwen3-Embedding-0.6B Q8_0 con llama.cpp b9947: 1024 dimensiones,
  norma L2 1.0, /v1/embeddings real. Latencia 1 texto 0.031 s, 4 texts 0.875 s,
  16 texts 3.265 s, 32 texts 5.5 s (CPU, 2 hilos). Vulkan (-ngl 99) cargó y
  respondió en 0.438 s para 1 texto; no se midió escalado Vulkan.
- Reranker Qwen3-Reranker-0.6B Q8_0: endpoint /rerank con campo relevance_score.
  Autorizacion correcta 0.999779 vs revocada 0.015881. Negacion: 0.999778 vs
  0.999491 (casi empate). 4/8/16/32/64 candidatos: 1.234/2.266/4.734/9.032/18.172 s.
- Compactor-Qwen3.5-4B Q4_K_M: con plantilla y enable_thinking=false retiene
  12/12 hechos (739 chars) vs 12/12 del Qwen3.5 original (806 chars); prompt
  generico 6/12. NSCP determinista 12/12 pero 4118 chars por wrapper/pinned.
- Carga compactor en caliente 5.58 s, en frio 40.61 s; RSS pico 3209 MB en
  carga y 3266 MB en inferencia; 64 tokens tardaron 19.265 s en CPU.

2. DECISION
- BM25 primero cuando no hay necesidad semantica: coste 0 de inferencia.
- Embedding para recuperacion semantica; hibrido BM25+embedding+RRF solo si
  hay reranker sano y presion de contexto < 1.0.
- Reranker acotado a top-k pequeno (4-8): a 32 candidatos ya cuesta ~9 s.
- Compactor solo bajo presion alta >=0.85 y con plantilla especializada;
  si falla, RECOVERY determinista, nunca UNKNOWN -> PASS.
- No cargar tres modelos a la vez: RSS del compactor solo ya es ~3.2 GB.
- Memoria vectorial persistente: SQLite + vectores + identidad de evento,
  dedupe por identidad (nunca por texto), invalidacion al cambiar embedding.

3. RIESGOS CONTRADICHOS POR EVIDENCIA
- No afirmar que el reranker entiende negaciones: diferencia 0.000287.
- No afirmar probabilidades calibradas: los scores no estan calibrados.
- No afirmar bitwise determinismo de embeddings en batch: mismo texto en
  posiciones distintas difiere hasta 0.00324 (cos 0.9997); si es identico
  en peticiones unitarias (maxdiff 0.0).
- No inferir ahorro economico de tokens estimados sin medir latencia/RAM.


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
