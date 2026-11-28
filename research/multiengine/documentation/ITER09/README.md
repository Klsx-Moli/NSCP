ITER09 — LOCAL EXECUTION (T015/T016 executed, T017 failed, T018 not started)
Development SHA: 98f96fa9ec7a6dba7a46d26aeb8481597e9e0976
Executed: 2026-11-28T07:56:21.486257+00:00

T015 TESTED: 253 passed, 1 skipped (CI targeted list + tests/test_context_workbench.py, Qt offscreen).

T016 TESTED, complete=true:
- preview: expected_evidence_visible=true, tokens_before=3808,
  tokens_after=792, reference_only_tokens=313.
- memory: first inserted=28, reused=0,
  embedded_unique_texts=3; replay inserted=0,
  reused=28; HTTP requests 1 -> 0;
  exact_recall=True, session_isolation=True.

T017 BLOCKED (not an incompatible-version verdict):
- host_head=a9ff9799e273f525b82718cdc69fdec71b1dca5a, error_type=PermissionError.
- PermissionError on an isolated Hermes install lease; reproduced in two attempts.
- child also reported ModuleNotFoundError for install_hermes_context after Hermes relaunch via runpy.
- No Hermes upgrade, no plugin activation in the productive profile, no host/source edits.

T018 NOT_EXECUTED: conditional on T015/T016/T017 all finishing correctly; T017 failed.
No downloads. No new campaign. No DB, weight, session or private path published.
