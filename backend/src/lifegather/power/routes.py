"""Authenticated thin UI adapter; the same service is available through MCP."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from lifegather.auth.routes import require_session
from lifegather.auth.store import CurrentSession
from lifegather.power.service import PowerCenter, PowerSnapshot


def service_for(request: Request) -> PowerCenter:
    return PowerCenter(
        request.app.state.auth_store.engine,
        vault_enabled=request.app.state.private_settings.enabled,
        gmail_enabled=request.app.state.settings.google_enabled,
        handlers=set(request.app.state.scan_service.registry.handlers),
    )


def power_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/power", response_model=PowerSnapshot)
    def snapshot(
        request: Request,
        current: Annotated[CurrentSession, Depends(require_session)],
    ) -> PowerSnapshot:
        return service_for(request).read(current.user)

    return router
