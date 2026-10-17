from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from lifegather.config import Settings


def create_app() -> FastAPI:
    settings = Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        yield

    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Report process liveness; no storage or model provider is connected yet."""
        return {"status": "ok"}

    if settings.static_dir is not None:
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="ui")

    return app
