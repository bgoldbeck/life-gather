# Account isolation (Phase 5.3)

Status: in progress. Every service already filters by the signed-in account.
This increment adds a second, database-enforced lock so one missed filter cannot
read or change another account's data, and a cross-account test suite.

## Scope

- **Row-level security.** A migration creates the `lifegather_account` database
  role, grants it table access and enables PostgreSQL row-level security on every
  table with a `user_id` column (and `users` by `id`). Policies only show rows
  whose owner equals the acting account.
- **Acting account per request.** Signing in to the web API or MCP binds the
  account; each database connection taken while bound switches to
  `lifegather_account` and records the account id. Startup, migrations, the
  scheduler, retention sweeps and operator recovery stay in the unrestricted
  system context.
- **Background jobs.** Each claimed scan job runs bound to its owner.
- **Files.** While an account is bound, file storage refuses keys outside
  `users/<account>/`.
- **Tests.** A cross-account suite signs in two accounts and tries every HTTP
  route and MCP tool that takes an identifier with the other account's ids; a
  guard test fails when a new route or owned table is not covered. A test removes
  a service filter on purpose and shows RLS still hides the other account's rows.

Per-user file-size and storage quotas (the third 5.3 item) are a separate
increment.

## Acceptance

- No cross-account reads or writes through HTTP routes or MCP tools, with RLS on.
- A deliberately removed service filter is caught by RLS.
- Every owned table has RLS and a policy; new owned tables fail a guard test
  until they do.
- The full backend suite passes with RLS active in every signed-in request.
