# Phase 0 Docker checkpoint

Verified locally on 2026-10-16. This checkpoint establishes the application foundation; it does not implement memory storage or authentication.

## Delivered

- React/TypeScript/Vite workspace with Tailwind and shadcn/ui, local bundled fonts, responsive navigation and honest planned-feature states.
- FastAPI health endpoint, typed environment settings, static frontend serving and private-data directory creation.
- Configuration rejects a private-data directory inside the public static directory.
- Multi-stage Docker build with a Python-only production runtime and a non-root UID/GID of 10001.
- Compose service with localhost port 8787, health check, a named `/data` volume, read-only root filesystem, dropped capabilities and no-new-privileges.
- Build context excludes local environments, dependencies, personal data and environment files.

## Executed checks

- Backend: `uv run --locked pytest` — 8 tests passed; Ruff lint/format checks and strict mypy passed.
- Frontend: `npm test` — 2 interaction tests passed; lint, TypeScript checks, formatting and production build passed. `npm audit` reported zero vulnerabilities.
- Packaging: `uv build` produced a source distribution and wheel. `docker compose config --quiet` passed.
- Docker: `docker compose up --build --detach --wait` built the frontend and backend and reached healthy status.
- HTTP: the Docker-served homepage and `/health` both returned 200; health returned `{"status":"ok"}`.
- Browser: the Docker-served React page rendered; navigation worked; mobile viewport had no horizontal overflow. No browser console errors were observed on the Docker homepage.
- Runtime: verified UID 10001, absence of Node/npm, absence of local `.env` files, a read-only app root and a writable `/data` directory.
- Persistence: wrote a synthetic probe in `/data`, recreated the container, verified the probe remained, and removed the probe. No personal records were used.

## Local environment notes

- Existing applications occupy host ports 8000 and 8080. LifeGather uses 8787 for both the host and internal container port.
- Docker Desktop required launching through Windows Explorer after socket-access errors from the desktop-agent shell. Its previous runtime directory was preserved as `run.before-lifegather-20261016` under the local Docker directory. No Docker images or volumes were deleted.
- Original planning/instruction documents that were untracked before this work were left unchanged and unstaged.

## Next milestone and boundaries

Implement [Google sign-in and per-user data isolation](AUTH_REQUIREMENTS.md) before adding personal-memory operations. This user-selected milestone supersedes the original single-user assumption and comes before the deterministic memory graph.

There is no database yet, so no schema migration or database backup/restore workflow is included. Persistence evidence covers the data volume. Authentication, model connections, personal records, graph services and remote/public deployment remain outside this checkpoint.
