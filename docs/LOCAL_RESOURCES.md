# Local resource management (experimental)

Use one absolute extras directory shared across worktrees. The resource CLI
does not start models, modify Ollama stores, download files, or alter PATH.

PowerShell, from a checkout with src available:

    $env:PYTHONPATH = "src"
    $root = "$HOME\Documents\NSCP\extras"
    python -m nscp_resources --root $root list
    python -m nscp_resources --root $root import-local --from-dir "$HOME\Downloads"

Review the read-only plan before adding --apply. Only exact known filenames
are considered, in supplied directories. Kompress requires a complete bundle
in a single directory (native onnx/ is supported). Import copies rather than
moves, checks hashes, refuses conflicts, reserves 25 GiB free, and atomically
publishes each file without replacing any destination. Re-run after partial
completion. File presence/hash recording does not certify upstream provenance,
runtime compatibility or inference. The plan contains private local paths:
do not publish it. Use list for shareable relative paths after review.

For storage on another volume, pass --root or set NSCP_EXTRAS_DIR in the
current process. NSCP_HOME/extras is another fallback. No worktree-local copy
is required. Existing external model stores are not modified.

This is the first deliberately narrow resource-management implementation,
not yet a downloader, runtime supervisor or full installation lockfile.
