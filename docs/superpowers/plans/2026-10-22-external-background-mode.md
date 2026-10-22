# External background mode (Phase 5.2)

Goal: scheduled scans can be run by a scheduler outside the app process (system
cron now, Cloudflare Cron Trigger in Phase 5.4), while the in-process loop stays
the self-hosted default. One code path: the tick reuses `ScheduleService.dispatch`
and the same lease-guarded `ScanWorker` claim/run steps.

Scope:
- `LIFEGATHER_BACKGROUND_MODE=inprocess|external` (default `inprocess`). `external`
  starts no in-process scan loop.
- `LIFEGATHER_JOB_TICK_TOKEN` (32+ characters). With external mode and a token,
  `POST /internal/jobs/tick` accepts `Authorization: Bearer <token>` (constant-time
  comparison) and otherwise answers 404. One tick at a time per instance (409 when
  busy). Responses carry counts only, never account or scan content.
- `python -m lifegather.jobs [--seconds N]` runs one tick from the command line for
  system cron (`docker compose exec backend ...`); no token needed.
- Time bound: a tick dispatches due schedules, then claims and runs queued scans
  until the budget (default 50 s, 1–300 s) ends. A scan still running at the
  deadline saves its checkpoint after the current step and is handed back to the
  queue without spending a recovery attempt; the next tick resumes it.

Out of scope: Cloudflare Worker/wrangler files (5.4), operator dashboards (5.8),
moving conversation retention out of the process.

Acceptance checks:
- Settings validation for mode and token; external mode starts no worker task.
- Tick endpoint: 404 when disabled, 401 on a missing/wrong token, 200 counts on a
  correct token, 409 when a tick is already running; no content in responses.
- A due schedule is dispatched and run by one tick; a long scan pauses at the
  deadline, keeps its checkpoint and attempts, and finishes on the next tick.
- CLI runs one tick and exits 0; fails cleanly on invalid settings.
- Backend pytest, ruff, mypy from `backend/`.
