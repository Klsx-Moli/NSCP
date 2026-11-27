"""Historial conversacional persistente para el compactor de contexto.

Principio duro del módulo: este store guarda SIEMPRE el historial
íntegro. La compresión solo reescribe lo que se envía al modelo; nunca
modifica, recorta ni borra lo almacenado aquí. La compresión "olvida
más despacio", pero sin este store no hay memoria que recuperar.

Sin dependencias externas: sqlite3 de la biblioteca estándar.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS turns (
    conv_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER NOT NULL DEFAULT 0,
    pinned INTEGER NOT NULL DEFAULT 0,
    offloaded_path TEXT,
    summarized_in TEXT,
    PRIMARY KEY (conv_id, seq)
)
"""


@dataclass
class Turn:
    """Un turno de conversación, tal como se almacena en el store."""

    role: str  # system | user | assistant | tool
    content: str
    token_count: int = 0
    turn_id: str = ""
    pinned: bool = False
    offloaded_path: str | None = None
    summarized_in: str | None = None


class ConversationStore:
    """Historial persistente en SQLite. No destructivo por diseño."""

    def __init__(self, db_path: str):
        base = os.path.dirname(os.path.abspath(db_path))
        os.makedirs(base, exist_ok=True)
        self._db = sqlite3.connect(db_path)
        self._db.execute(_SCHEMA)
        self._db.commit()

    def append(self, conv_id: str, turn: Turn) -> Turn:
        """Añade un turno al final y le asigna turn_id si no tiene."""
        seq = self._db.execute(
            "SELECT COALESCE(MAX(seq), 0) FROM turns WHERE conv_id = ?",
            (conv_id,),
        ).fetchone()[0] + 1
        if not turn.turn_id:
            turn.turn_id = f"{conv_id}#{seq:05d}"
        self._db.execute(
            "INSERT INTO turns (conv_id, seq, role, content, token_count,"
            " pinned, offloaded_path, summarized_in)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                conv_id,
                seq,
                turn.role,
                turn.content,
                turn.token_count,
                int(turn.pinned),
                turn.offloaded_path,
                turn.summarized_in,
            ),
        )
        self._db.commit()
        return turn

    def load(self, conv_id: str) -> list[Turn]:
        """Historial íntegro, en orden, incluidas anotaciones."""
        rows = self._db.execute(
            "SELECT seq, role, content, token_count, pinned, offloaded_path,"
            " summarized_in FROM turns WHERE conv_id = ? ORDER BY seq",
            (conv_id,),
        ).fetchall()
        return [
            Turn(
                role=r[1],
                content=r[2],
                token_count=r[3],
                turn_id=f"{conv_id}#{r[0]:05d}",
                pinned=bool(r[4]),
                offloaded_path=r[5],
                summarized_in=r[6],
            )
            for r in rows
        ]

    def mark_summarized(self, conv_id: str, upto_seq: int,
                        summary_id: str) -> int:
        """Anota turnos con seq <= upto_seq como contenidos en un resumen.

        Solo anota; NO borra ni edita el contenido original. Devuelve
        el número de turnos marcados.
        """
        cur = self._db.execute(
            "UPDATE turns SET summarized_in = ?"
            " WHERE conv_id = ? AND seq <= ?",
            (summary_id, conv_id, upto_seq),
        )
        self._db.commit()
        return cur.rowcount

    def count(self, conv_id: str) -> int:
        return self._db.execute(
            "SELECT COUNT(*) FROM turns WHERE conv_id = ?", (conv_id,)
        ).fetchone()[0]

    def close(self) -> None:
        self._db.close()
