# Hybrid Hermes request selection — opt-in experimental

The hybrid engine preserves the native durable compressor; request-only
selection is independently verified. Defaults remain observe/references.
A selection policy can explicitly choose bm25, embedding or embedding_rerank.

    {"route":"native","output_reserve":2048,"selection_mode":"experimental","selection_route":"embedding","retrieval":{"embedding_port":18101,"max_requests":12},"max_model_calls":1}

Set this as NSCP_HYBRID_POLICY only in an isolated Hermes profile AFTER
qualifying the installed host and its actual recall tool dispatch. Native
summary route retains the native provider policy (can be remote/costly).
Observe never invokes additional models. Request selection requires the
host to request the recall schema before archiving, but that is only a
necessary condition: the inspected host can skip colliding names or disable
the context_engine toolset. The operator must confirm actual dispatch and
no collision in a separate session before using experimental mode.
Never use the request-only standalone engine as a substitute for the
native compressor in production. No activation or global config changes.
All optional modules are installed in the plugin's own package namespace.
