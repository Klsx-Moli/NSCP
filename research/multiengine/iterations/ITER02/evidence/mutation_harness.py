"""Mutation execution on disposable copies of the 9e6646b tree."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

E = Path(__file__).parent
SRC_WORKTREE = Path(sys.argv[1])
PY = str(SRC_WORKTREE / ".venv/Scripts/python.exe")
ROOT = Path(tempfile.mkdtemp(prefix="nscp-mutations-", dir=str(E)))

MUTATIONS = [
    ("MUT-NEG-001", "local_summary.py",
     'if result.get("done") is not True or result.get("done_reason") != "stop":',
     'if result.get("done") is False:',
     ["tests/test_local_summary.py", "tests/test_summarizer.py"],
     "accept truncated/non-stop responses"),
    ("MUT-AUTH-001", "local_summary.py",
     'url.hostname not in ("localhost", "127.0.0.1", "::1")',
     'url.hostname not in ("localhost", "127.0.0.1", "::1", "api.openai.com")',
     ["tests/test_local_summary.py"],
     "authorize a non-loopback provider"),
    ("MUT-SILENT-001", "context_compactor.py",
     '"verification": {"status": "not_verified"}',
     '"verification": {"status": "verified"}',
     ["tests/test_context_compactor.py", "tests/test_context_loss.py"],
     "claim verification without running it"),
    ("MUT-ACCOUNT-001", "token_estimator.py",
     'tokens = math.ceil(chars / 4)',
     'tokens = math.ceil(chars / 4) * 2',
     ["tests/test_agent_context_benchmark.py", "tests/test_agent_context.py"],
     "double estimated token counts"),
    ("MUT-ROLE-001", "context_compactor.py",
     '{"role": v.role if v.role in _VALID_ROLES else "user", "content": v.content} for v in views]',
     '{"role": "user", "content": v.content} for v in views]',
     ["tests/test_context_compactor.py"],
     "force every compacted role to user"),
    ("MUT-META-001", "context_compactor.py",
     '"schema": "neuroprompt/compaction-result/v1",',
     '"schema": "corrupted",',
     ["tests/test_agent_context.py"],
     "corrupt compaction result schema metadata"),
    ("MUT-COUNT-001", "context_compactor.py",
     '"compression_ratio": round(before / after, 2) if after else 0.0,',
     '"compression_ratio": round(2 * before / after, 2) if after else 0.0,',
     ["tests/test_context_compactor.py", "tests/test_agent_context_benchmark.py"],
     "double the reported compression ratio"),
    ("MUT-ID-001", "agent_context.py",
     'identity = [message["role"], message.get("tool_call_id"), message["content"]]',
     'identity = [message["role"], None, message["content"]]',
     ["tests/test_agent_context.py", "tests/test_hermes_context_adapter.py"],
     "ignore tool_call_id in message identity"),
]

IGNORE = shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", ".tmp", "*.egg-info")
out = {"sha": "9e6646b418a34d36d8ba09eb354bd81191caff69", "copies_root": str(ROOT), "results": {}}

for mid, rel, old, new, tests, semantics in MUTATIONS:
    work = ROOT / mid
    work.mkdir()
    for item in ("src", "tests", "integrations", "tools", "scripts", "pyproject.toml", "requirements.txt"):
        p = SRC_WORKTREE / item
        if p.is_dir():
            shutil.copytree(p, work / item, ignore=IGNORE)
        elif p.exists():
            shutil.copy(p, work / item)
    target = work / "src" / rel
    text = target.read_text(encoding="utf-8")
    if old not in text:
        out["results"][mid] = {"verdict": "APPLY_FAILED", "semantics": semantics,
                               "detail": "exact source fragment not found"}
        print(mid, "APPLY_FAILED", flush=True)
        continue
    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(work / "src"), QT_QPA_PLATFORM="offscreen",
               PYTHONDONTWRITEBYTECODE="1")
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [PY, "-m", "pytest", "-q", "--tb=no", "-p", "no:cacheprovider",
             "--basetemp", str(ROOT / (mid + "-tmp")), *tests],
            cwd=str(work), env=env, capture_output=True, text=True, timeout=120,
        )
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-1][:300] if (proc.stdout + proc.stderr).strip() else "no output"
        killed = proc.returncode != 0
        verdict = "KILLED" if killed else "FALSE_COVERAGE"
        detail = f"rc={proc.returncode} summary={tail}"
    except subprocess.TimeoutExpired:
        verdict, detail = "KILLED_TIMEOUT", "targeted run exceeded 120s"
    out["results"][mid] = {
        "verdict": verdict, "semantics": semantics, "detail": detail,
        "tests": tests, "duration_s": round(time.perf_counter() - t0, 2),
        "copy": str(work),
        "stdout_tail": tail if "tail" in locals() else "",
    }
    print(mid, verdict, detail[:120], flush=True)

counts = {}
for r in out["results"].values():
    counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
out["counts"] = counts
(E / "mutation_execution.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
print("COUNTS", counts)
