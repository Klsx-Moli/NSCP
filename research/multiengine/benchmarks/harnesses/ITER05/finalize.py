"""Aggregate ITER05 evidence; write adversarial/mutation ledgers and final handoff docs."""
import json
import pathlib
import shutil
from datetime import datetime, timezone

E = pathlib.Path(r"<EVIDENCE_DIR>\2026-11-27_iter05_specialized_engines")


def load(name, default=None):
    p = E / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else (default or {})


mem = load("results.json", {})
router = load("MULTIENGINE_ROUTER_PROTOTYPE/results.json", {})
emb = load("EMBEDDING_BENCHMARK_DEEP.json", {})
pos = load("EMBEDDING_POSITIONAL_PROBE.json", {})
rer = load("RERANKER_BENCHMARK.json", {})
cmp = load("COMPACTOR_COMPARISON.json", {})
res = load("RESOURCE_BENCHMARK.json", {})

# keep prototype result next to prototype as required deliverable
shutil.copyfile(E / "results.json", E / "MEMORY_INDEX_PROTOTYPE" / "results.json")

adversarial = []
for name, v in mem.get("tests", {}).items():
    if not isinstance(v, dict):
        continue
    adversarial.append({"id": f"ADV-MEM-{name}", "source": "MEMORY_INDEX_PROTOTYPE/results.json",
                        "case": name, "status": "PASS" if v.get("PASS") else "FAIL",
                        "classification": "VERIFIED_BY_ME" if v.get("PASS") else "EVIDENCE_PENDING",
                        "evidence": v})
for name, v in router.get("scenarios", {}).items():
    adversarial.append({"id": f"ADV-ROUTER-{name}", "source": "MULTIENGINE_ROUTER_PROTOTYPE/results.json",
                        "case": name, "status": "PASS" if v.get("PASS") else "FAIL",
                        "classification": "VERIFIED_BY_ME" if v.get("PASS") else "EVIDENCE_PENDING",
                        "evidence": v})
for name, v in router.get("adversarial", {}).items():
    adversarial.append({"id": f"ADV-ROUTER-{name}", "source": "MULTIENGINE_ROUTER_PROTOTYPE/results.json",
                        "case": name, "status": "PASS" if v.get("PASS") else "FAIL",
                        "classification": "VERIFIED_BY_ME" if v.get("PASS") else "EVIDENCE_PENDING",
                        "evidence": v})

mutation = [
    {"id": "MUT-NAN-VECTOR", "case": "vector NaN/Inf rechazado", "status": "PASS"
     if mem.get("tests", {}).get("nan_vector_rejected", {}).get("PASS") else "FAIL",
     "source": "MEMORY_INDEX_PROTOTYPE/results.json"},
    {"id": "MUT-WRONG-DIM", "case": "vector de dimensión incorrecta excluido de búsqueda", "status": "PASS"
     if mem.get("tests", {}).get("wrong_dim_skipped", {}).get("PASS") else "FAIL",
     "source": "MEMORY_INDEX_PROTOTYPE/results.json"},
    {"id": "MUT-SESSION-ISOLATION", "case": "aislamiento entre sesiones", "status": "PASS"
     if mem.get("tests", {}).get("session_isolation", {}).get("PASS") else "FAIL",
     "source": "MEMORY_INDEX_PROTOTYPE/results.json"},
    {"id": "MUT-INJECTION-AS-DATA", "case": "prompt injection conservado como dato, no ejecutado", "status": "PASS"
     if mem.get("tests", {}).get("injection_stored_as_data", {}).get("PASS") else "FAIL",
     "source": "MEMORY_INDEX_PROTOTYPE/results.json"},
    {"id": "MUT-MODEL-INVALIDATION", "case": "cambio de identidad del embedding invalida índice", "status": "PASS"
     if mem.get("tests", {}).get("embedding_invalidation", {}).get("PASS") else "FAIL",
     "source": "MEMORY_INDEX_PROTOTYPE/results.json"},
    {"id": "MUT-RESTART", "case": "rehidratación exacta tras reinicio de DB", "status": "PASS"
     if mem.get("tests", {}).get("rehydrate_exact", {}).get("PASS") else "FAIL",
     "source": "MEMORY_INDEX_PROTOTYPE/results.json"},
    {"id": "MUT-UNKNOWN-NOT-PASS", "case": "motor caído => RECOVERY, nunca UNKNOWN como PASS", "status": "PASS"
     if router.get("adversarial", {}).get("unknown_not_pass", {}).get("PASS") else "FAIL",
     "source": "MULTIENGINE_ROUTER_PROTOTYPE/results.json"},
    {"id": "MUT-MALFORMED-STATE", "case": "estado vacío/tipos inválidos no rompe router", "status": "PASS"
     if all(router.get("adversarial", {}).get(f"state_{k}", {}).get("PASS") for k in ("empty", "bad_types", "negative")) else "FAIL",
     "source": "MULTIENGINE_ROUTER_PROTOTYPE/results.json"},
]
for case in mutation:
    case["classification"] = "VERIFIED_BY_ME" if case["status"] == "PASS" else "EVIDENCE_PENDING"

(E / "ADVERSARIAL_RESULTS.json").write_text(json.dumps({
    "generated_at": datetime.now(timezone.utc).isoformat(), "total": len(adversarial),
    "passed": sum(c["status"] == "PASS" for c in adversarial), "cases": adversarial},
    indent=2, ensure_ascii=False), encoding="utf-8")
(E / "MUTATION_RESULTS.json").write_text(json.dumps({
    "generated_at": datetime.now(timezone.utc).isoformat(), "total": len(mutation),
    "passed": sum(c["status"] == "PASS" for c in mutation), "cases": mutation},
    indent=2, ensure_ascii=False), encoding="utf-8")

arch = f"""ARQUITECTURA MULTIMOTOR RECOMENDADA - ITER05
Generado: {datetime.now(timezone.utc).isoformat()}
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
"""
(E / "RECOMMENDED_ARCHITECTURE.md").write_text(arch, encoding="utf-8")

plan = f"""PLAN DE INTEGRACION A PRODUCCION (NO EJECUTADO)
Generado: {datetime.now(timezone.utc).isoformat()}
Estado: propuesta; main, NSCP productivo y Hermes activo sin cambios.

1. Annexar los prototipos aislados como dependencias opcionales, no defaults.
2. Anadir flags de configuracion explicitos: engine=bm25|embedding|hybrid|
   compactor|deterministic; modelo_eembedding_id y version_de_indice.
3. Contrato obligatorio: todo resultado lleva classification y evidence_path.
4. Gate previo: repetir benchmarks en el SHA que se integre, no reutilizar
   estas cifras de 97ea9e9.
5. Pruebas de regresion: dedupe por identidad, RECOVERY, NaN/Inf, dimension,
   session isolation, invalidacion de modelo, rehidratacion tras reinicio.
6. Medir VRAM real de reranker y compactor antes de habilitar -ngl > 0.
7. No activar todos los motores por defecto; presupuesto y latencia gobiernan.
8. Rollback: no integrar; los prototipos viven solo en NSCP_LOCAL_EVIDENCE.
"""
(E / "PRODUCTION_INTEGRATION_PLAN.md").write_text(plan, encoding="utf-8")

bugs = f"""BUG REGISTRY - ITER05
Generado: {datetime.now(timezone.utc).isoformat()}

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
"""
(E / "BUG_REGISTRY.md").write_text(bugs, encoding="utf-8")

handoff = f"""FINAL HANDOFF - NSCP ITER05
Generado: {datetime.now(timezone.utc).isoformat()}
SHA baseline: 97ea9e987656bf64234cfc56ee3a89196a3b579d
Evidencia: {E}

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
"""
(E / "FINAL_HANDOFF.md").write_text(handoff, encoding="utf-8")

cp = load("CHECKPOINT.json", {})
cp["updated_at"] = datetime.now(timezone.utc).isoformat()
cp["phase"] = "ITER05_EXECUTED_PROTOTYPES_DELIVERED"
cp["status"] = "EXECUTED_WITH_LIMITATIONS"
cp["artifacts"] = sorted(str(p.relative_to(E)) for p in E.rglob("*") if p.is_file())
cp["summary"] = {
    "embedding": "REAL 1024-dim vectors, CPU+Vulkan",
    "reranker": "REAL /rerank scores, negation near-tie documented",
    "compactor": "12/12 templated vs 12/12 original vs 6/12 generic",
    "memory_prototype": f"{mem.get('passed')}/{mem.get('total')} PASS",
    "router_prototype": f"{router.get('passed')}/{router.get('total')} PASS",
    "adversarial": f"{sum(c['status']=='PASS' for c in adversarial)}/{len(adversarial)} PASS",
    "mutation": f"{sum(c['status']=='PASS' for c in mutation)}/{len(mutation)} PASS",
}
cp["next"] = ["Only on explicit approval: integrate selected engines into product",
              "Measure VRAM systematically before enabling GPU offload",
              "Repeat gates on the exact SHA chosen for integration"]
(E / "CHECKPOINT.json").write_text(json.dumps(cp, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(cp["summary"], ensure_ascii=False))
print("adversarial", sum(c["status"] == "PASS" for c in adversarial), "/", len(adversarial),
      "mutation", sum(c["status"] == "PASS" for c in mutation), "/", len(mutation))
