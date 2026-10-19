"""Bounded private image storage. Attachments never establish ownership."""

import hashlib
import warnings
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Literal
from uuid import uuid4

from PIL import Image, ImageOps
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from lifegather.auth.store import Account
from lifegather.memory.notes import NoteConflict, NoteService
from lifegather.memory.schemas import SourceInput
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.photos.models import Photo, PhotoAsset

MAX_BYTES = 8 * 1024 * 1024
MAX_PREVIEW = 2 * 1024 * 1024
Purpose = Literal["receipt", "nameplate", "photo"]


class PhotoList(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    asset_id: str = Field(default="", max_length=36)
    cursor: str = Field(default="", max_length=36)
    limit: int = Field(default=25, ge=1, le=25)


class PhotoRead(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    photo_id: str = Field(min_length=1, max_length=36)


class PhotoDetach(PhotoRead):
    asset_id: str = Field(min_length=1, max_length=36)
    expected_updated_at: int = Field(ge=0)


class PhotoAttach(PhotoDetach):
    pass


class PhotoDelete(PhotoRead):
    expected_updated_at: int = Field(ge=0)


@dataclass(frozen=True)
class Decoded:
    preview: bytes
    mime: str
    width: int
    height: int


def decode(raw: bytes) -> Decoded:
    if not raw or len(raw) > MAX_BYTES:
        raise MemoryError("Choose an image no larger than 8 MiB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw), formats=("JPEG", "PNG", "WEBP")) as image:
                width, height = image.size
                if (
                    getattr(image, "n_frames", 1) != 1
                    or max(width, height) > 10000
                    or width * height > 20000000
                ):
                    raise ValueError("Image dimensions or frame count exceed limits")
                mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}[
                    str(image.format)
                ]
                image.load()
                rotated = ImageOps.exif_transpose(image)
                rotated.thumbnail((2048, 2048))
                # A fresh canvas strips inherited EXIF/GPS, profiles and comments.
                clean = Image.new("RGB", rotated.size, "white")
                rgba = rotated.convert("RGBA")
                clean.paste(rgba, mask=rgba.getchannel("A"))
                result = BytesIO()
                clean.save(result, format="JPEG", quality=85)
                preview = result.getvalue()
                if len(preview) > MAX_PREVIEW:
                    raise ValueError("Preview too large")
                return Decoded(preview, mime, width, height)
    except Exception:
        raise MemoryError(
            "Choose a valid, single-frame JPEG, PNG or WebP under 20 megapixels"
        ) from None


class PhotoService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.memory = MemoryService(engine)

    @staticmethod
    def owned(db: Session, actor: Account, identifier: str) -> Photo:
        row = db.scalar(
            select(Photo).where(Photo.user_id == actor.id, Photo.id == identifier)
        )
        if row is None:
            raise MemoryError("Photo not found")
        return row

    @staticmethod
    def view(row: Photo) -> dict[str, Any]:
        return {
            name: getattr(row, name)
            for name in (
                "id",
                "filename",
                "mime",
                "purpose",
                "size",
                "width",
                "height",
                "created_at",
                "updated_at",
                "deleted_at",
                "source_id",
            )
        }

    def list(self, actor: Account, value: PhotoList) -> dict[str, Any]:
        data = PhotoList.model_validate(value)
        with Session(self.engine) as db:
            query = select(Photo).where(
                Photo.user_id == actor.id,
                Photo.deleted_at.is_(None),
                Photo.id > data.cursor,
            )
            if data.asset_id:
                self.memory._entity(db, actor, data.asset_id)
                query = query.join(PhotoAsset, PhotoAsset.photo_id == Photo.id).where(
                    PhotoAsset.user_id == actor.id, PhotoAsset.asset_id == data.asset_id
                )
            rows = list(db.scalars(query.order_by(Photo.id).limit(data.limit + 1)))
            return {
                "items": [self.view(r) for r in rows[: data.limit]],
                "next_cursor": rows[data.limit - 1].id
                if len(rows) > data.limit
                else None,
            }

    def get(self, actor: Account, identifier: str) -> dict[str, Any]:
        with Session(self.engine) as db:
            return self.view(self.owned(db, actor, identifier))

    def binary(
        self, actor: Account, identifier: str, original: bool = False
    ) -> tuple[bytes, str]:
        with Session(self.engine) as db:
            row = self.owned(db, actor, identifier)
            if row.deleted_at is not None:
                raise MemoryError("Photo was deleted")
            value = row.original if original else row.preview
            if value is None:
                raise MemoryError("Photo unavailable")
            return value, row.mime

    def attach(self, db: Session, actor: Account, row: Photo, asset_id: str) -> None:
        asset = self.memory._entity(db, actor, asset_id)
        if asset.kind != "asset":
            raise MemoryError("Choose a physical asset")
        if (
            db.scalar(
                select(PhotoAsset.id).where(
                    PhotoAsset.user_id == actor.id,
                    PhotoAsset.photo_id == row.id,
                    PhotoAsset.asset_id == asset_id,
                )
            )
            is None
        ):
            now = self.memory.clock()
            db.add(
                PhotoAsset(
                    id=str(uuid4()),
                    user_id=actor.id,
                    photo_id=row.id,
                    asset_id=asset_id,
                    recorded_at=now,
                )
            )
            row.updated_at = max(now, row.updated_at + 1)
            self.memory._audit(
                db, actor, "photo_attached", f"{row.id}:{asset.id}", row.updated_at
            )

    def upload(
        self,
        actor: Account,
        raw: bytes,
        filename: str,
        purpose: Purpose = "photo",
        asset_id: str = "",
    ) -> dict[str, Any]:
        if (
            purpose not in {"receipt", "nameplate", "photo"}
            or not filename
            or len(filename) > 200
            or any(ord(c) < 32 or c in "/\\" for c in filename)
        ):
            raise MemoryError("Invalid photo name or purpose")
        decoded = decode(raw)
        content_hash = hashlib.sha256(raw).hexdigest()
        with self.memory._write() as db:
            row = db.scalar(
                select(Photo).where(
                    Photo.user_id == actor.id,
                    Photo.content_hash == content_hash,
                    Photo.deleted_at.is_(None),
                )
            )
            if row is None:
                count, size = db.execute(
                    select(
                        func.count(Photo.id),
                        func.coalesce(func.sum(Photo.size + Photo.preview_size), 0),
                    ).where(Photo.user_id == actor.id, Photo.deleted_at.is_(None))
                ).one()
                if (
                    count >= 200
                    or size + len(raw) + len(decoded.preview) > 256 * 1024 * 1024
                ):
                    raise MemoryError(
                        "Photo storage limit reached (200 photos / 256 MiB)"
                    )
                now = self.memory.clock()
                row = Photo(
                    id=str(uuid4()),
                    user_id=actor.id,
                    content_hash=content_hash,
                    filename=filename,
                    purpose=purpose,
                    mime=decoded.mime,
                    size=len(raw),
                    width=decoded.width,
                    height=decoded.height,
                    preview_size=len(decoded.preview),
                    original=raw,
                    preview=decoded.preview,
                    source_id=None,
                    created_at=now,
                    updated_at=now,
                    deleted_at=None,
                )
                db.add(row)
                db.flush()
                self.memory._audit(db, actor, "photo_uploaded", row.id, now)
            if asset_id:
                self.attach(db, actor, row, asset_id)
            db.flush()
            return self.view(row)

    def detach(self, actor: Account, value: PhotoDetach) -> dict[str, Any]:
        data = PhotoDetach.model_validate(value)
        with self.memory._write() as db:
            row = self.owned(db, actor, data.photo_id)
            asset = self.memory._entity(db, actor, data.asset_id)
            if asset.kind != "asset":
                raise MemoryError("Choose a physical asset")
            link = db.scalar(
                select(PhotoAsset).where(
                    PhotoAsset.user_id == actor.id,
                    PhotoAsset.photo_id == row.id,
                    PhotoAsset.asset_id == asset.id,
                )
            )
            # An already absent link is a safe replay, even after a lost response.
            if link is None:
                return self.view(row)
            if row.updated_at != data.expected_updated_at:
                raise NoteConflict("Photo changed. Reload before removing its link.")
            db.delete(link)
            row.updated_at = max(self.memory.clock(), row.updated_at + 1)
            self.memory._audit(
                db, actor, "photo_detached", f"{row.id}:{asset.id}", row.updated_at
            )
            db.flush()
            return self.view(row)

    def link(self, actor: Account, value: PhotoAttach) -> dict[str, Any]:
        data = PhotoAttach.model_validate(value)
        with self.memory._write() as db:
            row = self.owned(db, actor, data.photo_id)
            asset = self.memory._entity(db, actor, data.asset_id)
            if asset.kind != "asset":
                raise MemoryError("Choose a physical asset")
            if row.deleted_at is not None:
                raise MemoryError("Photo was deleted")
            existing = db.scalar(
                select(PhotoAsset.id).where(
                    PhotoAsset.user_id == actor.id,
                    PhotoAsset.photo_id == row.id,
                    PhotoAsset.asset_id == asset.id,
                )
            )
            if existing is None:
                if row.updated_at != data.expected_updated_at:
                    raise NoteConflict("Photo changed. Reload before linking it.")
                self.attach(db, actor, row, asset.id)
                db.flush()
            return self.view(row)

    def delete(self, actor: Account, value: PhotoDelete) -> dict[str, Any]:
        data = PhotoDelete.model_validate(value)
        with self.memory._write() as db:
            row = self.owned(db, actor, data.photo_id)
            if row.deleted_at is None:
                if row.updated_at != data.expected_updated_at:
                    raise NoteConflict("Photo changed. Reload before deleting.")
                row.deleted_at = self.memory.clock()
                row.original = row.preview = None
                self.memory._audit(db, actor, "photo_deleted", row.id, row.deleted_at)
            return self.view(row)

    def source_photo(self, actor: Account, source_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as db:
            source = self.memory._source(db, actor, source_id)
            root = NoteService._root(db, actor, source)
            row = db.scalar(
                select(Photo).where(Photo.user_id == actor.id, Photo.source_id == root)
            )
            return self.view(row) if row else None

    def save_reading(
        self, actor: Account, identifier: str, value: dict[str, Any]
    ) -> dict[str, Any]:
        from lifegather.reconciliation.proposals import AssetExtraction, ProposalService

        with self.memory._write() as db:
            row = self.owned(db, actor, identifier)
            if row.deleted_at is not None:
                raise MemoryError("Photo was deleted")
            if not row.source_id:
                source = self.memory._ingest_in(
                    db,
                    actor,
                    SourceInput(
                        text=value["transcription"]
                        or "[No readable text was extracted from this photo.]",
                        source_type="conversation",
                        namespace="photo-memory",
                        external_id=row.id,
                    ),
                )
                row.source_id = source.id
                row.updated_at = max(self.memory.clock(), row.updated_at + 1)
                self.memory._audit(
                    db, actor, "photo_transcribed", row.id, row.updated_at
                )
                db.flush()
            return ProposalService(self.engine)._create_in(
                db,
                actor,
                row.source_id,
                AssetExtraction(
                    candidate=value["candidate"], explanation=value["explanation"]
                ),
            )

    def save_receipt_reading(
        self, actor: Account, identifier: str, value: dict[str, Any]
    ) -> dict[str, Any]:
        """Save one original transcription and its validated receipt atomically."""
        from lifegather.reconciliation.receipt_models import ReceiptProposal
        from lifegather.reconciliation.receipts import ReceiptExtraction, ReceiptService

        text = value["transcription"]
        if not isinstance(text, str) or len(text) > 4000:
            raise MemoryError("Photo transcription exceeds the reading limit")
        data = ReceiptExtraction.model_validate(
            {"items": value["items"], "explanation": value["explanation"]}
        )
        receipts = ReceiptService(self.engine)
        receipts.bounded(data.items)
        with self.memory._write() as db:
            row = self.owned(db, actor, identifier)
            if row.deleted_at is not None:
                raise MemoryError("Photo was deleted")
            if row.source_id:
                existing = db.scalar(
                    select(ReceiptProposal.id).where(
                        ReceiptProposal.user_id == actor.id,
                        ReceiptProposal.source_id == row.source_id,
                    )
                )
                if existing:
                    return receipts._create_in(db, actor, row.source_id, data)
                raise NoteConflict(
                    "Photo already has a transcription. "
                    "Reload it before receipt review."
                )
            source = self.memory._ingest_in(
                db,
                actor,
                SourceInput(
                    text=text or "[No readable text was extracted from this photo.]",
                    source_type="conversation",
                    namespace="photo-memory",
                    external_id=row.id,
                ),
            )
            row.source_id = source.id
            row.updated_at = max(self.memory.clock(), row.updated_at + 1)
            self.memory._audit(db, actor, "photo_transcribed", row.id, row.updated_at)
            db.flush()
            return receipts._create_in(db, actor, source.id, data)
