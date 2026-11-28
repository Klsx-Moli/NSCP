"""Opt-in loopback llama.cpp retrieval for exact historical excerpts.

A trusted, explicitly configured local daemon is required. HTTP responses
cannot attest the server's loaded model or prove semantic correctness.
No process management, downloads, remote fallback or generated text.
"""
from __future__ import annotations

import json
import math
import time
import urllib.request
from collections import OrderedDict
from dataclasses import dataclass

if __package__:
    from .semantic_memory import _vector
    from .semantic_ranking import rerank_results
else:
    from semantic_memory import _vector
    from semantic_ranking import rerank_results

MAX_SPANS = 64
MAX_BATCH = 4
MAX_ITEM_BYTES = 1536
MAX_RESPONSE = 8 * 1024 * 1024
MAX_CACHE_COMPONENTS = 65536
MAX_CACHE_ENTRIES = 64


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Local retrieval redirect rejected")


def _post(port, path, payload, timeout):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
    req = urllib.request.Request(f"http://127.0.0.1:{port}" + path, data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with opener.open(req, timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE + 1)
    if len(raw) > MAX_RESPONSE:
        raise ValueError("Local retrieval response exceeds limit")
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("error"):
        raise ValueError("Invalid local retrieval response")
    return data


@dataclass(frozen=True)
class RetrievalConfig:
    embedding_port: int
    reranker_port: int | None = None
    dimension: int = 1024
    query_prefix: str = ""
    timeout: float = 60.0
    max_requests: int = 24
    total_timeout: float = 120.0
    min_similarity: float | None = None
    cache_entries: int = 0

    def __post_init__(self):
        for port in (self.embedding_port, self.reranker_port):
            if port is None and self.reranker_port is None and self.embedding_port is not None:
                continue
            if type(port) is not int or not 1 <= port <= 65535:
                raise ValueError("Invalid loopback port")
        if self.reranker_port == self.embedding_port:
            raise ValueError("Embedding and reranker must use distinct ports")
        if (type(self.dimension) is not int or not 1 <= self.dimension <= 16384
                or not isinstance(self.query_prefix, str)
                or len(self.query_prefix.encode("utf-8")) > 512
                or type(self.timeout) not in (int, float) or not 0 < self.timeout <= 180
                or type(self.max_requests) is not int or not 1 <= self.max_requests <= 128
                or type(self.total_timeout) not in (int, float) or not 0 < self.total_timeout <= 600
                or type(self.cache_entries) is not int or not 0 <= self.cache_entries <= MAX_CACHE_ENTRIES
                or (self.min_similarity is not None and (type(self.min_similarity) not in (int, float)
                    or not -1 <= self.min_similarity <= 1))):
            raise ValueError("Invalid retrieval policy")


def embedding_results(response, count, dimension):
    if not isinstance(response, dict) or not isinstance(response.get("data"), list):
        raise ValueError("Missing embedding data")
    if len(response["data"]) != count:
        raise ValueError("Incomplete embedding response")
    out = {}
    for item in response["data"]:
        if not isinstance(item, dict):
            raise ValueError("Invalid embedding item")
        i = item.get("index")
        if type(i) is not int or not 0 <= i < count or i in out:
            raise ValueError("Invalid embedding index")
        out[i] = _vector(item.get("embedding"), dimension)
    return [out[i] for i in range(count)]


class SemanticSpanSelector:
    """Score every offered span, then optionally rerank the top 16.

    Budget is global to this selector instance, including failed requests.
    Always returns original IDs, not a generated summary or an authorization.
    No calibrated abstention threshold; scores are experimental rankings.
    """
    def __init__(self, config):
        if not isinstance(config, RetrievalConfig):
            raise ValueError("Expected retrieval configuration")
        self._config = config
        self._cache = OrderedDict()
        self._cache_limit = min(config.cache_entries, MAX_CACHE_COMPONENTS // config.dimension)
        self._cache_hits = 0
        self._deduplicated_inputs = 0
        self._successful_inputs_sent = 0
        self.requests = 0
        self.last_selection = None
        self._started = None

    @property
    def config(self):
        return self._config

    def cache_stats(self):
        """Counts from completed embedding operations, never content or vectors."""
        return {"entry_limit": self._cache_limit, "entries": len(self._cache),
                "cache_hits": self._cache_hits, "deduplicated_inputs": self._deduplicated_inputs,
                "successful_inputs_sent": self._successful_inputs_sent}

    def _missing_items(self, items):
        if not self._cache_limit:
            return list(items)
        return [item for item in dict.fromkeys(items) if item not in self._cache]

    def _call(self, port, path, payload):
        if self.requests >= self.config.max_requests:
            raise ValueError("Local retrieval request limit")
        now = time.monotonic()
        if self._started is None:
            self._started = now
        remaining = self.config.total_timeout - (now - self._started)
        if remaining <= 0:
            raise TimeoutError("Local retrieval time budget exhausted")
        self.requests += 1
        try:
            result = _post(port, path, payload, min(self.config.timeout, remaining))
            if time.monotonic() - self._started > self.config.total_timeout:
                raise TimeoutError("Local retrieval time budget exhausted")
            return result
        except Exception:
            self._cache.clear()
            raise

    def embed(self, items):
        """Bounded explicit embedding operation for session-local memory."""
        if (not isinstance(items, (list, tuple)) or not 1 <= len(items) <= MAX_SPANS + 1
                or any(not isinstance(s, str) or not s or len(s.encode("utf-8")) > MAX_ITEM_BYTES for s in items)):
            raise ValueError("Invalid or oversized embedding inputs")
        if self._started is not None and time.monotonic() - self._started >= self.config.total_timeout:
            self._cache.clear()
            raise TimeoutError("Local retrieval time budget exhausted")
        missing = self._missing_items(items)
        needed = (len(missing) + MAX_BATCH - 1) // MAX_BATCH
        if self.requests + needed > self.config.max_requests:
            raise ValueError("Local retrieval request budget insufficient")
        vectors = []
        try:
            for i in range(0, len(missing), MAX_BATCH):
                batch = missing[i:i + MAX_BATCH]
                response = self._call(self.config.embedding_port, "/v1/embeddings", {"input": batch})
                vectors.extend(embedding_results(response, len(batch), self.config.dimension))
        except Exception:
            # Do not retain a partial batch or reuse entries after a daemon failure.
            self._cache.clear()
            raise
        self._successful_inputs_sent += len(missing)
        if not self._cache_limit:
            return vectors
        resolved = {item: self._cache[item] for item in items if item in self._cache}
        self._cache_hits += sum(item in resolved for item in items)
        self._deduplicated_inputs += sum(item not in resolved for item in items) - len(missing)
        resolved.update((item, tuple(vector)) for item, vector in zip(missing, vectors))
        # Materialize results before eviction; never expose mutable cached vectors.
        result = [list(resolved[item]) for item in items]
        for item in items:
            self._cache[item] = resolved[item]
            self._cache.move_to_end(item)
            if len(self._cache) > self._cache_limit:
                self._cache.popitem(last=False)
        return result

    def __call__(self, query, spans):
        self.last_selection = None
        if not isinstance(query, str) or not query.strip() or not 1 <= len(spans) <= MAX_SPANS:
            raise ValueError("Invalid or oversized semantic candidate pool")
        ids = [s.id for s in spans]
        if any(type(i) is not int for i in ids) or len(set(ids)) != len(ids):
            raise ValueError("Invalid span identity")
        # Exact text deduplication is local to this single source result.
        # Keep the first occurrence and account for every original offset.
        # Never merge separate messages, sessions, or historical events.
        unique = {}
        groups = {}
        for span in spans:
            if not isinstance(span.text, str):
                raise ValueError("Invalid span text")
            if span.text not in unique:
                unique[span.text] = span
                groups[span.id] = []
            groups[unique[span.text].id].append(span.id)
        representatives = list(unique.values())
        self.last_selection = {"offered_occurrences": len(spans),
                               "unique_texts": len(representatives),
                               "duplicate_occurrences": len(spans) - len(representatives),
                               "occurrence_groups": groups}
        items = [self.config.query_prefix + query] + [s.text for s in representatives]
        if any(not isinstance(s, str) or not s or len(s.encode("utf-8")) > MAX_ITEM_BYTES for s in items):
            raise ValueError("Oversized local retrieval input")
        needed = (len(self._missing_items(items)) + MAX_BATCH - 1) // MAX_BATCH + int(self.config.reranker_port is not None)
        if self.requests + needed > self.config.max_requests:
            raise ValueError("Local retrieval request budget insufficient")
        vectors = self.embed(items)
        q = vectors[0]
        scored = [(s, max(-1.0, min(1.0, math.fsum(a * b for a, b in zip(q, v)))))
                  for s, v in zip(representatives, vectors[1:])]
        ranked = sorted(scored, key=lambda pair: (-pair[1], pair[0].id))
        threshold = self.config.min_similarity
        self.last_selection.update(similarity_scores=[{"id": s.id, "score": score} for s, score in ranked],
                                   experimental_min_similarity=threshold,
                                   answerability="unknown", embedding_cache=self.cache_stats())
        pool = [s for s, score in ranked if threshold is None or score >= threshold][:16]
        if not pool:
            self.last_selection["abstention"] = "experimental_similarity_cutoff"
            return []
        if self.config.reranker_port is not None:
            response = self._call(self.config.reranker_port, "/rerank",
                                  {"query": query, "documents": [s.text for s in pool]})
            try:
                scores = rerank_results([str(s.id) for s in pool], response)
            except Exception:
                self._cache.clear()
                raise
            return [int(sid) for sid, _ in scores[:6]]
        return [s.id for s in pool[:6]]
