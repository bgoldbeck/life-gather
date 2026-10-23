import asyncio
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy.exc import SQLAlchemyError
from starlette.routing import Route
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from lifegather.assets.routes import asset_router
from lifegather.assets.type_routes import asset_type_router
from lifegather.auth.account_routes import account_router
from lifegather.auth.bot_check import TurnstileCheck
from lifegather.auth.email_routes import email_router
from lifegather.auth.email_service import EmailAuth
from lifegather.auth.email_validation import EmailAuthError
from lifegather.auth.google import GoogleProvider
from lifegather.auth.mail import MailSender, smtp_sender
from lifegather.auth.routes import auth_router
from lifegather.auth.store import AuthStore
from lifegather.auth.terms_routes import terms_router
from lifegather.chat.claude import ClaudeProvider
from lifegather.chat.google import GeminiProvider
from lifegather.chat.provider import OpenAIProvider
from lifegather.chat.retention import retention_sweeps
from lifegather.chat.routes import chat_router
from lifegather.config import Settings
from lifegather.credentials.middleware import CredentialBodyLimit
from lifegather.credentials.routes import private_router
from lifegather.credentials.service import PrivateSettings, VaultError, read_keyring
from lifegather.documents.routes import document_router
from lifegather.findings.routes import finding_router
from lifegather.forwarding import SignedProxyHeaders
from lifegather.jobs import scan_service, scan_worker
from lifegather.mailboxes.provider import GmailProvider
from lifegather.mailboxes.routes import mailbox_router
from lifegather.maintenance.routes import maintenance_router
from lifegather.mcp_api.tools import build_server
from lifegather.mcp_api.transport import PrivateMCP
from lifegather.memory.export_routes import export_router, restore_router
from lifegather.memory.history_routes import history_router
from lifegather.memory.notes import NoteConflict
from lifegather.memory.origins import change_origin
from lifegather.memory.routes import graph_router, library_router
from lifegather.memory.service import MemoryError
from lifegather.operations.logs import RequestLog, configure_logging
from lifegather.operations.monitor import OperationsMonitor
from lifegather.operations.routes import operations_router
from lifegather.photos.routes import photo_router
from lifegather.power.routes import power_router
from lifegather.power.service import PowerCenter
from lifegather.profiles.routes import profile_router
from lifegather.purchases.routes import purchase_router
from lifegather.reconciliation.queue_routes import review_router
from lifegather.reconciliation.receipt_routes import receipt_router
from lifegather.scans.routes import scan_router
from lifegather.scans.schedule_routes import schedule_router
from lifegather.scans.tick_routes import tick_router
from lifegather.search.routes import search_router
from lifegather.startup import StartupError, run_startup_tasks, schema_current
from lifegather.storage.routes import storage_router
from lifegather.storage.settings import storage_from_settings
from lifegather.version import __version__, build_info


def create_app(mail_sender: MailSender | None = None) -> FastAPI:
    settings = Settings()
    configure_logging()
    mcp_server = build_server(
        lambda: PowerCenter(
            app.state.auth_store.engine,
            vault_enabled=app.state.private_settings.enabled,
            gmail_enabled=settings.google_enabled,
            handlers=set(app.state.scan_service.registry.handlers),
        )
    )
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
        keyring = read_keyring(settings)
        store = AuthStore(
            settings.database(),
            test_login_enabled=settings.test_login_enabled,
            terms_version=settings.terms_version,
        )
        app.state.object_storage = storage_from_settings(settings)
        if settings.migrate_on_start:
            run_startup_tasks(
                store, app.state.object_storage, settings.data_dir, keyring
            )
        elif not schema_current(store.engine):
            store.engine.dispose()
            raise StartupError(
                "The database needs upgrading: run python -m lifegather.migrate"
            )
        app.state.auth_store = store
        sender = mail_sender if mail_sender is not None else smtp_sender(settings)
        app.state.email_auth = EmailAuth(store, sender, settings.public_url)
        app.state.operations_monitor = OperationsMonitor(store.engine, settings, sender)
        try:
            app.state.private_settings = PrivateSettings(
                store.engine, keyring.active if keyring is not None else None
            )
            app.state.scan_service = scan_service(
                store.engine,
                app.state.private_settings,
                app.state.gmail_provider,
                app.state.object_storage,
                {
                    "openai": app.state.chat_provider,
                    "anthropic": app.state.claude_provider,
                    "google": app.state.google_provider,
                },
            )
            app.state.scan_worker = scan_worker(app.state.scan_service)
            app.state.tick_lock = asyncio.Lock()
            tasks = []
            if settings.background_mode == "inprocess":
                tasks.append(asyncio.create_task(app.state.scan_worker.serve()))
            tasks.append(asyncio.create_task(retention_sweeps(store.engine)))
            tasks.append(asyncio.create_task(app.state.operations_monitor.serve()))
            try:
                async with mcp_server.session_manager.run():
                    yield
            finally:
                # Keep errors captured just before shutdown.
                with suppress(SQLAlchemyError):
                    await asyncio.to_thread(app.state.operations_monitor.flush)
                for task in tasks:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
        finally:
            store.engine.dispose()

    app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.bot_check = (
        TurnstileCheck(settings.turnstile_secret_key.get_secret_value())
        if settings.bot_check_enabled
        else None
    )
    app.state.gmail_provider = GmailProvider(settings)
    app.state.chat_provider = OpenAIProvider()
    app.state.claude_provider = ClaudeProvider()
    app.state.google_provider = GeminiProvider()
    app.state.chat_slots = asyncio.Semaphore(4)
    app.state.photo_slots = asyncio.Semaphore(2)
    app.state.document_slots = asyncio.Semaphore(1)
    app.state.restore_slots = asyncio.Semaphore(1)
    app.state.mcp_gate = PrivateMCP(mcp_app, app, settings)
    app.state.mcp_server = mcp_server
    app.router.routes.append(Route("/mcp", app.state.mcp_gate))
    app.include_router(auth_router(settings, GoogleProvider(settings)))
    app.include_router(private_router())
    app.include_router(email_router(settings))
    app.include_router(account_router())
    app.include_router(terms_router(settings))
    app.include_router(chat_router())
    app.include_router(asset_router())
    app.include_router(asset_type_router())
    app.include_router(photo_router())
    app.include_router(finding_router())
    app.include_router(review_router())
    app.include_router(receipt_router())
    app.include_router(graph_router())
    app.include_router(library_router())
    app.include_router(export_router())
    app.include_router(restore_router())
    app.include_router(profile_router())
    app.include_router(maintenance_router())
    app.include_router(history_router())
    app.include_router(document_router())
    app.include_router(mailbox_router())
    app.include_router(scan_router())
    app.include_router(schedule_router())
    app.include_router(purchase_router())
    app.include_router(power_router())
    app.include_router(search_router())
    app.include_router(storage_router())
    app.include_router(tick_router(settings))
    app.include_router(operations_router())
    app.add_middleware(CredentialBodyLimit)
    app.add_middleware(RequestLog)
    if settings.trusted_proxy_list:
        # Outermost, so rate limits and logs see the forwarded client and scheme.
        # The image runs uvicorn with --no-proxy-headers; only listed peers count.
        app.add_middleware(
            ProxyHeadersMiddleware, trusted_hosts=settings.trusted_proxy_list
        )
    # Added last so it runs first and always removes the secret header.
    app.add_middleware(
        SignedProxyHeaders, secret=settings.proxy_secret.get_secret_value()
    )

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
        path = request.url.path
        method = "unspecified"
        if path.startswith("/api/profiles"):
            method = "manual_entry"
        elif path.endswith("/review") or path.startswith("/api/review"):
            method = "review"
        elif path.startswith("/api/assets/") or "/correction" in path:
            method = "correction"
        elif path.startswith(("/api/photos", "/api/documents")):
            method = "import"
        external = path.rstrip("/") == "/mcp"
        with change_origin(
            interface="mcp" if external else "web",
            initiator="external_client" if external else "account_request",
            method="unspecified" if external else method,
        ):
            response = await call_next(request)
        if request.url.path.startswith(("/auth/", "/api/", "/internal/")):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
        elif settings.static_dir is not None and path not in {
            "/mcp",
            "/health",
            "/health/ready",
        }:
            hashed_asset = re.fullmatch(
                r"/assets/[^/]+-[A-Za-z0-9_-]{8,}\."
                r"(?:js|css|woff2?|ttf|otf|png|jpe?g|gif|svg|webp|avif|ico)",
                path,
            )
            response.headers["Cache-Control"] = (
                "public, max-age=31536000, immutable"
                if hashed_asset
                and response.status_code in {200, 206, 304}
                and not response.headers.get("content-type", "").startswith("text/html")
                else "no-cache, must-revalidate"
            )
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/api/version")
    def version_info() -> dict[str, str | None]:
        return build_info(settings.build_revision)

    @app.post("/share-target", include_in_schema=False)
    def share_target_fallback() -> RedirectResponse:
        """Answer an Android share that the app's service worker did not receive.

        The worker normally keeps shared files in the browser until the signed-in
        page saves them. Without it, the body is never read or stored; the app
        opens and asks the person to share again.
        """
        return RedirectResponse("/?share=unavailable", status_code=303)

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Report process liveness without exposing account or provider details."""
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready() -> JSONResponse:
        """Ready when startup finished and the database answers at schema head."""
        store = getattr(app.state, "auth_store", None)
        try:
            ok = store is not None and schema_current(store.engine)
        except SQLAlchemyError:
            ok = False
        return JSONResponse(
            {"status": "ready" if ok else "not_ready"},
            status_code=200 if ok else 503,
            headers={"Cache-Control": "no-store"},
        )

    if settings.static_dir is not None:
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="ui")

    return app
