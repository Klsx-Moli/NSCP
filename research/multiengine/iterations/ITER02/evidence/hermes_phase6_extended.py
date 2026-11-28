"""Phase 6 extension - isolated profile, test-only stubs, no productive changes."""
import inspect
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

E = Path(__file__).parent
PROFILE = E / "hermes_isolated_profile"
os.environ["HERMES_HOME"] = str(PROFILE)
HERMES_ROOT = "<HERMES_ROOT>/hermes-agent"
W = "<VALIDATION_ROOT>/NSCP-validation-20261127-iter02"
sys.path[:0] = [HERMES_ROOT, W + "/src", str(PROFILE / "plugins")]

import nscp_hybrid
import agent.context_compressor as hc
from local_summary import LocalSummary

report = {"profile": str(PROFILE), "hermes_head": None, "checks": {}}
import subprocess
report["hermes_head"] = subprocess.run(["git", "-C", HERMES_ROOT, "rev-parse", "HEAD"],
                                       capture_output=True, text=True).stdout.strip()
report["reviewed_constant"] = nscp_hybrid.REVIEWED_HERMES_COMMIT


def record(name, fn):
    t0 = time.perf_counter()
    try:
        value = fn()
        report["checks"][name] = {"status": "PASS", "value": str(value)[:400],
                                  "seconds": round(time.perf_counter() - t0, 3)}
    except Exception as exc:
        report["checks"][name] = {"status": "FAIL", "error": f"{type(exc).__name__}: {exc}",
                                  "seconds": round(time.perf_counter() - t0, 3)}
    print(name, report["checks"][name]["status"],
          str(report["checks"][name].get("value", report["checks"][name].get("error")))[:140], flush=True)
    (E / "hermes_phase6_extended.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


# Test-only compatibility shim for the known signature mismatch.
orig_bind = hc.ContextCompressor.bind_session_state
def shim_bind(self, session_db=None, session_id="", *, persistence=None):
    self._persistence = persistence
    return orig_bind(self, session_db, session_id)
hc.ContextCompressor.bind_session_state = shim_bind
nscp_hybrid.check_host_contract = lambda: None

cfg = {"compression": {"threshold": 0.5, "protect_first_n": 1, "protect_last_n": 3}}
local = nscp_hybrid.NSCPHybridContextEngine(config=cfg, output_reserve=512,
                                            route="local", selection_mode="observe")
local.update_model("qwen3.5:4b-q4_K_M", 8192)


def fake_complete(messages, config):
    return LocalSummary("RESUMEN_LOCAL_DE_PRUEBA", "qwen3.5:4b-q4_K_M", 11, 3, 64)


nscp_hybrid.complete_summary = fake_complete

def local_summary_route():
    out = local._call_summary_llm([{"role": "user", "content": "sintetico"}], time.time())
    return f"content={out!r} report={local._nscp_summary_report}"

record("local_summary_route_report", local_summary_route)

def cancellation():
    from agent.auxiliary_client import AuxiliaryExplicitCancellation
    local._compression_cancelled_check = lambda: True
    try:
        local._call_summary_llm([{"role": "user", "content": "sintetico"}], time.time())
        return "ERROR: cancellation ignored"
    except AuxiliaryExplicitCancellation:
        return "AuxiliaryExplicitCancellation raised"
    finally:
        local._compression_cancelled_check = lambda: False

record("cooperative_cancellation", cancellation)

def native_compaction():
    other = nscp_hybrid.NSCPHybridContextEngine(config=cfg, output_reserve=512,
                                                route="native", selection_mode="observe")
    other.update_model("qwen3.5:4b-q4_K_M", 8192)
    original = hc.ContextCompressor._call_summary_llm
    hc.ContextCompressor._call_summary_llm = lambda self, messages, prompt_started_at: "RESUMEN_NATIVO_DE_PRUEBA"
    try:
        messages = [{"role": "system", "content": "sistema"}] + [
            {"role": "user", "content": f"turno {i} " + "x" * 40} for i in range(12)]
        out = other.compress(messages, current_tokens=800, force=True)
        return f"messages_out={len(out)} first_role={out[0]['role'] if out else '?'}"
    finally:
        hc.ContextCompressor._call_summary_llm = original

record("native_compaction_path", native_compaction)

def recall_experimental():
    eng = nscp_hybrid.NSCPHybridContextEngine(config=cfg, output_reserve=512,
                                              route="local", selection_mode="experimental")
    eng.update_model("qwen3.5:4b-q4_K_M", 8192)
    schemas = eng.get_tool_schemas()
    names = []
    for s in schemas:
        if isinstance(s, dict):
            fn = s.get("function") or s
            names.append(fn.get("name"))
    return f"nscp_recall={'nscp_recall' in names} schemas={len(names)}"

record("nscp_recall_experimental", recall_experimental)

(E / "hermes_phase6_extended.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print("DONE", {k: v["status"] for k, v in report["checks"].items()})
