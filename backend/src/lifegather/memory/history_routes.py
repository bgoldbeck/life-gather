from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request

from lifegather.auth.routes import require_session
from lifegather.auth.store import CurrentSession
from lifegather.memory.history import FieldHistory, FieldHistoryRead


def history_router() -> APIRouter:
    router = APIRouter(prefix="/api/history")

    @router.get("/fields")
    def fields(
        request: Request,
        current: Annotated[CurrentSession, Depends(require_session)],
        entity_id: Annotated[str, Query(min_length=1, max_length=36)],
        field: Annotated[
            str, Query(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
        ],
        cursor: Annotated[str, Query(max_length=36)] = "",
        limit: Annotated[int, Query(ge=1, le=10)] = 5,
    ) -> dict[str, Any]:
        return FieldHistory(request.app.state.auth_store.engine).get(
            current.user,
            FieldHistoryRead(
                entity_id=entity_id, field=field, cursor=cursor, limit=limit
            ),
        )

    return router
