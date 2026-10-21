"""Authenticated UI adapters for shared asset type operations."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Request

from lifegather.assets.type_schemas import TypeAssign, TypeFieldSave, TypeSave
from lifegather.assets.types import AssetTypes
from lifegather.auth.routes import require_session, require_write_session
from lifegather.auth.store import CurrentSession

Read = Annotated[CurrentSession, Depends(require_session)]
Write = Annotated[CurrentSession, Depends(require_write_session)]
Identifier = Annotated[str, Path(min_length=1, max_length=36)]


def asset_type_router() -> APIRouter:
    router = APIRouter(prefix="/api/asset-types")

    def service(request: Request) -> AssetTypes:
        return AssetTypes(request.app.state.auth_store.engine)

    @router.get("")
    def catalog(
        request: Request,
        current: Read,
        include_retired: bool = False,
        cursor: Annotated[str, Query(max_length=36)] = "",
    ) -> dict[str, Any]:
        return service(request).list(current.user, include_retired, cursor)

    @router.post("")
    def save(request: Request, body: TypeSave, current: Write) -> dict[str, Any]:
        return service(request).save(current.user, body)

    @router.post("/assign")
    def assign(request: Request, body: TypeAssign, current: Write) -> dict[str, Any]:
        return service(request).assign(current.user, body)

    @router.post("/fields")
    def field(request: Request, body: TypeFieldSave, current: Write) -> dict[str, Any]:
        return service(request).save_field(current.user, body)

    @router.get("/assets/{entity_id}")
    def asset(
        request: Request,
        entity_id: Identifier,
        current: Read,
        history: bool = False,
        cursor: Annotated[str, Query(max_length=36)] = "",
    ) -> dict[str, Any]:
        return service(request).record(current.user, entity_id, history, cursor)

    @router.get("/{type_id}/history")
    def history(
        request: Request,
        type_id: Identifier,
        current: Read,
        cursor: Annotated[str, Query(max_length=36)] = "",
    ) -> dict[str, Any]:
        return service(request).history(current.user, type_id, cursor)

    @router.get("/{type_id}")
    def get(request: Request, type_id: Identifier, current: Read) -> dict[str, Any]:
        return service(request).get(current.user, type_id)

    return router
