"""Authenticated personal download and restore; never a database backup endpoint."""

import asyncio
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool

from lifegather.auth.routes import require_session, require_write_session
from lifegather.auth.store import CurrentSession
from lifegather.memory.archive import MAX_ARCHIVE_BYTES, ArchiveError, PersonalArchive
from lifegather.memory.export import ExportLimitError, RecordExport
from lifegather.memory.restore import (
    PersonalRestore,
    RestoreConflict,
    RestoreError,
    RestoreLimitError,
)
from lifegather.memory.service import MemoryError


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
            content = PersonalArchive(
                request.app.state.auth_store.engine,
                request.app.state.object_storage,
            ).download(current.user)
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


def restore_router() -> APIRouter:
    router = APIRouter(prefix="/api/import")

    @router.post("/archive")
    async def archive(
        request: Request,
        current: Annotated[CurrentSession, Depends(require_write_session)],
    ) -> dict[str, Any]:
        if request.headers.get("content-type", "") != "application/zip":
            raise HTTPException(415, "Upload the personal archive ZIP")
        if request.headers.get("content-encoding", "identity") != "identity":
            raise HTTPException(415, "Compressed uploads are not accepted")
        slots: asyncio.Semaphore = request.app.state.restore_slots
        if slots.locked():
            raise HTTPException(429, "Another restore is running; try again shortly")
        async with slots:
            try:
                async with asyncio.timeout(120):
                    raw = bytearray()
                    async for chunk in request.stream():
                        if len(raw) + len(chunk) > MAX_ARCHIVE_BYTES:
                            raise HTTPException(413, "Archive exceeds the 64 MiB limit")
                        raw.extend(chunk)
            except TimeoutError:
                raise HTTPException(408, "Upload timed out") from None
            # Check again after receiving bytes, before saving anything.
            require_write_session(request, require_session(request))
            service = PersonalRestore(
                request.app.state.auth_store.engine,
                request.app.state.object_storage,
            )
            try:
                return await run_in_threadpool(
                    service.restore, current.user, bytes(raw)
                )
            except RestoreLimitError as error:
                raise HTTPException(413, str(error)) from None
            except RestoreConflict as error:
                raise HTTPException(409, str(error)) from None
            except (RestoreError, MemoryError) as error:
                raise HTTPException(422, str(error)) from None

    return router
