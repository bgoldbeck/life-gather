# Private MCP recall adapter: first chat-foundation slice

Continue the approved roadmap over the tested memory/reconciliation services. Main chat only; preserve unrelated document edits. No provider calls, personal-data transfers, external OAuth integration, paid service configuration, source push, or Docker operation.

## Scope and verified SDK contract

Official `mcp==2.3.0` is installed and locked with `mcp-types==2.3.0`. Use `MCPServer` from `mcp.server`, typed tool `Context` from `mcp.server.mcpserver`, and Streamable HTTP in stateless JSON-response mode. The host FastAPI lifespan explicitly enters the SDK session manager after constructing the transport. No new domain tables/migration are needed.

Expose read-only tools for memory search, entity/facts, original source pages, graph connections, timeline, entity lists, and discovery current state/reviews/inventory/history. All delegate to existing framework-independent services. No writes, SQL, filesystem access, provider credentials, exports or operator snapshots are tools. This is a useful protocol boundary before adding chat and scoped write execution; it is not a working chat interface.

The endpoint is a private same-origin app adapter, not an externally connectable OAuth resource server. Wrap `/mcp` with exact configured Host/Origin validation, valid app session, Fetch Metadata rejection for cross-site calls, and session CSRF on POST. Reject bearer headers and unrecognized session/client-state headers rather than treating them as authority. Authenticated POST is the only transport method exposed. The SDK also receives an explicit Host/Origin allowlist. No unauthenticated fallback or browser CORS wildcard.

Carry a server-created access context through the actual HTTP Request scope, not caller `_meta` or global user state. Reauthenticate before every tool invocation; a direct in-process SDK call without that context must fail closed. Verify concurrent users never share results. Use standard typed inputs, explicit bounds and extra-field rejection; root tool arguments contain only a `data` object and cannot inject actor/context/owner fields.

## Limits and safe results

Request bodies: 16 KiB, one JSON-RPC object (no batches). Tools return structured JSON and normal MCP content. Domain payloads cap at 32 KiB UTF-8; actual transport responses cap at 96 KiB with a sanitized error fallback. Source text pages default/max 4,000 characters; entity/history/graph/list pages default 25, max 50; graph depth 1–2. Fact results cite source IDs; quotes remain accessible through source pages rather than repeated without bounds in every fact.

At most eight MCP requests run concurrently per process and 120 authenticated requests per user per minute, in a bounded 1,024-user in-memory limiter. Limits reset on restart; durable provider usage/cost accounting is still required before chat. Send no-store/no-referrer headers. Return generic validation/protocol/internal errors without raw arguments, SQL or personal text. Domain not-found failures do not distinguish foreign IDs. Untrusted episode text is returned as data; tools cannot execute its instructions.

## Verification and completion

1. Write failing HTTP protocol tests for anonymous/revoked sessions, Host/Origin/CSRF, tool discovery, source paging, owner-scoped reads, guessed foreign IDs, extra arguments, invalid types/limits, batches/oversized requests, output caps, rate/concurrency bounds, and untrusted source text.
2. Build typed input/result adapter helpers, read-only SDK tools, guarded transport and host lifespan integration before static assets. Verify installed context propagation through real protocol requests, including concurrent users and direct in-process failure.
3. Run backend and existing UI tests, lint/format/types, package build/migration contents and Compose checks as relevant. Refresh the local code-only source graph and commit passing source changes and this plan locally. Stop before chat/provider or writable tools.
