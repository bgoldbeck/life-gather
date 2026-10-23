# LifeGather

[![Source version](https://img.shields.io/badge/source_version-v0.86.1-426B46)](CHANGELOG.md)

This badge identifies the source release. Check the login screen or app header for your running container’s version.

LifeGather is a private, self-hosted personal-memory application built around an evidence-backed knowledge graph and natural-language chat.

It aims to help organize possessions, events, documents, and relationships while preserving the original sources, tracking changes over time, and distinguishing facts from inferences and unknowns.

## Project status

Profiles offers [sourced maintenance tasks](docs/MAINTENANCE.md), with optional
calendar dates, an explicit timezone and preserved completion/correction history.
The Maintenance view lists tasks across your records. No automatic reminders or
maintenance intervals are inferred.

Your conversations offers [reviewed transcript deletion](docs/CONVERSATION_PRIVACY.md)
with a fresh count, separate pending-request stop and explicit permanent confirmation.
Saved evidence, profile changes, files, scans and usage remain independent.

Profiles supports [named custom details](docs/CUSTOM_PROFILE_DETAILS.md), such as
tire size or fuel type, with original evidence, explicit unknowns and corrections.
Existing identity fields and physical-item matching keep their established meaning.
The [contextual assistant](docs/CONTEXTUAL_ASSISTANT.md) can save these supplied
details with explicit commands such as `Set custom "Tire size" to 205/55R16`.

Operators can create, verify and restore [encrypted installation backups](docs/OPERATOR_RECOVERY.md)
including every owner's database, photo/PDF originals, configuration and vault key.
Recovery creates a new directory and never starts or replaces an installation.

Assets now supports [reversible two-record consolidation](docs/ASSET_CONSOLIDATION.md):
choose a primary record after a fresh complete comparison and explicitly confirm
the same physical item. Original evidence, conflicting facts and history remain.
Current browsing, galleries, profiles, graph and recall share the chosen identity.

Settings provides a [private records download](docs/RECORD_EXPORT.md) with saved
evidence and history, purchases/units, conversations and file metadata. Opt into
the [personal ZIP archive](docs/PERSONAL_ARCHIVE.md) to include active saved photo/PDF
originals and a hash manifest. Credentials and installation state remain excluded.

Use **Add asset** on Assets for private manual inventory entry, including
duplicate checks and original user-stated evidence, without an AI provider.

Profiles, Assets and Graph now offer [field change history](docs/CHANGE_HISTORY.md)
with evidence, dates and recorded editing/AI workflow attribution.

Chat can now [request a bounded email evidence scan](docs/EMAIL_SCANS.md)
from an explicitly chosen connected Gmail mailbox, then open its saved progress.

The app now reports its running version on the login screen and in the app header.
See [versioning](docs/VERSIONING.md) and the [changelog](CHANGELOG.md) for release numbering; older Docker images need an update to display it.

The source includes a responsive React shell, Google sign-in, and [email/password signup and recovery](docs/EMAIL_PASSWORD_AUTH.md) with persistent server-side sessions. Native registration/recovery need a configured installation email sender; real SMTP delivery has not been tested here. Follow [Google login setup](docs/GOOGLE_LOGIN.md) to configure an OAuth client; real Google sign-in needs installation credentials. The [evidence-backed memory core](docs/MEMORY_CORE.md) now provides private Python services for sources, graph facts, history, search, export, and database snapshots. The [reconciliation service](docs/RECONCILIATION.md) now distinguishes purchased units, enriches reliable matches, and preserves review/correction decisions. The [private MCP recall adapter](docs/PRIVATE_MCP.md) exposes authenticated recall and explicit note-write tools over those services. The first [text chat increment](docs/TEXT_CHAT.md) adds persistent conversations, explicit original-text capture, keyword recall, evidence inspection, saved-note correction/history, and optional OpenAI answers. [Reviewed asset proposals](docs/ASSET_PROPOSALS.md) now connect one saved note to a sourced physical item after human confirmation. [Multi-item receipts](docs/MULTI_ITEM_RECEIPTS.md) add reviewed quantities and atomic batch confirmation; the [Memories library](docs/MEMORIES.md) provides private capture and browsing. Streaming and bounded graph recall are implemented. Source-backed line totals in USD/EUR/GBP/CAD/AUD/JPY and purchase dates are available on confirmed receipt purchases, with editable source suggestions. Current receipt purchase records are accessible directly from each asset, with source and history links. Chat can recall bounded latest reviewed receipt details for named assets; reviewed single-item drafts can also record clear identities in one action. [Reviewed discovery-evidence batches](docs/EVIDENCE_BATCHES.md) can move up to five associations together and reverse an unchanged batch. [Explicit replacement links](docs/REPLACEMENTS.md) connect distinct physical items without changing their receipts or ownership. Existing private photos can be linked into another item gallery without another upload. Broader financial extraction remains planned. LifeGather is a working name pending clearance. Completed, tested features follow the standing source and container release rule in `AGENTS.md`; publishing does not redeploy existing installations.


Settings supports a separate [private Gmail connection](docs/EMAIL_SCANS.md), requested/scheduled evidence scans and optional [AI purchase discovery](docs/EMAIL_DISCOVERY.md). Connecting alone never scans mail. Clear purchases create inferred assets; possible duplicates and uncertainty go to Review.

## Run with Docker

For local testing without account setup, explicitly enable [one-click test mode](docs/TEST_MODE.md). It is disabled by default and exposes a shared test workspace only when enabled.

For testing without Google or email delivery, the installation owner can [create a private local sign-in account](docs/LOCAL_ACCOUNT_SETUP.md) using an interactive terminal command. It requires an updated image containing this feature.

The source also includes [private settings and an encrypted credential vault](docs/PRIVATE_SETTINGS.md). Google login needs one-time OAuth setup by the installation owner; individual users only choose their Google account. The optional vault key is a separate server setting and is not a sign-in requirement.

For TrueNAS or an installation without a local source build, use the published image `ghcr.io/bgoldbeck/life-gather:latest`. See [TrueNAS installation and updates](docs/TRUENAS.md) and the [image-only Compose file](deploy/compose.image.yaml). GitHub Actions is disabled; maintainers verify releases locally and rebuild/upload images only with user approval.

To build and publish when your connection is free, use the [local release script and instructions](docs/LOCAL_RELEASE.md). It asks separately before building and uploading, reports local image sizes, and never pushes or merges source code.

Install Docker Engine with the Compose plugin on Linux, or Docker Desktop with the Linux engine on Windows/macOS. No host Python or Node.js installation is needed for this path.

The standalone test-preview launcher names containers `lifegather-preview-v<version>`
using the downloaded image's OCI version label and starts that exact inspected
image ID. Docker's Name column therefore identifies the running version. Existing
containers keep their actual version until deliberately recreated; source updates
and image publication do not redeploy them. Compose project/volume names stay stable.

From the repository root:

```powershell
docker compose up --build --detach --wait
docker compose ps
```

Open <http://127.0.0.1:8787> for the app or <http://127.0.0.1:8787/health> for `{"status":"ok"}`. The one service serves both the built frontend and backend. Node.js is used only during the image build.

To change the local port or application name, copy `.env.example` to `.env` at the repository root. Set `LIFEGATHER_PORT` to an available host port, then recreate the service. Both host and container default to port 8787; changing `LIFEGATHER_PORT` changes only the host port. The root `.env` configures Compose; `backend/.env` is for local Python development only and is not copied into the image.

Useful commands:

```powershell
docker compose logs --tail 100 backend
docker compose restart backend
docker compose down
```

Compose also runs a PostgreSQL (pgvector) `db` service; set `LIFEGATHER_DB_PASSWORD` in the root `.env` first (see [PostgreSQL](docs/POSTGRESQL.md)). `docker compose down` preserves the named `lifegather-db` database volume and the `lifegather-data` volume mounted at `/data`. **Do not add `--volumes` unless you intend to erase local application data.** The app applies packaged Alembic migrations on startup, and on its first start copies an existing `/data/auth.sqlite3` from older releases into the empty database. Private data is never served from the frontend asset directory.

The container runs as UID/GID 10001, with a read-only root filesystem, a writable `/data` volume, a temporary `/tmp`, and dropped Linux capabilities. The source-build Compose file publishes only on `127.0.0.1`; the image-only TrueNAS Compose file publishes on all IPv4 interfaces (`0.0.0.0`) for LAN access. Configure Google login using the documented public URL and credentials; non-loopback login requires HTTPS. Remote exposure remains deferred, and the old published preview is unauthenticated.

The source includes private memory and reconciliation services, an authenticated MCP adapter, text chat and an [operator recovery CLI](docs/OPERATOR_RECOVERY.md). Personal record import and a recovery UI remain later work. See the login guide for session expiry, revocation, private storage, and verification limits.

## Backend development

Prerequisites: [uv](https://docs.astral.sh/uv/getting-started/installation/) and Python 3.13. uv can install the Python version if it is missing.

Run these commands from the repository root:

```powershell
cd backend
uv sync --locked
uv run --locked uvicorn lifegather.main:create_app --factory --reload --host 127.0.0.1 --port 8787
```

Open <http://127.0.0.1:8787/health> to see `{"status":"ok"}`. API documentation is available at <http://127.0.0.1:8787/docs>. Stop the server with Ctrl+C. Stop the Compose service before using local Python development, because both use host port 8787.

Dependencies are installed into `backend/.venv`; `backend/uv.lock` records resolved versions. No environment activation or global package installation is needed. To reproduce the environment from scratch, run `uv sync --locked` in a fresh checkout.

Optionally copy `backend/.env.example` to `backend/.env` and adjust `LIFEGATHER_APP_NAME`. Commands must run from `backend/` so the application reads that directory's `.env`. Environment variables take precedence over `.env` values. Keep secrets out of version control.

### Checks

From `backend/`:

```powershell
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
```

`/health` reports process liveness only; it does not check database or model availability. The development server binds to localhost. Private settings and MCP require authenticated sessions; `/health` remains public. Remote deployment requires the documented HTTPS and authentication configuration.

## Frontend development

Use Node.js 24 and npm. In a second terminal, from the repository root:

```powershell
cd frontend
npm ci
npm run dev
```

Open the localhost URL printed by Vite (normally <http://127.0.0.1:5173>). The development server proxies `/health` to the backend at `127.0.0.1:8787`; update `frontend/vite.config.ts` if you choose a different backend port. All fonts and application assets are bundled locally; no model provider is contacted.

From `frontend/`, run the frontend checks:

```powershell
npm test
npm run lint
npm run typecheck
npm run format:check
npm run build
```

The UI uses Tailwind CSS and shadcn/ui primitives. Chat supports explicit text memory capture, keyword search, streaming and optional OpenAI/Claude/Gemini recall; Settings manages private credentials and consent. The [Assets browser](docs/ASSETS.md) shows private inventory, sourced details and history. Memories provides capture/search/history, and Graph provides a bounded evidence-backed explorer.

The [text memory chat](docs/TEXT_CHAT.md) provides private persistent conversations, original-text saving, keyword recall, evidence inspection and saved-note history. Reviewed item/receipt extraction, private photo/PDF evidence, streaming, sourced profiles and per-user appearance settings are implemented. Broader life-management and research workflows remain separate roadmap increments.

## Planned stack

- React, TypeScript, Vite, Tailwind CSS, and shadcn/ui
- Python, FastAPI, Pydantic, SQLAlchemy, and Alembic
- PostgreSQL (with pgvector) and Model Context Protocol (MCP)
- Docker Compose for private, self-hosted deployment

## Privacy principles

- Preserve source evidence and historical corrections.
- Keep personal data private and require explicit configuration before sending it to external model providers.
- Validate and authorize domain operations through application services.

Private receipt/nameplate uploads, galleries and optional reviewed vision extraction are available; see [photo evidence and storage limits](docs/PHOTO_EVIDENCE.md).

The [persistent review queue](docs/REVIEW_QUEUE.md) collects pending proposals and uncertain physical-item matches without requiring AI calls.

[OpenAI, Claude and Google Gemini connections](docs/AI_PROVIDERS.md) now share evidence-backed chat, reviewed extraction, photos, permission and usage limits. Live provider access has not been verified.

[Private document evidence](docs/DOCUMENTS.md) supports PDF, DOCX, XLSX, text,
Markdown and CSV originals, bounded local previews and reviewed
text capture. Light/dark appearance, sourced home/vehicle profiles, streaming chat
and an evidence-backed graph are implemented in source; deployment is separate.

[Memories](docs/MEMORIES.md) provides private source browsing, literal search, correction history and direct note capture without an AI connection. The top-bar [search](docs/SEARCH.md) finds assets, records, photos, documents and sources together and opens each where it lives.
