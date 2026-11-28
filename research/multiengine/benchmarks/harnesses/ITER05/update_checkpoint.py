"""Checkpoint update after completed ITER05 model identity + embedding + reranker units."""
import json
import pathlib
from datetime import datetime, timezone

E = pathlib.Path(r"<EVIDENCE_DIR>\2026-11-27_iter05_specialized_engines")
p = E / "CHECKPOINT.json"
d = json.loads(p.read_text(encoding="utf-8"))
d["updated_at"] = datetime.now(timezone.utc).isoformat()
d["phase"] = "03_EMBEDDING_AND_04_RERANKER_EXECUTED"
d["status"] = "EXECUTED_WITH_FINDINGS"
d["artifacts"] = [
    "MODEL_INVENTORY.json", "RUNTIME_COMPATIBILITY.json", "CHECKPOINT.json",
    "EMBEDDING_BENCHMARK.json", "EMBEDDING_BENCHMARK_DEEP.json", "EMBEDDING_POSITIONAL_PROBE.json",
    "RERANKER_BENCHMARK.json", "COMPACTOR_CHAT_TEMPLATE.txt",
    "inventory_and_runtime.py", "gguf_meta_fix.py", "meta_targeted.py",
    "activate_embedding.py", "embedding_deep.py", "embedding_positional_probe.py", "activate_reranker.py",
    "logs/llama-server-help.txt", "logs/llama-server-version.txt",
    "logs/embedding-server.txt", "logs/embedding-deep-cpu.txt", "logs/embedding-deep-vulkan.txt",
    "logs/embedding-positional-probe.txt", "logs/reranker-server.txt",
]
d["verified_facts"] = {
    "embedding": "llama.cpp b9947 /v1/embeddings REAL: 1024 dims, finite, L2 norm 1.0, CPU and Vulkan both load",
    "embedding_semantics": "gato/felino 0.8585; gato/quantum 0.4169; ES-EN cat 0.7973",
    "embedding_determinism": "single requests bitwise identical (maxdiff 0.0); same text at different batch positions differs max_abs 0.00246-0.00324, cos ~0.9997 -> numeric batch nondeterminism, not semantic instability",
    "reranker": "llama.cpp /rerank REAL: relevance_score field; autorizacion correct 0.999779 vs revoked 0.015881; finite; 4..64 candidates scale ~1.2s..18.2s",
    "reranker_negation_warning": "negation case: correct 0.999778 vs negated 0.999491 (near tie) -> no claim of negation understanding",
}
d["next"] = [
    "Compactor-Qwen3.5-4B: real inference with extracted chat template, temp 0, bounded output",
    "Compare Compactor vs Qwen3.5 original vs deterministic NSCP on identical state fixture",
    "Adversarial/mutation, memory prototype, router prototype, resource benchmark",
]
p.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
print("checkpoint updated", d["phase"])
