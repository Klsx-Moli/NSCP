"""Router prototype tests + adversarial checks. Real execution, no model calls needed."""
import json
import pathlib
import sys
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).parent
E = HERE.parent
sys.path.insert(0, str(HERE))
import router  # noqa: E402

ALL = {"bm25": True, "embedding": True, "reranker": True, "compactor": True,
       "extractive": True, "deterministic": True}

SCENARIOS = [
    ("short_no_need", {"context_tokens": 800, "num_ctx": 8192, "history_len": 2,
                       "available": ALL}, router.PASSTHROUGH),
    ("code_present", {"context_tokens": 3000, "num_ctx": 8192, "history_len": 5,
                      "has_code": True, "available": ALL}, router.DETERMINISTIC),
    ("semantic_full", {"context_tokens": 3000, "num_ctx": 8192, "semantic_need": True,
                       "available": ALL}, router.HYBRID),
    ("semantic_no_reranker", {"context_tokens": 3000, "num_ctx": 8192, "semantic_need": True,
                              "health": {"reranker": False}, "available": ALL}, router.EMBEDDING),
    ("no_models", {"context_tokens": 3000, "num_ctx": 8192, "semantic_need": True,
                   "available": {"bm25": False, "embedding": False}}, router.DETERMINISTIC),
    ("lexical", {"context_tokens": 3000, "num_ctx": 8192, "available": {"bm25": True}}, router.BM25),
    ("high_pressure", {"context_tokens": 7800, "num_ctx": 8192, "available": ALL}, router.COMPACTOR),
    ("high_pressure_no_compactor", {"context_tokens": 7800, "num_ctx": 8192,
                                    "available": {"compactor": False}}, router.DETERMINISTIC),
    ("compactor_failed", {"context_tokens": 7800, "num_ctx": 8192, "available": ALL,
                          "health": {"compactor": False}, "last_failure": "compactor"}, router.RECOVERY),
    ("extraction", {"context_tokens": 3000, "num_ctx": 8192, "extraction_need": True,
                    "available": ALL}, router.EXTRACTIVE),
    ("budget_zero", {"context_tokens": 3000, "num_ctx": 8192, "budget_tokens": 0,
                     "available": ALL}, router.ABORT),
    ("critical_risk", {"context_tokens": 3000, "num_ctx": 8192, "risk": "critical",
                       "available": ALL}, router.ABORT),
]

out = {"generated_at": datetime.now(timezone.utc).isoformat(), "classification": "EVIDENCE_PENDING",
       "scenarios": {}, "adversarial": {}, "errors": []}
for name, state, expected in SCENARIOS:
    engine, reason, touched = router.decide(state)
    out["scenarios"][name] = {"expected": expected, "got": engine, "reason": reason,
                              "engines_touched": touched,
                              "PASS": engine == expected and len(touched) <= 3}

# adversarial: no route may activate every engine by default
worst = router.decide({"context_tokens": 8192, "num_ctx": 8192, "semantic_need": True,
                       "history_len": 1000, "available": ALL, "risk": "normal"})
out["adversarial"]["no_all_engines"] = {"got": worst, "PASS": len(worst[2]) <= 3}
# adversarial: UNKNOWN status must not become PASS
out["adversarial"]["unknown_not_pass"] = {
    "healthy_false_routes_to_recovery": router.decide({"context_tokens": 7800, "num_ctx": 8192,
        "available": ALL, "health": {"compactor": False}, "last_failure": "compactor"})[0] == router.RECOVERY,
    "PASS": router.decide({"context_tokens": 7800, "num_ctx": 8192, "available": ALL,
        "health": {"compactor": False}, "last_failure": "compactor"})[0] == router.RECOVERY}
# adversarial: empty/malformed state must not crash
for label, state in (("empty", {}), ("bad_types", {"context_tokens": "x", "num_ctx": None}),
                     ("negative", {"context_tokens": -5, "num_ctx": 8192, "budget_tokens": -1})):
    try:
        r = router.decide(state)
        out["adversarial"]["state_" + label] = {"got": r[0], "PASS": isinstance(r[0], str)}
    except Exception as exc:
        out["adversarial"]["state_" + label] = {"error": f"{type(exc).__name__}: {exc}", "PASS": False}

passed = sum(1 for v in list(out["scenarios"].values()) + list(out["adversarial"].values()) if v.get("PASS"))
total = len(out["scenarios"]) + len(out["adversarial"])
out["passed"] = passed
out["total"] = total
out["classification"] = "VERIFIED_BY_ME" if passed == total else "EVIDENCE_PENDING"
(HERE / "results.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps({"passed": passed, "total": total,
                  "failed": [k for k, v in list(out["scenarios"].items()) + list(out["adversarial"].items())
                             if not v.get("PASS")]}, ensure_ascii=False))
