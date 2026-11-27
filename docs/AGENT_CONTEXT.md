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

Use a separate disposable Hermes profile/session. The default plugin mode is
**observe**: it produces a plan without rewriting the request or issuing recall
references. Manually choose:

```yaml
context:
  engine: nscp_context
```

For a controlled experiment only, verify the `context_engine` toolset is enabled
and `nscp_recall` is registered without name collisions. The current hook does
not expose the final tool list, so this verification is an operator precondition.
Then set `NSCP_CONTEXT_MODE=experimental` in the environment used to start Hermes.
In PowerShell: `$env:NSCP_CONTEXT_MODE = 'experimental'`. An insufficient estimated
budget leaves the original request unchanged and reports `budget_unmet`. Recall is
limited to references actually emitted in this binding, and revalidates the
current transcript on every read. Observe mode does not invoke any local LLM.
The native compressor is not delegated to in either mode; do not use the plugin
for long-running critical sessions until native fallback is implemented.

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


## Reproducible structural benchmark

From the repository root, in PowerShell:

```powershell
$env:PYTHONPATH = "src"
python tools/benchmark_agent_context.py --out agent-context-benchmark.json
```

Nine deterministic synthetic cases compare unchanged input, oldest-first,
cache-prefix-first, largest-first with focus protection, and adaptive planning.
Each modified result is rehydrated from the original transcript and checked
byte-for-byte as Python text; message metadata and input immutability are
asserted. Timing covers planning only, not recovery or provider execution.
The report deliberately leaves actual provider tokens, cache hits, cost, and
semantic task success null. Real anonymized traces and provider A/B are
separate future acceptance gates.

A protected assistant call also protects its tool result. Results from
`nscp_recall` are not recursively elided. Focus guards inspect both tool-call
arguments and returned text, so a file read need not echo its own filename.


## Native-preserving hybrid candidate (experimental)

`nscp_hybrid` subclasses the installed Hermes `ContextCompressor`. Native
`compress`, usage tracking, archive/commit ownership, cooldowns and manual
compaction remain native; NSCP's request-only selection is an additional hook.
The reviewed upstream contract is Hermes commit
`ed1cbc8de49b233bb71f38e96ed013b52f43ee20`.
Signature checks do not establish runtime compatibility. The subclass
maps explicit native constructor settings; it does not reproduce every
host-initialization override (e.g. Codex threshold autoraise). Not a drop-in
production replacement. Plugin-process isolation is not supported.

Install without activation:

```powershell
python scripts/install_hermes_context.py --engine nscp_hybrid
```

The engine requires `NSCP_HYBRID_POLICY` JSON with a positive main-model
output reservation and an explicit route. For a disposable test profile
with an 8192-token output reservation (change it to match your main provider):

```powershell
$env:NSCP_HYBRID_POLICY = '{"route":"local","output_reserve":8192,"selection_mode":"observe","local":{"model":"qwen3.5:4b-q4_K_M","num_ctx":8192,"num_predict":2048,"timeout":120}}'
```

Only after preflight verification choose `context.engine: nscp_hybrid`.
Do not assume that setting the config proves the plugin loaded: Hermes can
fall back to its built-in compressor when plugin loading fails. Check the
actual engine identity and status. Keep native `context.engine: compressor`
for important sessions until real-host validation is complete.

- `route: native` delegates summary generation to Hermes. Its router can use
  paid or remote providers, including main-model fallback on capacity errors.
  It is not a zero-cost route.
- `route: local` calls the local Ollama API with typed messages and no
  alternate provider in the NSCP summary hook. It requires a trusted
  local daemon, positively identified GGUF metadata, non-truncated completion
  and reported usage. It rejects prompts larger than a conservative wire
  budget instead of silently dropping text. Native summary failure aborts;
  native deterministic fallback is prohibited in this hook. Other host
  activity is outside this guarantee. Local model availability and
  compatibility with the host's typed templates are not yet verified.
- `selection_mode: observe` is default; native compression remains available
  and NSCP reports hypothetical request plans. `experimental` enables
  request rewriting only with a valid recoverable plan and requires the
  `context_engine` toolset and non-conflicting `nscp_recall`.

Local mode refuses micro-compaction, prepare-ahead and provider-native
Responses compaction; server-owned Codex thread mode is unsupported.
A local model with 8192 context may be too small for the native summary
prompt. This is a visible blocker, not a signal to silently switch providers.
No model was downloaded, no live session activated, and no native configuration
modified by the installer.
