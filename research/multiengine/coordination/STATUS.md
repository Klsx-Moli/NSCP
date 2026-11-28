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
