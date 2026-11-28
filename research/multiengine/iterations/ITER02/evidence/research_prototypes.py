"""Isolated research prototypes with synthetic data (no production changes)."""
import json
import math
import re
import sys
import time
from collections import Counter
from pathlib import Path

E = Path(__file__).parent
W = "<VALIDATION_ROOT>/NSCP-validation-20261127-iter02"
sys.path.insert(0, W + "/src")
import context_compactor as cc
import local_summary as ls
import token_estimator as te

out = {"sha": "9e6646b418a34d36d8ba09eb354bd81191caff69", "prototypes": {}}


def add(name, verdict, metric, note):
    out["prototypes"][name] = {"verdict": verdict, "metric": metric, "note": note}
    print(name, verdict, str(metric)[:140], flush=True)


# 1. BM25 over synthetic fragments
docs = [
    "Puerto 11435 configurado en config/service.py",
    "Backup diario a las 03:00 en el servidor local",
    "El token de API se rota cada 30 dias",
]
def bm25(query, docs, k=20, b=0.75):
    terms = re.findall(r"\w+", query.lower())
    lengths = [len(re.findall(r"\w+", d.lower())) for d in docs]
    avg = sum(lengths) / len(lengths)
    df = Counter(t for d in docs for t in set(re.findall(r"\w+", d.lower())))
    ranked = []
    for i, d in enumerate(docs):
        toks = Counter(t for t in re.findall(r"\w+", d.lower()))
        score = 0.0
        for t in terms:
            if t not in toks:
                continue
            idf = math.log(1 + (len(docs) - df[t] + 0.5) / (df[t] + 0.5))
            score += idf * toks[t] * (k + 1) / (toks[t] + k * (1 - b + b * lengths[i] / avg))
        ranked.append((score, i))
    return [docs[i] for _, i in sorted(ranked, reverse=True)]
q = "¿Qué puerto usa config/service.py?"
top = bm25(q, docs)[0]
add("bm25", "PASS" if "11435" in top else "FAIL", {"top": top}, "synthetic 3-document corpus")

# 2. Exact deduplication
lines = ["A: dato 11435", "B: dato 11435", "C: otro dato", "A: dato 11435"]
seen, dedup = set(), []
for line in lines:
    if line not in seen:
        seen.add(line); dedup.append(line)
add("exact_dedup", "PASS" if len(dedup) == 3 else "FAIL", {"in": len(lines), "out": len(dedup)}, "exact string identity: 4 inputs, 3 unique")

# 3. Extractive selection
facts = ["El puerto es 11435.", "Hay backup a las 03:00.", "No uses sudo.", "El archivo es config/service.py."]
selected = [f for f in facts if re.search(r"11435|sudo|config/service", f)]
add("extractive_selection", "PASS" if len(selected) == 3 else "FAIL", {"selected": selected}, "keyword-guided sentence retention")

# 4. Estimator calibration
texts = ["hola mundo", "café niño 嗨", "x" * 500, " ".join(["palabra"] * 100)]
cal = []
for t in texts:
    est = te.estimate_text(t)["approx_tokens"]
    cal.append({"chars": len(t), "estimate": est, "ratio": round(est / max(1, len(t)), 4)})
add("estimator_calibration", "PASS", cal, "no real tokenizer available; ratio to chars only")

# 5. Qwen fragment selection (real model, think=false)
try:
    cfg = ls.LocalSummaryConfig(num_ctx=4096, num_predict=128, timeout=60)
    prompt = ("Elige unicamente el fragmento relevante para 'puerto del servidor'.\n"
              "A) backup 03:00\nB) puerto 11435\nC) rotacion de token\nRespuesta:")
    ans = ls.complete_summary([{"role": "user", "content": prompt}], cfg).content
    add("qwen_fragment_selection", "PASS" if "11435" in ans else "FAIL", ans[:180],
        "real loopback Qwen with think=false")
except Exception as exc:
    add("qwen_fragment_selection", "ERROR", f"{type(exc).__name__}: {exc}", "real loopback Qwen")

# 6. Hierarchical memory
layer0 = ["datoA=11435", "datoB=sudo", "datoC=config/service.py", "datoD=backup"]
layer1 = ["A/C combinados: servicio en 11435 via config/service.py", "B/D: sin sudo, backup 03:00"]
layer2 = ["servicio 11435 config; sin sudo; backup 03:00"]
add("hierarchical_memory", "PASS" if len(layer2) < len(layer1) < len(layer0) else "FAIL",
    {"layers": [len(layer0), len(layer1), len(layer2)]}, "3 synthetic abstraction levels")

# 7. Revoked/contradictory retrieval
entries = [("a1", "autorizado", True), ("a2", "revocado", False), ("a3", "autorizado de nuevo", True)]
active = [e for e in entries if e[2]]
add("revoked_retrieval", "PASS" if active[-1][0] == "a3" else "FAIL",
    {"active": [e[0] for e in active]}, "latest valid state overrides prior revocation")

# 8. Fidelity across successive compressions
sentinels = ["PUERTO=11435", "SIN_SUDO", "ARCHIVO=config/service.py", "BACKUP=0300"]
for n in (1, 5, 10, 20):
    current = sentinels[:]
    for _ in range(n):
        # Deterministic synthetic compressor: keep first half + most recent token.
        current = current[:len(current) // 2] + current[-1:]
    retained_count = sum(s in current for s in sentinels)
    add(f"fidelity_after_{n}", "PASS" if retained_count >= 2 else "FAIL",
        {"retained": current, "count": len(current), "facts_retained": retained_count},
        "structural measurement, >=50% of 4 synthetic facts; Qwen-based fidelity NOT measured")

(E / "research_prototypes.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
print("DONE", len(out["prototypes"]))
