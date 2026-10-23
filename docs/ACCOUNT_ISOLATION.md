# Account isolation (Phase 5.3)

Status: delivered in 0.81.0; per-user storage quotas followed in 0.89.0 (see
[storage quotas](STORAGE_QUOTAS.md)). Every service already filtered
by the signed-in account; this adds a second, database-enforced lock so one missed
filter cannot read or change another account's data.

## How it works

- **Row-level security.** Migration `0033_account_row_security` creates the
  database role `lifegather_account` (roles are server-wide, so it is created once
  and reused), grants it table access and makes the connecting user a member. It
  enables PostgreSQL row-level security on every table with a `user_id` column
  and on `users` (by `id`), with one `account_rows` policy each: rows are visible,
  writable and insertable only when the owner equals the
  `lifegather.account_id` setting.
- **Acting account.** `lifegather.database.ACTING_ACCOUNT` holds the account a
  request or job acts for. Signing in to a web route (`require_session`) or an MCP
  call binds it. Each database connection taken while it is set switches to
  `lifegather_account` and sets `lifegather.account_id`; connections taken with no
  account switch back to the unrestricted connecting user.
- **System context.** Startup tasks, migrations, schedule dispatch and job
  claiming, conversation retention sweeps, sign-in itself and operator recovery
  run with no acting account and see every row, as before. The connecting user
  owns the tables (or is the superuser), so policies do not apply to it.
- **Background jobs.** The scan worker claims a job in the system context, then
  runs it bound to the job's owner.
- **Files.** While an account is bound, file storage refuses any key outside
  `users/<account>/`.

## Requirements

The database user in `LIFEGATHER_DATABASE_URL` must be able to create the role
(superuser or `CREATEROLE`) the first time the migration runs, unless an
administrator created `lifegather_account` and granted it to that user beforehand
(see [PostgreSQL](POSTGRESQL.md)). The Docker Compose setup and the test suite use
a superuser. New tables created by later migrations
are granted to `lifegather_account` automatically, but a new table with a
`user_id` column must add its own `account_rows` policy; a test fails until it
does.

## Tests

`backend/tests/test_account_isolation.py`:

- every owned table has row-level security and the policy;
- raw SQL with no owner filter, acting for one account, sees and changes only
  that account's rows, and cannot move a row to another account;
- a deliberately removed owner filter in a service is caught by row-level
  security through the HTTP API;
- file storage refuses another account's keys; scan jobs act for their owner;
- a second account calls every HTTP route (about 115, except sign-in and health)
  and every MCP tool with the first account's identifiers in path, query and
  body fields. No response contains the first account's records or ids, and a
  digest of all its rows is unchanged. About 87% of routes and 89% of tools get
  past input validation with generated bodies; the rest are refused earlier;
- a guard test fails when a route or tool gains an identifier the suite does not
  know how to fill.

## Not included

Per-user storage quotas were added separately in 0.89.0 (see
[storage quotas](STORAGE_QUOTAS.md)). Sign-in bookkeeping tables (`login_flows`, `auth_attempts`)
and the encrypted `vault_key` have no owner column and no policy.
