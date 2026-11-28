BUG REGISTRY - ITER05
Generado: 2026-11-28T00:42:13.479626+00:00

BUG-01 EMBEDDING-BATCH-NONDETERMINISM | confirmed | severity low
  Mismo texto en distintas posiciones de un batch: maxdiff 0.00246-0.00324,
  cos 0.9997. Peticiones unitarias maxdiff 0.0. Causa probable: orden de
  operaciones float en batching. Mitigacion: no exigir bitwise identity;
  usar umbral cos >= 0.999 si se necesita cache .

BUG-02 RERANKER-NEGATION-NEAR-TIE | confirmed | severity medium
  'el servidor esta apagado' 0.999778 vs 'el servidor no esta apagado'
  0.999491. No usar el score para decidir autorizaciones ni negaciones.

BUG-03 SCORES-NOT-CALIBRATED | confirmed | severity medium
  relevance_score no es probabilidad. No convertir en porcentaje.

BUG-04 OLLAMA-UNAVAILABLE | confirmed | severity low
  /api/tags rechazo conexion (WinError 10061). No se reinicio ni modifico el
  servicio. Sustituto: Qwen3.5 original GGUF servido por llama-server.

BUG-05 GGUF-FULL-KV-PARSE-DESYNC | confirmed | severity low
  Parser propio de metadata se desincronizo en arrays v3; se uso extraccion
  dirigida por clave y se verifico contra bytes crudos (type 4=UINT32,
  6=FLOAT32, 8=STRING). No afecta a los modelos ni al runtime.

BUG-06 RSS-MEASUREMENT-PARSE | fixed | severity low
  tasklist CSV con comas miles; corregido en resource_probe.py.

BUG-07 EASY-BENCHMARK-NONDISCRIMINATING | confirmed | severity medium
  Banco con solapamiento lexico produjo 1.0 en A-G. Corregido añadiendo
  MULTIENGINE_DIFFERENTIAL_HARD.json con parafasis y ES-EN.
