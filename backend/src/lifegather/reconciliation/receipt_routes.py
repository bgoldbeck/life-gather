from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Request

from lifegather.auth.routes import require_session, require_write_session
from lifegather.auth.store import CurrentSession
from lifegather.reconciliation.receipts import (
    ReceiptPreview,
    ReceiptReview,
    ReceiptService,
)


def receipt_router() -> APIRouter:
    router = APIRouter(prefix="/api/receipts")

    def service(request: Request) -> ReceiptService:
        return ReceiptService(request.app.state.auth_store.engine)

    @router.get("/{receipt_id}")
    def receipt(
        request: Request,
        receipt_id: Annotated[str, Path(min_length=1, max_length=36)],
        current: Annotated[CurrentSession, Depends(require_session)],
    ) -> dict[str, Any]:
        return service(request).get(current.user, receipt_id)

    @router.post("/preview")
    def preview(
        request: Request,
        body: ReceiptPreview,
        current: Annotated[CurrentSession, Depends(require_write_session)],
    ) -> dict[str, Any]:
        return service(request).preview(current.user, body)

    @router.post("/review")
    def review(
        request: Request,
        body: ReceiptReview,
        current: Annotated[CurrentSession, Depends(require_write_session)],
    ) -> dict[str, Any]:
        return service(request).review(current.user, body)

    return router
