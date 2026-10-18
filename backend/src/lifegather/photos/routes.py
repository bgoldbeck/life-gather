import asyncio
from typing import Annotated, Any
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
from lifegather.photos.service import (
    MAX_BYTES,
    PhotoDelete,
    PhotoDetach,
    PhotoList,
    PhotoService,
    Purpose,
)

Read = Annotated[CurrentSession, Depends(require_session)]
Write = Annotated[CurrentSession, Depends(require_write_session)]
Identifier = Annotated[str, Path(min_length=1, max_length=36)]


def photo_router() -> APIRouter:
    router = APIRouter(prefix="/api/photos")

    def service(request: Request) -> PhotoService:
        return PhotoService(request.app.state.auth_store.engine)

    @router.get("")
    def photos(
        request: Request,
        current: Read,
        asset_id: Annotated[str, Query(max_length=36)] = "",
        cursor: Annotated[str, Query(max_length=36)] = "",
        limit: Annotated[int, Query(ge=1, le=25)] = 25,
    ) -> dict[str, Any]:
        return service(request).list(
            current.user, PhotoList(asset_id=asset_id, cursor=cursor, limit=limit)
        )

    @router.post("", status_code=201)
    async def upload(
        request: Request,
        current: Write,
        filename: Annotated[str, Header(alias="X-File-Name", max_length=2400)],
        purpose: Purpose = "photo",
        asset_id: Annotated[str, Query(max_length=36)] = "",
    ) -> dict[str, Any]:
        if request.headers.get("content-encoding", "identity") != "identity":
            raise HTTPException(415, "Compressed uploads are not accepted")
        slots: asyncio.Semaphore = request.app.state.photo_slots
        if slots.locked():
            raise HTTPException(429, "Photo uploads are busy; try again shortly")
        async with slots:
            try:
                async with asyncio.timeout(10):
                    raw = bytearray()
                    async for chunk in request.stream():
                        if len(raw) + len(chunk) > MAX_BYTES:
                            raise HTTPException(413, "Photo exceeds 8 MiB")
                        raw.extend(chunk)
            except TimeoutError:
                raise HTTPException(408, "Upload timed out") from None
            # Check again after receiving bytes, before persisting anything.
            require_write_session(request, require_session(request))
            return await run_in_threadpool(
                service(request).upload,
                current.user,
                bytes(raw),
                unquote(filename),
                purpose,
                asset_id,
            )

    @router.get("/{photo_id}")
    def photo(request: Request, photo_id: Identifier, current: Read) -> dict[str, Any]:
        return service(request).get(current.user, photo_id)

    @router.get("/{photo_id}/preview")
    def preview(request: Request, photo_id: Identifier, current: Read) -> Response:
        raw, _ = service(request).binary(current.user, photo_id)
        return Response(
            raw, media_type="image/jpeg", headers={"X-Content-Type-Options": "nosniff"}
        )

    @router.get("/{photo_id}/original")
    def original(request: Request, photo_id: Identifier, current: Read) -> Response:
        raw, mime = service(request).binary(current.user, photo_id, True)
        extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[
            mime
        ]
        return Response(
            raw,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="photo-{photo_id}.{extension}"'
                ),
                "X-Content-Type-Options": "nosniff",
            },
        )

    @router.post("/detach")
    def detach(request: Request, body: PhotoDetach, current: Write) -> dict[str, Any]:
        return service(request).detach(current.user, body)

    @router.post("/delete")
    def delete(request: Request, body: PhotoDelete, current: Write) -> dict[str, Any]:
        return service(request).delete(current.user, body)

    return router
