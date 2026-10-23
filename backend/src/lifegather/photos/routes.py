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
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from lifegather.auth.routes import (
    require_session,
    require_write_session,
    session_for,
)
from lifegather.auth.store import CurrentSession
from lifegather.photos.galleries import (
    GalleryAdd,
    GalleryCreate,
    GalleryDelete,
    GalleryList,
    GalleryRemove,
    GalleryService,
    GalleryUpdate,
)
from lifegather.photos.service import (
    MAX_BYTES,
    PhotoAttach,
    PhotoDelete,
    PhotoDeleteMany,
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
        return PhotoService(
            request.app.state.auth_store.engine, request.app.state.object_storage
        )

    @router.get("")
    def photos(
        request: Request,
        current: Read,
        asset_id: Annotated[str, Query(max_length=36)] = "",
        gallery_id: Annotated[str, Query(max_length=36)] = "",
        cursor: Annotated[str, Query(max_length=36)] = "",
        limit: Annotated[int, Query(ge=1, le=25)] = 25,
    ) -> dict[str, Any]:
        return service(request).list(
            current.user,
            PhotoList(
                asset_id=asset_id, gallery_id=gallery_id, cursor=cursor, limit=limit
            ),
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
            require_write_session(request, session_for(request))
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

    @router.get("/{photo_id}/assets")
    def assets(request: Request, photo_id: Identifier, current: Read) -> dict[str, Any]:
        return {"items": service(request).assets(current.user, photo_id)}

    @router.get("/{photo_id}/galleries")
    def galleries(
        request: Request, photo_id: Identifier, current: Read
    ) -> dict[str, Any]:
        return GalleryService(request.app.state.auth_store.engine).list(
            current.user, GalleryList(photo_id=photo_id)
        )

    @router.get("/{photo_id}/email-sources")
    def email_sources(
        request: Request, photo_id: Identifier, current: Read
    ) -> dict[str, Any]:
        return {"items": service(request).email_sources(current.user, photo_id)}

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

    @router.post("/attach")
    def attach(request: Request, body: PhotoAttach, current: Write) -> dict[str, Any]:
        return service(request).link(current.user, body)

    @router.post("/detach")
    def detach(request: Request, body: PhotoDetach, current: Write) -> dict[str, Any]:
        return service(request).detach(current.user, body)

    @router.post("/delete")
    def delete(request: Request, body: PhotoDelete, current: Write) -> dict[str, Any]:
        return service(request).delete(current.user, body)

    @router.post("/delete-many")
    def delete_many(
        request: Request, body: PhotoDeleteMany, current: Write
    ) -> dict[str, Any]:
        return service(request).delete_many(current.user, body)

    return router


class GalleryEdit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: str = Field(min_length=1, max_length=80)
    event_on: str | None = Field(default=None, max_length=10)
    expected_updated_at: int = Field(ge=0)


class GalleryVersion(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_updated_at: int = Field(ge=0)


class GalleryPhotos(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    photo_ids: list[str] = Field(min_length=1, max_length=50)


class GalleryPhoto(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    photo_id: str = Field(min_length=1, max_length=36)


def gallery_router() -> APIRouter:
    router = APIRouter(prefix="/api/photo-galleries")

    def service(request: Request) -> GalleryService:
        return GalleryService(request.app.state.auth_store.engine)

    @router.get("")
    def galleries(request: Request, current: Read) -> dict[str, Any]:
        return service(request).list(current.user, GalleryList())

    @router.post("", status_code=201)
    def create(request: Request, body: GalleryCreate, current: Write) -> dict[str, Any]:
        return service(request).create(current.user, body)

    @router.get("/{gallery_id}")
    def gallery(
        request: Request, gallery_id: Identifier, current: Read
    ) -> dict[str, Any]:
        return service(request).get(current.user, gallery_id)

    @router.post("/{gallery_id}/update")
    def update(
        request: Request, gallery_id: Identifier, body: GalleryEdit, current: Write
    ) -> dict[str, Any]:
        return service(request).update(
            current.user,
            GalleryUpdate(gallery_id=gallery_id, **body.model_dump()),
        )

    @router.post("/{gallery_id}/delete")
    def delete(
        request: Request, gallery_id: Identifier, body: GalleryVersion, current: Write
    ) -> dict[str, Any]:
        return service(request).delete(
            current.user,
            GalleryDelete(
                gallery_id=gallery_id, expected_updated_at=body.expected_updated_at
            ),
        )

    @router.post("/{gallery_id}/photos")
    def add(
        request: Request, gallery_id: Identifier, body: GalleryPhotos, current: Write
    ) -> dict[str, Any]:
        return service(request).add(
            current.user, GalleryAdd(gallery_id=gallery_id, photo_ids=body.photo_ids)
        )

    @router.post("/{gallery_id}/photos/remove")
    def remove(
        request: Request, gallery_id: Identifier, body: GalleryPhoto, current: Write
    ) -> dict[str, Any]:
        return service(request).remove(
            current.user, GalleryRemove(gallery_id=gallery_id, photo_id=body.photo_id)
        )

    return router
