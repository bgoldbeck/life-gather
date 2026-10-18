from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from lifegather.auth.email_routes import email_router
from lifegather.auth.email_service import EmailAuth
from lifegather.auth.email_validation import EmailAuthError
from lifegather.auth.google import GoogleProvider
from lifegather.auth.mail import MailSender, SmtpSender
from lifegather.auth.routes import auth_router
from lifegather.auth.store import AuthStore
from lifegather.config import Settings
from lifegather.credentials.middleware import CredentialBodyLimit
from lifegather.credentials.routes import private_router
from lifegather.credentials.service import PrivateSettings, VaultError, read_key


def create_app(mail_sender: MailSender | None = None) -> FastAPI:
    settings = Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        store = AuthStore(settings.data_dir / "auth.sqlite3")
        store.migrate()
        app.state.auth_store = store
        sender = mail_sender
        if sender is None and settings.mail_enabled:
            sender = SmtpSender(
                settings.smtp_host,
                settings.smtp_port,
                settings.smtp_username,
                settings.smtp_password.get_secret_value(),
                settings.smtp_sender,
                settings.smtp_implicit_tls,
            )
        app.state.email_auth = EmailAuth(store, sender, settings.public_url)
        try:
            app.state.private_settings = PrivateSettings(
                store.engine, read_key(settings.vault_key_file)
            )
            yield
        finally:
            store.engine.dispose()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.settings = settings
    app.include_router(auth_router(settings, GoogleProvider(settings)))
    app.include_router(private_router())
    app.include_router(email_router(settings))
    app.add_middleware(CredentialBodyLimit)

    @app.exception_handler(EmailAuthError)
    async def email_auth_error(request: Request, error: EmailAuthError) -> JSONResponse:
        return JSONResponse({"detail": str(error)}, status_code=error.status)

    @app.exception_handler(VaultError)
    async def vault_error(request: Request, error: VaultError) -> JSONResponse:
        return JSONResponse({"detail": str(error)}, status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        # Validation errors may otherwise echo submitted credential values.
        return JSONResponse({"detail": "Invalid request"}, status_code=422)

    @app.middleware("http")
    async def private_auth_responses(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        if request.url.path.startswith(("/auth/", "/api/")):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Report process liveness without exposing account or provider details."""
        return {"status": "ok"}

    if settings.static_dir is not None:
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="ui")

    return app
