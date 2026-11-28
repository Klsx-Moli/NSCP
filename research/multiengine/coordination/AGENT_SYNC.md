# Mandatory agent Git synchronization

Applies at start AND end of each local NSCP task, including a continuation after a tool interruption.

1. Locate the actual checkout and worktrees. Run git status --short and git worktree list --porcelain before changes.
2. git fetch origin; record refs for origin/main, origin/feature/context-compactor and origin/research/multiengine.
3. Read TASKS.json, STATUS.md, HANDOFF.md, CHECKPOINT.json from the fetched research ref.
4. Research worktree only: if clean and the local HEAD is an ancestor of the fetched research ref, fast-forward with git merge --ff-only origin/research/multiengine. If divergent or dirty, preserve changes and reconcile deliberately; do not reset or force.
5. Test feature in a fresh detached validation worktree at the exact required SHA. Do not merge it into main or research, and do not overwrite existing worktrees. Reuse a single shared extras root.
6. Work only on assigned tasks. Preserve original evidence, sanitize public artifacts, never stage weights, private sessions, DBs, credentials, local paths or arbitrary logs. No git add . indiscriminately.
7. Before publishing, re-fetch and check remote research HEAD; resolve conflicts without discarding either agent's changes. Review staged diff and git diff --check. Commit coherent research artifacts only.
8. Push explicitly to origin/research/multiengine without force. Verify git ls-remote origin refs/heads/research/multiengine equals the intended local commit. Record final SHA, feature tested SHA and worktree status.
9. If no new artifact or coordination change exists, do not create an empty commit. Still fetch and report final refs.

Do not upgrade or activate Hermes software as part of Git sync. Never modify active Hermes config, skills, main, or feature/context-compactor. Local host qualification uses an isolated temporary profile. A failed or interrupted command may already have effects; inspect before replay.
