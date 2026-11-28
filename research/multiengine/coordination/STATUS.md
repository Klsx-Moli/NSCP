SHARED STATUS — research/multiengine
Updated: 2026-11-28T02:21:14.001253+00:00
Base: 97ea9e987656bf64234cfc56ee3a89196a3b579d (origin/feature/context-compactor, verified by fetch)
Repo visibility: PUBLIC — all published text sanitized of personal paths.

Local main: fab8557 (ahead 2, untouched). Original checkout untouched.
Worktree: <REPO_ROOT>-research-multiengine (sanitized in docs as <WORKTREE>).
Remote branch before this commit: absent. Created from verified base.

Transferred: ITER01-ITER05 evidence/harnesses/prototypes, sanitized.
ITER06: NOT_ACCESSIBLE — no ITER06 directory or files found in evidence root.

Verified: embeddings real, reranker real, compactor A/B real, differential
hard/discriminating, memory 12/12, router 17/17, mutation 8/8.
Pending: remote review, VRAM measurement, H/I/J routes, ITER06 evidence.

UPDATE 2026-11-28T02:26:17.686557+00:00: T006 TESTED. ITER06 iniciado con evidencia nueva (proxy de offload).
No se han publicado pesos, DBs, venvs ni sesiones. Sin merge ni push a main.

UPDATE 2026-11-28T05:28:56.834521+00:00: ITER07 executed on isolated validation worktree at 7835e7c746bed1429b993d2f7a21ae380dfd37c3.
Tests 41 passed/1 skipped; 4 managed resources present; corrected benchmark
complete with no errors; four new-engine smoke tests executed.
main and feature/context-compactor untouched. No new campaign started.

REMOTE REVIEW 2026-11-28T05:52:00Z: T012 ACCEPTED for replayed index attribution and metric arithmetic only. 270 rows, 135 rerank rows, 44 nonempty rerank calls; 43 change rank and 43 old zip assignments would change top4. No metric discrepancies. All routes return candidates on both no-answer queries. ITER05 rerank ranking comparison superseded. Feature candidate 5fbdd030ec5571039159534a413ff8b44fe3dc45; local ITER08 runner prepared. T013/T014 pending; no new downloads needed. Main unchanged.

UPDATE 2026-11-28T06:19:50.317157+00:00: ITER08 local validation complete at 5fbdd030ec5571039159534a413ff8b44fe3dc45. Tests 51 passed/1 skipped;
six-model catalog verified; prepared runner complete=true; NLI 15/21 with semantic_gate=not_validated.
No downloads, no new campaign, no product/main/feature changes.

REMOTE REVIEW 2026-11-28: ITER08 artifacts inspected; CI 5fbdd03 success 703 full +10 subtests, 231 targeted. Exact old semantic plan independently reconstructed 3808/313/1242; projecting exact duplicate removal gives 643 estimated tokens, not new inference. 5/6 selected spans had identical text. Both ONNX scorers and equal-score baseline 4/6; NLI 15/21, not qualified. T013/T014 accepted only for reported execution and saved-evidence scope. New feature candidate 98f96fa9ec7a6dba7a46d26aeb8481597e9e0976, eight commits, new CI pending at publication. T015-T018 bounded local tests prepared; T019 remote review. No production activation.

UPDATE 2026-11-28T07:56:21.486257+00:00: ITER09 at 98f96fa9ec7a6dba7a46d26aeb8481597e9e0976: T015 TESTED (253 passed, 1 skipped), T016 TESTED
(runner complete=true, 28/28 replay reuse), T017 BLOCKED by reproducible Hermes
isolated-install PermissionError; T018 not executed. No downloads, no product/main/feature changes.
