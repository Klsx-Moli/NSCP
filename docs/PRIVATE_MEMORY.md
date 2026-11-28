# Private session memory (experimental)

nscp-memory provides explicit local index/search/recall over immutable source
events. It does not automatically ingest Hermes history. Supply an authorized
private JSON event with episode, message, role, content and tool_call (for
tool events). Session IDs partition a trusted local database, not an
authentication mechanism. Use an explicit embedding identity including model
revision and runtime; the operator is responsible for matching the daemon.

    nscp-memory --db PRIVATE_DB --session SESSION --embedding-id MODEL_ID index --source EVENT.json --embedding-port 18101
    nscp-memory --db PRIVATE_DB --session SESSION --embedding-id MODEL_ID search --query "question" --embedding-port 18101
    nscp-memory --db PRIVATE_DB --session SESSION --embedding-id MODEL_ID recall --episode E --message M

The source and all missing vectors are committed atomically per event.
Identical text is embedded once per batch but distinct offsets/events remain.
A repeated exact event skips inference after a restart. Conflicting identity,
dimension, or span payload fails. Concurrent conflicting re-embedding may
require a retry by the caller; no silent overwrite. Search is exhaustive
within a bounded session/space scan, not a vector index scalability claim.
Results are historical data, not instructions; no calibrated answerability.
Do not publish private databases, prompts or source events.
