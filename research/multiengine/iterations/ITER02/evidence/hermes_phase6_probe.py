"""Phase 6 - isolated Hermes/nscp_hybrid observation. No productive Hermes config touched."""
import inspect
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

E = Path(__file__).parent
PROFILE = E / "hermes_isolated_profile"
PROFILE.mkdir(exist_ok=True)
os.environ["HERMES_HOME"] = str(PROFILE)

HERMES_ROOT = "<HERMES_ROOT>/hermes-agent"
W = "<VALIDATION_ROOT>/NSCP-validation-20261127-iter02"
sys.path[:0] = [HERMES_ROOT, W + "/src", str(PROFILE / "plugins"), W + "/integrations/hermes"]

report = {"profile": str(PROFILE), "hermes_root": HERMES_ROOT,
          "reviewed_constant": None, "checks": {}}


def record(name, fn):
    t0 = time.perf_counter()
    try:
        value = fn()
        report["checks"][name] = {"status": "PASS", "value": str(value)[:500],
                                  "seconds": round(time.perf_counter() - t0, 2)}
    except Exception as exc:
        report["checks"][name] = {"status": "FAIL", "error": f"{type(exc).__name__}: {exc}",
                                  "seconds": round(time.perf_counter() - t0, 2)}
    print(name, report["checks"][name]["status"], str(report["checks"][name].get("value", report["checks"][name].get("error")))[:140], flush=True)


import subprocess
git_head = subprocess.run(["git", "-C", HERMES_ROOT, "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
report["hermes_git_head"] = git_head

import nscp_hybrid
import agent.context_compressor as hc
report["reviewed_constant"] = nscp_hybrid.REVIEWED_HERMES_COMMIT
report["import_paths"] = {
    "ContextCompressor": hc.ContextCompressor.__module__,
    "nscp_hybrid": nscp_hybrid.__file__,
    "compressor_file": inspect.getsourcefile(hc.ContextCompressor),
}
report["signature_audit"] = {}
for name, required in {
    "__init__": {"model", "max_tokens", "threshold_tokens_cap", "abort_on_summary_failure", "tail_mode", "model_thresholds", "min_tail_user_messages"},
    "update_model": {"model", "context_length", "max_tokens"},
    "compress": {"messages", "current_tokens", "force", "memory_context", "bypass_cooldown"},
    "bind_session_state": {"session_db", "session_id", "persistence"},
    "_call_summary_llm": {"messages", "prompt_started_at"},
}.items():
    method = getattr(hc.ContextCompressor, name, None)
    params = set(inspect.signature(method).parameters) if method else set()
    report["signature_audit"][name] = {"missing": sorted(required - params), "actual": sorted(params)}

record("host_contract", nscp_hybrid.check_host_contract)
cfg = {"compression": {"threshold": 0.5, "protect_first_n": 3, "protect_last_n": 20}}

record("construct_observe", lambda: nscp_hybrid.NSCPHybridContextEngine(
    config=cfg, output_reserve=2048, route="local", selection_mode="observe").name)

# Test-only compatibility shim: DOES NOT change productive Hermes or NSCP files.
original_bind = hc.ContextCompressor.bind_session_state
def shim_bind(self, session_db=None, session_id="", *, persistence=None):
    self._persistence = persistence
    return original_bind(self, session_db, session_id)
hc.ContextCompressor.bind_session_state = shim_bind
nscp_hybrid.check_host_contract = lambda: None

engine = None
def make_engine():
    global engine
    engine = nscp_hybrid.NSCPHybridContextEngine(
        config=cfg, output_reserve=2048, route="local", selection_mode="observe")
    return engine.name

record("construct_with_shim", make_engine)

def update_model():
    engine.update_model("qwen3.5:4b-q4_K_M", 8192)
    return f"name={engine.name} context={engine.context_length} threshold={engine.threshold_percent}"

record("update_model", update_model)

def bind_persistence():
    db = sqlite3.connect(str(PROFILE / "sessions.sqlite"))
    engine.bind_session_state(db, "session-A", persistence=object())
    return f"session={getattr(engine, '_session_id', '?')} persistence={'set' if getattr(engine,'_persistence',None) is not None else 'none'}"

record("persistence_available", bind_persistence)

def select_contract():
    result = engine.select_context(
        [{"role": "user", "content": "resume"}],
        conversation_messages=[{"role": "user", "content": "contexto " * 50}],
        incoming_message={"role": "user", "content": "pregunta"},
        budget_tokens=8192)
    return f"selection_type={type(result).__name__} mode={engine._nscp_selection.mode}"

record("selection_contract", select_contract)

def recall_registration():
    schemas = engine.get_tool_schemas()
    names = []
    for s in schemas:
        if isinstance(s, dict):
            fn = s.get("function") or s
            names.append(fn.get("name"))
    return f"schemas={len(schemas)} nscp_recall={'nscp_recall' in names}"

record("nscp_recall_manifest", recall_registration)

def native_route():
    other = nscp_hybrid.NSCPHybridContextEngine(
        config=cfg, output_reserve=2048, route="native", selection_mode="observe")
    other.update_model("qwen3.5:4b-q4_K_M", 8192)
    return f"route={other._nscp_route} name={other.name}"

record("native_route_identity", native_route)

def local_failure():
    from local_summary import LocalSummaryConfig, complete_summary
    bad = LocalSummaryConfig(model="modelo-inexistente:latest", timeout=5)
    try:
        complete_summary([{"role": "user", "content": "x"}], bad)
        return "ERROR: accepted missing model"
    except Exception as exc:
        return f"controlled_failure={type(exc).__name__}"

record("controlled_local_failure", local_failure)

def reset_recovery():
    engine.on_session_reset()
    engine.update_model("qwen3.5:4b-q4_K_M", 8192)
    return f"post_reset_compression_count={engine.compression_count}"

record("reset_recovery", reset_recovery)

def signature_compat():
    clone = engine.clone_for_agent()
    return f"clone_name={clone.name} route={clone._nscp_route}"

record("signature_compatibility", signature_compat)

(E / "hermes_phase6.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print("DONE", {k: v["status"] for k, v in report["checks"].items()})
