# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim-bookworm AS backend-build
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/src/ ./src/
RUN uv sync --locked --no-dev --no-editable

FROM python:3.13-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/backend/.venv/bin:$PATH" \
    LIFEGATHER_DATA_DIR=/data \
    LIFEGATHER_STATIC_DIR=/app/static
RUN groupadd --gid 10001 lifegather \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin lifegather \
    && mkdir /data \
    && chown lifegather:lifegather /data
WORKDIR /app
COPY --from=backend-build /app/backend/.venv /app/backend/.venv
COPY --from=frontend-build /frontend/dist /app/static
USER 10001:10001
EXPOSE 8787
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/health', timeout=2).close()"]
CMD ["uvicorn", "lifegather.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8787", "--no-proxy-headers"]
