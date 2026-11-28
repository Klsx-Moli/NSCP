# ITER09 — minimal local execution

No additional downloads. Use a fresh detached feature worktree and existing
NSCP Python environment. First run targeted regressions (see CI) and
tests/test_context_workbench.py with Qt offscreen.

    $env:PYTHONPATH = "src"
    python tools/run_iter09_local.py --root ABSOLUTE_EXTRAS --server ABSOLUTE_LLAMA_SERVER --out NEW_EVIDENCE_DIR --ngl 99

This runs one synthetic semantic request and one atomic memory index/reopen/
recall/isolation experiment. It uses a single embedding server. The DB is
local and must not be published. Publish only sanitized checkpoint/logs.
It records actual local request counts and estimated context size; no
provider billing or semantic-equivalence claim.

Separately, using the Python interpreter and actual source root of the
installed Hermes, run (from the feature worktree):

    HERMES_PYTHON scripts/qualify_hermes_context.py --hermes-source ACTUAL_HERMES_SOURCE_ROOT --out NEW_HOST_REPORT.json

The qualification uses a temporary home, installs the plugin only there,
imports actual host code, checks signatures, invokes actual tool registration,
request selection and sequential dispatch with synthetic history/persistence.
It does not activate the live plugin, invoke a provider, or certify native
durable compaction. A socket guard is not a security sandbox. Inspect
the report for private paths before publishing. If the installed Hermes
version does not expose the inspected hooks, preserve the failure; do not
modify Hermes or force an upgrade.

Start/end synchronization: fetch origin, record actual feature/research/main
refs, preserve dirty worktrees, fast-forward research only if safe, publish
sanitized evidence only there, verify remote SHA. Never merge main, overwrite
local changes or activate production Hermes.
