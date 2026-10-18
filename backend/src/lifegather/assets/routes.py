from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Request

from lifegather.assets.actions import ActionService, AssetChange
from lifegather.assets.batch import (
    EvidenceBatchService,
    EvidenceMove,
    EvidenceMovePreview,
    EvidenceRestore,
)
from lifegather.assets.purchases import AssetPurchases, AssetPurchasesRead
from lifegather.assets.replacements import (
    ReplacementRecord,
    ReplacementService,
    ReplacementWithdraw,
)
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

    @router.get("/{asset_id}/purchases")
    def purchases(
        request: Request,
        asset_id: Annotated[str, Path(min_length=1, max_length=36)],
        current: Authenticated,
        cursor: Annotated[
            str, Query(max_length=38, pattern=r"^(?:[a-f0-9-]{36}:[0-7])?$")
        ] = "",
        limit: Annotated[int, Query(ge=1, le=5)] = 5,
    ) -> dict[str, Any]:
        return AssetPurchases(request.app.state.auth_store.engine).get(
            current.user,
            AssetPurchasesRead(asset_id=asset_id, cursor=cursor, limit=limit),
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

    @router.post("/evidence/preview")
    def preview_move(
        request: Request, body: EvidenceMovePreview, current: Authenticated
    ) -> dict[str, Any]:
        return EvidenceBatchService(request.app.state.auth_store.engine).preview(
            current.user, body
        )

    @router.post("/evidence/move")
    def move_evidence(
        request: Request,
        body: EvidenceMove,
        current: Annotated[CurrentSession, Depends(require_write_session)],
    ) -> dict[str, Any]:
        return EvidenceBatchService(request.app.state.auth_store.engine).move(
            current.user, body
        )

    @router.post("/evidence/restore")
    def restore_evidence(
        request: Request,
        body: EvidenceRestore,
        current: Annotated[CurrentSession, Depends(require_write_session)],
    ) -> dict[str, Any]:
        return EvidenceBatchService(request.app.state.auth_store.engine).restore(
            current.user, body
        )

    @router.post("/replacements/record")
    def record_replacement(
        request: Request,
        body: ReplacementRecord,
        current: Annotated[CurrentSession, Depends(require_write_session)],
    ) -> dict[str, Any]:
        return ReplacementService(request.app.state.auth_store.engine).change(
            current.user, body
        )

    @router.post("/replacements/withdraw")
    def withdraw_replacement(
        request: Request,
        body: ReplacementWithdraw,
        current: Annotated[CurrentSession, Depends(require_write_session)],
    ) -> dict[str, Any]:
        return ReplacementService(request.app.state.auth_store.engine).change(
            current.user, body
        )

    return router
