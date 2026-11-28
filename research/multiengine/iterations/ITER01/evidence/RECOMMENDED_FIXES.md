# RECOMMENDED FIXES — NSCP Compressor

## P1 — Editable install path resolution
**Contract broken:** `pip install -e .` from worktree must resolve to worktree src, not original checkout.
**Observed:** Editable `.pth` initially pointed to `<REPO_ROOT>\src`.
**Fix:** Ensure `pyproject.toml` path handling or use explicit `--editable` path; document CI requirement to `pip install -e <worktree>`.

## P2 — Hermes reviewed commit mismatch
**Contract broken:** Installed Hermes runtime (`b71fb0c`) is newer than reviewed upstream reference (`ed1cbc8`).
**Impact:** `nscp_hybrid` may encounter contract drift; `get_status().nscp_host_runtime_verified` remains false.
**Fix:** Update `REVIEWED_HERMES_COMMIT` in `integrations/hermes/nscp_hybrid/__init__.py` to match actual runtime, or gate activation on explicit runtime verification.

## P3 — Qwen3 thinking mode causing empty content
**Contract broken:** `complete_summary` expects `message.content` non-empty, but Qwen3.5:4b-q4_K_M with default settings may return thinking-first with empty `content` when `num_predict` is low.
**Impact:** Local summary path may raise `No usable assistant summary`.
**Fix:** Either disable thinking (`think: false`) in `local_summary.py` for Qwen3, or increase `num_predict` minimum, or handle thinking content extraction.

## P4 — Ollama benchmark context sizing
**Contract broken:** `num_predict` + reserve exceeds `num_ctx` when context grows.
**Impact:** Requests may fail or truncate.
**Fix:** Enforce `num_predict + 1024 <= num_ctx` (already in `LocalSummaryConfig.__post_init__`) and surface clear error; add benchmark cases at boundary.

## P5 — VRAM measurement gap
**Contract broken:** VRAM not measured during benchmarks.
**Impact:** Cannot confirm OOM safety at 16384+ contexts.
**Fix:** Use `nvidia-smi` / `rocm-smi` / Windows performance counters; or rely on driver-reported adapter RAM as proxy.

## P6 — Adversarial test execution backlog
**Contract broken:** 53 adversarial cases defined but not executed.
**Impact:** No empirical evidence of robustness against the enumerated failure families.
**Fix:** Prioritize S-01..S-41 (structural) and M-01..M-12 (semantic) in a follow-up campaign with synthetic fixtures and a live Qwen inference loop.

## P7 — npsc-gui help invocation
**Contract broken:** `npsc-gui --help` blocks on GUI event loop.
**Impact:** CI help smoke test may hang.
**Fix:** Add a `--help`-aware pre-check in `npsc_gui/main.py` that exits before creating QApplication, or document that `npsc-gui` must be tested via import only.

## P8 — Mutation testing coverage
**Contract broken:** 8 mutation classes planned but not executed.
**Impact:** No empirical proof that existing tests detect silent corruptions.
**Fix:** Create disposable secondary copy of worktree, apply each mutation, run targeted test subset, record detection matrix.
