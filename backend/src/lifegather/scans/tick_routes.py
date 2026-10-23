import hmac
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from lifegather.config import Settings
from lifegather.jobs import DEFAULT_TICK_SECONDS, MAX_TICK_SECONDS


def tick_router(settings: Settings) -> APIRouter:
    """Bearer-token tick for an outside scheduler; absent unless configured."""
    router = APIRouter(prefix="/internal/jobs")
    expected = f"Bearer {settings.job_tick_token.get_secret_value()}".encode()

    @router.post("/tick")
    async def tick(
        request: Request,
        authorization: Annotated[str, Header()] = "",
    ) -> dict[str, Any]:
        if not settings.tick_endpoint_enabled:
            raise HTTPException(404, "Not Found")
        if not hmac.compare_digest(authorization.encode(), expected):
            raise HTTPException(
                401, "Invalid tick token", headers={"WWW-Authenticate": "Bearer"}
            )
        # Checked after the token so callers without it learn nothing more.
        raw = request.query_params.get("seconds", str(DEFAULT_TICK_SECONDS))
        if (
            not (raw.isascii() and raw.isdigit())
            or not 1 <= int(raw) <= MAX_TICK_SECONDS
        ):
            raise HTTPException(422, f"seconds must be 1-{MAX_TICK_SECONDS}")
        seconds = int(raw)
        lock = request.app.state.tick_lock
        if lock.locked():
            raise HTTPException(409, "A tick is already running")
        async with lock:
            report = await request.app.state.scan_worker.tick(seconds)
            # With containers asleep between ticks, the tick is also when stuck
            # jobs are noticed and captured errors are stored and alerted.
            monitor = request.app.state.operations_monitor
            await run_in_threadpool(monitor.check_jobs)
            await run_in_threadpool(monitor.flush)
        return {"status": "ok", **asdict(report)}

    return router
