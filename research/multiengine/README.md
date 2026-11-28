NSCP research/multiengine — shared research branch
Base SHA: 97ea9e987656bf64234cfc56ee3a89196a3b579d
Created: 2026-11-28T02:21:14.001253+00:00

Purpose: transfer reproducible research evidence and prototypes from ITER01-ITER05
for independent audit by the remote agent. Nothing here is product code.

Quick start for reviewers:
1. Read coordination/STATUS.md, HANDOFF.md, TASKS.json, DECISIONS.md.
2. Check coordination/EVIDENCE_INDEX.json for per-file SHA256 and provenance.
3. Read coordination/SANITIZATION.md before running harnesses (paths are placeholders).
4. Start with prototypes/memory and prototypes/router results, then
   iterations/ITER05/evidence/MULTIENGINE_DIFFERENTIAL_HARD.json.

Structure:
  coordination/        shared state, tasks, handoff, decisions, evidence index
  iterations/ITERxx/   original sanitized results and logs per iteration
  prototypes/          isolated executable prototypes (no src/ imports)
  benchmarks/          datasets, harnesses, results README
  tests/               test inventory
  documentation/       proposals and bug registry

ITER06 is NOT_ACCESSIBLE locally; see iterations/ITER06/README.md and TASKS T005.
