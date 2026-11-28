"""Native hybrid contract tests: a simulated host, not live Hermes."""
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from test_agent_context import transcript

ROOT = Path(__file__).resolve().parents[1]


class Cancellation(Exception):
    pass


class FakeNative:
    """Minimal native contract with sentinels for delegation/failure paths."""
    def __init__(self, model, threshold_percent=0.5, protect_first_n=3,
                 protect_last_n=20, summary_target_ratio=0.2, abort_on_summary_failure=False,
                 max_tokens=None, model_thresholds=None, threshold_tokens_cap=None,
                 proactive_prune_tokens=0, proactive_prune_min_result_chars=8000,
                 proactive_prune_min_reclaim_tokens=4096, min_tail_user_messages=1,
                 tail_mode="lean"):
        self.model = model
        self.threshold_percent = threshold_percent
        self.protect_first_n = protect_first_n
        self.protect_last_n = protect_last_n
        self.abort_on_summary_failure = abort_on_summary_failure
        self.max_tokens = max_tokens
        self.context_length = 0
        self._session_id = ""
        self._persistence = None
        self._last_summary_error = None
        self.native_calls = []
        self.cancelled = False

    def update_model(self, model, context_length, base_url="", api_key="", provider="",
                     api_mode="", max_tokens=None):
        self.model = model
        self.context_length = context_length
        if max_tokens is not None:
            self.max_tokens = max_tokens

    def bind_session_state(self, session_db=None, session_id="", *, persistence=None):
        self._session_id = session_id
        self._persistence = persistence

    def compress(self, messages, current_tokens=None, focus_topic=None, force=False,
                 memory_context="", bypass_cooldown=False):
        self.native_calls.append("compress")
        return messages

    def on_session_reset(self):
        self.native_calls.append("reset")

    def on_session_end(self, session_id, messages):
        self.native_calls.append("end")

    def get_tool_schemas(self):
        return [{"name": "native_tool"}]

    def handle_tool_call(self, name, args, **kwargs):
        return json.dumps({"native": name})

    def _call_summary_llm(self, messages, prompt_started_at):
        self.native_calls.append("native_summary")
        return "native summary"

    def _on_summary_failure(self, e, turns_to_summarize, focus_topic, memory_context):
        self.native_calls.append("native_failure")
        return "native fallback"

    def _fallback_summary_for_window(self, telemetry, turns_to_summarize, n_dropped, feasibility_skip):
        self.native_calls.append("static_fallback")
        return "static summary"

    def _fallback_streak_skip(self, telemetry):
        self.native_calls.append("streak_skip")
        return True

    def _feasibility_skip(self, telemetry, turns_to_summarize, compress_start, compress_end):
        self.native_calls.append("feasibility_skip")
        return True

    def _compression_cancelled(self):
        return self.cancelled

    def _record_compression_failure_cooldown(self, seconds, error):
        self.native_calls.append(("cooldown", seconds))

    def get_status(self):
        return {"native": True}


class FakeContextEngine:
    def on_session_reset(self):
        self.compression_count = 0

    def get_status(self):
        return {}


def load_file(name, path, package=False):
    spec = importlib.util.spec_from_file_location(
        name, path, submodule_search_locations=[str(path.parent)] if package else None)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def hybrid(monkeypatch, tmp_path):
    modules = {
        "agent": {},
        "agent.context_engine": {"ContextEngine": FakeContextEngine},
        "agent.context_compressor": {"ContextCompressor": FakeNative},
        "agent.auxiliary_client": {"AuxiliaryExplicitCancellation": Cancellation},
        "agent.conversation_compression": {"_raise_if_stale_attempt": lambda _: None},
    }
    for name, attrs in modules.items():
        module = ModuleType(name)
        module.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, module)
    installer = load_file("_hybrid_installer_test", ROOT / "scripts" / "install_hermes_context.py")
    dest = installer.install(tmp_path, "nscp_hybrid")
    plugin = load_file("_hybrid_test_plugin", dest / "__init__.py", package=True)
    try:
        yield plugin, installer, dest
    finally:
        for name in list(sys.modules):
            if name.startswith("_hybrid_test_plugin") or name == "_hybrid_installer_test":
                sys.modules.pop(name, None)


def build(plugin, *, route="local", mode="observe", config=None):
    return plugin.NSCPHybridContextEngine(config=config or {}, output_reserve=2048,
                                         route=route, selection_mode=mode)


def test_native_engine_identity_and_delegation(hybrid):
    plugin, _, _ = hybrid
    engine = build(plugin, route="native")
    assert isinstance(engine, FakeNative)
    assert type(engine).compress is FakeNative.compress
    assert engine.abort_on_summary_failure is True
    rows = transcript()
    assert engine.compress(rows, force=True) is rows
    assert engine._call_summary_llm(rows, 0) == "native summary"
    assert engine._on_summary_failure(ValueError(), [], None, "") == "native fallback"
    assert engine._fallback_summary_for_window({}, [], 2, True) == "static summary"
    assert engine._fallback_streak_skip({}) and engine._feasibility_skip({}, [], 0, 1)
    assert engine.get_tool_schemas() == [{"name": "native_tool"}]
    assert json.loads(engine.handle_tool_call("native_tool", {})) == {"native": "native_tool"}


def test_local_summary_success_and_failure_never_calls_native_router(hybrid, monkeypatch):
    plugin, _, _ = hybrid
    engine = build(plugin)
    messages = [{"role": "user", "content": "Summarize"}]
    monkeypatch.setattr(plugin, "complete_summary", lambda rows, cfg:
                        SimpleNamespace(content="local summary", model=cfg.model,
                                        prompt_eval_count=99, eval_count=7, input_wire_bytes=100))
    assert engine._call_summary_llm(messages, 0) == "local summary"
    assert engine.get_status()["nscp_summary_report"]["prompt_eval_count"] == 99
    assert engine._on_summary_failure(RuntimeError("secret"), [], None, "") is None
    assert engine.native_calls == [("cooldown", 60.0)]
    assert "secret" not in json.dumps(engine.get_status())
    assert not engine._fallback_streak_skip({})
    assert not engine._feasibility_skip({}, [], 0, 1)
    with pytest.raises(plugin.LocalSummaryError):
        engine._fallback_summary_for_window({}, [], 2, True)
    assert "static_fallback" not in engine.native_calls


def test_local_cancellation_does_not_publish_or_arm_cooldown(hybrid, monkeypatch):
    plugin, _, _ = hybrid
    engine = build(plugin)

    def cancel(rows, cfg):
        engine.cancelled = True
        return SimpleNamespace(content="late", model=cfg.model, prompt_eval_count=1,
                               eval_count=1, input_wire_bytes=1)

    monkeypatch.setattr(plugin, "complete_summary", cancel)
    with pytest.raises(Cancellation):
        engine._call_summary_llm([], 0)
    assert engine.get_status()["nscp_summary_report"] is None
    with pytest.raises(Cancellation):
        engine._on_summary_failure(Cancellation(), [], None, "")
    assert not engine.native_calls


def test_hybrid_observe_keeps_native_and_experimental_scopes_recall(hybrid):
    plugin, _, _ = hybrid
    rows = transcript()
    for i in range(15):
        rows.extend([{"role": "user", "content": f"question {i}"},
                     {"role": "assistant", "content": "answer"}])
    store = SimpleNamespace(messages=SimpleNamespace(read_conversation=lambda session: [
        SimpleNamespace(as_openai_message=lambda row=row: row) for row in rows
    ] if session == "s1" else []))
    cfg = {"compression": {"protect_last_n": 8, "threshold": 0.75}}
    engine = build(plugin, route="native", config=cfg)
    engine.update_model("main", 8192)
    engine.bind_session_state(None, "s1", persistence=store)
    assert engine.select_context(rows) is None
    assert engine.get_status()["nscp_request"]["nscp_last_plan"]["disposition"] == "observe_only"
    engine = build(plugin, route="native", mode="experimental", config=cfg)
    engine.get_tool_schemas()
    engine.update_model("main", 8192)
    engine.bind_session_state(None, "s1", persistence=store)
    assert engine.select_context(rows) is not None
    ref = engine.get_status()["nscp_request"]["nscp_last_plan"]["references"][0]
    assert json.loads(engine.handle_tool_call("nscp_recall", {"reference": ref}))["content"]
    clone = engine.clone_for_agent()
    assert clone._session_id == "" and not clone._nscp_selection._issued_refs
    engine.bind_session_state(None, "s2", persistence=store)
    assert "error" in json.loads(engine.handle_tool_call("nscp_recall", {"reference": ref}))


def test_config_rejections_and_installer_ownership(hybrid):
    plugin, installer, dest = hybrid
    with pytest.raises(ValueError):
        build(plugin, config={"compression": {"micro_compact": True}})
    with pytest.raises(ValueError):
        build(plugin, config={"compression": {"threshold": float("nan")}})
    with pytest.raises(ValueError):
        plugin.native_options({}, True)
    with pytest.raises(ValueError):
        build(plugin, route="auto")
    assert installer.install(dest.parent.parent, "nscp_hybrid") == dest
    assert (dest / "local_summary.py").is_file() and (dest / "request_engine.py").is_file()
    (dest / "plugin.yaml").write_text("changed", encoding="utf-8")
    with pytest.raises(FileExistsError):
        installer.install(dest.parent.parent, "nscp_hybrid")


def test_registration_requires_explicit_policy(hybrid, monkeypatch):
    plugin, _, _ = hybrid
    cli = ModuleType("hermes_cli")
    config = ModuleType("hermes_cli.config")
    config.load_config_readonly = lambda: {}
    monkeypatch.setitem(sys.modules, "hermes_cli", cli)
    monkeypatch.setitem(sys.modules, "hermes_cli.config", config)
    registered = []
    ctx = SimpleNamespace(register_context_engine=registered.append)
    monkeypatch.delenv("NSCP_HYBRID_POLICY", raising=False)
    monkeypatch.delenv("HERMES_PLUGIN_HOST_PROCESS", raising=False)
    with pytest.raises(RuntimeError, match="NSCP_HYBRID_POLICY"):
        plugin.register(ctx)
    assert registered == []
    monkeypatch.setenv("NSCP_HYBRID_POLICY", '{"route":"local","output_reserve":2048}')
    plugin.register(ctx)
    assert registered[0].name == "nscp_hybrid"
    monkeypatch.setenv("HERMES_PLUGIN_HOST_PROCESS", "1")
    with pytest.raises(RuntimeError, match="in-process"):
        plugin.register(ctx)



def test_hybrid_bm25_preview_and_observe_never_invokes_selector(hybrid, monkeypatch):
    plugin, _, dest = hybrid
    rows = transcript()
    rows[4]["content"] += " Unique answer token."
    for i in range(15):
        rows.extend([{"role": "user", "content": f"question {i}"},
                     {"role": "assistant", "content": "answer"}])
    rows.append({"role": "user", "content": "Unique answer?"})
    store = SimpleNamespace(messages=SimpleNamespace(read_conversation=lambda session: [
        SimpleNamespace(as_openai_message=lambda row=row: row) for row in rows]))
    cfg = {"compression": {"protect_last_n": 8, "threshold": 0.75}}
    engine = plugin.NSCPHybridContextEngine(config=cfg, output_reserve=2048, route="native",
                                             selection_mode="experimental", selection_route="bm25")
    engine.get_tool_schemas()
    engine.update_model("main", 8192)
    engine.bind_session_state(None, "s", persistence=store)
    result = engine.select_context(rows)
    assert result is not None
    assert "Unique answer token." in result[4]["content"]
    report = engine.get_status()["nscp_request"]["nscp_last_plan"]
    assert report["verification"]["status"] == "structurally_verified"
    assert (dest / "local_retrieval.py").is_file()
    from importlib import import_module
    retrieval = import_module(plugin.__name__ + ".local_retrieval")
    def forbidden(*args):
        pytest.fail("observe must not send history to a model")
    monkeypatch.setattr(retrieval, "_post", forbidden)
    observed = plugin.NSCPHybridContextEngine(config=cfg, output_reserve=2048, route="native",
        selection_mode="observe", selection_route="embedding",
        retrieval=retrieval.RetrievalConfig(18101))
    observed.update_model("main", 8192)
    observed.bind_session_state(None, "s", persistence=store)
    assert observed.select_context(rows) is None
    assert observed.get_status()["nscp_request"]["nscp_last_plan"]["disposition"] == "observe_only"
