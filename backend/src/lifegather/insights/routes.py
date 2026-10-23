from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import ValidationError

from lifegather.auth.routes import require_session
from lifegather.auth.store import CurrentSession
from lifegather.insights.service import (
    DashboardRead,
    EventKind,
    InsightsService,
    TimelineRead,
)

Read = Annotated[CurrentSession, Depends(require_session)]
Zone = Annotated[str, Query(min_length=1, max_length=64)]


def insights_router() -> APIRouter:
    router = APIRouter(prefix="/api/insights")

    def service(request: Request) -> InsightsService:
        return InsightsService(request.app.state.auth_store.engine)

    @router.get("/dashboard")
    def dashboard(
        request: Request,
        current: Read,
        months: Annotated[int, Query(ge=6, le=24)] = 12,
        timezone: Zone = "UTC",
    ) -> dict[str, Any]:
        try:
            value = DashboardRead.model_validate(
                {"months": months, "timezone": timezone}
            )
        except ValidationError:
            raise HTTPException(
                422, "Choose 6, 12 or 24 months and a known time zone"
            ) from None
        return service(request).dashboard(current.user, value)

    @router.get("/timeline")
    def timeline(
        request: Request,
        current: Read,
        month: Annotated[str, Query(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")],
        kind: Annotated[list[EventKind] | None, Query(max_length=7)] = None,
        timezone: Zone = "UTC",
    ) -> dict[str, Any]:
        try:
            value = TimelineRead(
                month=month,
                timezone=timezone,
                **({"kinds": list(dict.fromkeys(kind))} if kind else {}),
            )
        except ValidationError:
            raise HTTPException(422, "Unknown time zone") from None
        return service(request).timeline(current.user, value)

    return router
