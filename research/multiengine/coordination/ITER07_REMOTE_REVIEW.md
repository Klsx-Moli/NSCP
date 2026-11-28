# ITER07 remote review — T012

Source research commit: bba91b31aab76117c4936ec42c3c54b991174939
Evaluated feature commit: 7835e7c746bed1429b993d2f7a21ae380dfd37c3
Candidate feature commit: 5fbdd030ec5571039159534a413ff8b44fe3dc45

VERIFIED_BY_ME: retrieved dataset.json and results.json directly and independently reconstructed all metrics and all reranking orderings from candidate_ids and explicit raw result indices. 270 rows, 135 rerank rows, 44 nonempty unique rerank calls across case/route (not repeated k cutoffs), 43 reordered, 43 old positional-zip errors at top4, 0 metric discrepancies. All six routes returned results for both no-answer cases. Embedding top1 11/13, embedding+rerank 12/13; both recall@4 1.0. These are synthetic development cases, not a sealed holdout. No raw embedding vectors were stored, so actual cosine scores cannot be independently replayed from this artifact. Model execution remains VERIFIED_BY_EXECUTOR, not remotely re-executed.

STATICALLY_INSPECTED: earlier ITER05 harness paired scores by list position and did not retain original indices. Its 48 corresponding before/after rankings were unchanged. ITER07 demonstrates that the response ordering can differ from candidate ordering; do not reuse the old rerank comparison. Fixed 16-candidate rerank pools mean k is output cutoff, not varying rerank input size. No calibrated abstention.

STATICALLY_INSPECTED: smoke_new_engines.py uses sigmoid of class 1 for CTXPrune. Upstream riceharvest/ctxprune e49a1de270e0dc74090f5dfa0b4e79100c5421e7 src/ctxprune/compress.py uses softmax over both logits. Smoke kept_text was empty; neither the reported keep ratio nor inference alone demonstrates valid compression. New adapter is raw token scoring, not upstream pipeline parity. NLI 3/6 label agreement is not sufficient for a semantic or authority gate.

ITER07 server reports record exit_before_cleanup=null, termination_requested=true, exit_after_cleanup=1 for embedding and reranker; this is intentional cleanup evidence, not an unexpected inference failure. No direct VRAM measurement.

CI at 7835e7c: run 46108431311 success, 184 targeted, 656 full plus 10 subtests, coverage 74%, Ruff pass. New feature candidates must be checked separately.

Decision: T012 accepted only for attribution and arithmetic. Old T004 ranking comparison superseded. T002/T003 original prototypes not accepted. T013/T014 are bounded local execution; no model download or production activation needed.
