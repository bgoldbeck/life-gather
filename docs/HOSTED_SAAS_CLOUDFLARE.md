# Hosted SaaS on Cloudflare, with self-hosting kept first-class

Research date: 2026-10-22. Design report only; nothing was deployed, purchased or
configured. Source baseline: `main` at v0.66.0 (`17facd8`), with the PostgreSQL
migration planned on `claude/postgresql-migration` but not merged. Cloudflare and
Google facts below come from their public documentation on the research date;
prices and limits change, so recheck them before committing money.

## Summary

LifeGather can run as a multi-tenant hosted service on Cloudflare without a
rewrite and without giving up the self-hosted Docker app. The recommended shape is:

- **The same Docker image** runs in both places. On Cloudflare it runs as a
  Cloudflare Container behind a thin Worker; on a Linux server it runs from Docker
  Compose exactly as today.
- **PostgreSQL** (the in-progress migration) holds all records. Hosted uses a
  managed Postgres with pgvector (PlanetScale Postgres is billable through
  Cloudflare; Neon/Supabase/RDS also work). Self-hosted uses a Postgres sidecar.
- **Files** use the v0.66.0 storage abstraction: R2 (S3-compatible) when hosted,
  the local `/data/files` directory when self-hosted.
- **Tenancy stays "one shared database, every row owned by a user"**, which is
  what the code already does, hardened with PostgreSQL row-level security and
  cross-account tests.
- Background scans move from "always inside the web process" to "inside the web
  process **or** woken by an external tick", because Cloudflare containers sleep.

About ten bounded increments separate today's code from a hosted beta. Most of
them also improve self-hosting (environment secrets, migrations as a job, proxy
handling, readiness checks). The two largest non-code items are Google's
restricted-scope verification for Gmail and an operational backup/restore story.

## What LifeGather is today

| Area | Current state (v0.66.0) | Hosted impact |
| --- | --- | --- |
| Packaging | One image: Vite build served as static files by FastAPI/uvicorn on port 8787, non-root, read-only root FS | Runs unchanged as a Cloudflare Container |
| Database | SQLite file `/data/auth.sqlite3`, FTS5 search; PostgreSQL with pgvector from 0.75 | Container disk is ephemeral, so Postgres is a hard prerequisite |
| Files | `lifegather.storage`: `local` or `s3`; keys `users/<id>/...`; hash-checked reads | R2 fits directly. Image lacks the `s3` extra (boto3) |
| Accounts | Google login and email/password; any Google account may register; per-user isolation | Already multi-user; needs abuse controls and lifecycle work |
| Isolation | Owner checks in services (`owner_id`/`user_id` in ~90 modules) | Add DB-enforced backstop (RLS) and a cross-tenant test suite |
| Secrets | One 32-byte AES-GCM vault key read from a file; encrypts every user's AI keys and Gmail tokens | Must come from a secret store, needs versioning for rotation |
| Config | Env vars + optional installation JSON file outside `/data` | Env-only works; file path options stay for self-hosting |
| Background work | `ScanWorker` asyncio task inside the web process; lease/heartbeat claims in DB; schedule dispatch each loop | Sleeping containers never run schedules; needs an external tick |
| Startup | `store.migrate()` and inline-file moves run in app lifespan | Several instances would race; move to a one-shot job with a lock |
| Limits | In-process semaphores (4 chat, 2 photo, 1 document); DB-backed daily AI quota | Per instance, which is fine; quotas are already DB-backed |
| Proxying | uvicorn `--no-proxy-headers`; MCP host/origin locked to `LIFEGATHER_PUBLIC_URL` | Must trust only the Worker's forwarded headers |
| Email | SMTP settings | Any SMTP provider, or Cloudflare Email Service |
| AI | Bring-your-own OpenAI/Anthropic/Gemini keys stored per user | Works as-is; platform-paid AI would be a new billing feature |
| Gmail | `gmail.readonly` OAuth scope | Restricted scope: public use needs Google verification and a CASA assessment |
| Recovery | Encrypted installation-wide bundle; personal archive ZIP | Operator bundle does not scale to many tenants; needs provider backups + per-user export/delete |

## Cloudflare capabilities that matter (checked 2026-10-22)

- **Containers** are generally available on the Workers Paid plan since
  2026-04-13. Each container instance is driven by a Durable Object and reached
  through a Worker. Instance types run from `lite` (1/16 vCPU, 256 MiB) through
  `basic` (1/4 vCPU, 1 GiB), `standard-1` (1/2 vCPU, 4 GiB) to `standard-4`
  (4 vCPU, 12 GiB). Billing is per 10 ms while running: memory and disk on
  provisioned size, CPU on active use.
- **Container disk is ephemeral.** A sleeping instance restarts from the image
  with a fresh disk. `sleepAfter` defaults to 10 minutes. There is no built-in
  autoscaling yet; you route to named instances or pick a random one from a pool.
  Cold starts are typically 1 to 3 seconds plus app startup.
- **Outbound networking:** internet access is on by default, including non-HTTP
  ports, so the Python app can talk to Postgres over TCP and to SMTP directly.
  `enableInternet`, `allowedHosts` and `deniedHosts` can restrict it. Containers
  can also reach Worker bindings (R2, KV, Durable Objects) through outbound
  handlers on virtual hostnames.
- **Secrets** are Worker secrets or Secrets Store values, read by the Durable
  Object and passed to the container as environment variables at start. A changed
  secret applies on the next container start.
- **Hyperdrive** pools and caches Postgres connections for Workers. It does not
  help a long-running Python container that keeps its own connection pool, so it
  is optional here. PlanetScale Postgres (and MySQL) can now be created and billed
  through the Cloudflare dashboard; PlanetScale Postgres supports pgvector.
- **R2:** $0.015/GB-month standard storage, $4.50 per million writes, $0.36 per
  million reads, no egress fees; 10 GB, 1M writes and 10M reads free each month.
  It speaks the S3 API, which the existing `s3` backend already uses.
- **Cron Triggers and Queues** can wake a container on a schedule or per job.
- **Email Service** (Workers Paid): 3,000 outbound emails/month included, then
  $0.35 per 1,000.
- **Access (Zero Trust):** free up to 50 seats. Useful to protect operator/admin
  routes; not suitable as the customer login for a public SaaS.
- **Turnstile** (bot check) is free and fits the sign-up and password forms.

## Recommended hosted architecture

```
Browser / MCP client
   │ HTTPS (custom domain, Cloudflare TLS, WAF, rate limits, Turnstile on sign-up)
   ▼
Worker "lifegather-edge"  (TypeScript, ~100 lines, deploy/cloudflare/)
   ├─ /ops/*  → Cloudflare Access (operator only)
   ├─ everything else → container pool: getRandom / fixed names app-0..app-N
   └─ Cron Trigger (every 1–5 min) → POST /internal/jobs/tick on one instance
   ▼
Cloudflare Container: ghcr.io/bgoldbeck/life-gather (same image as self-host)
   ├─ PostgreSQL + pgvector  (managed; TCP via psycopg pool; TLS required)
   ├─ R2 bucket via S3 API   (private; LIFEGATHER_STORAGE_BACKEND=s3)
   ├─ SMTP / Cloudflare Email Service
   └─ AI providers / Gmail API (users' own credentials from the vault)
Secrets Store → vault key, DB URL, R2 keys, Google OAuth secret, tick token
```

Decisions behind it:

1. **Containers, not a Workers rewrite.** The app is FastAPI with native libraries
   (Pillow, cryptography, pypdf), long-running streamed chat and ten-minute scan
   jobs. Containers run it unchanged; a Python Workers port would be a redesign
   with no product benefit.
2. **Stateless app instances.** With Postgres and R2 there is no durable state on
   container disk. Any instance can serve any request. Start with two always-warm
   `basic` or `standard-1` instances; add names to the pool to scale.
3. **Shared database, owner-scoped rows (pool model).** The code is already built
   this way, and per-user databases would multiply migrations, backups and cost.
   Add Postgres row-level security keyed on the acting user as a second lock, set
   per transaction by the service layer. Storage keys already start with
   `users/<id>/`.
4. **Jobs: two modes, one code path.** `LIFEGATHER_BACKGROUND_MODE=inprocess`
   (default, self-hosting) keeps today's loop. `external` disables the loop and
   exposes an authenticated tick endpoint that dispatches due schedules and runs
   claimed jobs for a bounded time. The existing lease/heartbeat claims already
   make concurrent workers safe.
5. **Secrets via environment.** Add `LIFEGATHER_VAULT_KEY` (base64) alongside the
   file option, and key IDs so the key can rotate. Long term, wrap per-user data
   keys with the master key so one user's material can be destroyed on deletion.
6. **Cloudflare-specific code stays in `deploy/cloudflare/`** (Worker, wrangler
   config, runbook). The Python app never imports Cloudflare SDKs.

### Alternative with the same image

If Containers' per-instance memory pricing or placement becomes a problem, run the
same image on any VM or managed container host and keep Cloudflare in front
(proxy/WAF, R2, Email, Access). This is the self-hosted path plus a Tunnel, so it
needs no extra application work. It is the fallback, not the first choice, because
it brings back server patching and capacity planning.

## Self-hosted Docker stays first-class

Rules for every hosted increment:

- One codebase, one image, one release process. No hosted-only fork or branch.
- The default `docker-compose.yml` keeps working on any Linux server without a
  Cloudflare account: app + Postgres sidecar + local file directory.
- Hosted behaviour is selected only by settings that also make sense self-hosted
  (`DATABASE_URL`, storage backend, background mode, trusted proxy, env secrets).
- Self-hosters can still put the app behind a Cloudflare Tunnel (see
  [remote access](REMOTE_ACCESS.md)) or any reverse proxy, or use their own S3/R2
  bucket, without running the hosted Worker.
- Tests run the service suite against Postgres with both `local` and `s3` storage
  (an S3 stub), and both background modes.

## Gaps to close

| # | Gap | Why it blocks hosting | Also helps self-hosting? |
| --- | --- | --- | --- |
| G1 | PostgreSQL migration not merged | Ephemeral disk; multiple instances | Yes (planned already) |
| G2 | Image lacks `s3` extra and Postgres driver | R2 backend fails at startup | Yes |
| G3 | Vault key only from a file; single unversioned key | Containers get secrets as env; rotation | Yes |
| G4 | Migrations and file moves run in every app start | Instances race on deploy | Yes |
| G5 | Scan worker only in-process | Sleeping instances skip schedules | Optional |
| G6 | No trusted-proxy handling (client IP, scheme) | Rate limits and audit see the Worker, not the user | Yes, behind any proxy |
| G7 | Isolation enforced only in service code | One missed filter leaks another user's data | Yes |
| G8 | No per-user storage/usage quotas | Abuse and cost control | Minor |
| G9 | Sign-up abuse controls, terms/privacy acceptance | Public registration | No |
| G10 | Account deletion across DB, R2 and backups | Privacy law and user trust | Yes |
| G11 | Backups are installation-wide bundles | Need PITR + per-user restore | Partly |
| G12 | Gmail `gmail.readonly` needs Google verification + CASA | Unverified apps cap at 100 users and warn | No |
| G13 | Operator view, structured logs, alerting | Running a service for others | Partly |
| G14 | Billing/plans | Charging for the service | No (conditional) |

## Phased steps

**Step A: portable container (self-host benefits first).** Finish and merge the
Postgres migration (G1). Add `s3` and the Postgres driver to the image (G2).
Accept the vault key and installation settings from environment variables with
key IDs (G3). Add `python -m lifegather.migrate` as a one-shot job guarded by a
Postgres advisory lock, and make startup tasks lock-protected (G4). Split
`/health` into liveness and readiness. Add `LIFEGATHER_TRUSTED_PROXY` handling for
forwarded scheme and client IP (G6).
*Acceptance:* the same image passes the smoke test with local files + Postgres
sidecar and with an S3 stub + external Postgres; two instances start at once
without migration races.

**Step B: external background mode (G5).** `LIFEGATHER_BACKGROUND_MODE` with an
authenticated, bounded `/internal/jobs/tick`; schedule dispatch and job claims
unchanged. *Acceptance:* schedules fire on time with the in-process loop disabled
and ticks arriving from two instances; a cancelled or expired lease resumes once.

**Step C: isolation hardening (G7, G8).** Row-level security policies on owned
tables, set by the session per transaction; a cross-account test suite that tries
every HTTP route and MCP tool with another user's IDs; per-user file-size and total
storage quotas. *Acceptance:* tests prove no cross-user reads/writes with RLS on,
and a deliberately removed service filter is caught by RLS.

**Step D: Cloudflare deployment package.** `deploy/cloudflare/` Worker and wrangler
config: container class, pool routing, streaming pass-through for chat, Cron
tick, secrets from Secrets Store, R2 bucket, Access on `/ops`. A runbook for
creating the account resources. *Acceptance:* a staging deployment with synthetic
accounts passes sign-in, upload, streamed chat, scheduled scan and restart tests;
no secrets in Git; container egress limited to needed hosts where practical.

**Step E: hosted account lifecycle (G9, G10).** Turnstile on sign-up and password
forms, terms and privacy acceptance, verified account deletion that removes DB
rows and R2 objects and records when backups expire, and the existing personal
archive as the export. *Acceptance:* a deleted test account leaves no rows or
objects; export round-trips.

**Step F: backups and recovery for many users (G11).** Provider point-in-time
recovery for Postgres; R2 object versioning or lifecycle-protected copies; a
restore drill into staging; per-user restore from the personal archive.
*Acceptance:* a timed restore drill meets a written RPO/RTO.

**Step G: Google verification (G12).** Production OAuth branding, privacy policy,
domain verification, restricted-scope review and CASA Tier 2 assessment for
`gmail.readonly`, renewed yearly. Until then, Gmail scanning is limited to
allowlisted test users. *Acceptance:* Google approval recorded.

**Step H: operations (G13).** Structured JSON logs without private content, error
alerting, an operator page behind Access showing job backlog, failures and storage
use, and a status page. **Step I (conditional): plans and billing (G14).**

Steps A–C are worth doing even if hosting never launches. Public launch should
wait for the Phase 3 dependability gate in the [feature plan](FEATURE_PLAN.md).

## Cost sketch (USD/month, list prices on 2026-10-22)

Container figures assume always-on instances (no sleep) and modest CPU use.

| Item | Pilot (~10 users) | Small production (~100 users) |
| --- | --- | --- |
| Workers Paid plan | $5 | $5 |
| Containers | 1 × `basic` ≈ $7 | 2 × `standard-1` ≈ $60 |
| Postgres | PlanetScale PS-5 single node $5 (not HA) | HA tier; price from PlanetScale calculator |
| R2 | free tier (under 10 GB) | ~200 GB ≈ $3 + operations |
| Email | included (3,000/month) | included or ≈ $1 |
| Access, Turnstile, Cron | $0 | $0 |
| **Platform subtotal** | **≈ $17** | **≈ $70 + HA database** |

One-off and yearly: a domain, and Google's CASA Tier 2 assessment (vendor
sources quote roughly $540–$1,000 per year for the self-serve lab path, plus weeks
of review). AI usage stays on each user's own provider key unless platform-paid AI
is added later. Memory, not CPU, dominates container cost: 4 GiB always on is about
$26/month per instance, so measure real memory use before picking `standard-1`.

## Risks

- **Privacy and trust shift.** Hosting other people's receipts, documents, Gmail
  tokens and AI keys makes Lisa a data processor. Needs a privacy policy, deletion
  guarantees, breach response and care with jurisdictions. Cloudflare terminates
  TLS and sees traffic.
- **Single vault key.** Today one key decrypts every user's credentials. Leakage
  from a secret store or a debug dump exposes all tenants. Mitigate with key IDs,
  rotation and per-user wrapped keys.
- **Cross-tenant bugs.** Isolation is code-enforced. RLS and the cross-account
  suite are the mitigation; treat any cross-user finding as a release blocker.
- **Container behaviour.** Ephemeral disk, sleep after inactivity, no autoscaling
  yet and placement chosen by Cloudflare. Mitigate with stateless instances, a warm
  pool, external ticks, and placing the database near where instances run (verify
  container placement controls before choosing the database region).
- **Streaming through the Worker.** Chat uses streamed responses; verify long
  streams and upload limits (100 MB request body on the Free plan) through the
  Worker before launch.
- **Google review.** Restricted-scope approval can take weeks and must be renewed
  yearly; without it Gmail stays limited to 100 test users.
- **Vendor lock-in.** Kept low by the S3 API, standard Postgres and an unmodified
  image; the Worker shim is the only Cloudflare-specific code.
- **Cost surprises.** Always-on memory, AI abuse via platform keys (if ever added)
  and R2 write-heavy patterns. Set budgets and quotas from day one.

## Inconsistencies with existing documents

- Update 2026-10-23: the Step D test-site package is in `deploy/cloudflare/`
  ([Cloudflare test site](CLOUDFLARE_TEST_SITE.md)). It keeps secrets as Worker
  secrets rather than Secrets Store (fewer setup steps for one Worker), puts the
  whole test site behind Access, and resolves the `AGENTS.md` anti-goal line below.

- `AGENTS.md` lists "public SaaS infrastructure" among the anti-goals "unless a
  later task specifically requests and justifies them". The hosted option was
  requested on 2026-10-22 and is now Phase 5 of the feature plan. Proposed
  resolution: when Step D starts, update that anti-goal line to reference Phase 5,
  so hosted infrastructure is allowed only within its scoped increments.
- Resolved in 0.75: `PROJECT_PLAN.md` and the app now use PostgreSQL.
- `REMOTE_ACCESS.md` defers remote access; that deferral is about the self-hosted
  phone path and is unaffected by a separate hosted option.

## Sources

- [Containers and Sandboxes GA (2026-04-13)](https://developers.cloudflare.com/changelog/2026-04-13-containers-sandbox-ga)
- [Containers pricing and instance types](https://developers.cloudflare.com/containers/pricing/)
- [Containers FAQ (disk, cold starts, sleepAfter)](https://developers.cloudflare.com/containers/faq)
- [Higher container limits (2026-02-25)](https://developers.cloudflare.com/changelog/post/2026-02-25-higher-container-resource-limits)
- [Containers outbound traffic](https://developers.cloudflare.com/containers/platform-details/outbound-traffic)
- [Containers: connect to Workers and bindings](https://developers.cloudflare.com/containers/platform-details/workers-connections/)
- [Containers: env vars and secrets](https://developers.cloudflare.com/containers/examples/env-vars-and-secrets/)
- [Hyperdrive pricing](https://developers.cloudflare.com/hyperdrive/platform/pricing)
- [PlanetScale databases with Cloudflare billing](https://developers.cloudflare.com/changelog/post/2026-06-18-planetscale-databases-cloudflare-billing/)
- [PlanetScale pgvector](https://planetscale.com/docs/postgres/extensions/pgvector) and [$5 single node](https://planetscale.com/blog/5-dollar-planetscale)
- [R2 pricing summary](https://filebase.com/blog/cloudflare-r2-pricing-costs-savings-and-alternatives-in-2026/)
- [Cloudflare Email Service pricing](https://developers.cloudflare.com/email-service/platform/pricing/)
- [Zero Trust pricing summary](https://zerotrustcost.com/cloudflare-zero-trust-pricing)
- [Google OAuth verification and CASA summary](https://www.unipile.com/integrating-google-oauth-2-0-user-authentication-into-your-app/)
