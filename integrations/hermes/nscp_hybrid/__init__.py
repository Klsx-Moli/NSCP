"""Opt-in native Hermes compressor with NSCP request selection.

Tested against a simulated host contract, not a live Hermes installation.
Native policy parity and private summary-hook compatibility are acceptance gates.
"""
from __future__ import annotations

import inspect
import json
import math
import os
from copy import deepcopy

from agent.context_compressor import ContextCompressor

from .agent_context import available_request_budget
from .local_summary import LocalSummaryConfig, LocalSummaryError, complete_summary
from .request_engine import NSCPContextEngine

REVIEWED_HERMES_COMMIT = "ed1cbc8de49b233bb71f38e96ed013b52f43ee20"


def _integer(cfg, name, default, minimum=0):
    value = cfg.get(name, default)
    if type(value) is not int or value < minimum:
        raise ValueError(f"Invalid compression.{name}")
    return value


def _ratio(cfg, name, default):
    value = cfg.get(name, default)
    if type(value) not in (float, int) or not math.isfinite(value) or not 0 < value <= 1:
        raise ValueError(f"Invalid compression.{name}")
    return float(value)


def native_options(config, output_reserve):
    """Map explicit constructor settings; not a claim of complete host parity."""
    if not isinstance(config, dict) or type(output_reserve) is not int or output_reserve < 1:
        raise ValueError("Explicit positive main-model output reservation required")
    cfg = config.get("compression", {})
    if not isinstance(cfg, dict):
        raise ValueError("Invalid compression config")
    cap = cfg.get("threshold_tokens")
    if cap is not None and (type(cap) is not int or cap <= 0):
        raise ValueError("Invalid compression.threshold_tokens")
    tail = cfg.get("tail_mode", "lean")
    if tail not in ("lean", "legacy"):
        raise ValueError("Invalid compression.tail_mode")
    overrides = cfg.get("model_thresholds", {})
    if not isinstance(overrides, dict) or not all(
            isinstance(k, str) and k and type(v) in (int, float)
            and math.isfinite(v) and 0 < v <= 1 for k, v in overrides.items()):
        raise ValueError("Invalid compression.model_thresholds")
    return {
        "threshold_percent": _ratio(cfg, "threshold", 0.50),
        "protect_first_n": _integer(cfg, "protect_first_n", 3),
        "protect_last_n": _integer(cfg, "protect_last_n", 20, 1),
        "summary_target_ratio": _ratio(cfg, "target_ratio", 0.20),
        "abort_on_summary_failure": True,
        "max_tokens": output_reserve,
        "model_thresholds": dict(overrides),
        "threshold_tokens_cap": cap,
        "proactive_prune_tokens": _integer(cfg, "proactive_prune_tokens", 0),
        "proactive_prune_min_result_chars": _integer(cfg, "proactive_prune_min_result_chars", 8000, 200),
        "proactive_prune_min_reclaim_tokens": _integer(cfg, "proactive_prune_min_reclaim_tokens", 4096),
        "min_tail_user_messages": _integer(cfg, "min_tail_user_messages", 1, 1),
        "tail_mode": tail,
    }


def check_host_contract():
    # Catch incompatible signatures early. Passing is not proof of semantics.
    requirements = {
        "__init__": {"model", "max_tokens", "threshold_tokens_cap", "abort_on_summary_failure",
                     "tail_mode", "model_thresholds", "min_tail_user_messages"},
        "update_model": {"model", "context_length", "max_tokens"},
        "compress": {"messages", "current_tokens", "force", "memory_context", "bypass_cooldown"},
        "bind_session_state": {"session_db", "session_id", "persistence"},
        "_call_summary_llm": {"messages", "prompt_started_at"},
        "_on_summary_failure": {"e", "turns_to_summarize", "focus_topic", "memory_context"},
        "_fallback_summary_for_window": {"telemetry", "turns_to_summarize", "n_dropped", "feasibility_skip"},
        "_fallback_streak_skip": {"telemetry"},
        "_feasibility_skip": {"telemetry", "turns_to_summarize", "compress_start", "compress_end"},
    }
    for name, required in requirements.items():
        method = getattr(ContextCompressor, name, None)
        if not callable(method) or not required.issubset(inspect.signature(method).parameters):
            raise RuntimeError(f"Unsupported native Hermes contract: {name}")


class NSCPHybridContextEngine(ContextCompressor):
    def __init__(self, *, config, output_reserve, route, local_config=None, selection_mode="observe",
                 selection_route="references", retrieval=None, max_model_calls=1, tool_reserve=0):
        if route not in ("native", "local"):
            raise ValueError("Explicit summary route must be native or local")
        check_host_contract()
        if not isinstance(config, dict):
            raise ValueError("Invalid Hermes config")
        compression = config.get("compression", {})
        options = native_options(config, output_reserve)
        if route == "local":
            # These optional host paths have not been qualified against the local-only
            # hook. Reject rather than silently changing the user's host configuration.
            if any(compression.get(key) not in (None, False, 0) for key in
                   ("micro_compact", "prepare_ahead", "codex_responses_native")):
                raise ValueError("Local hybrid route requires micro/prepare-ahead/server compaction off")
            if local_config is not None and not isinstance(local_config, LocalSummaryConfig):
                raise ValueError("Invalid local summary configuration")
        self._nscp_route = route
        self._nscp_local = local_config or LocalSummaryConfig()
        self._nscp_summary_report = None
        self._nscp_init_config = {"compression": deepcopy(compression)}
        if type(tool_reserve) is not int or tool_reserve < 0:
            raise ValueError("Invalid explicit tool/framing reserve")
        self._nscp_output_reserve = output_reserve
        self._nscp_tool_reserve = tool_reserve
        self._nscp_selection = NSCPContextEngine(mode=selection_mode, selection_route=selection_route,
                                                retrieval=retrieval, max_model_calls=max_model_calls)
        # Host initializes the actual model/endpoint via update_model immediately
        # after selecting the plugin. Native construction defers metadata lookup.
        super().__init__(model="", **options)

    @property
    def name(self):
        return "nscp_hybrid"

    def clone_for_agent(self):
        return type(self)(config=self._nscp_init_config,
                          output_reserve=self._nscp_output_reserve,
                          route=self._nscp_route, local_config=self._nscp_local,
                          selection_mode=self._nscp_selection.mode,
                          selection_route=self._nscp_selection.selection_route,
                          retrieval=self._nscp_selection.retrieval,
                          max_model_calls=self._nscp_selection.max_model_calls,
                          tool_reserve=self._nscp_tool_reserve)

    def update_model(self, model, context_length, base_url="", api_key="", provider="",
                     api_mode="", max_tokens=None):
        if self._nscp_route == "local" and api_mode == "codex_app_server":
            raise RuntimeError("Local hybrid does not support server-owned Codex thread compaction")
        super().update_model(model, context_length, base_url=base_url, api_key=api_key,
                             provider=provider, api_mode=api_mode, max_tokens=max_tokens)
        self._nscp_selection.context_length = self.context_length
        self._nscp_selection.threshold_percent = self.threshold_percent
        self._nscp_selection.protect_first_n = self.protect_first_n
        self._nscp_selection.protect_last_n = self.protect_last_n
        self._nscp_summary_report = None

    def bind_session_state(self, session_db=None, session_id="", *, persistence=None):
        super().bind_session_state(session_db, session_id, persistence=persistence)
        self._nscp_selection.bind_session_state(None, self._session_id,
                                                getattr(self, "_persistence", None))
        self._nscp_summary_report = None

    def on_session_reset(self):
        super().on_session_reset()
        self._nscp_selection.on_session_reset()
        self._nscp_summary_report = None

    def on_session_end(self, session_id, messages):
        super().on_session_end(session_id, messages)
        self._nscp_selection.on_session_end(session_id, messages)
        self._nscp_summary_report = None

    def select_context(self, request_messages, *, conversation_messages=None,
                       incoming_message=None, budget_tokens=0):
        # The native compressor's own persisted compaction and usage tracking
        # are inherited, not replaced by NSCP's request-only optimization.
        length = budget_tokens or self.context_length
        reserve = self.max_tokens or 0
        try:
            input_budget = available_request_budget(length, output=reserve, tools=self._nscp_tool_reserve)
        except ValueError:
            return None
        # Use a reduced window for request planning; native threshold/output
        # accounting remains in ContextCompressor.
        return self._nscp_selection.select_context(
            request_messages, conversation_messages=conversation_messages,
            incoming_message=incoming_message, budget_tokens=input_budget)

    def get_tool_schemas(self):
        schemas = list(super().get_tool_schemas())
        if self._nscp_selection.mode == "experimental":
            schemas.extend(self._nscp_selection.get_tool_schemas())
        return schemas

    def handle_tool_call(self, name, args, **kwargs):
        if name == "nscp_recall" and self._nscp_selection.mode == "experimental":
            return self._nscp_selection.handle_tool_call(name, args, **kwargs)
        return super().handle_tool_call(name, args, **kwargs)

    def _call_summary_llm(self, messages, prompt_started_at):
        if self._nscp_route == "native":
            return super()._call_summary_llm(messages, prompt_started_at)
        self._nscp_summary_report = None
        from agent.auxiliary_client import AuxiliaryExplicitCancellation
        from agent.conversation_compression import _raise_if_stale_attempt

        _raise_if_stale_attempt(self)
        if self._compression_cancelled():
            raise AuxiliaryExplicitCancellation()
        result = complete_summary(messages, self._nscp_local)
        _raise_if_stale_attempt(self)
        if self._compression_cancelled():
            raise AuxiliaryExplicitCancellation()
        self._nscp_summary_report = {
            "route": "local", "model": result.model,
            "prompt_eval_count": result.prompt_eval_count, "eval_count": result.eval_count,
            "input_wire_bytes": result.input_wire_bytes, "outcome": "response_received",
        }
        return result.content

    def _on_summary_failure(self, e, turns_to_summarize, focus_topic, memory_context):
        if self._nscp_route == "native":
            return super()._on_summary_failure(e, turns_to_summarize, focus_topic, memory_context)
        # Do not use the native main-model retry ladder for the local-only hook.
        from agent.auxiliary_client import AuxiliaryExplicitCancellation
        from agent.conversation_compression import _raise_if_stale_attempt

        _raise_if_stale_attempt(self)
        if isinstance(e, AuxiliaryExplicitCancellation) or self._compression_cancelled():
            raise AuxiliaryExplicitCancellation() from None
        self._nscp_summary_report = {"route": "local", "outcome": "failed",
                                     "error_type": type(e).__name__}
        self._last_summary_error = "NSCP local summary failed; no alternate provider requested"
        self._record_compression_failure_cooldown(60.0, self._last_summary_error)
        return None  # native abort_on_summary_failure=True preserves the window

    def _fallback_streak_skip(self, telemetry):
        if self._nscp_route == "local":
            return False
        return super()._fallback_streak_skip(telemetry)

    def _feasibility_skip(self, telemetry, turns_to_summarize, compress_start, compress_end):
        if self._nscp_route == "local":
            return False
        return super()._feasibility_skip(telemetry, turns_to_summarize, compress_start, compress_end)

    def _fallback_summary_for_window(self, telemetry, turns_to_summarize, n_dropped, feasibility_skip):
        if self._nscp_route == "local":
            # Defense against native deterministic-skip paths that bypass the
            # abort-on-summary-failure flag. The reviewed host calls this BEFORE
            # _commit_window. Never return a fabricated successful summary.
            raise LocalSummaryError("Static fallback prohibited by local summary policy")
        return super()._fallback_summary_for_window(
            telemetry, turns_to_summarize, n_dropped, feasibility_skip)

    def get_status(self):
        status = super().get_status()
        status.update(nscp_hybrid=True, nscp_summary_route=self._nscp_route,
                      nscp_summary_report=deepcopy(self._nscp_summary_report),
                      nscp_request=self._nscp_selection.get_status(),
                      nscp_tool_reserve=self._nscp_tool_reserve,
                      nscp_host_reference=REVIEWED_HERMES_COMMIT,
                      nscp_host_runtime_verified=False)
        return status


def register(ctx):
    # No implicit cost policy; registration requires explicit operator choice.
    if os.environ.get("HERMES_PLUGIN_HOST_PROCESS") == "1":
        raise RuntimeError("NSCP hybrid requires in-process native compressor identity")
    from hermes_cli.config import load_config_readonly

    raw = os.environ.get("NSCP_HYBRID_POLICY")
    if not raw:
        raise RuntimeError("NSCP_HYBRID_POLICY must explicitly select native or local summary")
    policy = json.loads(raw)
    allowed = {"route", "output_reserve", "local", "selection_mode", "selection_route",
               "retrieval", "max_model_calls", "tool_reserve"}
    if not isinstance(policy, dict) or set(policy) - allowed:
        raise ValueError("Invalid NSCP hybrid policy")
    local = policy.get("local", {})
    if not isinstance(local, dict):
        raise ValueError("Invalid local summary policy")
    retrieval = policy.get("retrieval")
    if retrieval is not None:
        if not isinstance(retrieval, dict):
            raise ValueError("Invalid retrieval policy")
        from .local_retrieval import RetrievalConfig
        retrieval = RetrievalConfig(**retrieval)
    ctx.register_context_engine(NSCPHybridContextEngine(
        config=load_config_readonly(), output_reserve=policy.get("output_reserve"),
        route=policy.get("route"), local_config=LocalSummaryConfig(**local),
        selection_mode=policy.get("selection_mode", "observe"),
        selection_route=policy.get("selection_route", "references"), retrieval=retrieval,
        max_model_calls=policy.get("max_model_calls", 1), tool_reserve=policy.get("tool_reserve", 0)))
