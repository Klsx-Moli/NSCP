# State resolution and NLI diagnostics

The ITER07 NLI smoke achieved 3/6 labels; it is not a permission verifier.
The experimental NLI adapter validates the actual label mapping, pair input
and finite logits; no implicit truncation. Its scores are uncalibrated.
Use tools/benchmark_nli.py with explicit local --model, --tokenizer,
--config, --out paths in the isolated ONNX environment. A result is a
diagnostic label, never authority.

context_state resolves only explicit structured grant/revoke events with
an external trusted host binding to the complete event digest. It is not
a natural language extractor. A raw source hash is not a trust anchor;
never accept a model's own digest set as authentication. Scope is exact;
there is no wildcard/inheritance. The caller must apply its own hard policy
veto and actual authorization checks. Candidate grants are not tool execution
permission. Tool/assistant/system data cannot create a user grant. Future
events are excluded, expired latest grants never resurrect prior grants,
conflicting authenticated identity/sequence fails closed, exact replay is
idempotent. This is an in-memory resolver, not a persistent event store
or a complete policy engine. It is not wired into Hermes.
