import os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import context_compactor as cc


def mk_history(n, chars=300, pinned_content=None):
    turns = []
    if pinned_content is not None:
        turns.append(cc.TurnView(role="system", content=pinned_content, pinned=True))
    for i in range(n):
        turns.append(cc.TurnView(role="user" if i % 2 == 0 else "assistant", content=f"t{i} " + "x" * chars))
    return [cc.TurnView(v.role, v.content, cc.estimate_tokens(v.content), v.pinned) for v in turns]


def test_passthrough_below_threshold():
    msgs, rep = cc.compact_history(mk_history(4), num_ctx=8192, level="safe")
    assert rep["triggered"] is False and rep["compression_ratio"] == 1.0 and len(msgs) == 4 and msgs[0]["role"] == "user"


def test_partition_keeps_recent_and_pinned():
    views = [cc.to_view(t) for t in mk_history(20, chars=120, pinned_content="REGLAS FIJAS")]
    pinned, middle, recent = cc.partition_turns(views, keep_recent=8)
    assert len(pinned) == 1 and len(recent) == 8 and len(middle) == 12


def test_pinned_merged_into_first_system_message():
    msgs, rep = cc.compact_history(mk_history(20, pinned_content="NO_DESTRUCTIVO"), num_ctx=1024)
    assert rep["triggered"] is True and msgs[0]["role"] == "system"
    assert "NO_DESTRUCTIVO" in msgs[0]["content"] and cc.HERMES_WRAPPER in msgs[0]["content"]


def test_order_preserved_in_assembled_messages():
    msgs, _ = cc.compact_history(mk_history(20), num_ctx=2048)
    tags = [m["content"].split(" ")[0] for m in msgs[1:] if m["content"].startswith("t")]
    assert tags == sorted(tags, key=lambda t: int(t[1:]))


def test_offload_moves_large_blocks(tmp_path):
    big = cc.TurnView("assistant", "y" * 3000, 750)
    small = cc.TurnView("user", "corto", 2)
    out, count = cc.offload_large_blocks([big, small], str(tmp_path), 600)
    assert count == 1 and "movido a archivo" in out[0].content and out[1].content == "corto"
    files = list(tmp_path.iterdir())
    assert len(files) == 1 and files[0].read_text() == "y" * 3000


def test_code_blocks_are_never_offloaded(tmp_path):
    code = cc.TurnView("assistant", "```python\n" + "x" * 3000 + "\n```", 800)
    out, count = cc.offload_large_blocks([code], str(tmp_path), 600)
    assert count == 0 and out[0].content.startswith("```python")


def test_without_summarizer_drops_oldest_middle():
    msgs, rep = cc.compact_history(mk_history(20), num_ctx=1024)
    assert rep["triggered"] is True and rep["actions"]["dropped_turns"] > 0
    assert rep["tokens_after"] < rep["tokens_before"] and rep["compression_ratio"] > 1.0


def test_with_summarizer_injected():
    fake = lambda turns: "RESUMEN: " + "; ".join(t.content[:6] for t in turns)  # noqa: E731
    msgs, rep = cc.compact_history(mk_history(20), num_ctx=1024, summarizer=fake)
    assert rep["actions"]["summarized_turns"] == 12 and "RESUMEN" in msgs[0]["content"]
    assert rep["actions"]["dropped_turns"] == 0


def test_insufficient_window_raises():
    with pytest.raises(ValueError):
        cc.compact_history(mk_history(20, pinned_content="r" * 4000), num_ctx=200)


def test_offload_integrated_in_compact_history(tmp_path):
    hist = mk_history(20, chars=300)
    big = cc.TurnView("assistant", "z" * 4000, 1000)
    hist[2] = big
    msgs, rep = cc.compact_history(hist, num_ctx=2048, storage_dir=str(tmp_path))
    assert rep["actions"]["offloaded"] == 1 and len(list(tmp_path.iterdir())) == 1


def test_history_input_not_mutated():
    hist = mk_history(20)
    snapshot = [(v.role, v.content, v.token_count) for v in hist]
    cc.compact_history(hist, num_ctx=1024)
    assert snapshot == [(v.role, v.content, v.token_count) for v in hist]
