from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Request

from lifegather.auth.routes import require_session, require_write_session
from lifegather.auth.store import CurrentSession
from lifegather.findings.service import FindingRemove, FindingSave, FindingService
from lifegather.memory.service import MemoryService

Read = Annotated[CurrentSession, Depends(require_session)]
Write = Annotated[CurrentSession, Depends(require_write_session)]


def finding_router() -> APIRouter:
    router = APIRouter(prefix="/api/research-findings")

    def service(request: Request) -> FindingService:
        return FindingService(MemoryService(request.app.state.auth_store.engine))

    @router.post("", status_code=201)
    def save(request: Request, body: FindingSave, current: Write) -> dict[str, Any]:
        return service(request).save(current.user, body)

    @router.post("/remove")
    def remove(request: Request, body: FindingRemove, current: Write) -> dict[str, Any]:
        return service(request).remove(current.user, body)

    @router.get("/assets/{asset_id}")
    def for_asset(
        request: Request,
        asset_id: Annotated[str, Path(min_length=1, max_length=36)],
        current: Read,
    ) -> dict[str, Any]:
        return service(request).for_asset(current.user, asset_id)

    return router
