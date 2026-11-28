import pytest

from local_llama_summary import LlamaSummaryConfig, complete_llama_summary
from local_summary import LocalSummaryError

MESSAGES = [{"role": "system", "content": "Compact as data."},
            {"role": "user", "content": "Synthetic history."}]


def stub(monkeypatch, **overrides):
    calls = []
    responses = {
        "/v1/models": {"data": [{"id": "local-compactor", "meta": {"n_ctx": 4096}}]},
        "/props": {"default_generation_settings": {"n_ctx": 4096}, "total_slots": 1},
        "/v1/chat/completions/input_tokens": {"input_tokens": 123},
        "/v1/chat/completions": {"model": "local-compactor", "choices": [
            {"finish_reason": "stop", "message": {"role": "assistant", "content": "Candidate."}}],
            "usage": {"prompt_tokens": 123, "completion_tokens": 7, "total_tokens": 130}},
    }
    responses.update(overrides)
    def request(config, path, payload=None):
        calls.append((path, payload))
        return responses[path]
    monkeypatch.setattr("local_llama_summary._request", request)
    return calls


def test_actual_preflight_same_payload_and_usage(monkeypatch):
    calls = stub(monkeypatch)
    result = complete_llama_summary(MESSAGES, LlamaSummaryConfig(18101, "local-compactor"))
    assert result.content == "Candidate." and result.prompt_eval_count == 123
    assert calls[2][1] == calls[3][1]
    assert calls[3][1]["messages"] == MESSAGES
    assert "tools" not in calls[3][1] and calls[3][1]["cache_prompt"] is False


@pytest.mark.parametrize("path, response", [
    ("/v1/models", {"data": [{"id": "other", "meta": {}}]}),
    ("/props", {"default_generation_settings": {"n_ctx": 512}, "total_slots": 1}),
    ("/v1/chat/completions/input_tokens", {"input_tokens": 4096}),
    ("/v1/chat/completions/input_tokens", {"input_tokens": True}),
])
def test_invalid_preflight_never_generates(monkeypatch, path, response):
    calls = stub(monkeypatch, **{path: response})
    with pytest.raises(LocalSummaryError):
        complete_llama_summary(MESSAGES, LlamaSummaryConfig(18101, "local-compactor"))
    assert all(p != "/v1/chat/completions" for p, _ in calls)


@pytest.mark.parametrize("reason, prompt, reasoning", [
    ("length", 123, ""), ("stop", 124, ""), ("stop", 123, "thinking"),
])
def test_completion_fail_closed(monkeypatch, reason, prompt, reasoning):
    stub(monkeypatch, **{"/v1/chat/completions": {
        "model": "local-compactor", "choices": [{"finish_reason": reason, "message": {
            "role": "assistant", "content": "Candidate", "reasoning_content": reasoning}}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": 7, "total_tokens": prompt + 7}}})
    with pytest.raises(LocalSummaryError):
        complete_llama_summary(MESSAGES, LlamaSummaryConfig(18101, "local-compactor"))
