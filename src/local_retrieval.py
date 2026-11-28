"""Opt-in loopback llama.cpp retrieval for exact historical excerpts.

A trusted, explicitly configured local daemon is required. HTTP responses
cannot attest the server's loaded model or prove semantic correctness.
No process management, downloads, remote fallback or generated text.
"""
from __future__ import annotations

import json
import math
import urllib.request
from dataclasses import dataclass

from semantic_memory import _vector
from semantic_ranking import rerank_results

MAX_SPANS = 64
MAX_BATCH = 4
MAX_ITEM_BYTES = 1536
MAX_RESPONSE = 8 * 1024 * 1024


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
                or type(self.max_requests) is not int or not 1 <= self.max_requests <= 128):
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
        self.config = config
        self.requests = 0

    def _call(self, port, path, payload):
        if self.requests >= self.config.max_requests:
            raise ValueError("Local retrieval request limit")
        self.requests += 1
        return _post(port, path, payload, self.config.timeout)

    def __call__(self, query, spans):
        if not isinstance(query, str) or not query.strip() or not 1 <= len(spans) <= MAX_SPANS:
            raise ValueError("Invalid or oversized semantic candidate pool")
        ids = [s.id for s in spans]
        if any(type(i) is not int for i in ids) or len(set(ids)) != len(ids):
            raise ValueError("Invalid span identity")
        items = [self.config.query_prefix + query] + [s.text for s in spans]
        if any(not isinstance(s, str) or not s or len(s.encode("utf-8")) > MAX_ITEM_BYTES for s in items):
            raise ValueError("Oversized local retrieval input")
        needed = (len(items) + MAX_BATCH - 1) // MAX_BATCH + int(self.config.reranker_port is not None)
        if self.requests + needed > self.config.max_requests:
            raise ValueError("Local retrieval request budget insufficient")
        vectors = []
        for i in range(0, len(items), MAX_BATCH):
            batch = items[i:i + MAX_BATCH]
            response = self._call(self.config.embedding_port, "/v1/embeddings", {"input": batch})
            vectors.extend(embedding_results(response, len(batch), self.config.dimension))
        q = vectors[0]
        ranked = sorted(zip(spans, vectors[1:]), key=lambda pair: (
            -math.fsum(a * b for a, b in zip(q, pair[1])), pair[0].id))
        pool = [s for s, _ in ranked[:16]]
        if self.config.reranker_port is not None:
            response = self._call(self.config.reranker_port, "/rerank",
                                  {"query": query, "documents": [s.text for s in pool]})
            scores = rerank_results([str(s.id) for s in pool], response)
            return [int(sid) for sid, _ in scores[:6]]
        return [s.id for s in pool[:6]]
