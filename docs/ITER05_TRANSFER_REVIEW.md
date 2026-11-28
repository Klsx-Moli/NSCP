# Research transfer review — ITER05

Source: research/multiengine at cce5af7a3aa22319d88ae98c7b8594aba274d89a.
Static inspection, not a replay of the Windows inference experiments.

- T002: memory prototype allows unscoped rows/search and unscoped rehydrate;
  its cosine is a dot product; uniqueness excludes embedding version and
  INSERT OR IGNORE masks identity conflicts. New experimental SemanticMemory
  separates immutable source identity from embedding-space identity and
  requires a bound session. Its session boundary is application-level, not
  OS authentication. A trusted local DB and caller are required; a digest
  does not protect against an adversary who can rewrite both content and digest.
- T003: router defaults missing health to true and can choose explicitly
  unhealthy embedding. Several invalid input cases are accepted. Not yet
  adopted in product.
- T004: hard differential zips candidate IDs with rerank result scores
  rather than mapping explicit result indices. If the runtime emits
  reordered results, attribution is invalid. Empty pools are skipped;
  some route denominators therefore differ. Metrics label top-1 hit as
  selection recall, and precision ignores the k cutoff. New strict parser
  and cutoff-aware metrics are available in semantic_ranking. Raw inference
  must be rerun using the corrected harness before claiming comparative
  superiority. The 4-query sample remains exploratory.

The new modules are independently testable without models. They are not yet
wired into Hermes, the current request planner, or an actual vector endpoint.
No previous experimental result has been silently relabeled as verified.
