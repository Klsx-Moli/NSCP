DECISIONES ITER05 (evidencia local, sujetas a revision remota)
Updated: 2026-11-28T02:21:14.001253+00:00
D1. BM25 por defecto solo si no hay necesidad semantica: coste 0 de inferencia.
    Evidencia: MULTIENGINE_DIFFERENTIAL_HARD.json A_BM25 selection 0.0.
D2. Embedding puro para parafasis/cross-lingual; RRF no siempre mejora selection.
    Evidencia: hard B selection 1.0 vs C 0.5.
D3. Reranker solo sobre pools que ya contienen el documento correcto.
    Evidencia: hard D selection 0.0 vs E 1.0.
D4. Compactor con plantilla y enable_thinking=false; sin prompt generico.
    Evidencia: COMPACTOR_COMPARISON.json 12/12 vs 6/12.
D5. Fallo de modelo => RECOVERY, nunca UNKNOWN -> PASS.
    Evidencia: MULTIENGINE_ROUTER_PROTOTYPE/results.json.
D6. No cargar tres modelos simultaneamente: RSS compactor ~3.2 GB.
    Evidencia: RESOURCE_BENCHMARK.json.
Ninguna decision autoriza integracion en producto.
