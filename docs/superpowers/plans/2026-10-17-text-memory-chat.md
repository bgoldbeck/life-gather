# Text memory chat: first usable increment

Implement persistent private conversations, explicit original-text memory capture,
keyword recall with evidence inspection, and optional OpenAI answers over that
evidence. Save/search must work without a model. OpenAI uses the user's selected
encrypted credential, existing external-AI consent, a fixed HTTPS endpoint,
bounded context/output, no automatic retries, and durable daily request limits.

Use owner-constrained SQLite tables and migration 0006. Keep chat transport in
HTTP and expose text capture through a typed MCP operation over the same service.
The model receives no write tools. It can suggest search terms, then answer using
bounded owned evidence. Validate source IDs before displaying citation buttons.
Persist messages, completion/failure states, and usage across restarts. Replayed
request IDs never run the provider twice. Interrupted work remains visible and
does not automatically resume or consume another request.

Acceptance: save text, reopen/reload a conversation, search from another conversation,
inspect original evidence, reject foreign IDs and missing CSRF, reject conflicting
replays, enforce consent/credential/daily limits, redact provider failures, and
verify migration upgrade/restore. Frontend tests cover save, recall, evidence,
loading, and error states. Run all existing checks.

This increment saves original text; structured extraction, graph fact correction,
discovery resolution, token streaming, and Light/Dark preference UI are subsequent
increments. Do not imply that a text note is a verified fact or a physical asset.
No live personal-data/model calls, Docker build/publication, or automatic connectors.
