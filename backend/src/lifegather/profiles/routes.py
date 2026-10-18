from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Request

from lifegather.auth.routes import require_session, require_write_session
from lifegather.auth.store import CurrentSession
from lifegather.memory.schemas import EntityView, FactView
from lifegather.profiles.service import ProfileChange, ProfileCreate, ProfileService


def profile_router() -> APIRouter:
    router = APIRouter(prefix="/api/profiles")

    @router.post("")
    def create(
        request: Request,
        body: ProfileCreate,
        current: Annotated[CurrentSession, Depends(require_write_session)],
    ) -> EntityView:
        return ProfileService(request.app.state.auth_store.engine).create(
            current.user, body
        )

    @router.post("/facts")
    def save(
        request: Request,
        body: ProfileChange,
        current: Annotated[CurrentSession, Depends(require_write_session)],
    ) -> FactView:
        return ProfileService(request.app.state.auth_store.engine).save(
            current.user, body
        )

    @router.get("/{entity_id}")
    def get(
        request: Request,
        current: Annotated[CurrentSession, Depends(require_session)],
        entity_id: Annotated[str, Path(min_length=1, max_length=36)],
        history: bool = False,
        cursor: Annotated[str | None, Query(max_length=36)] = None,
    ) -> dict[str, Any]:
        return ProfileService(request.app.state.auth_store.engine).get(
            current.user, entity_id, history=history, cursor=cursor
        )

    return router
