# Background scans from an outside scheduler

By default the app runs scheduled scans itself: a loop inside the backend checks
due schedules every second and runs queued scans. That stays the self-hosted
default and needs no setup.

Hosted platforms can put idle containers to sleep, which stops that loop. For
them, and for anyone who prefers system cron, set:

```
LIFEGATHER_BACKGROUND_MODE=external
```

The app then starts no scan loop. Scheduled scans, and scans started from the
Scans page or chat, run only when something outside calls a **tick**. Each tick
queues the schedules that are due, then runs queued scans until its time limit.
Conversation retention keeps its hourly in-app sweep in both modes.

## Tick from the command line (system cron)

```
docker compose exec -T backend python -m lifegather.jobs
```

Options: `--seconds N` (1–300, default 50). It prints content-free counts, for
example `Queued 1 scheduled scans, finished 1, paused 0 at the time limit.`, and
exits 1 with a short reason if settings or the database are not usable. A
crontab line that ticks every minute:

```
* * * * * cd /path/to/life-gather && docker compose exec -T backend python -m lifegather.jobs >/dev/null 2>&1
```

## Tick over HTTPS (Cloudflare Cron Trigger, other schedulers)

Set a long random token as well, for example `openssl rand -hex 32`:

```
LIFEGATHER_JOB_TICK_TOKEN=<64 hex characters>
```

The token must be at least 32 visible ASCII characters. Then:

```
curl -fsS -X POST -H "Authorization: Bearer $TOKEN" \
  "https://lifegather.example/internal/jobs/tick?seconds=50"
```

returns `{"status":"ok","dispatched":1,"ran":1,"paused":0,"stopped":"idle"}`.
`stopped` is `idle` when the queue emptied and `time_limit` when time ran out.

- Without external mode and a token, the endpoint answers 404.
- A missing or wrong token answers 401. The comparison is constant-time.
- `seconds` outside 1–300 answers 422, checked only after the token.
- A tick already running on that instance answers 409. Ticks on different
  instances are safe together: scans are claimed with database leases.
- Responses never contain account, mailbox or scan content.

Keep the token in your platform's secret store, never in source control. Rotate
it by changing the setting and the scheduler together; the app reads it at start.

## Time limit

The limit bounds when work starts and stops, not a single request to Gmail or an
AI provider. A scan still running at the limit stops after its current step,
keeps its saved checkpoint and goes back to the queue without using one of its
three recovery attempts; the next tick resumes it. So a tick can run past its
limit by one step. Give the scheduler's request timeout some headroom (for
example a 50-second tick with a 90-second timeout).

Schedules are only as punctual as the ticks: with ticks every five minutes, a
09:00 schedule queues by 09:05. After a gap only the latest missed occurrence is
queued, as with the in-process loop.
