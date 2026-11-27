"""Tests del núcleo de compresión. Headless: pytest tests/."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import context_compactor as cc  # noqa: E402


def mk_history(n, chars=300, pinned_content=None):
    turns = []
    if pinned_content is not None:
        turns.append(cc.TurnView(role="system", content=pinned_content,
                                 pinned=True))
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        turns.append(cc.TurnView(role=role, content=(f"t{i} " + "x" * chars)))
    return [cc.TurnView(v.role, v.content,
                        cc.estimate_tokens(v.content), v.pinned)
            for v in turns]


def test_passthrough_below_threshold():
    hist = mk_history(4)
    messages, report = cc.compact_history(hist, num_ctx=8192, level="safe")
    assert report["triggered"] is False
    assert report["compression_ratio"] == 1.0
    assert len(messages) == 4
    assert messages[0]["role"] == "user"


def test_partition_keeps_recent_and_pinned():
    hist = mk_history(20, chars=120, pinned_content="REGLAS FIJAS")
    views = [cc.to_view(t) for t in hist]
    pinned, middle, recent = cc.partition_turns(views, keep_recent=8)
    assert len(pinned) == 1
    assert len(recent) == 8
    assert len(middle) == 12


def test_pinned_merged_into_first_system_message():
    hist = mk_history(20, chars=300, pinned_content="NO_DESTRUCTIVO")
    messages, report = cc.compact_history(hist, num_ctx=1024)
    assert report["triggered"] is True
    assert messages[0]["role"] == "system"
    assert "NO_DESTRUCTIVO" in messages[0]["content"]
    assert cc.HERMES_WRAPPER in messages[0]["content"]


def test_order_preserved_in_assembled_messages():
    hist = mk_history(20, chars=300)
    messages, _ = cc.compact_history(hist, num_ctx=2048)
    contents = [m["content"] for m in messages[1:]]  # saltar system
    tags = [c.split(" ")[0] for c in contents if c.startswith("t")]
    assert tags == sorted(tags, key=lambda t: int(t[1:]))


def test_offload_moves_large_blocks(tmp_path):
    big = cc.TurnView("assistant", "y" * 3000, 750)
    small = cc.TurnView("user", "corto", 2)
    out, count = cc.offload_large_blocks([big, small], str(tmp_path), 600)
    assert count == 1
    assert "movido a archivo" in out[0]["content"]
    assert out[1]["content"] == "corto"
    files = list(tmp_path.iterdir())
    assert len(files) == 1
    assert files[0].read_text() == "y" * 3000


def test_code_blocks_are_never_offloaded(tmp_path):
    code = cc.TurnView("assistant", "```python\n" + "x" * 3000 + "\n```", 800)
    out, count = cc.offload_large_blocks([code], str(tmp_path), 600)
    assert count == 0
    assert out[0]["content"].startswith("```python")


def test_without_summarizer_drops_oldest_middle():
    hist = mk_history(20, chars=300)  # ~75 tok/turno, total > umbral
    messages, report = cc.compact_history(hist, num_ctx=1024)
    assert report["triggered"] is True
    assert report["actions"]["dropped_turns"] > 0
    assert report["tokens_after"] < report["tokens_before"]
    assert report["compression_ratio"] > 1.0


def test_with_summarizer_injected():
    hist = mk_history(20, chars=300)
    fake = lambda turns: "RESUMEN: " + "; ".join(  # noqa: E731
        t.content[:6] for t in turns)
    messages, report = cc.compact_history(
        hist, num_ctx=1024, summarizer=fake)
    assert report["actions"]["summarized_turns"] == 12
    assert "RESUMEN" in messages[0]["content"]
    assert report["actions"]["dropped_turns"] == 0


def test_insufficient_window_raises():
    hist = mk_history(20, chars=300,
                      pinned_content="r" * 4000)  # pinned ~1000 tok
    with pytest.raises(ValueError):
        cc.compact_history(hist, num_ctx=200)
