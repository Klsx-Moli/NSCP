import os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import random
import context_compactor as cc
from compaction_helpers import CODE, build, fake_summarizer


def test_code_turn_kept_verbatim_with_summarizer():
    hist = build(random.Random(1), 40, 5)
    msgs, rep = cc.compact_history(hist, num_ctx=3000, summarizer=fake_summarizer)
    out = "\n".join(m["content"] for m in msgs)
    a = rep["actions"]
    assert a["code_turns_kept"] > 0
    assert a["code_turns_kept"] + a["code_turns_dropped"] == sum(
        1 for v in cc.partition_turns(hist, 8)[1] if "```" in v.content)
    for v in cc.partition_turns(hist, 8)[1]:
        if "```" in v.content and a["code_turns_dropped"] == 0:
            assert v.content in out


def test_summarizer_never_receives_code_turns():
    seen = []

    def spy(turns):
        seen.extend(t.content for t in turns)
        return "RESUMEN"
    cc.compact_history(build(random.Random(2), 40, 3), num_ctx=3000, summarizer=spy)
    assert seen and all("```" not in s for s in seen)


def test_code_dropped_is_explicit_when_it_does_not_fit():
    hist = build(random.Random(3), 60, 1)
    msgs, rep = cc.compact_history(hist, num_ctx=1500)
    assert rep["actions"]["code_turns_dropped"] > 0
    assert rep["actions"]["code_turns_kept"] + rep["actions"]["code_turns_dropped"] > 0


def test_properties_over_random_histories():
    for seed in range(200):
        rng = random.Random(seed)
        n = rng.randint(10, 80)
        hist = build(rng, n, rng.choice([0, 1, 3, 7]))
        snapshot = [(v.role, v.content, v.token_count) for v in hist]
        ctx = rng.choice([1500, 2048, 4096])
        summ = fake_summarizer if rng.random() < 0.5 else None
        try:
            msgs, rep = cc.compact_history(hist, num_ctx=ctx, summarizer=summ)
        except ValueError:
            continue
        assert snapshot == [(v.role, v.content, v.token_count) for v in hist]
        if not rep["triggered"]:
            assert len(msgs) == len(hist)
            continue
        pinned, middle, recent = cc.partition_turns(hist, 8)
        assert all(p.content in msgs[0]["content"] for p in pinned)
        assert [m["content"] for m in msgs[len(msgs) - len(recent):]] == [r.content for r in recent]
        out = "\n".join(m["content"] for m in msgs)
        lost = sum(1 for v in middle if "```" in v.content and v.content not in out)
        assert lost == rep["actions"]["code_turns_dropped"], seed
        assert rep["tokens_after"] <= ctx, (seed, rep["tokens_after"], ctx)
