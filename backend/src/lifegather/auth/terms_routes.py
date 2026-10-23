import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from lifegather.auth.routes import require_signed_in_write, store_for
from lifegather.auth.store import CurrentSession, InvalidFlow
from lifegather.config import Settings

PLACEHOLDER = Path(__file__).with_name("terms_placeholder.md")
MAX_TERMS_BYTES = 200_000


class AcceptInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(min_length=1, max_length=40)


def terms_text(settings: Settings) -> str:
    """The owner's terms file, or the bundled placeholder they should replace."""
    path = settings.terms_file or PLACEHOLDER
    data = path.read_bytes()[: MAX_TERMS_BYTES + 1]
    if len(data) > MAX_TERMS_BYTES:
        raise ValueError("The terms file is larger than 200 KB")
    return data.decode("utf-8")


def terms_router(settings: Settings) -> APIRouter:
    router = APIRouter()

    @router.get("/auth/terms")
    def read_terms() -> JSONResponse:
        if not settings.terms_version:
            raise HTTPException(404, "This installation has no terms of use")
        try:
            text = terms_text(settings)
        except (OSError, ValueError):
            raise HTTPException(503, "The terms of use are unavailable") from None
        return JSONResponse(
            {"version": settings.terms_version, "text": text},
            headers={"Cache-Control": "no-store"},
        )

    @router.post("/auth/terms/accept")
    def accept_terms(
        data: AcceptInput,
        request: Request,
        current: Annotated[CurrentSession, Depends(require_signed_in_write)],
    ) -> Response:
        if not settings.terms_version:
            raise HTTPException(404, "This installation has no terms of use")
        try:
            store_for(request).accept_terms(
                current.user.id, data.version, now=int(time.time())
            )
        except InvalidFlow as error:
            raise HTTPException(409, str(error)) from None
        return Response(status_code=204)

    return router
