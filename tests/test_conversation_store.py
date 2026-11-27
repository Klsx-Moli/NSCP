"""Tests del store SQLite. Headless: pytest tests/."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from conversation_store import ConversationStore, Turn  # noqa: E402


def make(tmp_path):
    return ConversationStore(str(tmp_path / "hist.db"))


def test_append_and_load_roundtrip(tmp_path):
    store = make(tmp_path)
    store.append("c1", Turn(role="user", content="hola"))
    store.append("c1", Turn(role="assistant", content="respuesta"))
    loaded = store.load("c1")
    assert len(loaded) == 2
    assert loaded[0].content == "hola"
    assert loaded[1].role == "assistant"
    assert loaded[0].turn_id == "c1#00001"
    store.close()


def test_isolation_between_conversations(tmp_path):
    store = make(tmp_path)
    store.append("a", Turn("user", "uno"))
    store.append("b", Turn("user", "dos"))
    assert store.count("a") == 1
    assert store.count("b") == 1
    assert store.load("a")[0].content == "uno"
    store.close()


def test_pinned_persists(tmp_path):
    store = make(tmp_path)
    store.append("c", Turn("system", "reglas", pinned=True))
    assert store.load("c")[0].pinned is True
    store.close()


def test_mark_summarized_is_not_destructive(tmp_path):
    store = make(tmp_path)
    for i in range(5):
        store.append("c", Turn("user", f"turno {i}"))
    n = store.mark_summarized("c", upto_seq=3, summary_id="sum-1")
    assert n == 3
    loaded = store.load("c")
    assert len(loaded) == 5  # nada se borra
    assert loaded[0].summarized_in == "sum-1"
    assert loaded[2].content == "turno 2"  # contenido íntegro
    assert loaded[4].summarized_in is None
    store.close()


def test_store_file_created(tmp_path):
    store = make(tmp_path)
    store.close()
    assert (tmp_path / "hist.db").exists()
