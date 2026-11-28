import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from conversation_store import ConversationStore, Turn


def make(tmp_path):
    return ConversationStore(str(tmp_path / "hist.db"))


def test_append_and_load_roundtrip(tmp_path):
    s = make(tmp_path)
    s.append("c1", Turn(role="user", content="hola"))
    s.append("c1", Turn(role="assistant", content="respuesta"))
    loaded = s.load("c1")
    assert len(loaded) == 2 and loaded[0].content == "hola" and loaded[1].role == "assistant" and loaded[0].turn_id == "c1#00001"
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
    loaded = s.load("c")
    assert len(loaded) == 5 and loaded[0].summarized_in == "sum-1" and loaded[2].content == "turno 2" and loaded[4].summarized_in is None
    s.close()


def test_store_file_created(tmp_path):
    s = make(tmp_path)
    s.close()
    assert (tmp_path / "hist.db").exists()
