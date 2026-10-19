from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request

from lifegather.auth.routes import require_session, require_write_session
from lifegather.auth.store import CurrentSession
from lifegather.purchases.schemas import EvidenceSave, EvidenceWithdraw
from lifegather.purchases.service import PurchaseEvidenceService

Read = Annotated[CurrentSession, Depends(require_session)]
Write = Annotated[CurrentSession, Depends(require_write_session)]


def purchase_router() -> APIRouter:
    router = APIRouter(prefix="/api/purchases")

    def service(request: Request) -> PurchaseEvidenceService:
        return PurchaseEvidenceService(request.app.state.auth_store.engine)

    @router.get("")
    def purchases(
        request: Request,
        current: Read,
        cursor: str = Query(default="", max_length=36),
        limit: int = Query(default=10, ge=1, le=20),
    ) -> dict[str, Any]:
        return service(request).list(current.user, cursor, limit)

    @router.get("/sources/{identifier}")
    def source(request: Request, current: Read, identifier: str) -> dict[str, Any]:
        return service(request).source_context(current.user, identifier)

    @router.get("/sources/{identifier}/history")
    def history(
        request: Request,
        current: Read,
        identifier: str,
        before_revision: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        return service(request).history(current.user, identifier, before_revision)

    @router.post("/evidence")
    def save(request: Request, current: Write, body: EvidenceSave) -> dict[str, Any]:
        return service(request).save(current.user, body)

    @router.post("/withdraw")
    def withdraw(
        request: Request, current: Write, body: EvidenceWithdraw
    ) -> dict[str, Any]:
        return service(request).withdraw(current.user, body)

    @router.get("/{identifier}")
    def get(
        request: Request,
        current: Read,
        identifier: str,
        after: str = Query(default="", max_length=36),
        limit: int = Query(default=5, ge=1, le=10),
    ) -> dict[str, Any]:
        return service(request).get(current.user, identifier, after, limit)

    return router
