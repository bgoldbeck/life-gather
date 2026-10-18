# Private MCP recall adapter

LifeGather now exposes ten read-only tools and one explicit text-capture tool over the official Python MCP SDK
v2 (`mcp==2.3.0` in the lockfile). This is the internal protocol foundation for
chat. The first [text chat increment](TEXT_CHAT.md) adds a separate chat transport
and optional OpenAI recall. The model does not receive the capture tool.

## Authentication and transport

`POST /mcp` uses stateless Streamable HTTP with JSON responses. The host application
starts and stops the SDK session manager in its own lifespan.

Every request needs an existing LifeGather session cookie, its `X-CSRF-Token`,
and the exact configured public URL as `Origin` and Host. Cross-site Fetch Metadata,
duplicate authority headers, bearer authorization, and MCP session IDs are rejected.
There is no public or anonymous mode. The server derives the user from the session,
then rechecks it immediately before each tool invocation. Arguments and client
metadata cannot select another user or supply a trusted execution context.

This endpoint is an app-session adapter. It is not an externally connectable OAuth
resource server for Claude, Codex, or other desktop clients. Do not distribute
session cookies as integration credentials. A separately scoped OAuth integration
is required before supporting external clients.

The official v2 client supplies the protocol metadata envelope and mirrored
`MCP-Protocol-Version`, `Mcp-Method`, and (for tool calls) `Mcp-Name` headers.
The tested protocol version is `2026-07-28`; a bare JSON-RPC request without the
required SDK protocol metadata is insufficient. See the
[SDK ASGI guide](https://py.sdk.modelcontextprotocol.io/run/asgi/).

## Tools

Each tool accepts one `data` object. Unknown fields, owner/context overrides,
coerced numbers, and out-of-range values are rejected before execution.

| Tool | Result |
| --- | --- |
| `memory_save_text` | Explicitly preserve original text with a retry-safe request ID; no extracted facts or inventory |
| `memory_search` | Literal-word source and entity/alias search |
| `memory_get_entity` | Entity and a page of sourced facts, with optional world-date/system-time filters |
| `memory_source` | Original source metadata and a character page of text |
| `memory_related` | Bounded one- or two-hop graph connections |
| `memory_timeline` | Preserved fact versions, including superseded history |
| `memory_list_entities` | Private entities, including historical records |
| `discovery_get` | Current discovery identity/review decision |
| `discovery_reviews` | Unresolved discovery reviews |
| `discovery_inventory` | Actively bound discovery asset IDs |
| `discovery_history` | Preserved decisions and corrections |

For example, the arguments to `memory_search` are
`{"data":{"query":"trimmer","limit":10}}`. Calls return structured JSON alongside
normal MCP content. Read operations are annotated read-only; `memory_save_text`
is explicitly annotated as a write. All are non-destructive, idempotent, and
closed-world. No SQL, filesystem, export, backup, credential, provider, or graph
mutation operations are exposed. Text capture requires an explicit user request;
source content never authorizes a save.

Fact responses retain source IDs, status, and temporal history. Original evidence
and quotations can be inspected through `memory_source`; long quotations are not
repeated in every fact. Source text is untrusted data, including text that looks
like instructions. Inferred ownership remains inferred. Entity lists can contain
historical records, and a current system version without a world-date filter
does not establish present ownership. See [memory semantics](MEMORY_CORE.md) and
[reconciliation semantics](RECONCILIATION.md).

## Limits and privacy

- One JSON-RPC object per request; no batches. Body limit: 16 KiB, with a ten-second
  body-read timeout. Compressed bodies are rejected.
- Source pages: up to 4,000 characters. Other list/history/fact/graph pages:
  default 25, maximum 50; graph depth: at most two.
- Structured tool payload: at most 32 KiB of UTF-8 JSON. Complete transport
  response: at most 96 KiB. Oversized results return a generic error, without
  leaking a prefix of the rejected data; retry with a smaller page.
- Eight concurrent MCP requests per process, plus 120 authenticated requests per
  user per minute. The bounded in-memory limiter tracks up to 1,024 users and
  resets on restart. These are read limits, not durable model cost accounting.
- Responses use `Cache-Control: no-store` and `Referrer-Policy: no-referrer`.
  Validation/internal errors do not return raw arguments, SQL, or private text.

The adapter delegates to existing owner-scoped services. It adds no domain schema
or migration and sends no records to an external provider. Authentication still
uses the existing session database; domain reads do not append graph audit events.

## Verification and remaining work

From `backend/`, run `uv run --locked pytest tests/test_mcp_http.py`.
Protocol tests exercise all ten tools, the official SDK client, two-user isolation
under concurrent requests, session revocation, direct in-process denial, injected
arguments, source paging, response caps, and rate/concurrency limits. Synthetic
fixtures require no Google, SMTP, or model service.

The first text chat increment adds persistent messages, explicit source capture,
consent checks, and bounded OpenAI usage. Structured graph writes, correction UI,
and external-client OAuth remain separate milestones. Source
changes do not update an existing Docker container or published image; rebuilding
and uploading still require the user's approval.
