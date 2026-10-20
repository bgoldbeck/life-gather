import asyncio
from typing import Annotated, Any, Literal
from urllib.parse import unquote

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
)
from starlette.concurrency import run_in_threadpool

from lifegather.auth.routes import require_session, require_write_session
from lifegather.auth.store import CurrentSession
from lifegather.documents.extractor import MAX_BYTES
from lifegather.documents.formats import MIMES, PreviewOptions
from lifegather.documents.service import (
    DocumentDelete,
    DocumentPage,
    DocumentPreview,
    DocumentService,
    DocumentText,
)

Read = Annotated[CurrentSession, Depends(require_session)]
Write = Annotated[CurrentSession, Depends(require_write_session)]
Identifier = Annotated[str, Path(min_length=1, max_length=36)]


def document_router() -> APIRouter:
    router = APIRouter(prefix="/api/documents")

    def service(request: Request) -> DocumentService:
        return DocumentService(request.app.state.auth_store.engine)

    @router.get("")
    def documents(
        request: Request,
        current: Read,
        cursor: Annotated[str, Query(max_length=36)] = "",
        limit: Annotated[int, Query(ge=1, le=25)] = 25,
    ) -> dict[str, Any]:
        return service(request).list(
            current.user, DocumentPage(cursor=cursor, limit=limit)
        )

    @router.post("", status_code=201)
    async def upload(
        request: Request,
        current: Write,
        filename: Annotated[str, Header(alias="X-File-Name", max_length=2400)],
        encoding: Literal["utf-8-sig", "utf-16", "cp1252"] = "utf-8-sig",
    ) -> dict[str, Any]:
        if request.headers.get("content-encoding", "identity") != "identity":
            raise HTTPException(415, "Compressed uploads are not accepted")
        slots: asyncio.Semaphore = request.app.state.document_slots
        if slots.locked():
            raise HTTPException(429, "Document parsing is busy; try again shortly")
        async with slots:
            try:
                async with asyncio.timeout(10):
                    raw = bytearray()
                    async for chunk in request.stream():
                        if len(raw) + len(chunk) > MAX_BYTES:
                            raise HTTPException(413, "Document exceeds 8 MiB")
                        raw.extend(chunk)
            except TimeoutError:
                raise HTTPException(408, "Upload timed out") from None

            def active() -> None:
                require_write_session(request, require_session(request))

            active()
            return await run_in_threadpool(
                service(request).upload,
                current.user,
                bytes(raw),
                unquote(filename),
                active,
                PreviewOptions(encoding=encoding),
            )

    @router.post("/preview")
    async def preview(
        request: Request, body: DocumentPreview, current: Write
    ) -> dict[str, Any]:
        slots: asyncio.Semaphore = request.app.state.document_slots
        if slots.locked():
            raise HTTPException(429, "Document parsing is busy; try again shortly")
        async with slots:
            result = await run_in_threadpool(
                service(request).preview, current.user, body
            )
            require_write_session(request, require_session(request))
            return result

    @router.post("/text")
    def save_text(
        request: Request, body: DocumentText, current: Write
    ) -> dict[str, Any]:
        return service(request).save_text(current.user, body)

    @router.post("/delete")
    def delete(
        request: Request, body: DocumentDelete, current: Write
    ) -> dict[str, Any]:
        return service(request).delete(current.user, body)

    @router.get("/{document_id}")
    def document(
        request: Request, document_id: Identifier, current: Read
    ) -> dict[str, Any]:
        return service(request).get(current.user, document_id)

    @router.get("/{document_id}/original")
    def original(request: Request, document_id: Identifier, current: Read) -> Response:
        metadata = service(request).get(current.user, document_id)
        extension = metadata["format"]
        if extension not in MIMES:
            raise HTTPException(400, "Unsupported original format")
        return Response(
            service(request).binary(current.user, document_id),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": (
                    'attachment; filename="document-'
                    + document_id
                    + "."
                    + extension
                    + '"'
                ),
                "X-Content-Type-Options": "nosniff",
            },
        )

    return router
