"""User-requested memory deletion: remove saved text, keep the provenance chain.

Sources are cited by facts, assets, purchases and proposals, so a deleted memory
stays as a content-free row. Its text is replaced, its search entry and fact
evidence quotes are cleared, and a `source_deleted` audit receipt marks it.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, delete, or_, select, update
from sqlalchemy.orm import Session

from lifegather.auth.store import Account
from lifegather.memory.models import Episode, Evidence, NoteRevision
from lifegather.memory.notes import NoteService
from lifegather.memory.search_index import search_index
from lifegather.memory.service import (
    DELETED_TEXT,
    SOURCE_DELETED,
    MemoryError,
    MemoryService,
)


class MemoryDelete(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_id: str = Field(min_length=1, max_length=36)


class MemoryDeleteMany(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    memories: list[MemoryDelete] = Field(min_length=1, max_length=25)


class MemoryDeletion:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.memory = MemoryService(engine)

    def _versions(self, db: Session, actor: Account, source: Episode) -> list[str]:
        """Every version of a note (original and corrections), else the source."""
        root = NoteService._root(db, actor, source)
        revisions = select(NoteRevision.source_id).where(
            NoteRevision.user_id == actor.id, NoteRevision.root_source_id == root
        )
        return list(
            db.scalars(
                select(Episode.id)
                .where(
                    Episode.user_id == actor.id,
                    or_(Episode.id == root, Episode.id.in_(revisions)),
                )
                .order_by(Episode.recorded_at, Episode.id)
            )
        )

    def _delete_in(self, db: Session, actor: Account, source_id: str) -> int:
        source = self.memory._source(db, actor, source_id)
        deleted = 0
        now = self.memory.clock()
        for identifier in self._versions(db, actor, source):
            if self.memory.is_deleted(db, actor, identifier):
                continue
            row = self.memory._source(db, actor, identifier)
            row.text = DELETED_TEXT
            db.execute(
                delete(search_index).where(
                    search_index.c.user_id == actor.id,
                    search_index.c.record_id == identifier,
                    search_index.c.kind == "source",
                )
            )
            db.execute(
                update(Evidence)
                .where(Evidence.user_id == actor.id, Evidence.source_id == identifier)
                .values(quote=None)
            )
            self.memory._audit(db, actor, SOURCE_DELETED, identifier, now)
            db.flush()
            deleted += 1
        return deleted

    def delete_many(self, actor: Account, value: MemoryDeleteMany) -> dict[str, Any]:
        """Delete several memories in one transaction; an unknown one refuses all."""
        data = MemoryDeleteMany.model_validate(value)
        ids = [item.source_id for item in data.memories]
        if len(set(ids)) != len(ids):
            raise MemoryError("Each memory can be listed only once")
        with self.memory._write() as db:
            removed = sum(self._delete_in(db, actor, identifier) for identifier in ids)
        return {"deleted": ids, "deleted_count": len(ids), "versions_deleted": removed}
