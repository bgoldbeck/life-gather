"""Per-account stored-file usage and the optional account-wide storage limit."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lifegather.documents.models import Document
from lifegather.photos.models import Photo

MIB = 1024 * 1024


def account_limit(storage: object) -> int:
    """The configured limit in bytes; 0 means no account-wide limit."""
    return int(getattr(storage, "account_quota_bytes", 0) or 0)


def account_usage(db: Session, user_id: str) -> dict[str, int]:
    """Bytes an account keeps in file storage, counted from its live rows.

    Deleting a photo or document removes its stored files, so deleted rows do
    not count. Legacy inline copies are moved to storage on startup and count
    the same way.
    """
    photos, photo_bytes = db.execute(
        select(
            func.count(Photo.id),
            func.coalesce(func.sum(Photo.size + Photo.preview_size), 0),
        ).where(Photo.user_id == user_id, Photo.deleted_at.is_(None))
    ).one()
    documents, document_bytes = db.execute(
        select(
            func.count(Document.id), func.coalesce(func.sum(Document.size), 0)
        ).where(Document.user_id == user_id, Document.deleted_at.is_(None))
    ).one()
    return {
        "photos": int(photos),
        "photo_bytes": int(photo_bytes),
        "documents": int(documents),
        "document_bytes": int(document_bytes),
        "used_bytes": int(photo_bytes) + int(document_bytes),
    }


def has_room(db: Session, user_id: str, storage: object, added: int) -> bool:
    """Whether adding bytes keeps the account within its limit.

    Call inside the serialized write that stores the file, so concurrent
    uploads for one account cannot both pass.
    """
    limit = account_limit(storage)
    if not limit or added <= 0:
        return True
    return account_usage(db, user_id)["used_bytes"] + added <= limit


def describe_limit(storage: object) -> str:
    limit = account_limit(storage)
    return f"{limit / MIB:g} MiB" if limit else "no limit"


def quota_message(storage: object) -> str:
    return (
        "Your account's file storage is full "
        f"({describe_limit(storage)}); delete photos or documents to make room"
    )


def usage_view(db: Session, user_id: str, storage: object) -> dict[str, Any]:
    usage = account_usage(db, user_id)
    limit = account_limit(storage)
    return {
        **usage,
        "limit_bytes": limit or None,
        "available_bytes": max(0, limit - usage["used_bytes"]) if limit else None,
    }
