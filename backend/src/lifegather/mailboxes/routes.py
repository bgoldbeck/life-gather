import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from lifegather.auth.routes import (
    SESSION_COOKIE,
    require_session,
    require_write_session,
    session_for,
)
from lifegather.auth.store import CurrentSession
from lifegather.credentials.service import VaultError
from lifegather.mailboxes.provider import GmailProvider, MailboxFailure
from lifegather.mailboxes.service import Mailboxes
from lifegather.memory.service import MemoryError

FLOW_COOKIE = "lifegather_mailbox"


class Empty(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Disconnect(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mailbox_id: str = Field(min_length=1, max_length=36)
    expected_revision: int = Field(ge=1)


Read = Annotated[CurrentSession, Depends(require_session)]
Write = Annotated[CurrentSession, Depends(require_write_session)]


def mailbox_router() -> APIRouter:
    router = APIRouter()

    def service(request: Request) -> Mailboxes:
        return Mailboxes(
            request.app.state.auth_store.engine, request.app.state.private_settings
        )

    @router.get("/api/mailboxes")
    def mailboxes(request: Request, current: Read) -> dict[str, Any]:
        return {
            "items": service(request).list(current.user),
            "oauth_configured": request.app.state.settings.google_enabled,
            "vault_configured": request.app.state.private_settings.enabled,
        }

    @router.post("/api/mailboxes/google/start")
    def start(request: Request, body: Empty, current: Write) -> JSONResponse:
        if not request.app.state.settings.google_enabled:
            raise HTTPException(503, "Configure Google OAuth before connecting Gmail")
        browser = secrets.token_urlsafe(32)
        state, verifier = service(request).begin(
            current.user, request.cookies.get(SESSION_COOKIE, ""), browser
        )
        provider: GmailProvider = request.app.state.gmail_provider
        response = JSONResponse({"url": provider.authorization_url(state, verifier)})
        response.set_cookie(
            FLOW_COOKIE,
            browser,
            max_age=600,
            httponly=True,
            secure=request.app.state.settings.secure_cookies,
            samesite="lax",
            path="/auth/gmail",
        )
        return response

    @router.get("/auth/gmail/callback")
    async def callback(request: Request) -> RedirectResponse:
        response = RedirectResponse("/?mailbox=failed", status_code=303)
        response.delete_cookie(
            FLOW_COOKIE,
            path="/auth/gmail",
            httponly=True,
            secure=request.app.state.settings.secure_cookies,
            samesite="lax",
        )
        try:
            current = session_for(request)
            state = request.query_params.get("state", "")
            code = request.query_params.get("code", "")
            if not state or len(state) > 100 or len(code) > 4096:
                return response
            verifier = service(request).consume(
                current.user,
                request.cookies.get(SESSION_COOKIE, ""),
                request.cookies.get(FLOW_COOKIE, ""),
                state,
            )
            if not code or request.query_params.get("error"):
                return response
            provider: GmailProvider = request.app.state.gmail_provider
            grant = await provider.exchange(code, verifier)
            # A session revoked during the network call cannot save credentials.
            latest = session_for(request)
            if latest.user.id != current.user.id:
                return response
            service(request).connect(latest.user, grant)
            response.headers["location"] = "/?mailbox=connected"
        except (HTTPException, MemoryError, VaultError, MailboxFailure):
            pass
        return response

    @router.post("/api/mailboxes/disconnect")
    def disconnect(
        request: Request, body: Disconnect, current: Write
    ) -> dict[str, Any]:
        return service(request).disconnect(
            current.user, body.mailbox_id, body.expected_revision
        )

    return router
