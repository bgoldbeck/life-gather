"""Private app-session gate around the SDK's stateless Streamable HTTP app."""

import json
import secrets
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from urllib.parse import urlsplit

import anyio
from fastapi import FastAPI
from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from lifegather.auth.routes import SESSION_COOKIE
from lifegather.auth.store import TERMS_PENDING, AuthStore
from lifegather.config import Settings
from lifegather.database import account_scope
from lifegather.mcp_api.schemas import INPUTS
from lifegather.mcp_api.tools import Access

MAX_BODY = 16384
MAX_WIRE = 98304
PRIVATE_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


class ReadLimiter:
    def __init__(
        self,
        limit: int = 120,
        capacity: int = 1024,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit, self.capacity, self.clock = limit, capacity, clock
        self.users: OrderedDict[str, deque[float]] = OrderedDict()

    def allow(self, user_id: str) -> bool:
        now = self.clock()
        while self.users:
            oldest, values = next(iter(self.users.items()))
            if values and values[-1] > now - 60:
                break
            self.users.pop(oldest)
        if user_id not in self.users:
            if len(self.users) >= self.capacity:
                return False
            self.users[user_id] = deque()
        values = self.users[user_id]
        self.users.move_to_end(user_id)
        while values and values[0] <= now - 60:
            values.popleft()
        if len(values) >= self.limit:
            return False
        values.append(now)
        return True


class PrivateMCP:
    def __init__(self, app: ASGIApp, parent: FastAPI, settings: Settings) -> None:
        self.app, self.parent, self.settings = app, parent, settings
        self.limiter = ReadLimiter()
        self.slots = anyio.Semaphore(8)

    @staticmethod
    async def error(
        scope: Scope, receive: Receive, send: Send, status: int, detail: str
    ) -> None:
        await JSONResponse(
            {"detail": detail}, status_code=status, headers=PRIVATE_HEADERS
        )(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive)
        critical = {b"host", b"origin", b"cookie", b"x-csrf-token"}
        names = [
            key.lower()
            for key, _ in scope.get("headers", [])
            if key.lower() in critical
        ]
        if (
            len(names) != len(set(names))
            or request.headers.get("host", "").lower()
            != urlsplit(self.settings.public_url).netloc.lower()
            or request.headers.get("origin") != self.settings.public_url
            or request.headers.get("sec-fetch-site") == "cross-site"
        ):
            await self.error(
                scope, receive, send, 403, "Open MCP from this LifeGather installation"
            )
            return
        if (
            request.headers.get("authorization") is not None
            or request.headers.get("mcp-session-id") is not None
        ):
            await self.error(
                scope, receive, send, 403, "Only the private app session is supported"
            )
            return
        if request.method != "POST":
            await self.error(
                scope, receive, send, 405, "Use an authenticated JSON POST"
            )
            return
        store: AuthStore = self.parent.state.auth_store
        token = request.cookies.get(SESSION_COOKIE, "")
        current = (
            store.authenticate(token, now=int(time.time()))
            if len(token) <= 128
            else None
        )
        if current is None:
            await self.error(scope, receive, send, 401, "Sign in required")
            return
        if current.terms_pending:
            await self.error(scope, receive, send, 403, TERMS_PENDING)
            return
        if not secrets.compare_digest(
            request.headers.get("x-csrf-token", ""), current.csrf_token
        ):
            await self.error(scope, receive, send, 403, "Invalid CSRF token")
            return
        if (
            request.headers.get("content-type", "").split(";", 1)[0].strip()
            != "application/json"
            or request.headers.get("content-encoding", "identity") != "identity"
        ):
            await self.error(
                scope, receive, send, 415, "Use an uncompressed JSON request"
            )
            return
        if not self.limiter.allow(current.user.id):
            await self.error(
                scope, receive, send, 429, "Too many MCP requests; try again shortly"
            )
            return
        try:
            self.slots.acquire_nowait()
        except anyio.WouldBlock:
            await self.error(scope, receive, send, 429, "MCP busy; try again shortly")
            return
        try:
            with account_scope(current.user.id):
                await self._request(
                    scope, receive, send, Access(store, token, current.user.id)
                )
        finally:
            self.slots.release()

    async def _request(
        self, scope: Scope, receive: Receive, send: Send, access: Access
    ) -> None:
        body = bytearray()
        try:
            with anyio.fail_after(10):
                while True:
                    chunk = await receive()
                    if chunk["type"] == "http.disconnect":
                        return
                    data = chunk.get("body", b"")
                    if len(body) + len(data) > MAX_BODY:
                        await self.error(
                            scope, receive, send, 413, "MCP request too large"
                        )
                        return
                    body.extend(data)
                    if not chunk.get("more_body", False):
                        break
        except TimeoutError:
            await self.error(scope, receive, send, 408, "MCP request body timed out")
            return
        try:
            envelope = json.loads(body)
            if (
                not isinstance(envelope, dict)
                or envelope.get("jsonrpc") != "2.0"
                or not isinstance(envelope.get("method"), str)
            ):
                raise ValueError
            request_id = envelope.get("id")
            if request_id is not None and (
                isinstance(request_id, bool)
                or not isinstance(request_id, str | int)
                or len(str(request_id)) > 64
            ):
                raise ValueError
            if envelope["method"] == "tools/call":
                params = envelope.get("params")
                if not isinstance(params, dict) or params.get("name") not in INPUTS:
                    raise ValueError
                arguments = params.get("arguments")
                if (
                    not isinstance(arguments, dict)
                    or set(arguments) != {"data"}
                    or not isinstance(arguments["data"], dict)
                ):
                    raise ValueError
                INPUTS[params["name"]].model_validate(arguments["data"])
        except (ValueError, TypeError, UnicodeError, RecursionError, ValidationError):
            await self.error(
                scope, receive, send, 400, "Invalid MCP request or tool arguments"
            )
            return
        scope.setdefault("state", {})["lifegather_mcp"] = access
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        start: Message | None = None
        response_body = bytearray()
        oversized = False

        async def collect(message: Message) -> None:
            nonlocal start, oversized
            if message["type"] == "http.response.start":
                start = dict(message)
                return
            if message["type"] == "http.response.body":
                value = message.get("body", b"")
                if len(response_body) + len(value) > MAX_WIRE:
                    oversized = True
                elif not oversized:
                    response_body.extend(value)

        await self.app(scope, replay, collect)
        if oversized or start is None:
            await JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": envelope.get("id"),
                    "error": {
                        "code": -32603,
                        "message": "Response too large; use a smaller page",
                    },
                },
                headers=PRIVATE_HEADERS,
            )(scope, receive, send)
            return
        headers = [
            (key, value)
            for key, value in start.get("headers", [])
            if key.lower()
            not in {b"cache-control", b"referrer-policy", b"content-length"}
        ]
        headers.extend(
            [
                (b"cache-control", b"no-store"),
                (b"referrer-policy", b"no-referrer"),
                (b"content-length", str(len(response_body)).encode()),
            ]
        )
        start["headers"] = headers
        await send(start)
        await send(
            {
                "type": "http.response.body",
                "body": bytes(response_body),
                "more_body": False,
            }
        )
