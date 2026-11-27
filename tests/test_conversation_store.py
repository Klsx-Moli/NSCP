import os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from conversation_store import ConversationStore, Turn


def make(tmp_path):
    return ConversationStore(str(tmp_path / "hist.db"))


def test_append_and_load_roundtrip(tmp_path):
    s = make(tmp_path)
    s.append("c1", Turn(role="user", content="hola"))
    s.append("c1", Turn(role="assistant", content="respuesta"))
    l = s.load("c1")
    assert len(l) == 2 and l[0].content == "hola" and l[1].role == "assistant" and l[0].turn_id == "c1#00001"
    s.close()


def test_isolation_between_conversations(tmp_path):
    s = make(tmp_path)
    s.append("a", Turn("user", "uno"))
    s.append("b", Turn("user", "dos"))
    assert s.count("a") == 1 and s.count("b") == 1 and s.load("a")[0].content == "uno"
    s.close()


def test_pinned_persists(tmp_path):
    s = make(tmp_path)
    s.append("c", Turn("system", "reglas", pinned=True))
    assert s.load("c")[0].pinned is True
    s.close()


def test_mark_summarized_is_not_destructive(tmp_path):
    s = make(tmp_path)
    for i in range(5):
        s.append("c", Turn("user", f"turno {i}"))
    assert s.mark_summarized("c", upto_seq=3, summary_id="sum-1") == 3
    l = s.load("c")
    assert len(l) == 5 and l[0].summarized_in == "sum-1" and l[2].content == "turno 2" and l[4].summarized_in is None
    s.close()


def test_store_file_created(tmp_path):
    s = make(tmp_path)
    s.close()
    assert (tmp_path / "hist.db").exists()
