"""Isolated multi-engine router prototype. Decisions are deterministic and auditable."""
from __future__ import annotations

PASSTHROUGH = "PASSTHROUGH"
DETERMINISTIC = "DETERMINISTIC"
BM25 = "BM25"
EMBEDDING = "EMBEDDING"
HYBRID = "HYBRID_RETRIEVAL"
RERANKER = "RERANKER"
EXTRACTIVE = "EXTRACTIVE"
COMPACTOR = "COMPACTOR"
RECOVERY = "RECOVERY"
ABORT = "ABORT"


def _int(value, default=0):
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def decide(state):
    """Return (engine, reason, engines_touched). state is a plain dict.

    Hard constraints: no silent UNKNOWN->PASS, no all-engine default,
    bounded number of engines per request, safe fallback on model failure.
    """
    tok = _int(state.get("context_tokens", 0))
    num_ctx = max(1, _int(state.get("num_ctx", 8192), 8192))
    pressure = tok / num_ctx
    avail = state.get("available") or {}
    if not isinstance(avail, dict):
        avail = {}
    health = state.get("health") or {}
    if not isinstance(health, dict):
        health = {}
    budget = _int(state.get("budget_tokens", 1000), 1000)
    risk = state.get("risk", "normal")
    semantic = bool(state.get("semantic_need", False))
    code = bool(state.get("has_code", False))
    extraction = bool(state.get("extraction_need", False))
    history = int(state.get("history_len", 0))
    last_failure = state.get("last_failure")

    if risk == "critical" or budget <= 0:
        return ABORT, "critical risk or exhausted budget", [ABORT]
    if last_failure in ("compactor", "embedding", "reranker") and health.get(last_failure, True) is False:
        return RECOVERY, f"engine {last_failure} unhealthy; safe fallback, status DEGRADED", [RECOVERY]
    if pressure <= 0.35 and history < 8 and not semantic and not extraction:
        return PASSTHROUGH, "low context pressure, short history, no retrieval need", [PASSTHROUGH]
    if code and not semantic and avail.get("deterministic", True):
        return DETERMINISTIC, "code preserved verbatim by deterministic path", [DETERMINISTIC]
    if extraction and avail.get("extractive", False):
        return EXTRACTIVE, "extraction need with available extractive engine", [EXTRACTIVE]
    if semantic and not avail.get("embedding", False) and not avail.get("bm25", False):
        return DETERMINISTIC, "semantic need but no retrieval engine; deterministic fallback", [DETERMINISTIC]
    if semantic and avail.get("embedding", False):
        if avail.get("reranker", False) and health.get("reranker", True) and pressure < 1.0:
            return HYBRID, "semantic need with embedding+reranker available", [EMBEDDING, BM25, RERANKER]
        return EMBEDDING, "semantic need with embedding only", [EMBEDDING]
    if pressure >= 0.85 and avail.get("compactor", False) and health.get("compactor", True):
        return COMPACTOR, "high context pressure; specialized compactor authorized", [COMPACTOR]
    if pressure >= 0.85:
        return DETERMINISTIC, "high pressure but no healthy compactor; deterministic fallback", [DETERMINISTIC]
    if avail.get("bm25", False):
        return BM25, "lexical retrieval sufficient, no inference needed", [BM25]
    return DETERMINISTIC, "default conservative route", [DETERMINISTIC]
