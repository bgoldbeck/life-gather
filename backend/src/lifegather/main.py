from fastapi import FastAPI

from lifegather.config import Settings


def create_app() -> FastAPI:
    settings = Settings()
    app = FastAPI(title=settings.app_name)

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Report process liveness; no storage or model provider is connected yet."""
        return {"status": "ok"}

    return app
