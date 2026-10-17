# Evidence-backed memory core (feature #3)

This is a framework-independent, owner-scoped service layer with SQLite migration `0003_memory_core`. It stores source text, entities/aliases, literal facts and entity relationships, evidence links, temporal corrections, audit history, and FTS5 search. It does not yet add a working chat, graph UI, photo upload, model extraction, automatic reconciliation, or HTTP/MCP memory adapter. Existing UI placeholders remain appropriate.

## Service contract

Use `MemoryService(engine)` with a server-authenticated `Account`. Future HTTP/MCP adapters must get the account from authentication, never a caller-provided user ID. Source and fact inputs are validated Pydantic models; services own SQL and transaction boundaries.

| Method | Behavior |
| --- | --- |
| `ingest(actor, SourceInput(...))` | Preserve/reuse an original episode; return its ID and provenance |
| `create_entity(actor, EntityInput(...))` | Create a sourced record using an explicit idempotency operation key |
| `get_source` / `get_entity` | Read an owned source or entity; foreign IDs are not found |
| `add_alias` / `find_entities` | Source-backed aliases and exact normalized candidate lookup; no automatic merge |
| `assert_fact` | Add a literal or relationship with source evidence and status |
| `correct_fact` | Supersede one version, preserving its value/history and inherited evidence |
| `attach_evidence` | Link another owned source without inventing another entity/fact |
| `facts` / `timeline` | Filter system versions/world dates or read version history; page via the last returned fact ID |
| `search` | Bounded literal-word search over source text and entity names/aliases |
| `related` | Bounded one/two-hop graph traversal with evidence and a result-cap indicator |
| `export_page` | Owner-only pages for sources, entities, aliases, facts, evidence, or audit; excludes auth/vault tables |

## Provenance and retries

Sources retain original text, SHA-256, type, namespace, optional external ID, optional event date, and recorded time. Text is not silently trimmed or overwritten. Stable external IDs are scoped to user/type/namespace; replay returns the existing ID, while changed text/date under that ID is a conflict requiring a new source revision. Without an external ID, exact content/context/event-date replays are idempotent.

Entity/fact operation keys are unique within each owner's respective collection. Reusing a key with different content is a conflict. They are retry keys, not physical identity rules: two explicit unit keys can create two entities with identical names/models. Alias/name lookup returns candidates and never consolidates them.

Every entity and alias has an original source. Alias text must occur in that source. Each fact has at least one source; any supplied quote must be a verbatim substring. Evidence is preserved, but a quote's presence does not establish semantic truth. Later extraction/reconciliation must enforce its own evidence-quality and approval policies. Status values distinguish stated, verified, inferred, and unknown; extracting a receipt must not automatically make ownership verified.

Facts use exactly one related entity or literal, including explicit JSON null for unknown values. Literals support text, booleans, integers, and null; accounting amounts require the later typed purchase/financial model, not arbitrary graph arithmetic.

## Time and corrections

Valid-world bounds are day-precision dates with `[valid_from, valid_to)` semantics. Unknown dates stay null; vague years/months remain in original source text rather than becoming invented exact dates. `world_date` filters require a known start; missing start dates are excluded from definite historical answers.

System `recorded_at`/`superseded_at` and evidence arrival times are UTC Unix microseconds. `known_at` selects versions and evidence known at that system time. Corrections retire the prior system version and add a new one; inherited original evidence and the correction source both remain linked. If the clock has not advanced, correction time advances at least one microsecond past its predecessor to preserve ordering.

Without `world_date`, `facts` returns current system versions across all known world intervals, including intervals that have ended. It is not a shortcut for present ownership. Callers must supply the relevant date to answer definite current/historical questions and surface unknown-date claims separately. `timeline` includes superseded versions. Neither method interprets conflicting claims as a single certain answer.

## Bounds and isolation

Sources are capped at 20,000 characters; names/operation keys at 200; quotes/literal strings at 2,000. Search accepts up to 200 characters and 12 words, converts them to quoted AND tokens, and does not accept raw FTS expressions or rank using other users' document statistics. Public-facing adapters must additionally bound total serialized response size before introducing AI tools.

Lists/search/export/fact pages accept 1–100 records; alias/evidence lists cap at 100 per entity/fact. For fact/history pages, pass the last returned ID as `cursor` until a page is shorter than the limit. Graph depth is 1–2 and edge count is capped at 100; its cap indicator conservatively warns when the limit is reached. UUID export/entity cursors are for pagination, not chronological order. Paginated live queries are not a transactionally fixed export snapshot.

All reads/writes filter by owner, and composite foreign keys enforce matching owners for entity, source, fact, object, correction, alias, and evidence links. Writes are explicit serialized SQLite transactions; source/alias indexes and audit records commit with their records. A rejected operation rolls back rather than leaving a retired fact or orphan search entry. The shared FTS index returns only owner-filtered records with ownership checked again when loading results.

## Snapshot and restore

`operator_snapshot(engine, destination)` in `lifegather.memory.backup` uses SQLite's online backup API and integrity checking to create a new file with restrictive permissions. It refuses existing destinations and removes a partially created backup on failure. Choose a private destination outside served/static directories. Never expose this operator-only helper as a user/AI tool: it includes the entire database for all users, including session and encrypted-vault data.

To restore, stop the application, preserve the original database and journals, and restore into a controlled private location before starting with the appropriate configuration. Tests restore to a fresh database path and verify facts, ownership boundaries, FTS data, and foreign keys. There is no destructive automatic restore command. Back up the separate vault key securely if credential decryption is needed; it is not embedded in the snapshot. Future uploaded originals will need coordinated file backup when file storage is introduced.

## Verification

Synthetic fixtures cover ownership/maintenance/sale, historical and unknown dates, source/fact replays, concurrent source ingestion, duplicate-looking distinct objects, aliases, relationship cycles/bounds, invalid quotes and corrections, direct database owner constraints, cross-user service access/export/search, pagination, and snapshot restore. Existing login/settings tests run against the new migration head. No personal records or network model calls are needed.

References: [SQLite FTS5](https://www.sqlite.org/fts5.html), [Python SQLite backup API](https://docs.python.org/3.13/library/sqlite3.html#sqlite3.Connection.backup).
