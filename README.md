# LifeGather

LifeGather is a private, self-hosted personal-memory application built around an evidence-backed knowledge graph and natural-language chat.

It aims to help organize possessions, events, documents, and relationships while preserving the original sources, tracking changes over time, and distinguishing facts from inferences and unknowns.

## Project status

Phase 0 provides a local health endpoint, environment-based configuration, a responsive React navigation shell, and Docker Compose packaging. Memory storage, authentication, MCP, and model integration are not implemented yet. LifeGather is a working name pending clearance.

## Run with Docker

For TrueNAS or an installation without a local source build, use the published image `ghcr.io/bgoldbeck/life-gather:latest`. See [TrueNAS installation and updates](docs/TRUENAS.md) and the [image-only Compose file](deploy/compose.image.yaml). GitHub Actions verifies changes and refreshes the image after successful builds on `main`.

Install Docker Engine with the Compose plugin on Linux, or Docker Desktop with the Linux engine on Windows/macOS. No host Python or Node.js installation is needed for this path.

From the repository root:

```powershell
docker compose up --build --detach --wait
docker compose ps
```

Open <http://127.0.0.1:8787> for the app or <http://127.0.0.1:8787/health> for `{"status":"ok"}`. The one service serves both the built frontend and backend. Node.js is used only during the image build.

To change the local port or application name, copy `.env.example` to `.env` at the repository root. Set `LIFEGATHER_PORT` to an available port, then recreate the service. The default host port is 8787; port 8000 is used only inside the container. The root `.env` configures Compose; `backend/.env` is for local Python development only and is not copied into the image.

Useful commands:

```powershell
docker compose logs --tail 100 backend
docker compose restart backend
docker compose down
```

`docker compose down` preserves the named `lifegather-data` volume mounted at `/data`. **Do not add `--volumes` unless you intend to erase local application data.** There is no database yet; this volume establishes the persistence convention for the next milestone. Private data is never served from the frontend asset directory.

The container runs as UID/GID 10001, with a read-only root filesystem, a writable `/data` volume, a temporary `/tmp`, and dropped Linux capabilities. Compose publishes the app only on `127.0.0.1`. Authentication is not implemented: keep this preview local and do not enter personal data.

Database migrations and a tested SQLite backup/restore workflow will be added when storage is implemented. This preview accepts no personal records.

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

`/health` reports process liveness only; it does not check database or model availability. The development server binds to localhost and has no authentication. Authentication is required before introducing personal-data endpoints or remote deployment.

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

The UI uses Tailwind CSS and shadcn/ui primitives. Navigation works within the preview; Chat, Assets, Memories, Graph, and Settings explain their planned purpose without accepting personal data.

The next milestone is **Google sign-in and per-user data isolation**, before accepting personal memories. See [the authentication requirements](docs/AUTH_REQUIREMENTS.md). The earlier single-user assumption is superseded by this requirement. Deterministic memory storage follows authentication.

## Planned stack

- React, TypeScript, Vite, Tailwind CSS, and shadcn/ui
- Python, FastAPI, Pydantic, SQLAlchemy, and Alembic
- SQLite and Model Context Protocol (MCP)
- Docker Compose for private, self-hosted deployment

## Privacy principles

- Preserve source evidence and historical corrections.
- Keep personal data private and require explicit configuration before sending it to external model providers.
- Validate and authorize domain operations through application services.
