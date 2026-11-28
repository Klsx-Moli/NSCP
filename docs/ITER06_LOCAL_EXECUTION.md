# ITER06 bounded local execution

This development benchmark is a ready-to-run replacement for rewriting
the earlier differential harness. The public synthetic corpus contains 15
distinct questions, including multiple evidence and no-answer cases.
Top-k values are not independent cases. Scores map explicit result indices.
Failed routes remain incomplete, not zero-cost successes. Reranking uses a
fixed maximum candidate pool of 16, and measures output cutoffs separately;
it does not test different input pool sizes.

From an isolated feature worktree, set PYTHONPATH=src and run:

    python tools/benchmark_specialized_engines.py --root ABSOLUTE_EXTRAS --server ABSOLUTE_LLAMA_SERVER --out NEW_EVIDENCE_DIRECTORY --ngl 99

Use --ngl 0 for a separately identified CPU run. Servers are sequential,
loopback-only, and only child processes launched by the script are stopped.
Raw rerank index/score responses and candidate order are preserved. Logs and
arguments may contain private paths: sanitize before publication. The script
does not touch Ollama, Hermes, main, or provider APIs. An exit status after
intentional termination is recorded separately from unexpected exit.

This is not a sealed holdout and does not test permissions or full agent
continuity. No-answer routes are reported without imposing an uncalibrated
similarity threshold. Model identity and actual backend should be checked
against the log; --ngl is a requested policy, not direct VRAM telemetry.
