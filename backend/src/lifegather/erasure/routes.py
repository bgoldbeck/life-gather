"""Thin private adapter: preview, then erase one source and what came from it."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from lifegather.auth.routes import require_write_session
from lifegather.auth.store import CurrentSession
from lifegather.erasure.service import (
    ErasureConfirm,
    ErasureError,
    ErasureTarget,
    SourceErasure,
)

Write = Annotated[CurrentSession, Depends(require_write_session)]


def erasure_router() -> APIRouter:
    router = APIRouter(prefix="/api/erasure")

    def service(request: Request) -> SourceErasure:
        return SourceErasure(
            request.app.state.auth_store.engine, request.app.state.object_storage
        )

    # POST so the preview, like the erase, needs the session's CSRF token.
    @router.post("/preview")
    def preview(
        request: Request, body: ErasureTarget, current: Write
    ) -> dict[str, Any]:
        try:
            return service(request).preview(current.user, body)
        except ErasureError as error:
            raise HTTPException(error.status, str(error)) from None

    @router.post("/erase")
    def erase(request: Request, body: ErasureConfirm, current: Write) -> dict[str, Any]:
        try:
            return service(request).erase(current.user, body)
        except ErasureError as error:
            raise HTTPException(error.status, str(error)) from None

    return router
