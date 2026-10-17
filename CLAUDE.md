# LifeGather — Claude Code Brief

Read `AGENTS.md` and `PROJECT_PLAN.md` before changing code. They contain the product goal, invariants, selected stack, boundaries, milestones and testing expectations. Do not silently override them.

- LifeGather is an AI-first personal-memory app: knowledge must be evidence-backed, temporally correct, deduplicated and user-correctable.
- Backend: Python/FastAPI/SQLite/SQLAlchemy/Alembic; official MCP Python SDK **v2** (`MCPServer`, Streamable HTTP).
- Frontend: React/TypeScript/Vite/Tailwind/shadcn/ui.
- Start with `docs/FIRST_TASK.md`; implement a small task, verify it, and report exact changes/tests.
- Never implement direct LLM access to SQL, unsafe remote MCP exposure, or unreviewed schema redesign.
- If source code and documents disagree, report the inconsistency and propose a minimal resolution.
