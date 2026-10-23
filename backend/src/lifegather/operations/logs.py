"""Structured JSON logs that leave out private content.

Only fixed messages and allowlisted fields reach a log line. Requests log their
route template, never the raw path or query string, and exceptions log their
type and code location, never their message (which may quote personal data).
Error-level LifeGather records are also captured as operational events.
"""

import json
import logging
import sys
import time
import traceback
import uuid
from collections import deque
from collections.abc import Awaitable, Callable, MutableMapping
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("lifegather.requests")

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
ASGIApp = Callable[
    [Scope, Callable[[], Awaitable[Message]], Callable[[Message], Awaitable[None]]],
    Awaitable[None],
]

# Extra fields a log call may attach. Anything else is dropped from the output.
SAFE_FIELDS = (
    "method",
    "route",
    "status",
    "duration_ms",
    "request_id",
    "handler",
    "job",
    "count",
    "error_type",
)
# Fields that tell one kind of problem from another; counts and IDs do not.
FINGERPRINT_FIELDS = ("route", "method", "handler", "job", "error_type")
LOGGED_PREFIXES = ("/api/", "/auth/", "/internal/", "/mcp")
CAPTURE_LIMIT = 500


def _error_type(record: logging.LogRecord) -> str | None:
    if record.exc_info and record.exc_info[0] is not None:
        return record.exc_info[0].__name__
    return None


def _location(record: logging.LogRecord) -> list[str]:
    """Code frames of the exception, without its message or local values."""
    if not record.exc_info or record.exc_info[2] is None:
        return []
    frames = traceback.extract_tb(record.exc_info[2])[-6:]
    return [
        f"{frame.name} ({frame.filename.rsplit('/', 1)[-1]}:{frame.lineno})"
        for frame in frames
    ]


def safe_fields(record: logging.LogRecord) -> dict[str, str | int]:
    fields: dict[str, str | int] = {}
    for name in SAFE_FIELDS:
        value = record.__dict__.get(name)
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            continue
        fields[name] = value if isinstance(value, int) else value[:200]
    error_type = _error_type(record)
    if error_type is not None:
        fields.setdefault("error_type", error_type)
    return fields


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname.lower(),
            "logger": record.name,
            # LifeGather messages are fixed text; library messages are kept,
            # but exception text below never is.
            "message": record.getMessage(),
            **safe_fields(record),
        }
        location = _location(record)
        if location:
            entry["location"] = location
        return json.dumps(entry, separators=(",", ":"), default=str)


class EventCapture(logging.Handler):
    """Collect error records in memory; the operations monitor stores them."""

    def __init__(self) -> None:
        super().__init__(logging.ERROR)
        self.pending: deque[dict[str, Any]] = deque(maxlen=CAPTURE_LIMIT)

    def emit(self, record: logging.LogRecord) -> None:
        fields = safe_fields(record)
        self.pending.append(
            {
                "level": "critical" if record.levelno >= logging.CRITICAL else "error",
                "logger": record.name,
                # The unformatted template: arguments never reach stored events.
                "message": str(record.msg)[:300],
                "details": {
                    name: fields[name] for name in FINGERPRINT_FIELDS if name in fields
                },
                "at": int(record.created),
            }
        )

    def drain(self) -> list[dict[str, Any]]:
        events = []
        while self.pending:
            events.append(self.pending.popleft())
        return events


CAPTURE = EventCapture()


def configure_logging(stream: Any = None) -> None:
    """Send LifeGather and uvicorn logs through the JSON formatter. Idempotent."""
    formatter = JsonFormatter()
    app = logging.getLogger("lifegather")
    app.setLevel(logging.INFO)
    app.propagate = False
    for handler in list(app.handlers):
        if getattr(handler, "lifegather_json", False):
            app.removeHandler(handler)
    output = logging.StreamHandler(stream or sys.stderr)
    output.setFormatter(formatter)
    output.lifegather_json = True  # type: ignore[attr-defined]
    app.addHandler(output)
    if CAPTURE not in app.handlers:
        app.addHandler(CAPTURE)
    # Uvicorn's default formatter prints exception messages; ours does not.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        for handler in logging.getLogger(name).handlers:
            handler.setFormatter(formatter)


class RequestLog:
    """Log each API request once, and turn unexpected errors into a fixed 500."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Callable[[], Awaitable[Message]],
        send: Callable[[Message], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid.uuid4().hex[:16]
        started = time.monotonic()
        status = 500
        response_started = False

        async def tagged(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                status = message["status"]
                response_started = True
                message.setdefault("headers", [])
                message["headers"] = [
                    *message["headers"],
                    (b"x-request-id", request_id.encode()),
                ]
            await send(message)

        try:
            await self.app(scope, receive, tagged)
        except Exception:
            fields = self._fields(scope, request_id, 500, started)
            logger.exception("Request failed unexpectedly", extra=fields)
            if response_started:
                raise
            body = json.dumps(
                {"detail": "Something went wrong", "request_id": request_id}
            ).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"cache-control", b"no-store"),
                        (b"x-request-id", request_id.encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        path = scope.get("path", "")
        if path.startswith(LOGGED_PREFIXES) or status >= 500:
            fields = self._fields(scope, request_id, status, started)
            level = logging.WARNING if status >= 500 else logging.INFO
            logger.log(level, "Request", extra=fields)

    @staticmethod
    def _fields(
        scope: Scope, request_id: str, status: int, started: float
    ) -> dict[str, str | int]:
        route = scope.get("route")
        template = getattr(route, "path", None)
        return {
            "method": str(scope.get("method", ""))[:10],
            # The matched template ("/api/assets/{asset_id}"); unmatched paths,
            # which could carry anything, are not named.
            "route": template
            if isinstance(template, str) and template
            else "unmatched",
            "status": status,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "request_id": request_id,
        }
