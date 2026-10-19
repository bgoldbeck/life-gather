from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from lifegather.auth.routes import require_session, require_write_session
from lifegather.auth.store import CurrentSession
from lifegather.scans.schedules import ScheduleInput, ScheduleService


class ToggleSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_revision: int = Field(ge=1)
    enabled: bool


class EditSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_revision: int = Field(ge=1)
    data: ScheduleInput


Read = Annotated[CurrentSession, Depends(require_session)]
Write = Annotated[CurrentSession, Depends(require_write_session)]


def schedule_router() -> APIRouter:
    router = APIRouter(prefix="/api/scan-schedules")

    def service(request: Request) -> ScheduleService:
        return ScheduleService(request.app.state.scan_service)

    @router.get("")
    def schedules(request: Request, current: Read) -> dict[str, Any]:
        return service(request).list(current.user)

    @router.post("")
    def create(request: Request, current: Write, body: ScheduleInput) -> dict[str, Any]:
        return service(request).create(current.user, body)

    @router.post("/{identifier}/edit")
    def edit(
        request: Request, current: Write, identifier: str, body: EditSchedule
    ) -> dict[str, Any]:
        return service(request).edit(
            current.user, identifier, body.expected_revision, body.data
        )

    @router.post("/{identifier}/toggle")
    def toggle(
        request: Request, current: Write, identifier: str, body: ToggleSchedule
    ) -> dict[str, Any]:
        return service(request).toggle(
            current.user, identifier, body.expected_revision, body.enabled
        )

    return router
