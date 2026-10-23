import secrets
import time
from collections import OrderedDict, deque
from dataclasses import asdict
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from lifegather.auth.email_models import EmailCredential
from lifegather.auth.google import GoogleFailure, GoogleProvider
from lifegather.auth.store import (
    FLOW_SECONDS,
    SESSION_SECONDS,
    AuthStore,
    CurrentSession,
    InvalidFlow,
)
from lifegather.config import Settings
from lifegather.credentials.service import PrivateSettings
from lifegather.database import bind_account
from lifegather.version import build_info

SESSION_COOKIE = "lifegather_session"
FLOW_COOKIE = "lifegather_login"


class TestLoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


def store_for(request: Request) -> AuthStore:
    store: AuthStore = request.app.state.auth_store
    return store


def session_for(request: Request) -> CurrentSession:
    """Authenticate the request and act for its account from here on."""
    token = request.cookies.get(SESSION_COOKIE, "")
    current = store_for(request).authenticate(token, now=int(time.time()))
    if current is None:
        raise HTTPException(status_code=401, detail="Sign in required")
    bind_account(current.user.id)
    return current


async def require_session(request: Request) -> CurrentSession:
    current = await run_in_threadpool(session_for, request)
    # Bound in the request's own context, so the endpoint and anything it runs
    # in the thread pool use the account's row-level security.
    bind_account(current.user.id)
    return current


def require_write_session(
    request: Request, current: Annotated[CurrentSession, Depends(require_session)]
) -> CurrentSession:
    settings: Settings = request.app.state.settings
    if request.headers.get(
        "origin"
    ) != settings.public_url or not secrets.compare_digest(
        request.headers.get("x-csrf-token", ""),
        current.csrf_token,
    ):
        raise HTTPException(403, "Invalid request origin or CSRF token")
    return current


def auth_router(settings: Settings, provider: GoogleProvider) -> APIRouter:
    router = APIRouter()
    attempts: OrderedDict[str, deque[float]] = OrderedDict()

    def limit_attempts(request: Request) -> None:
        # Connection IP; forwarded only from a trusted or signed proxy (see
        # lifegather.forwarding). Bound memory and sessions.
        host = request.client.host if request.client else "unknown"
        now = time.monotonic()
        if host not in attempts and len(attempts) >= 1024:
            oldest = next(iter(attempts))
            if attempts[oldest] and attempts[oldest][-1] > now - 60:
                raise HTTPException(429, "Sign-in busy; try again shortly")
            attempts.pop(oldest)
        recent = attempts.setdefault(host, deque())
        attempts.move_to_end(host)
        while recent and recent[0] <= now - 60:
            recent.popleft()
        if len(recent) >= 10:
            raise HTTPException(429, "Too many sign-in attempts; try again shortly")
        recent.append(now)

    def cookie(response: Response, name: str, value: str, age: int) -> None:
        response.set_cookie(
            name,
            value,
            max_age=age,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="lax",
            path="/",
        )

    @router.get("/auth/session")
    def session_status(request: Request) -> JSONResponse:
        current = store_for(request).authenticate(
            request.cookies.get(SESSION_COOKIE, ""), now=int(time.time())
        )
        with Session(store_for(request).engine) as db:
            has_password = (
                current is not None
                and db.get(EmailCredential, current.user.id) is not None
            )
        private: PrivateSettings = request.app.state.private_settings
        return JSONResponse(
            {
                "configured": settings.google_enabled,
                "build": build_info(settings.build_revision),
                "test_login_enabled": settings.test_login_enabled,
                "email_password_enabled": has_password,
                "email_delivery_enabled": request.app.state.email_auth.delivery_enabled,
                "user": asdict(current.user) if current else None,
                **({"appearance": private.theme(current.user)} if current else {}),
                "csrf_token": current.csrf_token if current else None,
            }
        )

    @router.post("/auth/test-login")
    def test_login(request: Request, data: TestLoginInput) -> Response:
        if not settings.test_login_enabled:
            raise HTTPException(404, "Not found")
        if (
            request.headers.get("origin") != settings.public_url
            or request.headers.get("host", "").lower()
            != urlsplit(settings.public_url).netloc.lower()
            or request.headers.get("sec-fetch-site") == "cross-site"
        ):
            raise HTTPException(403, "Open test login from LifeGather")
        if (
            request.headers.get("content-type", "").split(";", 1)[0].strip()
            != "application/json"
        ):
            raise HTTPException(415, "Use a JSON request")
        token = request.cookies.get(SESSION_COOKIE, "")
        if store_for(request).authenticate(token, now=int(time.time())) is not None:
            raise HTTPException(409, "Sign out before entering the test workspace")
        limit_attempts(request)
        signed = store_for(request).test_login(now=int(time.time()), old_token=token)
        response = Response(status_code=204)
        cookie(response, SESSION_COOKIE, signed.token, SESSION_SECONDS)
        return response

    @router.get("/auth/google/start")
    async def start(request: Request) -> Response:
        if not settings.google_enabled:
            raise HTTPException(503, "Google sign-in is not configured")
        # Reject cross-site requests rather than replacing a user's active flow.
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Open sign-in from LifeGather")
        limit_attempts(request)
        browser, state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(4))
        try:
            url = await provider.authorization_url(state, nonce, verifier)
        except GoogleFailure:
            return RedirectResponse("/?auth_error=unavailable", status_code=303)
        store_for(request).begin_flow(
            browser, state, nonce, verifier, now=int(time.time())
        )
        response = RedirectResponse(url, status_code=303)
        cookie(response, FLOW_COOKIE, browser, FLOW_SECONDS)
        return response

    @router.get("/auth/google/callback")
    async def callback(request: Request) -> Response:
        response = RedirectResponse("/?auth_error=signin_failed", status_code=303)
        response.delete_cookie(
            FLOW_COOKIE,
            path="/",
            secure=settings.secure_cookies,
            httponly=True,
            samesite="lax",
        )
        if not settings.google_enabled:
            return response
        try:
            flow = store_for(request).consume_flow(
                request.cookies.get(FLOW_COOKIE, ""),
                request.query_params.get("state", ""),
                now=int(time.time()),
            )
            code = request.query_params.get("code", "")
            if not code or request.query_params.get("error"):
                return response
            identity = await provider.exchange(code, flow.nonce, flow.verifier)
            signed_in = store_for(request).login(
                identity.sub,
                identity.email,
                identity.name,
                now=int(time.time()),
            )
        except (InvalidFlow, GoogleFailure):
            return response
        store_for(request).logout(request.cookies.get(SESSION_COOKIE, ""))
        response.headers["location"] = "/"
        cookie(response, SESSION_COOKIE, signed_in.token, SESSION_SECONDS)
        return response

    @router.post("/auth/logout")
    def logout(
        request: Request,
        current: Annotated[CurrentSession, Depends(require_write_session)],
    ) -> Response:
        store_for(request).logout(request.cookies.get(SESSION_COOKIE, ""))
        response = Response(status_code=204)
        response.delete_cookie(
            SESSION_COOKIE,
            path="/",
            secure=settings.secure_cookies,
            httponly=True,
            samesite="lax",
        )
        return response

    @router.get("/api/me")
    def me(
        current: Annotated[CurrentSession, Depends(require_session)],
    ) -> dict[str, str]:
        return asdict(current.user)

    return router
