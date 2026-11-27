import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import context_compactor as cc
import random

CODE = "```python\ndef f_{i}():\n    return {i}\n```"


def build(rng, n, code_every):
    out = [cc.TurnView("system", "REGLA FIJA no destruir", pinned=True)]
    for i in range(n):
        body = f"t{i} " + "palabra " * rng.randint(20, 120)
        if code_every and i % code_every == 0:
            body += "\n" + CODE.format(i=i)
        out.append(cc.TurnView("user" if i % 2 == 0 else "assistant", body))
    return [cc.TurnView(v.role, v.content, cc.estimate_tokens(v.content), v.pinned) for v in out]


def fake_summarizer(turns):
    return "RESUMEN: " + "; ".join(t.content[:8] for t in turns)
