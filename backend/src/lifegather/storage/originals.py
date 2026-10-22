"""Original document/photo bytes in object storage, with legacy inline fallback."""

import hashlib
import logging
import secrets
from collections.abc import Iterable

from sqlalchemy import Engine, or_, select
from sqlalchemy.orm import Session

from lifegather.documents.models import Document
from lifegather.memory.service import MemoryService
from lifegather.photos.models import Photo
from lifegather.storage.base import ObjectStorage, StorageError, validate_key

logger = logging.getLogger(__name__)


def object_key(user_id: str, kind: str, identifier: str, part: str) -> str:
    return validate_key(f"users/{user_id}/{kind}/{identifier}/{part}")


def verified(data: bytes, size: int, digest: str | None = None) -> bytes:
    if len(data) != size or (
        digest is not None
        and not secrets.compare_digest(hashlib.sha256(data).hexdigest(), digest)
    ):
        raise StorageError("Stored file does not match its recorded hash")
    return data


def read_original(
    storage: ObjectStorage | None,
    key: str | None,
    inline: bytes | None,
    size: int,
    digest: str | None = None,
) -> bytes | None:
    """Stored bytes when a key is set, otherwise the legacy database copy."""
    if key is None:
        return inline
    if storage is None:
        raise StorageError("File storage is not configured")
    return verified(storage.get(key), size, digest)


def delete_quietly(storage: ObjectStorage | None, keys: Iterable[str | None]) -> bool:
    """Best effort after a committed delete; False leaves keys for a later retry."""
    if storage is None:
        return False
    complete = True
    for key in keys:
        if key is None:
            continue
        try:
            storage.delete(key)
        except StorageError:
            complete = False
    return complete


def _move_document(engine: Engine, storage: ObjectStorage, identifier: str) -> None:
    memory = MemoryService(engine)
    with Session(engine) as db:
        row = db.get(Document, identifier)
        if row is None or row.original_key is not None or row.original is None:
            return
        key = object_key(row.user_id, "documents", row.id, "original")
        storage.save(verified(row.original, row.size, row.content_hash), key)
    verified(storage.get(key), row.size, row.content_hash)
    with memory._write() as db:
        row = db.get(Document, identifier)
        if row is not None and row.original_key is None and row.original is not None:
            row.original_key, row.original = key, None


def _move_photo(engine: Engine, storage: ObjectStorage, identifier: str) -> None:
    memory = MemoryService(engine)
    with Session(engine) as db:
        row = db.get(Photo, identifier)
        if row is None:
            return
        moves: dict[str, str] = {}
        if row.original_key is None and row.original is not None:
            key = object_key(row.user_id, "photos", row.id, "original")
            storage.save(verified(row.original, row.size, row.content_hash), key)
            verified(storage.get(key), row.size, row.content_hash)
            moves["original"] = key
        if row.preview_key is None and row.preview is not None:
            key = object_key(row.user_id, "photos", row.id, "preview")
            storage.save(verified(row.preview, row.preview_size), key)
            verified(storage.get(key), row.preview_size)
            moves["preview"] = key
    if not moves:
        return
    with memory._write() as db:
        row = db.get(Photo, identifier)
        if row is None:
            return
        if "original" in moves and row.original_key is None:
            row.original_key, row.original = moves["original"], None
        if "preview" in moves and row.preview_key is None:
            row.preview_key, row.preview = moves["preview"], None


def _purge(engine: Engine, storage: ObjectStorage) -> None:
    """Retry object deletion for deleted rows whose earlier delete failed."""
    memory = MemoryService(engine)
    with Session(engine) as db:
        documents = list(
            db.scalars(
                select(Document.id).where(
                    Document.deleted_at.is_not(None), Document.original_key.is_not(None)
                )
            )
        )
        photos = list(
            db.scalars(
                select(Photo.id).where(
                    Photo.deleted_at.is_not(None),
                    or_(
                        Photo.original_key.is_not(None), Photo.preview_key.is_not(None)
                    ),
                )
            )
        )
    for identifier in documents:
        with memory._write() as db:
            document = db.get(Document, identifier)
            if document and delete_quietly(storage, [document.original_key]):
                document.original_key = None
    for identifier in photos:
        with memory._write() as db:
            photo = db.get(Photo, identifier)
            if photo and delete_quietly(
                storage, [photo.original_key, photo.preview_key]
            ):
                photo.original_key = photo.preview_key = None


def move_inline_originals(engine: Engine, storage: ObjectStorage) -> int:
    """Copy legacy database bytes to storage, verify, then clear the copy.

    Each row commits separately, so an interrupted run resumes where it stopped;
    deterministic keys make a repeated copy overwrite identical bytes.
    """
    moved = 0
    for model, mover in ((Document, _move_document), (Photo, _move_photo)):
        condition = or_(
            model.original.is_not(None),
            *([Photo.preview.is_not(None)] if model is Photo else []),
        )
        with Session(engine) as db:
            identifiers = list(
                db.scalars(select(model.id).where(condition).order_by(model.id))
            )
        for identifier in identifiers:
            try:
                mover(engine, storage, identifier)
            except StorageError:
                # The database copy stays and is still served; retried next start.
                logger.warning("Could not move a stored original; will retry")
                continue
            moved += 1
    _purge(engine, storage)
    return moved
