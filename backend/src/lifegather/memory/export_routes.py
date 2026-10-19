"""Authenticated personal JSON download; never a database backup endpoint."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict

from lifegather.auth.routes import require_write_session
from lifegather.auth.store import CurrentSession
from lifegather.memory.archive import ArchiveError, PersonalArchive
from lifegather.memory.export import ExportLimitError, RecordExport


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def export_router() -> APIRouter:
    router = APIRouter(prefix="/api/export")

    @router.post("/records")
    def records(
        request: Request,
        body: ExportRequest,
        current: Annotated[CurrentSession, Depends(require_write_session)],
    ) -> Response:
        try:
            content = RecordExport(request.app.state.auth_store.engine).download(
                current.user
            )
        except ExportLimitError as error:
            raise HTTPException(413, str(error)) from None
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        filename = f"lifegather-records-{stamp}.json"
        return Response(
            content=content,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
                "Pragma": "no-cache",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @router.post("/archive")
    def archive(
        request: Request,
        body: ExportRequest,
        current: Annotated[CurrentSession, Depends(require_write_session)],
    ) -> Response:
        try:
            content = PersonalArchive(request.app.state.auth_store.engine).download(
                current.user
            )
        except ExportLimitError as error:
            raise HTTPException(413, str(error)) from None
        except ArchiveError as error:
            raise HTTPException(409, str(error)) from None
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        filename = f"lifegather-archive-{stamp}.zip"
        return Response(
            content=content,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
                "Pragma": "no-cache",
                "X-Content-Type-Options": "nosniff",
            },
        )

    return router
