# Operations view (Phase 5.8)

Goal: whoever runs an installation can see that it is healthy without reading
anyone's personal records: structured logs that leave out private content,
alerts when something breaks, and an operator page showing job backlog, stuck
jobs, failures and storage use.

## Scope
- Structured logs: one JSON line per record. Requests log method, route
  template (never the raw path or query string), status, duration and a request
  ID. Exceptions log their type and code location only, never their message.
  Uvicorn's own loggers use the same formatter.
- Errors: an unexpected request error returns a fixed 500 with the request ID.
  Every error-level log record from LifeGather becomes an operational event
  (fixed message plus allowlisted fields, counted by fingerprint) in a new
  system table `operational_events`, unreadable by the per-account database
  role.
- Alerts: optional `LIFEGATHER_ALERT_WEBHOOK_URL` (HTTPS) and email to the
  operator addresses when SMTP is configured. At most one alert per event
  fingerprint per hour. Stuck jobs (expired scan leases, long-queued scans,
  overdue schedules) raise an alert from a periodic check and after each tick.
- Operator page: `LIFEGATHER_OPERATOR_EMAILS` lists the accounts that may see
  an Operations page. `GET /api/operator/overview` (404 for anyone else) returns
  counts only: scans by state, stuck jobs, failures by scan type over 7 days,
  schedule backlog, recent operational events, accounts and stored files
  (installation total plus the largest accounts by pseudonymous ID). The storage
  quota limit is shown once per-user quotas land. Hosted deployments should also
  put Cloudflare Access in front of `/api/operator/`.

## Acceptance checks
- Logging tests: a query string, exception message and request body never
  appear in log output or stored events.
- Service tests: stuck/backlog/failure counts, event dedupe, one alert per hour,
  webhook payload carries no personal content, operator check by email.
- Route tests: non-operators get 404; operators get the overview; the account
  database role cannot read `operational_events`.
- Frontend test: Operations appears only for operators and renders the overview.
- Full backend suite on PostgreSQL, mypy/ruff, frontend tests/lint/build.
