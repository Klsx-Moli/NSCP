from __future__ import annotations
import os
import sqlite3
from dataclasses import dataclass

_SCHEMA = ("CREATE TABLE IF NOT EXISTS turns (conv_id TEXT NOT NULL, seq INTEGER NOT NULL, "
           "role TEXT NOT NULL, content TEXT NOT NULL, token_count INTEGER NOT NULL DEFAULT 0, "
           "pinned INTEGER NOT NULL DEFAULT 0, offloaded_path TEXT, summarized_in TEXT, "
           "PRIMARY KEY (conv_id, seq))")


@dataclass
class Turn:
    role: str
    content: str
    token_count: int = 0
    turn_id: str = ""
    pinned: bool = False
    offloaded_path: str | None = None
    summarized_in: str | None = None


class ConversationStore:
    def __init__(self, db_path):
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._db = sqlite3.connect(db_path)
        self._db.execute(_SCHEMA)
        self._db.commit()

    def append(self, conv_id, turn):
        seq = self._db.execute("SELECT COALESCE(MAX(seq),0) FROM turns WHERE conv_id=?", (conv_id,)).fetchone()[0] + 1
        if not turn.turn_id:
            turn.turn_id = f"{conv_id}#{seq:05d}"
        self._db.execute("INSERT INTO turns VALUES (?,?,?,?,?,?,?,?)",
                         (conv_id, seq, turn.role, turn.content, turn.token_count, int(turn.pinned),
                          turn.offloaded_path, turn.summarized_in))
        self._db.commit()
        return turn

    def load(self, conv_id):
        rows = self._db.execute("SELECT seq,role,content,token_count,pinned,offloaded_path,summarized_in "
                                "FROM turns WHERE conv_id=? ORDER BY seq", (conv_id,)).fetchall()
        return [Turn(r[1], r[2], r[3], f"{conv_id}#{r[0]:05d}", bool(r[4]), r[5], r[6]) for r in rows]

    def mark_summarized(self, conv_id, upto_seq, summary_id):
        c = self._db.execute("UPDATE turns SET summarized_in=? WHERE conv_id=? AND seq<=?",
                             (summary_id, conv_id, upto_seq))
        self._db.commit()
        return c.rowcount

    def count(self, conv_id):
        return self._db.execute("SELECT COUNT(*) FROM turns WHERE conv_id=?", (conv_id,)).fetchone()[0]

    def close(self):
        self._db.close()
