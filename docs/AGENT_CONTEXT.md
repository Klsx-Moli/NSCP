# NSCP Agent Context — experimental native integration

Status: implementation candidate, not production-ready. Tests use a simulated host;
a real Hermes installation, provider and tool dispatch have not been exercised.
No default configuration is changed. The existing legacy compactor is not used by
this adapter.

## Why two distinct paths

- `npsc-compact`: legacy text-history compactor, optional local Ollama Qwen
  summarizer, estimated content tokens and lexical diagnostics. It refuses
  agent tool messages and metadata it cannot preserve.
- `npsc-agent-context`: structured request-only planner. It keeps all messages,
  roles, order, assistant tool calls, IDs and other fields. It replaces only
  large text payloads from complete old tool-call batches by a content reference.
  The original must exist in the supplied canonical transcript.
- Hermes plugin `nscp_context`: uses the documented ContextEngine
  `select_context` hook and reads the bound session's replay repository;
  `nscp_recall` returns original data in bounded pages. No writes, no network,
  no cross-session lookups. It fails open to the unchanged request when the
  required storage contract is unavailable. It does **not** perform durable
  compaction or manual /compress, and cannot guarantee that a request fits.

Reference: https://hermes-agent.nousresearch.com/docs/developer-guide/context-engine-plugin

## Offline evaluation (no Hermes or model needed)

From the repository root:

```powershell
python src/npsc_agent_cli.py plan --input request.json --transcript history.json --budget 12000
python src/npsc_agent_cli.py recall --transcript history.json --reference <sha256> --offset 0 --limit 4000
```

Inputs are OpenAI-format JSON message arrays or objects with a messages array.
Exit 2 means the estimated budget could not be satisfied or the reference was
not found. The output is a request preview, not a replacement for history.
The default count is a UTF-8 heuristic, not actual provider token usage.

## Local Qwen comparison

```powershell
ollama pull qwen3.5:4b-q4_K_M
python src/npsc_compact_cli.py --input text-history.json --out result.json --num-ctx 8192 --summarizer ollama --model qwen3.5:4b-q4_K_M --summarizer-num-ctx 8192 --strict
```

The summarizer's local context/output budget differs from the target model's
budget. The generator is not yet connected to the native agent path; this
prevents a hallucinated summary from being promoted to agent instructions.

## Optional Hermes experiment

Before any installation, inspect Hermes's version and ensure its ContextEngine
has select_context, bind_session_state (persistence) and the engine-tool API.
The installer copies source only; it refuses to overwrite a different plugin.

```powershell
python scripts/install_hermes_context.py
```

Use a separate disposable Hermes profile/session, verify the plugin can load and
that nscp_recall is available to the agent. Only then manually choose:

```yaml
context:
  engine: nscp_context
```

Rollback by restoring `context.engine: compressor` and restarting Hermes. No
automatic activation, provider switching, config rewriting or model downloads.

## Remaining acceptance gates

- Real Hermes host compatibility, isolated plugin-process compatibility, tool
  visibility, provider message sanitization, and recovery across resume/restart.
- Exact target tokenizer/accounting including tool schemas, response reserve,
  actual billed input/cache tokens, and measured latency.
- Native compression when deterministic references alone cannot fit; do not
  enable automatic generative summaries until grounded fidelity is demonstrated.
- Tests against real anonymized agent traces, negations and conflicting
  decisions, concurrent subagents and plugin failure/timeout.


## Adaptive request planning (offline, no model)

`--strategy adaptive` selects a cache-prefix-oriented plan near the budget
and largest-eligible-result-first at high pressure. Explicit paths, hashes and
identifiers in the latest user message (or repeatable `--focus` arguments) protect
matching tool results from elision. Provider-specific sidecar content is left
alone. The default library strategy remains oldest-first for compatibility.

The report includes eligible results, protected matches, selected strategy,
estimated savings and the number of unchanged prefix messages. These are
structural and heuristic metrics, not proof of cache hits or semantic relevance.
If protected content prevents fitting, the planner reports that fact rather
than relaxing protections. No new provider or model calls are made.
