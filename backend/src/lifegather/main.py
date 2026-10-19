import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from mcp.server.transport_security import TransportSecuritySettings
from starlette.routing import Route

from lifegather.assets.routes import asset_router
from lifegather.auth.email_routes import email_router
from lifegather.auth.email_service import EmailAuth
from lifegather.auth.email_validation import EmailAuthError
from lifegather.auth.google import GoogleProvider
from lifegather.auth.mail import MailSender, SmtpSender
from lifegather.auth.routes import auth_router
from lifegather.auth.store import AuthStore
from lifegather.chat.claude import ClaudeProvider
from lifegather.chat.google import GeminiProvider
from lifegather.chat.provider import OpenAIProvider
from lifegather.chat.routes import chat_router
from lifegather.config import Settings
from lifegather.credentials.middleware import CredentialBodyLimit
from lifegather.credentials.routes import private_router
from lifegather.credentials.service import PrivateSettings, VaultError, read_key
from lifegather.documents.routes import document_router
from lifegather.mailboxes.discovery import GmailDiscoveryHandler
from lifegather.mailboxes.provider import GmailProvider
from lifegather.mailboxes.routes import mailbox_router
from lifegather.mailboxes.scan import GmailImportHandler
from lifegather.mcp_api.tools import build_server
from lifegather.mcp_api.transport import PrivateMCP
from lifegather.memory.export_routes import export_router
from lifegather.memory.notes import NoteConflict
from lifegather.memory.routes import graph_router, library_router
from lifegather.memory.service import MemoryError
from lifegather.photos.routes import photo_router
from lifegather.profiles.routes import profile_router
from lifegather.purchases.routes import purchase_router
from lifegather.reconciliation.queue_routes import review_router
from lifegather.reconciliation.receipt_routes import receipt_router
from lifegather.scans.registry import ScanRegistry
from lifegather.scans.routes import scan_router
from lifegather.scans.schedule_routes import schedule_router
from lifegather.scans.schedules import ScheduleService
from lifegather.scans.service import ScanService
from lifegather.scans.worker import ScanWorker
from lifegather.version import __version__, build_info


def create_app(mail_sender: MailSender | None = None) -> FastAPI:
    settings = Settings()
    mcp_server = build_server()
    mcp_app = mcp_server.streamable_http_app(
        json_response=True,
        stateless_http=True,
        max_request_body_size=16384,
        transport_security=TransportSecuritySettings(
            allowed_hosts=[urlsplit(settings.public_url).netloc],
            allowed_origins=[settings.public_url],
        ),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        store = AuthStore(
            settings.data_dir / "auth.sqlite3",
            test_login_enabled=settings.test_login_enabled,
        )
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
            app.state.scan_service = ScanService(
                store.engine,
                ScanRegistry(
                    [
                        GmailImportHandler(
                            store.engine,
                            app.state.private_settings,
                            app.state.gmail_provider,
                        ),
                        GmailDiscoveryHandler(
                            store.engine,
                            app.state.private_settings,
                            app.state.gmail_provider,
                            {
                                "openai": app.state.chat_provider,
                                "anthropic": app.state.claude_provider,
                                "google": app.state.google_provider,
                            },
                        ),
                    ]
                ),
            )
            scheduler = ScheduleService(app.state.scan_service)
            worker = asyncio.create_task(
                ScanWorker(app.state.scan_service, scheduler.dispatch).serve()
            )
            try:
                async with mcp_server.session_manager.run():
                    yield
            finally:
                worker.cancel()
                with suppress(asyncio.CancelledError):
                    await worker
        finally:
            store.engine.dispose()

    app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.gmail_provider = GmailProvider(settings)
    app.state.chat_provider = OpenAIProvider()
    app.state.claude_provider = ClaudeProvider()
    app.state.google_provider = GeminiProvider()
    app.state.chat_slots = asyncio.Semaphore(4)
    app.state.photo_slots = asyncio.Semaphore(2)
    app.state.document_slots = asyncio.Semaphore(1)
    app.state.mcp_gate = PrivateMCP(mcp_app, app, settings)
    app.state.mcp_server = mcp_server
    app.router.routes.append(Route("/mcp", app.state.mcp_gate))
    app.include_router(auth_router(settings, GoogleProvider(settings)))
    app.include_router(private_router())
    app.include_router(email_router(settings))
    app.include_router(chat_router())
    app.include_router(asset_router())
    app.include_router(photo_router())
    app.include_router(review_router())
    app.include_router(receipt_router())
    app.include_router(graph_router())
    app.include_router(library_router())
    app.include_router(export_router())
    app.include_router(profile_router())
    app.include_router(document_router())
    app.include_router(mailbox_router())
    app.include_router(scan_router())
    app.include_router(schedule_router())
    app.include_router(purchase_router())
    app.add_middleware(CredentialBodyLimit)

    @app.exception_handler(MemoryError)
    async def memory_error(request: Request, error: MemoryError) -> JSONResponse:
        return JSONResponse(
            {"detail": str(error)},
            status_code=409 if isinstance(error, NoteConflict) else 400,
        )

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

    @app.get("/api/version")
    def version_info() -> dict[str, str | None]:
        return build_info(settings.build_revision)

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Report process liveness without exposing account or provider details."""
        return {"status": "ok"}

    if settings.static_dir is not None:
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="ui")

    return app
