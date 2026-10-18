# Personal AI connections

Version 0.9.0 supports OpenAI and Claude through the same private memory/chat runtime.
In Settings, save an AI credential with provider `openai` for OpenAI or `anthropic`
for Claude. This only stores an encrypted credential; it does not validate the key
or contact the provider. Enable external AI permission when desired. In Chat or
Photos, explicitly choose that connection and enter a model ID available to the
corresponding API account, supporting structured JSON and vision where needed.
Changing connections clears the model choice. No model is silently substituted.
Subscription access to a consumer chat product is not tested as API authorization.

Save memory, keyword search, browsing, uploads and human reviews work without AI.
An Ask request sends the question, at most four recent user-message excerpts and
up to eight matched evidence excerpts. Saved-note extraction sends only the chosen
current note; photo reading sends only its selected sanitized JPEG preview. Original
photos and credentials never appear in model tools. New successful live-call turn
results record the provider and model; reused proposals retain their original
sources and do not claim that a newly selected provider generated them. Historical
turns remain readable without new metadata. Memory is shared across providers, not
copied into provider-specific stores. All source and citation checks still apply.

Provider selection comes from the authenticated owner's immutable credential
metadata, rechecked before each outbound call. Only `openai` and `anthropic` AI
credentials are accepted. Unsupported/foreign/deleted credentials fail without
fallback. Fixed endpoints prevent user model names from choosing a destination.
Secrets remain in the encrypted private vault and are read internally per call;
no key-reading HTTP/MCP tool exists. This adds no connector activation or automatic
background ingestion.

Both providers share the existing 20-request-per-owner-per-UTC-day reservation,
four active chat slots, session checks, persistent turns, exact request replay,
explicit cancellation and no automatic retry. Each call has a 25-second network
timeout; the runtime bounds the whole turn to 65 seconds. Text payloads cap at
40,000 UTF-8 bytes, optional JPEG previews at 2 MiB, responses at 128 KiB and output
at 1,500 tokens. Redirects and environment proxies are disabled. Refusals, truncation,
non-text/tool output, malformed/oversized results and invalid usage/citations fail
with redacted errors. Failed calls can still incur provider charges. Successful
Claude usage includes any reported cached input counts; no prompt caching is
requested. These limits can reject complex requests or long photo transcriptions;
there is no automatic higher-budget retry.

Claude uses the fixed Messages endpoint with `anthropic-version: 2023-06-01`,
`output_config.format` JSON Schema and inline base64 JPEG content when requested.
Unsupported length/numeric/array bounds move into static schema descriptions;
Pydantic validates the original full schema locally before domain services see
results. Domain writes additionally enforce exact evidence and reviewed identity.
Schema property names/descriptions are static application data, never private
source text. The adapter uses the existing HTTP client, without a new SDK dependency
or a data migration.

Contracts checked 2026-10-18 against official documentation:
- [Claude Messages API](https://platform.claude.com/docs/en/api/messages/create)
- [Claude structured outputs and schema limitations](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [Claude image inputs](https://platform.claude.com/docs/en/build-with-claude/vision)
- [OpenAI Responses images](https://developers.openai.com/api/docs/guides/images-vision?api-mode=responses)

Verification uses mock HTTP transports and synthetic browser providers. No live API
key, personal memory/image, paid call or production redeployment was used. Account
access and model availability require a separate explicitly authorized live check.
Graphify was unavailable on the verification host; source/tests were inspected.

## Streaming replies (v0.14.0)

Ask AI uses a private POST/SSE transport. OpenAI Responses text deltas and Claude
Messages text deltas produce a transient draft; structural and citation checks
still gate the saved answer. Cancellation, failure or disconnect removes the draft.
No retries or provider-side conversation state are enabled. Note/photo extraction
continues to use complete structured results before review.

Protocol references: [OpenAI streaming](https://developers.openai.com/api/docs/guides/streaming-responses)
and [Claude streaming](https://platform.claude.com/docs/en/build-with-claude/streaming),
checked 2026-10-18. Synthetic streaming verification does not establish live account
or model access.
