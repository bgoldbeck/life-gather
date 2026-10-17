# First Claude Code / Codex Assignment — Phase 0

Copy the prompt below into Claude Code or Codex after placing this starter pack at the root of a new git repository.

---

You are implementing **LifeGather**, a private, self-hosted, AI-first personal-memory application.

Read `PROJECT_PLAN.md` and `AGENTS.md` first (`CLAUDE.md` if present). Implement **Phase 0 only**. Do not start the memory graph database or connect a paid AI provider yet.

## Required deliverables

1. Create a `frontend/` React + TypeScript + Vite app, using Tailwind CSS and shadcn/ui per their current official installation instructions.
2. Create a `backend/` FastAPI app with a `/health` endpoint that returns an unambiguous healthy response and a lightweight configuration module using environment variables.
3. Create a simple, polished **LifeGather** landing/dashboard shell with sidebar navigation labels for Chat, Overview, Assets, Memories, Graph and Settings. Mark not-yet-implemented views honestly; no fake personal metrics.
4. Create a **multi-stage Dockerfile** that builds Vite static assets and serves them using the Python backend without requiring Node.js in the production runtime.
5. Create a `docker-compose.yml` with one backend service, private local port binding by default, a dedicated persistent `/data` volume, and a health check.
6. Provide `.env.example`, `.gitignore`, `README.md`, backend dependency file, lockfile(s) where supported, lint/format/typecheck/test scripts, and clear local/Docker development commands.
7. Add a backend health endpoint test and at least one frontend component smoke test.
8. Add basic security defaults: non-root Docker process, no hardcoded model keys, no public exposure by default, clear future auth requirement, and no mock user data presented as authentic.
9. The project should be ready for adding an authenticated MCP SDK v2 server in the next phases, but do not expose an unauthenticated personal-data MCP endpoint.

## Constraints

- Follow current **official** FastAPI, Vite, shadcn/ui and Docker practices; avoid out-of-date boilerplate.
- No Graphiti, Neo4j, vector database, bank integrations, email ingestion or financial schema in this phase.
- Avoid excessive abstractions; optimize for a small, understandable repository.
- No database migrations until Phase 1; create a persistent directory now to establish deployment conventions.
- Keep domain logic out of HTTP routers when it is implemented in later phases.
- Do not claim tests passed unless you executed them.

## Acceptance checks

- A newcomer can follow `README.md` to start local frontend and backend development.
- `docker compose up --build` runs without needing a separate frontend runtime.
- The LifeGather page loads and the health endpoint responds.
- Restarting the container leaves the `/data` directory intact.
- Tests, lint and TypeScript checks run using documented commands.
- No secrets are committed; the application is not publicly accessible by default.

When done, report the files you created/modified, commands/tests run with actual outcomes, deviations from the plan, and the single next recommended Phase 1 task. Stop there.
