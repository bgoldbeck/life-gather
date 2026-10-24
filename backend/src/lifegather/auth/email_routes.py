import time
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from lifegather.auth.bot_check import BotCheck
from lifegather.auth.email_service import EmailAuth
from lifegather.auth.email_validation import EmailAuthError, email_key
from lifegather.auth.routes import SESSION_COOKIE, require_write_session, store_for
from lifegather.auth.store import SESSION_SECONDS, CurrentSession
from lifegather.config import Settings


class RequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    name: str = Field(default="", max_length=100)
    bot_token: str = Field(default="", max_length=2048)


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=128)


class CompletionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    purpose: Literal["signup", "reset", "link"]
    token: SecretStr = Field(min_length=20, max_length=100)
    password: SecretStr = Field(min_length=12, max_length=128)


def email_for(request: Request) -> EmailAuth:
    service: EmailAuth = request.app.state.email_auth
    return service


def client_id(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def require_origin(request: Request) -> None:
    settings: Settings = request.app.state.settings
    if (
        request.headers.get("origin") != settings.public_url
        or request.headers.get("sec-fetch-site") == "cross-site"
    ):
        raise HTTPException(403, "Open this form from LifeGather")
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip()
        != "application/json"
    ):
        raise HTTPException(415, "Use a JSON request")


def email_router(settings: Settings) -> APIRouter:
    router = APIRouter(dependencies=[Depends(require_origin)])

    @router.post("/auth/email/request/{action}")
    def request_email(
        action: Literal["signup", "reset"],
        data: RequestInput,
        request: Request,
        tasks: BackgroundTasks,
    ) -> JSONResponse:
        service = email_for(request)
        if not service.delivery_enabled:
            raise HTTPException(503, "Email delivery needs installation setup")
        bot_check: BotCheck | None = request.app.state.bot_check
        if bot_check is not None and not bot_check.verify(
            data.bot_token, client_id(request)
        ):
            raise HTTPException(400, "Complete the bot check and try again")
        key = email_key(data.email)
        if action == "signup" and (
            not data.name.strip() or any(ord(c) < 32 for c in data.name)
        ):
            raise HTTPException(422, "Enter a name between 1 and 100 characters")

        # Send after the response so existence/provider timing is not an oracle.
        def deliver() -> None:
            try:
                if action == "signup":
                    service.signup(
                        data.name, key, client=client_id(request), now=int(time.time())
                    )
                else:
                    service.request_reset(
                        key, client=client_id(request), now=int(time.time())
                    )
            except EmailAuthError:
                pass

        tasks.add_task(deliver)
        return JSONResponse(
            {
                "detail": "If this request can be completed, "
                "an email will arrive shortly. "
                "Check spam or try again later."
            },
            status_code=202,
        )

    @router.post("/auth/email/setup")
    def setup_password(
        request: Request,
        current: Annotated[CurrentSession, Depends(require_write_session)],
        tasks: BackgroundTasks,
    ) -> JSONResponse:
        service = email_for(request)
        if not service.delivery_enabled:
            raise HTTPException(503, "Email delivery needs installation setup")

        def deliver() -> None:
            try:
                service.request_setup(
                    current.user, client=client_id(request), now=int(time.time())
                )
            except EmailAuthError:
                pass

        tasks.add_task(deliver)
        return JSONResponse(
            {
                "detail": "If password setup is available, "
                "a verification link will arrive shortly."
            },
            status_code=202,
        )

    @router.post("/auth/email/login")
    def login(data: LoginInput, request: Request) -> Response:
        signed = email_for(request).login(
            data.email,
            data.password.get_secret_value(),
            client=client_id(request),
            now=int(time.time()),
            old_token=request.cookies.get(SESSION_COOKIE, ""),
        )
        response = Response(status_code=204)
        response.set_cookie(
            SESSION_COOKIE,
            signed.token,
            max_age=SESSION_SECONDS,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="lax",
            path="/",
        )
        return response

    @router.post("/auth/email/complete")
    def complete(data: CompletionInput, request: Request) -> Response:
        current = store_for(request).authenticate(
            request.cookies.get(SESSION_COOKIE, ""), now=int(time.time())
        )
        if data.purpose == "link":
            if current is None:
                raise HTTPException(
                    401, "Sign in to the account that requested password setup"
                )
            require_write_session(request, current)
        email_for(request).complete(
            data.purpose,
            data.token.get_secret_value(),
            data.password.get_secret_value(),
            client=client_id(request),
            now=int(time.time()),
            actor=current.user if current else None,
        )
        # Password reset/setup revokes all sessions, including this browser.
        response = Response(status_code=204)
        response.delete_cookie(
            SESSION_COOKIE,
            path="/",
            secure=settings.secure_cookies,
            httponly=True,
            samesite="lax",
        )
        return response

    return router
