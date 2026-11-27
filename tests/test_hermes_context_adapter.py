"""Adapter contract tests with a fake host; not a live Hermes integration test."""
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from test_agent_context import transcript

ROOT = Path(__file__).resolve().parents[1]


def load_file(name, path, package=False):
    spec = importlib.util.spec_from_file_location(
        name, path, submodule_search_locations=[str(path.parent)] if package else None)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def engine(monkeypatch, tmp_path):
    class ContextEngine:
        def get_status(self):
            return {}

        def on_session_reset(self):
            self.compression_count = 0

    agent = ModuleType("agent")
    contract = ModuleType("agent.context_engine")
    contract.ContextEngine = ContextEngine
    monkeypatch.setitem(sys.modules, "agent", agent)
    monkeypatch.setitem(sys.modules, "agent.context_engine", contract)
    installer = load_file("_nscp_installer_test", ROOT / "scripts" / "install_hermes_context.py")
    dest = installer.install(tmp_path)
    plugin = load_file("_nscp_test_plugin", dest / "__init__.py", package=True)
    try:
        yield plugin.NSCPContextEngine(), installer, dest
    finally:
        for name in list(sys.modules):
            if name.startswith("_nscp_test_plugin") or name == "_nscp_installer_test":
                sys.modules.pop(name, None)


def old_history():
    source = transcript()
    for i in range(10):
        source.extend([{"role": "user", "content": f"question {i}"},
                       {"role": "assistant", "content": "answer"}])
    return source


def test_adapter_request_selection_and_recall(engine):
    instance, _, _ = engine
    rows = old_history()
    store = SimpleNamespace(messages=SimpleNamespace(read_conversation=lambda session: [
        SimpleNamespace(as_openai_message=lambda row=row: row) for row in rows
    ] if session == "s1" else []))
    instance.bind_session_state(None, "s1", store)
    output = instance.select_context(rows, budget_tokens=6000)
    assert output is not None and output[4]["content"] != rows[4]["content"]
    ref = instance.get_status()["nscp_last_plan"]["references"][0]
    result = json.loads(instance.handle_tool_call("nscp_recall", {"reference": ref, "limit": 20}))
    assert result["content"] == rows[4]["content"][:20]
    assert instance.compress(rows, force=True) == rows
    assert instance.should_compress() is False
    instance.on_session_reset()
    assert instance.select_context(rows, budget_tokens=6000) is None
    assert "error" in json.loads(instance.handle_tool_call("nscp_recall", {"reference": ref}))


def test_clone_does_not_inherit_session_and_installer_is_non_overwriting(engine):
    instance, installer, dest = engine
    instance.bind_session_state(None, "secret", object())
    clone = instance.clone_for_agent()
    assert clone._session_id is None and clone._persistence is None
    assert installer.install(dest.parent.parent) == dest
    (dest / "plugin.yaml").write_text("custom", encoding="utf-8")
    with pytest.raises(FileExistsError):
        installer.install(dest.parent.parent)
    assert (dest / "plugin.yaml").read_text(encoding="utf-8") == "custom"


def test_unavailable_persistence_is_noop(engine):
    instance, _, _ = engine
    instance.bind_session_state(None, "s1")
    assert instance.select_context(old_history(), budget_tokens=1000) is None
