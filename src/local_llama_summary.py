"""Strict local llama.cpp summary proposals using the actual chat token meter.

Tested transport contract is llama.cpp b9947's documented endpoints.
A trusted single-model loopback server is required. No model download,
remote fallback, tools, or persistent history mutation.
"""
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass

from local_summary import LocalSummary, LocalSummaryError, _json, to_ollama_messages

MAX_RESPONSE = 8 * 1024 * 1024
_ALIAS = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")


@dataclass(frozen=True)
class LlamaSummaryConfig:
    port: int
    model_alias: str
    num_ctx: int = 4096
    num_predict: int = 512
    timeout: float = 180.0

    def __post_init__(self):
        if (type(self.port) is not int or not 1 <= self.port <= 65535
                or not isinstance(self.model_alias, str) or not _ALIAS.fullmatch(self.model_alias)
                or type(self.num_ctx) is not int or not 2048 <= self.num_ctx <= 32768
                or type(self.num_predict) is not int or not 1 <= self.num_predict < self.num_ctx - 128
                or type(self.timeout) not in (int, float) or not 0 < self.timeout <= 600):
            raise ValueError("Invalid local llama.cpp summary policy")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise LocalSummaryError("Local llama.cpp redirect rejected")


def _request(config, path, payload=None):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    data = None if payload is None else _json(payload).encode("utf-8")
    request = urllib.request.Request(f"http://127.0.0.1:{config.port}" + path, data=data,
                                     headers={"Content-Type": "application/json"})
    with opener.open(request, timeout=config.timeout) as response:
        raw = response.read(MAX_RESPONSE + 1)
    if len(raw) > MAX_RESPONSE:
        raise LocalSummaryError("Local llama.cpp response exceeds limit")
    result = json.loads(raw)
    if not isinstance(result, dict) or result.get("error"):
        raise LocalSummaryError("Invalid local llama.cpp response")
    return result


def _check_server(config):
    models = _request(config, "/v1/models")
    rows = models.get("data")
    if (not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict)
            or rows[0].get("id") != config.model_alias or not isinstance(rows[0].get("meta"), dict)
            or not rows[0]["meta"]):
        raise LocalSummaryError("Expected loaded single-model alias")
    props = _request(config, "/props")
    settings = props.get("default_generation_settings")
    if (not isinstance(settings, dict) or type(settings.get("n_ctx")) is not int
            or settings["n_ctx"] < config.num_ctx or props.get("total_slots") != 1):
        raise LocalSummaryError("Unqualified local context window or slot count")


def complete_llama_summary(messages, config):
    """Return a candidate completion only; local usage is not provider billing."""
    if not isinstance(config, LlamaSummaryConfig):
        raise ValueError("Expected llama.cpp summary policy")
    # Reuse strict historical role/tool pairing validation, but send the
    # original OpenAI-style messages (not Ollama's translated representation).
    to_ollama_messages(messages)
    wire_bytes = len(_json(messages).encode("utf-8"))
    if wire_bytes > 512 * 1024:
        raise LocalSummaryError("Local summary input exceeds wire limit")
    payload = {"model": config.model_alias, "messages": messages,
               "temperature": 0, "max_tokens": config.num_predict, "stream": False,
               "cache_prompt": False, "chat_template_kwargs": {"enable_thinking": False}}
    try:
        _check_server(config)
        counted = _request(config, "/v1/chat/completions/input_tokens", payload).get("input_tokens")
        if type(counted) is not int or not 0 < counted <= config.num_ctx - config.num_predict:
            raise LocalSummaryError("Local chat token budget unmet or unavailable")
        result = _request(config, "/v1/chat/completions", payload)
        if result.get("model") != config.model_alias:
            raise LocalSummaryError("Unexpected local response alias")
        choices = result.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise LocalSummaryError("Unexpected completion choices")
        choice = choices[0]
        message = choice.get("message")
        if (choice.get("finish_reason") != "stop" or not isinstance(message, dict)
                or message.get("role") != "assistant" or message.get("tool_calls")
                or message.get("reasoning_content") or message.get("reasoning")
                or not isinstance(message.get("content"), str) or not message["content"].strip()):
            raise LocalSummaryError("Incomplete, reasoning-only or non-text completion")
        usage = result.get("usage")
        if not isinstance(usage, dict):
            raise LocalSummaryError("Missing local token usage")
        prompt, generated = usage.get("prompt_tokens"), usage.get("completion_tokens")
        if (type(prompt) is not int or type(generated) is not int or prompt != counted
                or not 0 < generated <= config.num_predict or prompt + generated > config.num_ctx
                or type(usage.get("total_tokens")) is not int or usage["total_tokens"] != prompt + generated):
            raise LocalSummaryError("Local token usage inconsistent with preflight")
        return LocalSummary(message["content"].strip(), config.model_alias, prompt, generated, wire_bytes)
    except LocalSummaryError:
        raise
    except Exception as exc:
        raise LocalSummaryError("Local llama.cpp summary failed: " + type(exc).__name__) from None
