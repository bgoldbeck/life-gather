from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from lifegather.auth.routes import require_session, require_write_session
from lifegather.auth.store import CurrentSession
from lifegather.scans.service import ScanService


class ScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    handler_key: str = Field(min_length=1, max_length=50)
    config: dict[str, Any]
    request_id: str = Field(min_length=1, max_length=100)


class Empty(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


Read = Annotated[CurrentSession, Depends(require_session)]
Write = Annotated[CurrentSession, Depends(require_write_session)]


def scan_router() -> APIRouter:
    router = APIRouter(prefix="/api/scans")

    def service(request: Request) -> ScanService:
        result: ScanService = request.app.state.scan_service
        return result

    @router.get("/handlers")
    def handlers(request: Request, current: Read) -> dict[str, Any]:
        return {"items": service(request).registry.describe()}

    @router.get("")
    def runs(
        request: Request, current: Read, cursor: str = Query(default="", max_length=36)
    ) -> dict[str, Any]:
        return service(request).list(current.user, cursor)

    @router.post("")
    def start(request: Request, current: Write, body: ScanRequest) -> dict[str, Any]:
        return service(request).enqueue(
            current.user, body.handler_key, body.config, body.request_id
        )

    @router.get("/{identifier}")
    def get(
        request: Request,
        current: Read,
        identifier: str,
        after: int = Query(default=0, ge=0, le=50),
    ) -> dict[str, Any]:
        return service(request).get(current.user, identifier, after)

    @router.post("/{identifier}/cancel")
    def cancel(
        request: Request, current: Write, identifier: str, body: Empty
    ) -> dict[str, Any]:
        return service(request).cancel(current.user, identifier)

    return router
