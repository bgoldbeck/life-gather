# LifeGather

LifeGather is a private, self-hosted personal-memory application built around an evidence-backed knowledge graph and natural-language chat.

It aims to help organize possessions, events, documents, and relationships while preserving the original sources, tracking changes over time, and distinguishing facts from inferences and unknowns.

## Project status

Phase 0 is underway. The backend has a local health endpoint and environment-based configuration. The frontend, storage, authentication, MCP, and model integration are not implemented yet. LifeGather is a working name pending clearance.

## Backend development

Prerequisites: [uv](https://docs.astral.sh/uv/getting-started/installation/) and Python 3.13. uv can install the Python version if it is missing.

Run these commands from the repository root:

```powershell
cd backend
uv sync --locked
uv run --locked uvicorn lifegather.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000/health> to see `{"status":"ok"}`. API documentation is available at <http://127.0.0.1:8000/docs>. Stop the server with Ctrl+C.

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

The next Phase 0 slice is the React frontend shell, followed by Docker packaging and persistent-data conventions.

## Planned stack

- React, TypeScript, Vite, Tailwind CSS, and shadcn/ui
- Python, FastAPI, Pydantic, SQLAlchemy, and Alembic
- SQLite and Model Context Protocol (MCP)
- Docker Compose for private, self-hosted deployment

## Privacy principles

- Preserve source evidence and historical corrections.
- Keep personal data private and require explicit configuration before sending it to external model providers.
- Validate and authorize domain operations through application services.
