"""Owner-named photo galleries, such as one event. Galleries prove no claims."""

from datetime import date
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from lifegather.auth.store import Account
from lifegather.memory.notes import NoteConflict
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.photos.models import Photo, PhotoGallery, PhotoGalleryPhoto

MAX_GALLERIES = 100
MAX_ADD = 50


class GalleryFields(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: str = Field(min_length=1, max_length=80)
    # Only a date the owner typed, as YYYY-MM-DD.
    event_on: str | None = Field(default=None, max_length=10)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value or any(ord(c) < 32 for c in value):
            raise ValueError("Give the gallery a name")
        return value

    @field_validator("event_on")
    @classmethod
    def clean_date(cls, value: str | None) -> str | None:
        if not value:
            return None
        try:
            if len(value) != 10:
                raise ValueError
            return date.fromisoformat(value).isoformat()
        except ValueError:
            raise ValueError("Use a YYYY-MM-DD event date") from None


class GalleryCreate(GalleryFields):
    pass


class GalleryRead(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    gallery_id: str = Field(min_length=1, max_length=36)


class GalleryUpdate(GalleryFields):
    gallery_id: str = Field(min_length=1, max_length=36)
    expected_updated_at: int = Field(ge=0)


class GalleryDelete(GalleryRead):
    expected_updated_at: int = Field(ge=0)


class GalleryAdd(GalleryRead):
    photo_ids: list[str] = Field(min_length=1, max_length=MAX_ADD)

    @field_validator("photo_ids")
    @classmethod
    def bounded_ids(cls, value: list[str]) -> list[str]:
        if any(not item or len(item) > 36 for item in value):
            raise ValueError("Invalid photo")
        if len(set(value)) != len(value):
            raise ValueError("Each photo can be listed only once")
        return value


class GalleryRemove(GalleryRead):
    photo_id: str = Field(min_length=1, max_length=36)


class GalleryList(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    photo_id: str = Field(default="", max_length=36)


def active_members(actor: Account) -> Any:
    """Gallery memberships of photos that are not deleted."""
    return (
        select(PhotoGalleryPhoto)
        .join(
            Photo,
            (Photo.user_id == PhotoGalleryPhoto.user_id)
            & (Photo.id == PhotoGalleryPhoto.photo_id),
        )
        .where(PhotoGalleryPhoto.user_id == actor.id, Photo.deleted_at.is_(None))
    )


class GalleryService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.memory = MemoryService(engine)

    @staticmethod
    def owned(db: Session, actor: Account, identifier: str) -> PhotoGallery:
        row = db.scalar(
            select(PhotoGallery).where(
                PhotoGallery.user_id == actor.id, PhotoGallery.id == identifier
            )
        )
        if row is None:
            raise MemoryError("Gallery not found")
        return row

    @staticmethod
    def view(db: Session, actor: Account, row: PhotoGallery) -> dict[str, Any]:
        members = active_members(actor).where(PhotoGalleryPhoto.gallery_id == row.id)
        count = db.scalar(select(func.count()).select_from(members.subquery()))
        cover = db.scalar(
            members.with_only_columns(PhotoGalleryPhoto.photo_id)
            .order_by(PhotoGalleryPhoto.added_at, PhotoGalleryPhoto.id)
            .limit(1)
        )
        return {
            "id": row.id,
            "title": row.title,
            "event_on": row.event_on,
            "photo_count": count or 0,
            "cover_photo_id": cover,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def list(self, actor: Account, value: GalleryList) -> dict[str, Any]:
        """Galleries newest event first; undated ones after, by name."""
        data = GalleryList.model_validate(value)
        with Session(self.engine) as db:
            query = select(PhotoGallery).where(PhotoGallery.user_id == actor.id)
            if data.photo_id:
                if not db.scalar(
                    select(Photo.id).where(
                        Photo.user_id == actor.id, Photo.id == data.photo_id
                    )
                ):
                    raise MemoryError("Photo not found")
                query = query.where(
                    PhotoGallery.id.in_(
                        select(PhotoGalleryPhoto.gallery_id).where(
                            PhotoGalleryPhoto.user_id == actor.id,
                            PhotoGalleryPhoto.photo_id == data.photo_id,
                        )
                    )
                )
            rows = db.scalars(
                query.order_by(
                    PhotoGallery.event_on.desc().nulls_last(),
                    func.lower(PhotoGallery.title),
                    PhotoGallery.id,
                ).limit(MAX_GALLERIES)
            )
            return {"items": [self.view(db, actor, row) for row in rows]}

    def get(self, actor: Account, identifier: str) -> dict[str, Any]:
        with Session(self.engine) as db:
            return self.view(db, actor, self.owned(db, actor, identifier))

    @staticmethod
    def _named(
        db: Session, actor: Account, title: str, other_than: str = ""
    ) -> PhotoGallery | None:
        return db.scalar(
            select(PhotoGallery).where(
                PhotoGallery.user_id == actor.id,
                func.lower(PhotoGallery.title) == title.lower(),
                PhotoGallery.id != other_than,
            )
        )

    def create(self, actor: Account, value: GalleryCreate) -> dict[str, Any]:
        data = GalleryCreate.model_validate(value)
        with self.memory._write() as db:
            existing = self._named(db, actor, data.title)
            if existing is not None:
                # Repeating the same request, such as after a lost response.
                if existing.event_on == data.event_on:
                    return self.view(db, actor, existing)
                raise NoteConflict(f'A gallery named "{existing.title}" exists')
            count = db.scalar(
                select(func.count(PhotoGallery.id)).where(
                    PhotoGallery.user_id == actor.id
                )
            )
            if (count or 0) >= MAX_GALLERIES:
                raise MemoryError(f"Gallery limit reached ({MAX_GALLERIES})")
            now = self.memory.clock()
            row = PhotoGallery(
                id=str(uuid4()),
                user_id=actor.id,
                title=data.title,
                event_on=data.event_on,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.flush()
            self.memory._audit(db, actor, "photo_gallery_created", row.id, now)
            return self.view(db, actor, row)

    def update(self, actor: Account, value: GalleryUpdate) -> dict[str, Any]:
        data = GalleryUpdate.model_validate(value)
        with self.memory._write() as db:
            row = self.owned(db, actor, data.gallery_id)
            if row.title == data.title and row.event_on == data.event_on:
                return self.view(db, actor, row)
            if row.updated_at != data.expected_updated_at:
                raise NoteConflict("Gallery changed. Reload before editing it.")
            if self._named(db, actor, data.title, row.id) is not None:
                raise NoteConflict(f'A gallery named "{data.title}" exists')
            row.title = data.title
            row.event_on = data.event_on
            row.updated_at = max(self.memory.clock(), row.updated_at + 1)
            self.memory._audit(
                db, actor, "photo_gallery_updated", row.id, row.updated_at
            )
            db.flush()
            return self.view(db, actor, row)

    def delete(self, actor: Account, value: GalleryDelete) -> dict[str, Any]:
        """Delete the gallery and its memberships; every photo stays."""
        data = GalleryDelete.model_validate(value)
        with self.memory._write() as db:
            row = db.scalar(
                select(PhotoGallery).where(
                    PhotoGallery.user_id == actor.id,
                    PhotoGallery.id == data.gallery_id,
                )
            )
            # An already deleted gallery is a safe replay.
            if row is None:
                return {"id": data.gallery_id, "deleted": True}
            if row.updated_at != data.expected_updated_at:
                raise NoteConflict("Gallery changed. Reload before deleting it.")
            for member in db.scalars(
                select(PhotoGalleryPhoto).where(
                    PhotoGalleryPhoto.user_id == actor.id,
                    PhotoGalleryPhoto.gallery_id == row.id,
                )
            ):
                db.delete(member)
            db.flush()
            db.delete(row)
            self.memory._audit(
                db, actor, "photo_gallery_deleted", row.id, self.memory.clock()
            )
            return {"id": row.id, "deleted": True}

    def add(self, actor: Account, value: GalleryAdd) -> dict[str, Any]:
        """Add saved photos; photos already in the gallery are skipped."""
        data = GalleryAdd.model_validate(value)
        with self.memory._write() as db:
            row = self.owned(db, actor, data.gallery_id)
            photos = {
                photo.id: photo
                for photo in db.scalars(
                    select(Photo).where(
                        Photo.user_id == actor.id, Photo.id.in_(data.photo_ids)
                    )
                )
            }
            if len(photos) != len(data.photo_ids):
                raise MemoryError("Photo not found")
            if any(photo.deleted_at is not None for photo in photos.values()):
                raise MemoryError("Photo was deleted")
            present = set(
                db.scalars(
                    select(PhotoGalleryPhoto.photo_id).where(
                        PhotoGalleryPhoto.user_id == actor.id,
                        PhotoGalleryPhoto.gallery_id == row.id,
                        PhotoGalleryPhoto.photo_id.in_(data.photo_ids),
                    )
                )
            )
            now = self.memory.clock()
            added = 0
            for photo_id in data.photo_ids:
                if photo_id in present:
                    continue
                db.add(
                    PhotoGalleryPhoto(
                        id=str(uuid4()),
                        user_id=actor.id,
                        gallery_id=row.id,
                        photo_id=photo_id,
                        # Keeps the chosen order among photos added together.
                        added_at=now + added,
                    )
                )
                self.memory._audit(
                    db, actor, "photo_gallery_added", f"{row.id}:{photo_id}", now
                )
                added += 1
            if added:
                row.updated_at = max(now, row.updated_at + 1)
            db.flush()
            return self.view(db, actor, row) | {"added_count": added}

    def remove(self, actor: Account, value: GalleryRemove) -> dict[str, Any]:
        """Remove one photo from the gallery; the photo itself stays."""
        data = GalleryRemove.model_validate(value)
        with self.memory._write() as db:
            row = self.owned(db, actor, data.gallery_id)
            member = db.scalar(
                select(PhotoGalleryPhoto).where(
                    PhotoGalleryPhoto.user_id == actor.id,
                    PhotoGalleryPhoto.gallery_id == row.id,
                    PhotoGalleryPhoto.photo_id == data.photo_id,
                )
            )
            # An already absent photo is a safe replay.
            if member is not None:
                db.delete(member)
                row.updated_at = max(self.memory.clock(), row.updated_at + 1)
                self.memory._audit(
                    db,
                    actor,
                    "photo_gallery_removed",
                    f"{row.id}:{data.photo_id}",
                    row.updated_at,
                )
                db.flush()
            return self.view(db, actor, row)
