"""Strict loopback-only Ollama completion for an already assembled summary prompt.

Unlike summarize_turns(), this preserves the host's typed message hierarchy and
never chunks, substitutes a summary, or invokes another provider. A trusted local
Ollama daemon and a compatible model template remain prerequisites.
"""
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

DEFAULT_MODEL = "qwen3.5:4b-q4_K_M"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*:[A-Za-z0-9][A-Za-z0-9_.-]*\Z")


class LocalSummaryError(RuntimeError):
    """No complete local response; no alternate model/provider was attempted."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise LocalSummaryError("Local endpoint redirect rejected")


def _base(host):
    url = urlsplit(host)
    if (url.scheme != "http" or url.hostname not in ("localhost", "127.0.0.1", "::1")
            or url.username is not None or url.password is not None
            or url.path not in ("", "/") or url.query or url.fragment):
        raise ValueError("Ollama endpoint must be HTTP loopback")
    port = url.port if url.port is not None else 11434
    if not 1 <= port <= 65535:
        raise ValueError("Invalid Ollama port")
    address = "[::1]" if url.hostname == "::1" else "127.0.0.1"
    return f"http://{address}:{port}"


@dataclass(frozen=True)
class LocalSummaryConfig:
    model: str = DEFAULT_MODEL
    host: str = "http://127.0.0.1:11434"
    num_ctx: int = 8192
    num_predict: int = 2048
    timeout: float = 120.0

    def __post_init__(self):
        _base(self.host)
        if (not isinstance(self.model, str) or not _MODEL.fullmatch(self.model)
                or "cloud" in self.model.casefold()):
            raise ValueError("Use an explicit local model tag, not a cloud model")
        if (type(self.num_ctx) is not int or type(self.num_predict) is not int
                or not 2048 <= self.num_ctx <= 262144
                or not 1 <= self.num_predict <= 32768
                or self.num_predict + 1024 >= self.num_ctx
                or type(self.timeout) not in (int, float) or not 0 < self.timeout <= 600):
            raise ValueError("Invalid local context/output/timeout policy")


@dataclass(frozen=True)
class LocalSummary:
    content: str
    model: str
    prompt_eval_count: int
    eval_count: int
    input_wire_bytes: int


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _args(raw):
    def pairs(items):
        obj = {}
        for key, value in items:
            if key in obj:
                raise ValueError("Duplicate tool argument key")
            obj[key] = value
        return obj

    if not isinstance(raw, str):
        raise ValueError("Tool arguments must be a JSON object string")
    result = json.loads(raw, object_pairs_hook=pairs)
    if not isinstance(result, dict):
        raise ValueError("Tool arguments must decode to an object")
    _json(result)
    return result


def to_ollama_messages(messages):
    """Translate OpenAI-style historical tool calls into Ollama's typed shape.

    Preserve message order, roles, call IDs, tool names, and argument values.
    Fail on unknown fields, unpaired results, or ambiguous calls rather than
    silently discarding provider-specific content. Never expose callable tools.
    """
    if not isinstance(messages, list) or not messages:
        raise ValueError("Expected nonempty message list")
    out, pending = [], {}
    for row in messages:
        if not isinstance(row, dict):
            raise ValueError("Invalid summary message")
        role = row.get("role")
        if role not in ("system", "user", "assistant", "tool"):
            raise ValueError("Unsupported summary role")
        allowed = {"role", "content"}
        if role == "assistant":
            allowed.add("tool_calls")
        if role == "tool":
            allowed.add("tool_call_id")
        if set(row) - allowed:
            raise ValueError("Unsupported summary metadata")
        if pending and role != "tool":
            raise ValueError("Incomplete historical tool batch")
        content = row.get("content")
        calls = row.get("tool_calls")
        if role == "assistant" and content is None and calls:
            content = ""
        if not isinstance(content, str):
            raise ValueError("Unsupported summary content")
        dst = {"role": role, "content": content}
        if calls is not None:
            if role != "assistant" or not isinstance(calls, list) or not calls:
                raise ValueError("Invalid historical tool calls")
            wire_calls = []
            for index, call in enumerate(calls):
                if not isinstance(call, dict) or set(call) != {"id", "type", "function"}:
                    raise ValueError("Unsupported historical tool call")
                cid, fn = call["id"], call["function"]
                if (call["type"] != "function" or not isinstance(cid, str) or not cid
                        or cid in pending or not isinstance(fn, dict)
                        or set(fn) != {"name", "arguments"}
                        or not isinstance(fn["name"], str) or not fn["name"]):
                    raise ValueError("Invalid historical tool call")
                wire_calls.append({"id": cid, "function": {
                    "index": index, "name": fn["name"], "arguments": _args(fn["arguments"])}})
                pending[cid] = fn["name"]
            dst["tool_calls"] = wire_calls
        elif role == "tool":
            cid = row.get("tool_call_id")
            if not isinstance(cid, str) or cid not in pending:
                raise ValueError("Orphan or duplicate historical tool result")
            dst.update(tool_call_id=cid, tool_name=pending.pop(cid))
        out.append(dst)
    if pending:
        raise ValueError("Incomplete historical tool batch")
    return out


def _post(base, path, payload, timeout):
    request = urllib.request.Request(
        base + path, data=_json(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    with opener.open(request, timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise LocalSummaryError("Ollama response exceeds size limit")
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get("error"):
        raise LocalSummaryError("Invalid Ollama response")
    return value


def _positive_local_model(show):
    # Cloud models advertise remote_host/remote_model. Require local model
    # metadata before any conversation is sent, not just a loopback URL.
    if show.get("remote_host") or show.get("remote_model"):
        raise LocalSummaryError("Ollama reports an upstream model")
    if not isinstance(show.get("model_info"), dict) or not show["model_info"]:
        raise LocalSummaryError("Local model metadata unavailable")
    details = show.get("details")
    if not isinstance(details, dict) or details.get("format") != "gguf":
        raise LocalSummaryError("Expected locally installed GGUF model")


def complete_summary(messages, config=None):
    """Return validated local completion or raise; never return partial output."""
    config = config if config is not None else LocalSummaryConfig()
    if not isinstance(config, LocalSummaryConfig):
        raise ValueError("Invalid local summary config")
    wire = to_ollama_messages(messages)
    # Conservative UTF-8 wire bound with additional template/framing reserve.
    # It is not a tokenizer and may reject valid larger prompts.
    wire_bytes = len(_json(wire).encode("utf-8"))
    if wire_bytes + 512 + 32 * len(wire) > config.num_ctx - config.num_predict:
        raise LocalSummaryError("Host summary prompt exceeds conservative local budget")
    base = _base(config.host)
    try:
        metadata = _post(base, "/api/show", {"model": config.model}, config.timeout)
        _positive_local_model(metadata)
        result = _post(base, "/api/chat", {
            "model": config.model, "messages": wire, "stream": False,
            "think": False, "truncate": False, "shift": False,
            "options": {"num_ctx": config.num_ctx, "num_predict": config.num_predict,
                        "temperature": 0}}, config.timeout)
    except LocalSummaryError:
        raise
    except Exception as exc:
        # Never include provider error text or history in the error.
        raise LocalSummaryError("Local Ollama request failed: " + type(exc).__name__) from None
    if result.get("remote_host") or result.get("remote_model"):
        raise LocalSummaryError("Ollama reports upstream execution")
    if not isinstance(result.get("model"), str) or result["model"].casefold() != config.model.casefold():
        raise LocalSummaryError("Unexpected response model")
    if result.get("done") is not True or result.get("done_reason") != "stop":
        raise LocalSummaryError("Incomplete or unrecognized completion")
    prompt, completion = result.get("prompt_eval_count"), result.get("eval_count")
    if (type(prompt) is not int or type(completion) is not int
            or not 0 < prompt <= config.num_ctx - config.num_predict
            or not 0 < completion <= config.num_predict):
        raise LocalSummaryError("Missing or out-of-budget usage")
    message = result.get("message")
    if (not isinstance(message, dict) or message.get("role") != "assistant"
            or message.get("tool_calls") or not isinstance(message.get("content"), str)
            or not message["content"].strip()):
        raise LocalSummaryError("No usable assistant summary")
    return LocalSummary(message["content"].strip(), result["model"], prompt, completion, wire_bytes)
