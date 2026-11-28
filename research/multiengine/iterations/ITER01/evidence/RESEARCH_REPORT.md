# RESEARCH REPORT — NSCP Compressor

## Executive Summary
Campaign executed Phase 1-15 with the available hardware. No modifications to production checkout. All work isolated in detached worktree + evidence directory.

## Phase 1 — Inventory & Sync (COMPLETE)
- Local main: `fab8557` (2 commits ahead of origin/main `4d74f6b`).
- Remote feature/context-compactor: `b71fb0c6774f715d420889ce064c8e9d2728d5cf` (confirmed identical to known checkpoint).
- Isolated worktree created at `<VALIDATION_ROOT>/NSCP-validation-20261127-055413` (detached HEAD).
- Evidence directory created at `<EVIDENCE_DIR>\2026-11-27_b71fb0c`.

## Phase 2 — Environment Inventory (COMPLETE)
- OS: Windows 11 IoT Enterprise LTSC, build 26100.
- CPU: Intel Core i5-4570 @ 3.20GHz, 4 cores / 4 logical.
- RAM: 15.9 GB total, 2.41 GB free.
- SSD: 512 GB total, 490.68 GB free.
- GPU: Intel HD Graphics 4600 (1 GB), Radeon RX 570 Series (4 GB).
- Python 3.12.10, Git 2.55.0, OpenCode installed, Hermes installed at `<HERMES_ROOT>`.
- Ollama 0.32.15, local models: qwen3.5:4b-q4_K_M, qwen2.5:1.5b.

## Phase 3 — Regression (COMPLETE)
- `compileall`: PASS (src, scripts, tools, integrations, tests).
- `ruff`: PASS (E,F,W, ignore E501).
- `pytest tests`: **535 passed, 1 skipped, 0 failed, 10 subtests passed** (57.17s).
- All tests executed with `PYTHONPATH=src` and `QT_QPA_PLATFORM=offscreen`.

## Phase 4 — Packaging (PARTIALLY COMPLETE)
- Initial editable install incorrectly pointed to original checkout (`<REPO_ROOT>`). Fixed by reinstalling editable with explicit worktree path.
- Entry points verified: `npsc`, `npsc-compact`, `npsc-agent-context`, `npsc-gui`.
- `npsc-gui --help` triggers GUI event loop and was not completed; import of `npsc_gui.main` succeeds.

## Phase 5 — Hermes Compatibility (COMPLETED)
- Hermes installed at `<HERMES_ROOT>`; agent source at `hermes-agent`.
- Installed git HEAD: `b71fb0c6774f715d420889ce064c8e9d2728d5cf`.
- Reviewed upstream reference: `ed1cbc8de49b233bb71f38e96ed013b52f43ee20` (NOT resolvable locally).
- ContextEngine contract: ABC with `name`, `update_from_response`, `should_compress`, `compress` abstract; concrete defaults for lifecycle, select_context, preflight, etc.
- ContextCompressor contract: checked against NSCP `check_host_contract()` — signatures validated.
- Runtime live-session verification (full plugin load in Hermes): NOT_EXECUTED.

## Phase 6 — Sandbox (PLANNED, NOT_EXECUTED)
- No live Hermes session plugin load executed.

## Phase 7 — Ollama & Local Model (EXECUTED)
- Ollama version 0.32.15, local.
- Model qwen3.5:4b-q4_K_M available.
- Inference runs on GPU (100% GPU utilization, AMD Radeon RX 570).
- Context sizes tested: 4096, 8192, 16384.
- `num_predict` capped at 128 to keep runtime bounded; `done_reason=length` observed when cap hit.
- Token metrics: prompt_eval_count ~26, eval_count 128, total_duration ~31.4s, wall ~33.5s.
- Model uses "thinking" mode (Qwen3); response content may be empty until thinking completes.

## Phase 8 — Model Benchmark (EXECUTED, LIMITED)
- Metrics captured to `MODEL_BENCHMARK.json`.
- Context 4096: load ~18.6s, prompt_eval ~1.1s, eval ~3.1s, tokens/s ~10.4.
- Context 8192: load ~19.1s, prompt_eval ~0.9s, eval ~1.9s, tokens/s ~16.7.
- Context 16384: load ~18.6s, prompt_eval ~1.6s, eval ~4.6s, tokens/s ~7.0.
- GPU confirmed; VRAM not directly measured (AMD driver reports 4 GB adapter RAM).

## Phase 9 — Adversarial Cases (DEFINED, NOT_EXECUTED)
- 41 structural cases + 12 semantic cases defined in `ADVERSARIAL_CASES.json`.
- All marked NOT_EXECUTED due to lack of live model/session execution time.

## Phase 10 — Differential Benchmark (EXECUTED)
- `tools/benchmark_agent_context.py` run; output saved to `agent-context-benchmark.json` (21 KB).
- Schema `nscp/request-benchmark/v1`, synthetic data origin.
- Strategies compared: unchanged, oldest, cache_prefix, (others present in JSON).
- Token accounting: utf8_heuristic; provider_tokens null.

## Phase 11 — Research (PARTIAL)
- Key techniques identified: LLMLingua-2, extractive compression, semantic selection via Qwen, deduplication, episodic memory, semantic memory, BM25, embeddings, incremental caching, hierarchical compression, relevance-based compression, real-window adaptation, token estimator calibration, net-savings accounting, prefix reuse, cumulative loss detection, prompt-injection protection for archived results.
- Each requires dedicated benchmark and hardware profiling; not fully implemented in this campaign.

## Phase 12 — Mutation Reasoning (PLANNED, NOT_EXECUTED)
- 8 mutation classes defined in `MUTATION_RESULTS.json`.
- Target contracts: context_compactor, compression_policy, context_loss_verifier, token_estimator, agent_context.
- Detecting tests identified but not executed.

## Phase 13 — Coordination (COMPLETE)
- No push, no merge, no PR opened.
- Worktree left detached at validated SHA; evidence preserved.

## Phase 14 — Evidence (MOSTLY COMPLETE)
- Files generated: CHECKPOINT.json, ENVIRONMENT.json, LOCAL_SYNC_REPORT.md, TEST_RESULTS.json, HERMES_COMPATIBILITY_MATRIX.json, MODEL_BENCHMARK.json, ADVERSARIAL_CASES.json, MUTATION_RESULTS.json, BUG_REGISTRY.md, RESEARCH_REPORT.md (this file), RECOMMENDED_FIXES.md (pending), FINAL_HANDOFF.md (pending).

## Phase 15 — Loop
- One full iteration completed. Remaining independent work: sandbox Hermes profile creation, live plugin load, adversarial execution, mutation testing, larger model benchmarks.
