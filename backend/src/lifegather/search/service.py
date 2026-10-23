"""Owner-scoped search across records, sources, photos and documents.

Matching uses portable case-insensitive LIKE with escaped wildcards so the same
queries run on SQLite and PostgreSQL without a dialect-specific text index.
"""

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, and_, exists, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from lifegather.assets.identity import secondary_ids
from lifegather.auth.store import Account
from lifegather.documents.models import Document
from lifegather.memory.models import Entity, Episode, NoteRevision
from lifegather.memory.service import MemoryError, deleted_source
from lifegather.photos.models import Photo

MAX_WORDS = 8


class SearchQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=6, ge=1, le=10)


def words(query: str) -> list[str]:
    found = [word.casefold() for word in query.split() if word.strip()]
    if not found or len(found) > MAX_WORDS:
        raise MemoryError(f"Search requires 1 to {MAX_WORDS} words")
    return found


def all_words(column: Any, terms: list[str]) -> ColumnElement[bool]:
    return and_(*(column.icontains(term, autoescape=True) for term in terms))


def snippet(text: str, terms: list[str], width: int = 160) -> str:
    flat = re.sub(r"\s+", " ", text).strip()
    lowered = flat.casefold()
    start = min(
        (index for term in terms if (index := lowered.find(term)) >= 0), default=0
    )
    start = max(0, start - width // 4)
    piece = flat[start : start + width]
    return ("…" if start else "") + piece + ("…" if start + width < len(flat) else "")


class SearchService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def find(self, actor: Account, value: SearchQuery) -> dict[str, Any]:
        data = SearchQuery.model_validate(value)
        terms = words(data.q)
        with Session(self.engine) as db:
            items = [
                *self._records(db, actor, terms, data.limit),
                *self._photos(db, actor, terms, data.limit),
                *self._documents(db, actor, terms, data.limit),
                *self._sources(db, actor, terms, data.limit),
            ]
        return {"query": data.q, "items": items}

    @staticmethod
    def _records(
        db: Session, actor: Account, terms: list[str], limit: int
    ) -> list[dict[str, Any]]:
        rows = db.scalars(
            select(Entity)
            .where(
                Entity.user_id == actor.id,
                Entity.id.not_in(secondary_ids(actor)),
                all_words(Entity.name, terms),
            )
            .order_by(Entity.name, Entity.id)
            .limit(limit)
        )
        return [
            {
                "kind": "asset" if row.kind == "asset" else "record",
                "id": row.id,
                "title": row.name,
                "detail": row.kind,
            }
            for row in rows
        ]

    @staticmethod
    def _photos(
        db: Session, actor: Account, terms: list[str], limit: int
    ) -> list[dict[str, Any]]:
        rows = db.scalars(
            select(Photo)
            .where(
                Photo.user_id == actor.id,
                Photo.deleted_at.is_(None),
                all_words(Photo.filename, terms),
            )
            .order_by(Photo.created_at.desc(), Photo.id)
            .limit(limit)
        )
        return [
            {
                "kind": "photo",
                "id": row.id,
                "title": row.filename,
                "detail": row.purpose,
            }
            for row in rows
        ]

    @staticmethod
    def _documents(
        db: Session, actor: Account, terms: list[str], limit: int
    ) -> list[dict[str, Any]]:
        rows = db.execute(
            select(Document.id, Document.filename, Document.extracted_text)
            .where(
                Document.user_id == actor.id,
                Document.deleted_at.is_(None),
                and_(
                    *(
                        Document.filename.icontains(term, autoescape=True)
                        | Document.extracted_text.icontains(term, autoescape=True)
                        for term in terms
                    )
                ),
            )
            .order_by(Document.created_at.desc(), Document.id)
            .limit(limit)
        )
        return [
            {
                "kind": "document",
                "id": identifier,
                "title": filename,
                "detail": snippet(text, terms),
            }
            for identifier, filename, text in rows
        ]

    @staticmethod
    def _sources(
        db: Session, actor: Account, terms: list[str], limit: int
    ) -> list[dict[str, Any]]:
        superseded = exists(
            select(NoteRevision.id).where(
                NoteRevision.user_id == actor.id,
                NoteRevision.previous_source_id == Episode.id,
            )
        )
        rows = list(
            db.execute(
                select(Episode.id, Episode.text)
                .where(
                    Episode.user_id == actor.id,
                    ~deleted_source(actor.id, Episode.id),
                    ~superseded,
                    all_words(Episode.text, terms),
                )
                .order_by(Episode.recorded_at.desc(), Episode.id)
                .limit(limit)
            )
        )
        identifiers = [identifier for identifier, _ in rows]
        photos = {
            source_id: identifier
            for source_id, identifier in db.execute(
                select(Photo.source_id, Photo.id).where(
                    Photo.user_id == actor.id,
                    Photo.deleted_at.is_(None),
                    Photo.source_id.in_(identifiers),
                )
            )
        }
        documents = {
            source_id: identifier
            for source_id, identifier in db.execute(
                select(Document.source_id, Document.id).where(
                    Document.user_id == actor.id,
                    Document.deleted_at.is_(None),
                    Document.source_id.in_(identifiers),
                )
            )
        }
        return [
            {
                "kind": "source",
                "id": identifier,
                "title": snippet(text, terms, 80),
                "detail": snippet(text, terms),
                "photo_id": photos.get(identifier),
                "document_id": documents.get(identifier),
            }
            for identifier, text in rows
        ]
