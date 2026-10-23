# Operations: logs, alerts and the Operations page

v0.91.0 adds what the person running an installation needs to see that it is
healthy, without reading anyone's records.

## Logs without private content

The backend writes one JSON object per line to standard error (Docker and
`docker logs`, TrueNAS app logs and Cloudflare container logs all show them):

```json
{"time":"2026-10-23T05:40:12.031+00:00","level":"info","logger":"lifegather.requests","message":"Request","method":"GET","route":"/api/assets/{asset_id}","status":200,"duration_ms":14,"request_id":"5f0c9a1e2b7d4c33"}
```

- Requests to `/api/`, `/auth/`, `/internal/` and `/mcp` are logged with the
  **route template**, never the actual path or query string, so search text,
  IDs and file names stay out. Health checks and static files are not logged.
- Exceptions are logged by type and code location only (`"error_type"`,
  `"location"`). Exception messages, which can quote personal data, are never
  written. Uvicorn's own log lines use the same format.
- Only a fixed list of fields can appear: method, route, status, duration,
  request ID, scan type, job, count and error type.
- An unexpected error returns `{"detail":"Something went wrong","request_id":...}`
  with status 500. Every response carries an `X-Request-ID` header, so a person
  reporting a problem can quote it and the operator can find the log line.

## Alerts

Every error-level log line becomes an **operational event**: its fixed message
plus the route, scan type or error type, counted. Events are kept for 30 days in
the `operational_events` table (migration `0038_operational_events`). It has no
owner column and the per-account database role cannot read it.

Each kind of problem alerts at most once an hour. Alerts go to:

| Setting | Effect |
| --- | --- |
| `LIFEGATHER_ALERT_WEBHOOK_URL` | HTTPS URL that receives a JSON POST: `text` (a one-line summary that Slack-style webhooks show directly), `message`, `details`, `count`, `first_at`, `last_at`, `installation`, `level`. |
| `LIFEGATHER_OPERATOR_EMAILS` with SMTP configured | An email to each operator address. |

With neither, events are still recorded and shown on the Operations page.

Stuck background work also raises an alert ("Background jobs are stuck"):

- a running scan whose lease expired more than 2 minutes ago and was not taken
  up again,
- a scan waiting in the queue for over 30 minutes,
- an enabled schedule more than an hour past its run time.

The check runs every 5 minutes inside the app and after every tick
(`POST /internal/jobs/tick` or `python -m lifegather.jobs`), so hosted
installations whose containers sleep between ticks are covered too.

## The Operations page

Set `LIFEGATHER_OPERATOR_EMAILS` to a comma-separated list of the sign-in
emails that operate the installation (case does not matter). Those accounts see
**Operations** at the bottom of the navigation. Everyone else does not, and
`GET /api/operator/overview` answers them 404.

The page shows, across every account, counts only:

- **Background jobs:** queued and running scans, finished/failed in the last 7
  days, schedules active and paused, built-in or outside scheduler, and what is
  stuck.
- **Failures by scan type** over 7 days. Failure messages are not shown.
- **Recent problems:** the operational events above, with count, last seen and
  when an alert last went out.
- **Storage:** stored photo and document bytes and counts (live files,
  including photo previews), number of accounts, and the five largest accounts
  by a short pseudonym (`account-1a2b3c4d`, a hash of the account ID), counted
  the same way as [storage quotas](FILE_STORAGE.md), and the per-account limit
  from `LIFEGATHER_STORAGE_QUOTA_MB` ("No limit" when unset).

No names, emails, file names, record text or messages appear.

For a hosted installation reachable from the internet, also put Cloudflare
Access (or another identity proxy) in front of `/api/operator/`. The Cloudflare
test site is already behind Access as a whole.

## Settings

| Variable | Default | Notes |
| --- | --- | --- |
| `LIFEGATHER_OPERATOR_EMAILS` | empty | Comma-separated. Deployment-local: not carried by recovery bundles. |
| `LIFEGATHER_ALERT_WEBHOOK_URL` | empty | Must be HTTPS. Deployment-local. |

## Limits

- Error records reach the event table within 30 seconds (or when the page is
  opened, or after a tick). Events from a process that crashes before that are
  only in its log output.
- Alert delivery failures are logged as warnings and not retried until the next
  occurrence after the hour.
- Only scans count as background jobs; other background work (conversation
  retention, file moves) reports through error events.
