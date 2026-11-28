"""Session-scoped exact-source memory with versioned embedding spaces.

Experimental local SQLite component. No inference, network or implicit
cross-session retrieval. Text is historical data, not current authority.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1
ROLES = {"system", "user", "assistant", "tool"}


def _identifier(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 512 or "\x00" in value:
        raise ValueError("Invalid identity")
    return value


def _integer(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("Invalid integer")
    return value


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _vector(vector, dimension):
    if not isinstance(vector, (list, tuple)) or len(vector) != dimension:
        raise ValueError("Invalid vector dimension")
    if any(type(x) not in (int, float) for x in vector):
        raise ValueError("Invalid vector component")
    try:
        values = [float(x) for x in vector]
    except OverflowError as exc:
        raise ValueError("Invalid vector component") from exc
    if any(not math.isfinite(x) for x in values):
        raise ValueError("Non-finite vector")
    scale = max(abs(x) for x in values)
    if scale == 0:
        raise ValueError("Zero vector")
    scaled = [x / scale for x in values]
    norm = math.sqrt(math.fsum(x * x for x in scaled))
    return [x / norm for x in scaled]


class SemanticMemory:
    def __init__(self, path, *, session_id, embedding_id, dimension):
        self.session_id = _identifier(session_id)
        # Include model revision, tokenizer, input policy and runtime in this
        # caller-supplied identity. A display name alone is not sufficient.
        self.embedding_id = _identifier(embedding_id)
        self.dimension = _integer(dimension, 1, 16384)
        self.db = sqlite3.connect(str(Path(path)), timeout=5)
        self.db.row_factory = sqlite3.Row
        try:
            self.db.execute("PRAGMA foreign_keys=ON")
            with self.db:
                self.db.execute("BEGIN IMMEDIATE")
                version = self.db.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, SCHEMA_VERSION):
                    raise ValueError("Unsupported memory schema")
                if version == 0:
                    tables = self.db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                    ).fetchall()
                    if tables:
                        raise ValueError("Unrecognized existing database")
                    self.db.execute("""CREATE TABLE sources (
                        session TEXT NOT NULL, episode TEXT NOT NULL, message TEXT NOT NULL,
                        role TEXT NOT NULL, tool_call TEXT NOT NULL,
                        content TEXT NOT NULL, digest TEXT NOT NULL,
                        PRIMARY KEY(session, episode, message))""")
                    self.db.execute("""CREATE TABLE vectors (
                        session TEXT NOT NULL, episode TEXT NOT NULL, message TEXT NOT NULL,
                        start INTEGER NOT NULL, end INTEGER NOT NULL,
                        embedding TEXT NOT NULL, dimension INTEGER NOT NULL,
                        vector TEXT NOT NULL, span_digest TEXT NOT NULL,
                        PRIMARY KEY(session, episode, message, start, end, embedding),
                        FOREIGN KEY(session, episode, message)
                          REFERENCES sources(session, episode, message))""")
                    self.db.execute("CREATE TABLE spaces (embedding TEXT PRIMARY KEY, dimension INTEGER NOT NULL)")
                    self.db.execute("PRAGMA user_version=1")
                self.db.execute("INSERT OR IGNORE INTO spaces VALUES (?,?)",
                                (self.embedding_id, self.dimension))
                recorded = self.db.execute("SELECT dimension FROM spaces WHERE embedding=?",
                                           (self.embedding_id,)).fetchone()[0]
                if recorded != self.dimension:
                    raise ValueError("Embedding identity dimension conflict")
        except BaseException:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def add(self, *, episode, message, role, content, start, end, vector, tool_call=""):
        episode, message = _identifier(episode), _identifier(message)
        if role not in ROLES or not isinstance(content, str) or len(content) > 2_000_000:
            raise ValueError("Invalid source")
        if not isinstance(tool_call, str) or (role == "tool" and not tool_call):
            raise ValueError("Invalid tool identity")
        if tool_call:
            _identifier(tool_call)
        start = _integer(start, 0, len(content))
        end = _integer(end, start + 1, len(content))
        normalized = _vector(vector, self.dimension)
        # Canonical JSON makes exact replay distinguishable from conflicting
        # re-embedding. Re-embedding with a different identity is allowed.
        encoded = json.dumps(normalized, separators=(",", ":"), allow_nan=False)
        digest, span_digest = _digest(content), _digest(content[start:end])
        key = (self.session_id, episode, message)
        vkey = (*key, start, end, self.embedding_id)
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            old = self.db.execute("SELECT role,tool_call,content,digest FROM sources "
                                  "WHERE session=? AND episode=? AND message=?", key).fetchone()
            source = (role, tool_call, content, digest)
            if old is None:
                self.db.execute("INSERT INTO sources VALUES (?,?,?,?,?,?,?)", (*key, *source))
            elif tuple(old) != source:
                raise ValueError("Conflicting immutable source identity")
            old = self.db.execute("SELECT dimension,vector,span_digest FROM vectors WHERE "
                                  "session=? AND episode=? AND message=? AND start=? AND end=? AND embedding=?",
                                  vkey).fetchone()
            payload = (self.dimension, encoded, span_digest)
            if old is None:
                self.db.execute("INSERT INTO vectors VALUES (?,?,?,?,?,?,?,?,?)", (*vkey, *payload))
                return True
            if tuple(old) != payload:
                raise ValueError("Conflicting embedding replay")
            return False

    def _checked_source(self, row):
        content = row["content"]
        if not isinstance(content, str) or _digest(content) != row["digest"]:
            raise ValueError("Source integrity mismatch")
        return content

    def recall(self, *, episode, message, offset=0, limit=4000):
        key = (self.session_id, _identifier(episode), _identifier(message))
        _integer(offset, 0, 2_000_000)
        _integer(limit, 1, 12000)
        row = self.db.execute("SELECT * FROM sources WHERE session=? AND episode=? AND message=?",
                              key).fetchone()
        if row is None:
            return None
        content = self._checked_source(row)
        if offset > len(content):
            raise ValueError("Offset exceeds source")
        end = min(len(content), offset + limit)
        return {"session": self.session_id, "episode": episode, "message": message,
                "role": row["role"], "tool_call": row["tool_call"], "digest": row["digest"],
                "offset": offset, "end": end, "content": content[offset:end],
                "next_offset": end if end < len(content) else None,
                "trust": "historical_data_not_authorization"}

    def search(self, vector, *, k=8):
        _integer(k, 1, 256)
        query = _vector(vector, self.dimension)
        rows = self.db.execute("""SELECT v.*,s.content,s.digest,s.role,s.tool_call
            FROM vectors v JOIN sources s USING(session,episode,message)
            WHERE v.session=? AND v.embedding=? ORDER BY v.episode,v.message,v.start,v.end""",
                               (self.session_id, self.embedding_id))
        hits = []
        for row in rows:
            content = self._checked_source(row)
            start = _integer(row["start"], 0, len(content))
            end = _integer(row["end"], start + 1, len(content))
            text = content[start:end]
            if _digest(text) != row["span_digest"] or row["dimension"] != self.dimension:
                raise ValueError("Vector/source integrity mismatch")
            stored = _vector(json.loads(row["vector"]), self.dimension)
            score = math.fsum(a * b for a, b in zip(query, stored))
            hits.append({"session": self.session_id, "episode": row["episode"],
                         "message": row["message"], "role": row["role"], "tool_call": row["tool_call"],
                         "start": start, "end": end, "text": text, "source_digest": row["digest"],
                         "span_digest": row["span_digest"], "score": max(-1.0, min(1.0, score)),
                         "trust": "historical_data_not_authorization"})
        return sorted(hits, key=lambda h: -h["score"])[:k]
