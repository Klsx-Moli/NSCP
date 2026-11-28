# Semantic request excerpts (experimental)

The ITER07 model results motivate an optional embedding route, not a change
to the default reference planner. Start trusted llama.cpp embedding and
optionally rerank servers locally, using the validated model/runtime
configuration. NSCP does not start or stop them for this CLI.

    npsc-agent-context plan --input request.json --transcript original.json --budget 12000 --excerpts embedding --embedding-port 18101
    npsc-agent-context plan --input request.json --transcript original.json --budget 12000 --excerpts embedding-rerank --embedding-port 18101 --reranker-port 18102

The existing protection and exact-recall contracts apply. For eligible
archived results, all spans up to 64 are offered (rather than the lexical
sample used for generative IDs). Larger pools are explicitly skipped and
fall back to lexical selection; no claim of exhaustive semantic recovery
is made. The selector sends at most four items per request, validates
explicit indices and finite nonzero normalized vectors, and uses actual
HTTP request accounting with a default cap of 24 per plan. Optional
reranking uses only the top 16 and explicit server indices. Invalid
responses fail back to BM25, visibly. No external endpoint, proxy or
redirect is allowed. A trusted local daemon is a prerequisite; this
does not attest its model identity or prove it cannot perform egress.
Use the recorded server invocation and model hash.

No calibrated abstention policy or semantic equivalence claim. Rankings
are only candidate previews; original source remains available. Context
budget remains a UTF-8 heuristic. Not wired into Hermes or automatic
memory indexing yet.
