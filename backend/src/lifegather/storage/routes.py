from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from lifegather.auth.routes import require_session
from lifegather.auth.store import CurrentSession
from lifegather.storage.quota import usage_view

Read = Annotated[CurrentSession, Depends(require_session)]


def storage_router() -> APIRouter:
    router = APIRouter(prefix="/api/storage")

    @router.get("/usage")
    def usage(request: Request, current: Read) -> dict[str, Any]:
        with Session(request.app.state.auth_store.engine) as db:
            return usage_view(
                db, current.user.id, getattr(request.app.state, "object_storage", None)
            )

    return router
