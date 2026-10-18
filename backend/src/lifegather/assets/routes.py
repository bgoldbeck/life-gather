from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Request

from lifegather.assets.actions import ActionService, AssetChange
from lifegather.assets.service import AssetList, AssetRead, AssetService
from lifegather.auth.routes import require_session, require_write_session
from lifegather.auth.store import CurrentSession

Authenticated = Annotated[CurrentSession, Depends(require_session)]
Cursor = Annotated[str, Query(max_length=36)]


def asset_router() -> APIRouter:
    router = APIRouter(prefix="/api/assets")

    @router.get("")
    def assets(
        request: Request,
        current: Authenticated,
        query: Annotated[str, Query(max_length=200)] = "",
        cursor: Cursor = "",
        include_history: bool = False,
        limit: Annotated[int, Query(ge=1, le=25)] = 25,
    ) -> dict[str, Any]:
        return AssetService(request.app.state.auth_store.engine).list(
            current.user,
            AssetList(
                query=query, cursor=cursor, include_history=include_history, limit=limit
            ),
        )

    @router.get("/{asset_id}")
    def asset(
        request: Request,
        asset_id: Annotated[str, Path(min_length=1, max_length=36)],
        current: Authenticated,
        fact_cursor: Cursor = "",
        decision_cursor: Cursor = "",
        action_cursor: Cursor = "",
        limit: Annotated[int, Query(ge=1, le=25)] = 25,
    ) -> dict[str, Any]:
        return AssetService(request.app.state.auth_store.engine).get(
            current.user,
            AssetRead(
                asset_id=asset_id,
                fact_cursor=fact_cursor,
                decision_cursor=decision_cursor,
                action_cursor=action_cursor,
                limit=limit,
            ),
        )

    @router.post("/actions")
    def change(
        request: Request,
        body: AssetChange,
        current: Annotated[CurrentSession, Depends(require_write_session)],
    ) -> dict[str, Any]:
        return ActionService(request.app.state.auth_store.engine).apply(
            current.user, body
        )

    return router
