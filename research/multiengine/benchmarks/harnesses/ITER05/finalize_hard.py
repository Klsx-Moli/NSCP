"""Append hard-differential findings to handoff docs and checkpoint."""
import json
import pathlib
from datetime import datetime, timezone

E = pathlib.Path(r"<EVIDENCE_DIR>\2026-11-27_iter05_specialized_engines")
hard = json.loads((E / "MULTIENGINE_DIFFERENTIAL_HARD.json").read_text(encoding="utf-8"))
easy = json.loads((E / "MULTIENGINE_DIFFERENTIAL.json").read_text(encoding="utf-8"))

section = f"""

RESULTADO DIFERENCIAL DURO (sin solapamiento lexico, parafasis y ES-EN)
Generado: {datetime.now(timezone.utc).isoformat()}
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
"""
for name in ("FINAL_HANDOFF.md", "RECOMMENDED_ARCHITECTURE.md"):
    p = E / name
    p.write_text(p.read_text(encoding="utf-8") + section, encoding="utf-8")

bugs = E / "BUG_REGISTRY.md"
bugs.write_text(bugs.read_text(encoding="utf-8") + f"""
BUG-07 EASY-BENCHMARK-NONDISCRIMINATING | confirmed | severity medium
  Banco con solapamiento lexico produjo 1.0 en A-G. Corregido añadiendo
  MULTIENGINE_DIFFERENTIAL_HARD.json con parafasis y ES-EN.
""", encoding="utf-8")

cp_path = E / "CHECKPOINT.json"
cp = json.loads(cp_path.read_text(encoding="utf-8"))
cp["updated_at"] = datetime.now(timezone.utc).isoformat()
cp["summary"]["differential_easy"] = {k: v["recall_at_k"] for k, v in easy["summary"].items()}
cp["summary"]["differential_hard"] = {k: v["selection_recall"] for k, v in hard["summary"].items()}
cp["summary"]["warning"] = "easy benchmark nondiscriminating; use hard variant for conclusions"
cp["artifacts"] = sorted(str(p.relative_to(E)) for p in E.rglob("*") if p.is_file())
cp_path.write_text(json.dumps(cp, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(cp["summary"]["differential_hard"], ensure_ascii=False))
