import secrets
import time
from collections import OrderedDict, deque
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from lifegather.auth.google import GoogleFailure, GoogleProvider
from lifegather.auth.store import (
    FLOW_SECONDS,
    SESSION_SECONDS,
    AuthStore,
    CurrentSession,
    InvalidFlow,
)
from lifegather.config import Settings

SESSION_COOKIE = "lifegather_session"
FLOW_COOKIE = "lifegather_login"


def store_for(request: Request) -> AuthStore:
    store: AuthStore = request.app.state.auth_store
    return store


def require_session(request: Request) -> CurrentSession:
    token = request.cookies.get(SESSION_COOKIE, "")
    current = store_for(request).authenticate(token, now=int(time.time()))
    if current is None:
        raise HTTPException(status_code=401, detail="Sign in required")
    return current


def auth_router(settings: Settings, provider: GoogleProvider) -> APIRouter:
    router = APIRouter()
    attempts: OrderedDict[str, deque[float]] = OrderedDict()

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
        return JSONResponse(
            {
                "configured": settings.google_enabled,
                "user": asdict(current.user) if current else None,
                "csrf_token": current.csrf_token if current else None,
            }
        )

    @router.get("/auth/google/start")
    async def start(request: Request) -> Response:
        if not settings.google_enabled:
            raise HTTPException(503, "Google sign-in is not configured")
        # Reject cross-site requests rather than replacing a user's active flow.
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Open sign-in from LifeGather")
        # Single-process limit. Use actual connection IP, never forwarded headers.
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
        request: Request, current: Annotated[CurrentSession, Depends(require_session)]
    ) -> Response:
        if request.headers.get(
            "origin"
        ) != settings.public_url or not secrets.compare_digest(
            request.headers.get("x-csrf-token", ""),
            current.csrf_token,
        ):
            raise HTTPException(403, "Invalid logout request")
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
