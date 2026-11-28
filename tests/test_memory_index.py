from pathlib import Path

import pytest

from memory_index import index_source, run_cli
from semantic_memory import SemanticMemory


def event(**kw):
    return dict(dict(episode="episode", message="message", role="tool", tool_call="call",
                     content="x" * 768 + "important evidence"), **kw)


def test_index_restart_replay_and_distinct_occurrences(tmp_path):
    db = tmp_path / "memory.sqlite"
    calls = []

    def embed(texts):
        calls.append(texts)
        return [[1, 0] for _ in texts]

    with SemanticMemory(db, session_id="s", embedding_id="model-v1", dimension=2) as mem:
        r = index_source(mem, embed, **event())
        assert r["inserted"] == 3 and r["embedded_unique_texts"] == 2
        assert len(mem.search([1, 0])) == 3
    with SemanticMemory(db, session_id="s", embedding_id="model-v1", dimension=2) as mem:
        assert index_source(mem, embed, **event())["inserted"] == 0
        assert len(calls) == 1
        assert mem.recall(episode="episode", message="message")["content"] == event()["content"]
        with pytest.raises(ValueError, match="immutable"):
            index_source(mem, embed, **event(content="changed"))
    with SemanticMemory(db, session_id="other", embedding_id="model-v1", dimension=2) as mem:
        assert not mem.search([1, 0])


def test_incomplete_batch_never_commits(tmp_path):
    with SemanticMemory(tmp_path / "memory.sqlite", session_id="s", embedding_id="v", dimension=2) as mem:
        with pytest.raises(ValueError):
            index_source(mem, lambda _: [[1, 0]], **event())
        assert mem.recall(episode="episode", message="message") is None


def test_missing_db_recall_does_not_create(tmp_path):
    db = tmp_path / "missing.sqlite"
    assert run_cli(["--db", str(db), "--session", "s", "--embedding-id", "v",
                    "recall", "--episode", "e", "--message", "m"]) == 2
    assert not Path(db).exists()
