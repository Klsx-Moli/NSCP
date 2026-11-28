"""Qualify the installed Hermes host's NSCP hooks with synthetic data only.

Use the interpreter that normally runs Hermes. Imports the actual host
classes and hook/dispatch functions from an explicit source checkout, not
a live agent, gateway, provider or real session. Temporary home; no install
into the active profile. Socket blocking is an accident guard, not a sandbox.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from install_hermes_context import install

ROOT = Path(__file__).resolve().parents[1]


def _load_plugin(dest):
    spec = importlib.util.spec_from_file_location(
        "_nscp_qualification", dest / "__init__.py", submodule_search_locations=[str(dest)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fixture():
    rows = [
        {"role": "system", "content": "Synthetic offline host contract qualification."},
        {"role": "user", "content": "Inspect synthetic data."},
        {"role": "assistant", "content": "Inspecting."},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "synthetic-call", "type": "function",
             "function": {"name": "read", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "synthetic-call",
         "content": "routine synthetic log\n" * 900 + "Unique evidence: marker-XYZ."},
        {"role": "assistant", "content": "Inspection complete."},
    ]
    rows.extend([{"role": "user", "content": "Another question."},
                 {"role": "assistant", "content": "Synthetic answer."}] * 12)
    rows.append({"role": "user", "content": "What unique evidence was recorded?"})
    return rows


def qualify(host, report):
    # Record the actual imported code identity separately from the source
    # checkout's Git status. No claiming that a dirty checkout equals HEAD.
    for name, command in (("host_head", ["git", "-C", str(host), "rev-parse", "HEAD"]),
                          ("host_status", ["git", "-C", str(host), "status", "--porcelain"])):
        try:
            proc = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
            report[name] = (proc.stdout.strip() if proc.returncode == 0 else None)
        except (OSError, subprocess.TimeoutExpired):
            report[name] = None
    with tempfile.TemporaryDirectory(prefix="nscp-hermes-qualification-") as temp:
        home = Path(temp)
        os.environ["HERMES_HOME"] = str(home)
        os.environ["HOME"] = str(home)
        os.environ["USERPROFILE"] = str(home)
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["OLLAMA_NO_CLOUD"] = "1"
        for key in list(os.environ):
            if key.endswith(("_API_KEY", "_ACCESS_TOKEN", "_AUTH_TOKEN")):
                os.environ.pop(key, None)
        sys.path.insert(0, str(host))

        def blocked(*args, **kwargs):
            raise RuntimeError("Network disabled for qualification")

        # Only this script's process. No edits to host or environment registry.
        socket.socket.connect = blocked
        socket.socket.connect_ex = blocked
        socket.create_connection = blocked
        from agent import context_compressor, conversation_loop, agent_init, tool_executor

        modules = (context_compressor, conversation_loop, agent_init, tool_executor)
        for module in modules:
            if not Path(module.__file__).resolve().is_relative_to(host):
                raise ValueError("Host import escaped explicit source")
        report["host_modules"] = {m.__name__: str(Path(m.__file__).resolve().relative_to(host))
                                  for m in modules}
        from hashlib import sha256
        report["host_module_sha256"] = {m.__name__: sha256(Path(m.__file__).read_bytes()).hexdigest()
                                        for m in modules}
        plugin = _load_plugin(install(home, "nscp_hybrid"))
        plugin.check_host_contract()
        report["stages"]["signatures"] = "passed"
        rows = fixture()
        store = SimpleNamespace(messages=SimpleNamespace(read_conversation=lambda sid: [
            SimpleNamespace(as_openai_message=lambda row=row: row) for row in rows
        ] if sid == "synthetic-session" else []))
        engine = plugin.NSCPHybridContextEngine(
            config={"compression": {"protect_last_n": 8}}, output_reserve=2048, route="native",
            selection_mode="experimental", selection_route="bm25")
        engine.update_model("nscp-synthetic", 8192, base_url="http://127.0.0.1:1", provider="ollama")
        engine.bind_session_state(None, "synthetic-session", persistence=store)
        agent = SimpleNamespace(context_compressor=engine, tools=[], enabled_toolsets=None,
                                valid_tool_names=set(), session_id="synthetic-session",
                                platform="cli", model="nscp-synthetic",
                                _should_emit_quiet_tool_messages=lambda: False)
        logger = logging.getLogger("nscp.host.qualification")
        before = conversation_loop._apply_context_engine_selection(
            agent, rows, rows, rows[-1], logger=logger)
        if before != rows:
            raise ValueError("Archived without schema discovery")
        report["stages"]["pre_discovery_noop"] = "passed"
        agent_init._inject_context_engine_tools(agent)
        if "nscp_recall" not in agent._context_engine_tool_names:
            raise ValueError("Actual host did not install NSCP recall tool")
        if not tool_executor.is_context_engine_tool(agent, "nscp_recall"):
            raise ValueError("Actual dispatcher does not recognize NSCP recall")
        report["stages"]["host_tool_registration"] = "passed"
        # Rebind after host session-start callback, using synthetic store only.
        engine.bind_session_state(None, "synthetic-session", persistence=store)
        selected = conversation_loop._apply_context_engine_selection(
            agent, rows, rows, rows[-1], logger=logger)
        if selected == rows or not selected:
            raise ValueError("Host hook did not apply a synthetic plan")
        plan = engine.get_status()["nscp_request"]["nscp_last_plan"]
        if not plan or not plan["applied"] or plan["verification"]["status"] != "structurally_verified":
            raise ValueError("Missing structural verification")
        if "Unique evidence: marker-XYZ." not in selected[4]["content"]:
            raise ValueError("Expected exact excerpt missing")
        report["stages"]["host_request_selection"] = "passed"
        reference = plan["references"][0]
        call = tool_executor._ToolCallRef("nscp_recall", {"reference": reference}, "task", "recall", [])
        dispatch = tool_executor._resolve_sequential_dispatch(agent, call, selected)
        result = json.loads(dispatch.execute({"reference": reference, "limit": 20}))
        if result.get("content") != rows[4]["content"][:20]:
            raise ValueError("Host dispatch failed exact recall")
        report["stages"]["host_recall_dispatch"] = "passed"
        engine.bind_session_state(None, "other-session", persistence=store)
        result = json.loads(dispatch.execute({"reference": reference}))
        if "error" not in result:
            raise ValueError("Cross-session recall was not rejected")
        report["stages"]["session_isolation"] = "passed"
        report["stages"]["native_compression_inherited"] = (
            "passed" if type(engine).compress is context_compressor.ContextCompressor.compress else "failed")
        if report["stages"]["native_compression_inherited"] != "passed":
            raise ValueError("Native compressor was replaced")
        report["complete"] = True


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hermes-source", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args(argv)
    host = args.hermes_source.resolve(strict=True)
    if not (host / "agent" / "context_compressor.py").is_file():
        p.error("Supply the actual Hermes source root")
    if args.out.exists():
        p.error("Output already exists")
    report = {"schema": "nscp/hermes-host-qualification/v1", "complete": False, "stages": {},
              "limitations": ["synthetic persistence", "no provider generation",
                              "no live session", "no plugin discovery or actual compression",
                              "not production authorization"]}
    try:
        qualify(host, report)
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    return 0 if report["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
