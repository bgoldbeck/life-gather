# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
COPY backend/src/lifegather/version.py /backend/src/lifegather/version.py
ARG APP_REVISION=""
RUN LIFEGATHER_BUILD_REVISION=$APP_REVISION npm run build

# Third-party dependencies get their own stage and image layer, which changes only
# when pyproject.toml or uv.lock does. App-only updates then upload a small layer.
FROM python:3.13-slim-bookworm AS backend-deps
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --extra s3

FROM backend-deps AS backend-build
COPY backend/src/ ./src/
RUN uv sync --locked --no-dev --no-editable --extra s3 \
    && mkdir /app-package \
    && cd .venv \
    && cp -a --parents lib/python3.13/site-packages/lifegather \
        lib/python3.13/site-packages/lifegather_backend-*.dist-info /app-package/

FROM python:3.13-slim-bookworm AS runtime
ARG APP_REVISION=""
ENV LIFEGATHER_BUILD_REVISION=$APP_REVISION
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
COPY --from=backend-deps /app/backend/.venv /app/backend/.venv
COPY --from=backend-build /app-package/ /app/backend/.venv/
COPY --from=frontend-build /frontend/dist /app/static
USER 10001:10001
EXPOSE 8787
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/health', timeout=2).close()"]
CMD ["uvicorn", "lifegather.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8787", "--no-proxy-headers", "--no-access-log"]
