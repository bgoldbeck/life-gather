# LifeGather test site on Cloudflare

A private test copy of LifeGather running on Cloudflare (Phase 5.4 of the
[feature plan](FEATURE_PLAN.md), staging only). It runs the same image as
self-hosting, with:

- a **Cloudflare Container** running the app, started by a small Worker
  (`deploy/cloudflare/`), sleeping 5 minutes after the last request;
- **PostgreSQL** from Neon (free plan is enough; any PostgreSQL 16+ with
  pgvector works);
- a private **R2 bucket** for photos and documents;
- a **Cron Trigger** every 10 minutes that runs due scheduled scans
  ([outside scheduler](EXTERNAL_BACKGROUND.md));
- **Cloudflare Access** in front of everything, so only the email addresses you
  allow can open the site.

This is not a public launch. Public sign-up needs the Phase 3 gate, bot checks and
terms (5.5) and Google verification (5.7) first. Nothing in the self-hosted
Docker setup changes.

## What it costs

| Item | Price (October 2026 list prices) |
| --- | --- |
| Workers Paid plan (needed for Containers) | $5/month |
| Container, `basic` (1/4 vCPU, 1 GiB) | about $7/month if never asleep; less while asleep |
| Neon PostgreSQL, free plan | $0 (0.5 GB storage) |
| R2, Access (up to 50 users), Cron | $0 within free allowances |

The Cron Trigger wakes the container every 10 minutes, so expect it to be awake
about half the time. To stop all charges, follow [Remove the test site](#remove-the-test-site).

## Before you start

On your Windows computer you need:

- **Docker Desktop**, running (the deploy builds the image from this repository);
- **Node.js 22 LTS or newer** (<https://nodejs.org>);
- this repository, up to date: `git checkout main` then `git pull`.

All commands below run in a terminal opened in `deploy\cloudflare` of the
repository.

## Step 1: Cloudflare account and Workers Paid

1. Sign in at <https://dash.cloudflare.com> (create a free account if needed).
2. Go to **Workers & Pages** → **Plans** and choose **Workers Paid** ($5/month).
   Containers are not available on the free plan.
3. If asked, pick a `workers.dev` subdomain (for example `lisa`). The site will
   live at `https://lifegather-test.<subdomain>.workers.dev`.

## Step 2: The database (Neon)

1. Sign up at <https://neon.tech> and create a project named `lifegather-test`,
   PostgreSQL 17, in the region closest to you (for example AWS US East).
2. Open **SQL Editor** and run, one statement at a time:

   ```sql
   CREATE DATABASE lifegather TEMPLATE template0
     ENCODING 'UTF8' LC_COLLATE 'C' LC_CTYPE 'C';
   ```

   Then switch the editor's database drop-down to `lifegather` and run:

   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   SELECT datcollate FROM pg_database WHERE datname = current_database();
   ```

   The last query must answer `C` (or `C.UTF-8`). LifeGather refuses other
   collations because its sorting and paging rely on byte order.
3. Click **Connect**, choose database `lifegather`, and **turn connection pooling
   off** (the host name must not contain `-pooler`). LifeGather keeps its own
   connections and needs session features the pooler does not support. Copy the
   connection string; it looks like
   `postgresql://neondb_owner:...@ep-...us-east-2.aws.neon.tech/lifegather?sslmode=require`.

The app creates its tables and the `lifegather_account` row-security role on
first start.

## Step 3: The file bucket (R2)

1. In the Cloudflare dashboard go to **R2 Object Storage** → **Create bucket**,
   name it `lifegather-test-files`, location Automatic. Leave public access off.
2. Back on the R2 overview, open **Manage API tokens** (or **API** → **Manage API
   tokens**) → **Create Account API token**:
   - Permissions: **Object Read & Write**
   - Specify bucket: **Apply to specific buckets only** → `lifegather-test-files`
3. Create it and copy the **Access Key ID**, the **Secret Access Key** and the
   **S3 endpoint** (`https://<account id>.r2.cloudflarestorage.com`). The secret
   is shown only once.

## Step 4: Settings file

```
npm install
npm run init-settings
```

This creates `deploy\cloudflare\test-site.env` with a new vault key, tick
token and proxy secret. Git ignores this file; never commit or share it. Copy the `VAULT_KEYS`
line into your password manager: without it, saved AI keys and Gmail sign-ins on
the test site cannot be read. It is a new key, separate from your home server's.

Open `test-site.env` in Notepad and fill in:

- `DATABASE_URL` from step 2;
- `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` from step 3
  (and `R2_BUCKET` if you used another name).

Leave `PUBLIC_URL`, `ACCESS_TEAM_DOMAIN` and `ACCESS_AUD` for now.

## Step 5: First deploy

```
npx wrangler login
npm run deploy
```

`wrangler login` opens the browser; allow access. The deploy builds the image
with Docker (the first build takes several minutes), uploads it to Cloudflare's
registry and prints the site address, for example
`https://lifegather-test.lisa.workers.dev`. Put that address in
`PUBLIC_URL` (no trailing slash).

Cloudflare needs a few minutes to provision the container the first time. Until
Access is set up the site answers "locked"; that is expected.

## Step 6: Lock the site with Cloudflare Access

1. Dashboard → **Workers & Pages** → `lifegather-test` → **Settings** (or the
   **Access** tab) → **Protect this Worker behind Access** → **All traffic**.
2. Policy: allow **emails** and list your own address (and any tester's).
   Apply.
3. Go to **Zero Trust** → **Access** → **Applications**, open the application
   just created, and copy its **Application Audience (AUD) Tag** into
   `ACCESS_AUD`.
4. Zero Trust → **Settings** → **Team name and domain**: copy the team domain
   (`<team>.cloudflareaccess.com`) into `ACCESS_TEAM_DOMAIN`.

The Worker checks Access's signed token on every request itself too, so the site
stays locked even if the Access policy is later removed by mistake.

## Step 7: Send the settings and open the site

```
npm run push-settings
```

This stores every line of `test-site.env` as an encrypted Worker secret. Open
the `PUBLIC_URL` address, sign in to Access with your email code, and wait up to a
minute while the first start creates the database tables ("LifeGather is
starting" means reload shortly).

Check it is healthy: `PUBLIC_URL/health/ready` should answer `{"status":"ready"}`.

## Step 8: An account on the test site

Pick one:

- **Google sign-in (recommended).** In Google Cloud Console → **APIs & Services**
  → **Credentials**, open your OAuth client (or create a Web client), add the
  redirect URI `PUBLIC_URL/auth/google/callback`, and put the client ID and secret
  in `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`. Gmail scanning works only for
  addresses listed as test users on the consent screen until Google verifies the
  app (Phase 5.7).
- **Email and password without email delivery.** With Docker Desktop, run (one
  line, using the `DATABASE_URL` from `test-site.env`):

  ```
  docker run --rm -it -e LIFEGATHER_DATABASE_URL="<DATABASE_URL>" ghcr.io/bgoldbeck/life-gather:latest python -m lifegather.setup_account
  ```

  The image must be the same release as the test site or newer. Then use **Sign
  in with email**. See [local account setup](LOCAL_ACCOUNT_SETUP.md).
- **One-click test login.** Set `TEST_LOGIN_ENABLED=true`. Everyone who passes
  Access shares one workspace; use synthetic data only ([test mode](TEST_MODE.md)).

To try the sign-up protections, set `TURNSTILE_SITE_KEY` and
`TURNSTILE_SECRET_KEY` (a Turnstile widget for the Worker's hostname) and/or
`TERMS_VERSION`; see [sign-up protection](SIGNUP_PROTECTION.md). The terms text
is a placeholder.

After changing `test-site.env`, run `npm run push-settings` again. The container
reads settings when it starts, so changes apply after its next sleep: stay off the
site for about 15 minutes (it sleeps 5 quiet minutes after the last visit or
scheduled-scan check). A `npm run deploy` that changes the image also restarts it.

## Updating the test site

```
git pull
npm run deploy
```

Database migrations run automatically on the next start.

## Checking on it

- `npm run logs` streams the Worker's logs (query strings are redacted). Each
  Cron run logs counts like `{"status":"ok","dispatched":0,"ran":0,...}`.
- Dashboard → **Workers & Pages** → `lifegather-test` → **Containers** shows
  instances, their state and container logs.
- Neon's dashboard shows database size; R2's shows stored files.
- Put your sign-in email in `OPERATOR_EMAILS` to get the in-app
  [Operations page](OPERATIONS.md) (stuck jobs, failures, storage) and, with SMTP
  or `ALERT_WEBHOOK_URL`, error alerts. The whole test site is already behind
  Access; a public site should keep Access on `/api/operator/`.

## Visitor addresses

Sign-in limits count attempts per visitor address. The container only ever sees
the Worker connecting, so the Worker passes Cloudflare's `CF-Connecting-IP` as
`X-Forwarded-For` together with `PROXY_SECRET` in `X-LifeGather-Proxy-Secret`.
The app believes the forwarded address only when that secret matches its
`LIFEGATHER_PROXY_SECRET`, and removes the header before anything else sees it.
The Worker drops any copy a visitor sends. `LIFEGATHER_TRUSTED_PROXIES` stays
unset: Cloudflare's internal addresses are not fixed, and trusting every
address would let anyone who reached the container choose their own.

If you made `test-site.env` before this setting existed, add a line
`PROXY_SECRET=` followed by 64 random hex characters (for example from
`node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"`),
then run `npm run push-settings` and `npm run deploy`. Until then the Worker
answers with a "Missing test-site settings: PROXY_SECRET" page.

## Known limits of the test site

- **Behind Access only.** MCP clients and other programs cannot pass the Access
  sign-in, so private MCP is not available here.
- **Scheduled scans run within 10 minutes** of their time, not to the second.
- **Settings change on the next container start**, not immediately. A new
  `DATABASE_URL` or `VAULT_KEYS` therefore needs the container asleep first.
- **Outbound internet stays open** for the container: it needs Neon, R2, Google,
  AI providers, SMTP and web research sites.
- **Not a backup.** Neon's free plan keeps a short restore window. Export your
  personal archive from Settings if you add anything you want to keep.
- **Memory.** `basic` has 1 GiB. If large documents fail, change
  `instance_type` to `standard-1` in `wrangler.jsonc` and deploy again (about four
  times the memory cost).

## Remove the test site

1. `npx wrangler delete` in `deploy\cloudflare` (removes the Worker, container
   and its secrets).
2. R2 → `lifegather-test-files` → delete all objects, then delete the bucket; also
   delete its API token.
3. Zero Trust → Access → Applications: delete the `lifegather-test` application.
4. Neon: delete the `lifegather-test` project.
5. Optionally downgrade Workers Paid to Free.

## What the Worker does

`deploy/cloudflare/src/index.ts`:

- Refuses every request without a valid Access token for `ACCESS_AUD` (or, until
  Access is configured, every request; `ALLOW_WITHOUT_ACCESS=true` disables this
  lock and is not recommended).
- Answers 404 to `/internal/...` from outside; only the Cron Trigger calls the
  scan tick, with `JOB_TICK_TOKEN`.
- Replaces `X-Forwarded-For` and `X-Forwarded-Proto` with Cloudflare's view of
  the visitor and drops other forwarding headers.
- Starts the container with the settings from `container-settings.json`:
  external background mode, S3 storage on R2 and migrations on start are fixed;
  the rest come from the Worker secrets. A missing required setting is named
  (never its value) in a 503 answer.
- `POOL_SIZE` (default 1, at most `max_instances` in `wrangler.jsonc`) spreads
  visitors over several containers. Any instance can serve any request because
  records live in PostgreSQL and files in R2.

Checks: `npm run check` (TypeScript and unit tests) and `npm run dry-run`
(bundles the Worker without Docker or an account). The backend test
`tests/test_cloudflare_settings.py` fails if a setting the Worker passes is
renamed or rejected by the app.
