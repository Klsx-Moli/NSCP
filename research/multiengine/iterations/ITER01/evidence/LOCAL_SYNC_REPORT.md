# LOCAL SYNC REPORT - NSCP Compressor

## Initial state (before campaign)

- Working checkout: `<REPO_ROOT>` (branch `main`, HEAD `fab8557`, ahead of `origin/main` by 2 commits)
- Remote: `https://github.com/Klsx-Moli/NSCP.git`
- Known checkpoints:
  - `b71fb0c6774f715d420889ce064c8e9d2728d5cf` (origin/feature/context-compactor - KNOWN)
  - `4d74f6bfb3488fe67b1e667b09b96b705b03b68d` (origin/main - KNOWN)

## Post-fetch state (during campaign)

- `git fetch origin` -> `feature/context-compactor` updated/new
- `git rev-parse origin/feature/context-compactor` -> `b71fb0c6774f715d420889ce064c8e9d2728d5cf` (confirmed identical to KNOWN checkpoint)
- `git rev-parse origin/main` -> `4d74f6bfb3488fe67b1e667b09b96b705b03b68d` (confirmed identical to KNOWN)

## Isolation

- Isolated worktree created (detached HEAD) at:
  `<VALIDATION_ROOT>/NSCP-validation-20261127-055413`
- Base SHA: `b71fb0c6774f715d420889ce064c8e9d2728d5cf`
- `git rev-parse HEAD` -> `b71fb0c6774f715d420889ce064c8e9d2728d5cf`
- No local modifications introduced inside the worktree.

## Rules respected

- No modifications to `main` checkout.
- No merge, no push, no force-push, no reset --hard, no git clean, no force-push.
- No modifications to user productive Hermes configuration.
- No payment model execution.
- No private conversation data sent to external models.
- No disabling tests or lowering thresholds.

## Evidence

- Evidence directory: `<EVIDENCE_DIR>`
- Per-run directory: `2026-11-27_b71fb0c`
- Logs: `2026-11-27_b71fb0c\logs\full-tests.txt`, `2026-11-27_b71fb0c\logs\ci-targeted-tests.txt`
- Test evidence: `TEST_RESULTS.json`
- Environment: `ENVIRONMENT.json`
