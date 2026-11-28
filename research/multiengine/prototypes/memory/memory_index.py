"""Isolated persistent vector-memory prototype for ITER05. No product imports, no global config."""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from pathlib import Path

TOKEN_RE = re.compile(r"[A-Za-z0-9_./:-]+")


def cosine(a, b):
    if len(a) != len(b) or not a:
        raise ValueError("vector length mismatch")
    return sum(x * y for x, y in zip(a, b))


def tokens(text):
    return [t.lower() for t in TOKEN_RE.findall(text)]


class MemoryIndex:
    def __init__(self, db_path, active_model, index_version="v1"):
        self.db_path = str(db_path)
        self.active_model = active_model
        self.index_version = index_version
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL, episode_id TEXT NOT NULL, message_id TEXT NOT NULL,
                role TEXT NOT NULL, tool_call_id TEXT, source_sha256 TEXT NOT NULL,
                offset_start INTEGER NOT NULL, offset_end INTEGER NOT NULL,
                text TEXT NOT NULL, embedding_model TEXT NOT NULL, index_version TEXT NOT NULL,
                vector BLOB NOT NULL, event_key TEXT NOT NULL,
                UNIQUE(session_id, episode_id, message_id, tool_call_id, source_sha256, offset_start, offset_end)
            )""")
        self.conn.execute("CREATE INDEX IF NOT EXISTS ix_model ON chunks(embedding_model)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS ix_session ON chunks(session_id)")
        self.conn.commit()

    def add(self, *, session_id, episode_id, message_id, role="user", tool_call_id="",
            source_sha256, offset_start=0, offset_end=0, text, vector):
        if not isinstance(vector, list) or not vector:
            raise ValueError("empty vector")
        if any(not math.isfinite(float(x)) for x in vector):
            raise ValueError("non-finite vector component")
        key = "|".join([session_id, episode_id, message_id, tool_call_id or "",
                        source_sha256, str(offset_start), str(offset_end)])
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        cur = self.conn.execute("""INSERT OR IGNORE INTO chunks
            (session_id,episode_id,message_id,role,tool_call_id,source_sha256,offset_start,offset_end,
             text,embedding_model,index_version,vector,event_key)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (session_id, episode_id, message_id, role, tool_call_id or "", source_sha256,
             offset_start, offset_end, text, self.active_model, self.index_version,
             json.dumps([float(x) for x in vector]), digest))
        self.conn.commit()
        return cur.rowcount == 1

    def rows(self, session_id=None, model=None):
        q, args = "SELECT * FROM chunks WHERE embedding_model=?", [model or self.active_model]
        if session_id is not None:
            q += " AND session_id=?"
            args.append(session_id)
        return [dict(r) for r in self.conn.execute(q, args).fetchall()]

    def needs_reindex(self):
        other = self.conn.execute("SELECT COUNT(*) n FROM chunks WHERE embedding_model<>?",
                                  (self.active_model,)).fetchone()["n"]
        return other > 0

    def vector_search(self, query_vec, k=5, session_id=None):
        out = []
        for r in self.rows(session_id):
            v = json.loads(r["vector"])
            try:
                out.append((cosine(query_vec, v), r))
            except ValueError:
                continue
        return sorted(out, key=lambda x: -x[0])[:k]

    def bm25_search(self, query, k=5, session_id=None):
        rows = self.rows(session_id)
        docs = [tokens(r["text"]) for r in rows]
        n = len(docs)
        if not n:
            return []
        avdl = sum(len(d) for d in docs) / n
        df = {}
        for d in docs:
            for t in set(d):
                df[t] = df.get(t, 0) + 1
        k1, b = 1.5, 0.75
        scored = []
        qt = tokens(query)
        for r, d in zip(rows, docs):
            tf = {}
            for t in d:
                tf[t] = tf.get(t, 0) + 1
            score = 0.0
            for t in qt:
                if t not in tf:
                    continue
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                score += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avdl))
            if score > 0:
                scored.append((score, r))
        return sorted(scored, key=lambda x: -x[0])[:k]

    def hybrid_search(self, query, query_vec, k=5, session_id=None):
        a = self.vector_search(query_vec, k * 2, session_id)
        b = self.bm25_search(query, k * 2, session_id)
        rrf = {}
        for rank, (_, r) in enumerate(a, 1):
            rrf[r["id"]] = rrf.get(r["id"], 0) + 1 / (60 + rank)
        for rank, (_, r) in enumerate(b, 1):
            rrf[r["id"]] = rrf.get(r["id"], 0) + 1 / (60 + rank)
        by_id = {r["id"]: r for r in self.rows(session_id)}
        return [(s, by_id[i]) for i, s in sorted(rrf.items(), key=lambda x: -x[1])][:k]

    def rehydrate(self, chunk_id):
        r = self.conn.execute("SELECT * FROM chunks WHERE id=?", (chunk_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["vector_dim"] = len(json.loads(d["vector"]))
        return d

    def close(self):
        self.conn.close()
