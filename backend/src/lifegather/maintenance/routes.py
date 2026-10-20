from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Query, Request

from lifegather.auth.routes import require_session, require_write_session
from lifegather.auth.store import CurrentSession
from lifegather.maintenance.schemas import (
    MaintenanceChange,
    MaintenanceCreate,
    MaintenanceHistory,
    MaintenancePage,
)
from lifegather.maintenance.service import MaintenanceService

Read = Annotated[CurrentSession, Depends(require_session)]
Write = Annotated[CurrentSession, Depends(require_write_session)]
Identifier = Annotated[str, Path(min_length=1, max_length=36)]


def maintenance_router() -> APIRouter:
    router = APIRouter(prefix="/api/maintenance")

    def service(request: Request) -> MaintenanceService:
        return MaintenanceService(request.app.state.auth_store.engine)

    @router.get("")
    def tasks(
        request: Request,
        current: Read,
        entity_id: Annotated[str | None, Query(min_length=1, max_length=36)] = None,
        state: Literal["open", "completed", "canceled", "all"] = "open",
        cursor: Annotated[str, Query(max_length=512)] = "",
        limit: Annotated[int, Query(ge=1, le=20)] = 10,
    ) -> dict[str, Any]:
        return service(request).list(
            current.user,
            MaintenancePage(
                entity_id=entity_id, state=state, cursor=cursor, limit=limit
            ),
        )

    @router.post("")
    def create(
        request: Request, current: Write, body: MaintenanceCreate
    ) -> dict[str, str]:
        return service(request).create(current.user, body)

    @router.post("/revise")
    def revise(
        request: Request, current: Write, body: MaintenanceChange
    ) -> dict[str, str]:
        return service(request).revise(current.user, body)

    @router.get("/{task_id}")
    def task(request: Request, current: Read, task_id: Identifier) -> dict[str, Any]:
        return service(request).get(current.user, task_id)

    @router.get("/{task_id}/history")
    def history(
        request: Request,
        current: Read,
        task_id: Identifier,
        cursor: Annotated[str, Query(max_length=36)] = "",
        limit: Annotated[int, Query(ge=1, le=10)] = 5,
    ) -> dict[str, Any]:
        return service(request).history(
            current.user,
            MaintenanceHistory(task_id=task_id, cursor=cursor, limit=limit),
        )

    return router
