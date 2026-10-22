from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Query, Request

from lifegather.auth.routes import require_session, require_write_session
from lifegather.auth.store import CurrentSession
from lifegather.reconciliation.queue import (
    IdentityReview,
    IdentityUndo,
    ReviewPage,
    ReviewService,
)


def review_router() -> APIRouter:
    router = APIRouter(prefix="/api/reviews")

    def service(request: Request) -> ReviewService:
        return ReviewService(request.app.state.auth_store.engine)

    @router.get("")
    def reviews(
        request: Request,
        current: Annotated[CurrentSession, Depends(require_session)],
        kind: Literal["all", "proposals", "identities", "receipts"] = "all",
        cursor: Annotated[str, Query(max_length=38)] = "",
        limit: Annotated[int, Query(ge=1, le=25)] = 25,
    ) -> dict[str, Any]:
        return service(request).list(
            current.user, ReviewPage(kind=kind, cursor=cursor, limit=limit)
        )

    @router.get("/identities/{observation_id}")
    def detail(
        request: Request,
        observation_id: Annotated[str, Path(min_length=1, max_length=36)],
        current: Annotated[CurrentSession, Depends(require_session)],
    ) -> dict[str, Any]:
        return service(request).detail(current.user, observation_id)

    @router.post("/identities/review")
    def review(
        request: Request,
        body: IdentityReview,
        current: Annotated[CurrentSession, Depends(require_write_session)],
    ) -> dict[str, Any]:
        return service(request).review(current.user, body)

    @router.post("/identities/undo")
    def undo(
        request: Request,
        body: IdentityUndo,
        current: Annotated[CurrentSession, Depends(require_write_session)],
    ) -> dict[str, Any]:
        return service(request).undo(current.user, body)

    return router
