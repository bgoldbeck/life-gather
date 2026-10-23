"""Operator-only HTTP adapter. Hosted deployments also gate /api/operator/."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from lifegather.auth.routes import require_session
from lifegather.auth.store import CurrentSession
from lifegather.operations.monitor import OperationsMonitor
from lifegather.operations.service import OperationsOverview, is_operator


def operations_router() -> APIRouter:
    router = APIRouter(prefix="/api/operator")

    @router.get("/access")
    def access(
        request: Request,
        current: Annotated[CurrentSession, Depends(require_session)],
    ) -> dict[str, bool]:
        return {"operator": is_operator(request.app.state.settings, current.user)}

    @router.get("/overview", response_model=OperationsOverview)
    async def overview(
        request: Request,
        current: Annotated[CurrentSession, Depends(require_session)],
    ) -> OperationsOverview:
        if not is_operator(request.app.state.settings, current.user):
            # The same answer as a missing route: other accounts learn nothing.
            raise HTTPException(404, "Not Found")
        monitor: OperationsMonitor = request.app.state.operations_monitor
        # Show errors captured moments ago, not only after the next flush.
        await run_in_threadpool(monitor.flush)
        return await run_in_threadpool(monitor.view().read)

    return router
