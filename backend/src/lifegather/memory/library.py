"""Private, paginated source browsing, independent of chats and AI providers."""

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, and_, func, or_, select, text
from sqlalchemy.orm import Session, aliased

from lifegather.auth.store import Account
from lifegather.memory.models import Episode, NoteRevision
from lifegather.memory.notes import NoteService
from lifegather.memory.service import MemoryError, MemoryService


class LibraryPage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str = Field(default="", max_length=200)
    kind: Literal["all", "notes", "photos", "pdfs", "other"] = "all"
    include_history: bool = False
    cursor: str = Field(default="", max_length=36)
    limit: int = Field(default=25, ge=1, le=25)


class MemoryLibrary:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def list(self, actor: Account, value: LibraryPage) -> dict[str, Any]:
        data = LibraryPage.model_validate(value)
        revision = aliased(NoteRevision)
        root = aliased(Episode)
        later = aliased(NoteRevision)
        current = (
            ~select(later.id)
            .where(later.user_id == actor.id, later.previous_source_id == Episode.id)
            .exists()
        )
        namespace = func.coalesce(root.namespace, Episode.namespace)
        statement = (
            select(Episode, namespace.label("origin"), current.label("is_current"))
            .outerjoin(
                revision,
                and_(revision.user_id == actor.id, revision.source_id == Episode.id),
            )
            .outerjoin(
                root, and_(root.user_id == actor.id, root.id == revision.root_source_id)
            )
            .where(Episode.user_id == actor.id)
        )
        categories = {
            "notes": "chat-memory",
            "photos": "photo-memory",
            "pdfs": "pdf-memory",
        }
        if data.kind in categories:
            statement = statement.where(namespace == categories[data.kind])
        elif data.kind == "other":
            statement = statement.where(namespace.not_in(list(categories.values())))
        if not data.include_history:
            statement = statement.where(current)
        if data.query.strip():
            words = re.findall(r"[^\W_]+", data.query, re.UNICODE)
            if not words or len(words) > 12:
                raise MemoryError("Search requires 1 to 12 words")
            match = " AND ".join('"' + word + '"' for word in words)
            statement = statement.where(
                text(
                    "memory_sources.id IN (SELECT record_id FROM memory_fts "
                    "WHERE memory_fts MATCH :library_query AND user_id=:library_owner "
                    "AND kind='source')"
                ).bindparams(library_query=match, library_owner=actor.id)
            )
        with Session(self.engine) as db:
            if data.cursor:
                previous = MemoryService._source(db, actor, data.cursor)
                statement = statement.where(
                    or_(
                        Episode.recorded_at < previous.recorded_at,
                        and_(
                            Episode.recorded_at == previous.recorded_at,
                            Episode.id < previous.id,
                        ),
                    )
                )
            rows = list(
                db.execute(
                    statement.order_by(
                        Episode.recorded_at.desc(), Episode.id.desc()
                    ).limit(data.limit + 1)
                )
            )
            items = []
            for source, origin, is_current in rows[: data.limit]:
                kind = next((k for k, v in categories.items() if v == origin), "other")
                items.append(
                    {
                        "id": source.id,
                        "text": source.text[:240],
                        "kind": kind,
                        "recorded_at": source.recorded_at,
                        "is_current": bool(is_current),
                        "can_correct": bool(is_current) and NoteService.is_note(source),
                        "is_correction": source.namespace == "chat-note-correction",
                    }
                )
            return {
                "items": items,
                "next_cursor": rows[data.limit - 1][0].id
                if len(rows) > data.limit
                else None,
            }
