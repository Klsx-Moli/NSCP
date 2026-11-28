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


ITER08 extends the catalog to CTXPrune and multilingual MiniLM NLI.
Import each complete bundle explicitly from the existing ITER07 directory
(no new downloads):

    python -m nscp_resources --root ABSOLUTE_EXTRAS import-local --model-id ctxprune-small-int8 --from-dir ABSOLUTE_CTXPRUNE_DIR
    python -m nscp_resources --root ABSOLUTE_EXTRAS import-local --model-id multilingual-minilm-nli-onnx --from-dir ABSOLUTE_NLI_DIR

Add --apply only after checking the plan. All files for one model must
come from one source directory. Weight files may be in native onnx/ or
flat in the source folder; managed destinations use onnx/. These are
byte-preserving copies, not hard links to the original source.


## Resource-aware routing preview

`nscp-resources plan-route --policy policy.json` accepts a bounded JSON
object and calls the existing route planner with resource admission. It does
not require an extras directory. Example synthetic values (bytes, not measured
hardware or estimates for actual models):

```json
{
  "capacity": {"ram_bytes": 1000, "vram_bytes": null},
  "reserve": {"ram_bytes": 100, "vram_bytes": 0},
  "costs": {"embedding": {"ram_bytes": 500, "vram_bytes": 0}},
  "context_tokens": 12000,
  "request_budget": 8000,
  "need": "semantic",
  "health": {"embedding": "ready"},
  "allow_rerank": false
}
```

Capacity means currently available memory, not installed RAM/VRAM. Cost
means a conservative additional peak estimate including runtime and context
overheads, not weight size. Null capacity is unknown; a missing cost excludes
the engine. Zero must be explicitly justified by the caller. Simultaneous
embedding/reranking is admitted using the sum of incremental bounds; if the
combined estimate cannot fit, optional reranking is omitted without claiming
semantic quality. Exit 2 means recovery/abort or invalid input, not success.
A candidate route is not a successful compression. Health and resource values
are caller-supplied, not measurements or attestations; there is no atomic
reservation, live hardware sampler, cross-process lock, model launch or
automatic Hermes integration in this preview. Revalidate at execution time.


## Live RAM observation (read-only)

`nscp-resources snapshot` observes available physical RAM via Windows
GlobalMemoryStatusEx or Linux MemAvailable capped by all visible cgroup v2
memory.max/current ancestors. Unsupported or unreadable layouts report unknown.
Windows job limits, hidden cgroup ancestors and concurrent allocation races
are not covered. This is a point-in-time observation, not an allocation guarantee.
Pagefile/swap and disk space are not counted as physical RAM. Free VRAM remains
unknown; installed GPU memory is not a substitute.

`nscp-resources plan-route --policy policy.json --live-ram` caps the caller's
RAM value with the live observation (never increases an explicit cap).
An unreadable observation becomes unknown, not the stale caller value.
VRAM remains caller-supplied and is labeled as such. This is still a preview,
not automatic runtime admission or Hermes integration. No processes are started.
