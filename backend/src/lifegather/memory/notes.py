"""Explicit note corrections; original episodes and graph evidence are immutable."""

from collections.abc import Callable
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Engine, or_, select
from sqlalchemy.orm import Session

from lifegather.auth.store import Account
from lifegather.memory.models import Episode, NoteRevision
from lifegather.memory.schemas import SourceInput, SourceView
from lifegather.memory.service import MemoryError, MemoryService, fingerprint

NOTE_NAMESPACES = {"chat-memory", "chat-note-correction", "photo-memory"}


class NoteConflict(MemoryError):
    pass


class CorrectionInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, revalidate_instances="always"
    )
    source_id: str = Field(min_length=1, max_length=36)
    text: str = Field(min_length=1, max_length=4000)
    request_id: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def nonempty(self) -> Self:
        if not self.text.strip():
            raise ValueError("A correction cannot be blank")
        return self


class NoteHistoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_id: str = Field(min_length=1, max_length=36)
    cursor: str = Field(default="", max_length=36)
    limit: int = Field(default=25, ge=1, le=25)


class NoteService:
    def __init__(self, engine: Engine, clock: Callable[[], int] | None = None) -> None:
        self.engine = engine
        self.memory = MemoryService(engine, clock)

    @staticmethod
    def is_note(source: Episode) -> bool:
        return (
            source.source_type == "conversation" and source.namespace in NOTE_NAMESPACES
        )

    @staticmethod
    def _root(db: Session, actor: Account, source: Episode) -> str:
        root = db.scalar(
            select(NoteRevision.root_source_id).where(
                NoteRevision.user_id == actor.id,
                NoteRevision.source_id == source.id,
            )
        )
        return root or source.id

    @staticmethod
    def _head(db: Session, actor: Account, root: str) -> str:
        latest = db.scalar(
            select(NoteRevision.source_id)
            .where(
                NoteRevision.user_id == actor.id,
                NoteRevision.root_source_id == root,
            )
            .order_by(NoteRevision.recorded_at.desc(), NoteRevision.id.desc())
            .limit(1)
        )
        return latest or root

    def describe(self, actor: Account, source_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as db:
            source = self.memory._source(db, actor, source_id)
            if not self.is_note(source):
                return None
            root = self._root(db, actor, source)
            head = self._head(db, actor, root)
            return {
                "root_source_id": root,
                "current_source_id": head,
                "is_current": head == source_id,
                "can_correct": head == source_id,
            }

    def current(self, actor: Account, source_id: str) -> SourceView:
        with Session(self.engine) as db:
            source = self.memory._source(db, actor, source_id)
            if self.is_note(source):
                head = self._head(db, actor, self._root(db, actor, source))
                source = self.memory._source(db, actor, head)
            return SourceView.model_validate(source)

    def _record(self, db: Session, row: NoteRevision) -> None:
        db.add(row)
        db.flush()

    def _result(self, db: Session, actor: Account, row: NoteRevision) -> dict[str, Any]:
        source = self.memory._source(db, actor, row.source_id)
        return {
            "source": SourceView.model_validate(source).model_dump(mode="json"),
            "root_source_id": row.root_source_id,
            "previous_source_id": row.previous_source_id,
            "recorded_at": row.recorded_at,
        }

    def correct(self, actor: Account, value: CorrectionInput) -> dict[str, Any]:
        data = CorrectionInput.model_validate(value)
        key = fingerprint(data.model_dump())
        with self.memory._write() as db:
            previous = self.memory._source(db, actor, data.source_id)
            if not self.is_note(previous):
                raise MemoryError("Only saved text notes can be corrected here")
            existing = db.scalar(
                select(NoteRevision).where(
                    NoteRevision.user_id == actor.id,
                    NoteRevision.request_id == data.request_id,
                )
            )
            if existing is not None:
                if existing.fingerprint != key:
                    raise NoteConflict("Correction request conflict; use a new request")
                return self._result(db, actor, existing)
            root = self._root(db, actor, previous)
            if self._head(db, actor, root) != previous.id:
                raise NoteConflict(
                    "This note has a newer correction. Reload the current note."
                )
            if data.text == previous.text:
                raise MemoryError("The corrected note must change the text")
            now = max(self.memory.clock(), previous.recorded_at + 1)
            source = self.memory._ingest_in(
                db,
                actor,
                SourceInput(
                    text=data.text,
                    source_type="conversation",
                    namespace="chat-note-correction",
                    external_id=data.request_id,
                ),
                recorded_at=now,
            )
            row = NoteRevision(
                id=source.id,
                user_id=actor.id,
                root_source_id=root,
                previous_source_id=previous.id,
                source_id=source.id,
                request_id=data.request_id,
                fingerprint=key,
                recorded_at=now,
            )
            self._record(db, row)
            self.memory._audit(db, actor, "note_corrected", source.id, now)
            return self._result(db, actor, row)

    def history(
        self, actor: Account, source_id: str, cursor: str = "", limit: int = 25
    ) -> dict[str, Any]:
        data = NoteHistoryInput(source_id=source_id, cursor=cursor, limit=limit)
        with Session(self.engine) as db:
            source = self.memory._source(db, actor, data.source_id)
            if not self.is_note(source):
                raise MemoryError("Note history not found")
            root = self._root(db, actor, source)
            head = self._head(db, actor, root)
            version_ids = select(NoteRevision.source_id).where(
                NoteRevision.user_id == actor.id,
                NoteRevision.root_source_id == root,
            )
            query = select(Episode).where(
                Episode.user_id == actor.id,
                or_(Episode.id == root, Episode.id.in_(version_ids)),
            )
            if data.cursor:
                previous = db.scalar(query.where(Episode.id == data.cursor))
                if previous is None:
                    raise MemoryError("Invalid note history cursor")
                query = query.where(Episode.recorded_at > previous.recorded_at)
            rows = list(
                db.scalars(
                    query.order_by(Episode.recorded_at, Episode.id).limit(limit + 1)
                )
            )
            return {
                "items": [
                    {
                        "id": row.id,
                        "text": row.text[:160],
                        "recorded_at": row.recorded_at,
                        "is_current": row.id == head,
                        "is_original": row.id == root,
                    }
                    for row in rows[:limit]
                ],
                "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
                "root_source_id": root,
                "current_source_id": head,
            }
