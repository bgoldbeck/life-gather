from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles

from lifegather.auth.google import GoogleProvider
from lifegather.auth.routes import auth_router
from lifegather.auth.store import AuthStore
from lifegather.config import Settings


def create_app() -> FastAPI:
    settings = Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        store = AuthStore(settings.data_dir / "auth.sqlite3")
        store.migrate()
        app.state.auth_store = store
        try:
            yield
        finally:
            store.engine.dispose()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(auth_router(settings, GoogleProvider(settings)))

    @app.middleware("http")
    async def private_auth_responses(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        if request.url.path.startswith(("/auth/", "/api/")):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Report process liveness without exposing account or provider details."""
        return {"status": "ok"}

    if settings.static_dir is not None:
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="ui")

    return app
