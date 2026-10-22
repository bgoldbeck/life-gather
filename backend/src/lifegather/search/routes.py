from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request

from lifegather.auth.routes import require_session
from lifegather.auth.store import CurrentSession
from lifegather.search.service import SearchQuery, SearchService


def search_router() -> APIRouter:
    router = APIRouter(prefix="/api/search")

    @router.get("")
    def search(
        request: Request,
        current: Annotated[CurrentSession, Depends(require_session)],
        q: Annotated[str, Query(min_length=1, max_length=200)],
        limit: Annotated[int, Query(ge=1, le=10)] = 6,
    ) -> dict[str, Any]:
        return SearchService(request.app.state.auth_store.engine).find(
            current.user, SearchQuery(q=q, limit=limit)
        )

    return router
