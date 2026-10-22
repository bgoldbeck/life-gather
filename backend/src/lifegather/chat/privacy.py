"""Reviewed transcript deletion; independent saved evidence always remains."""

import json
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
from sqlalchemy import Engine, delete, func, select, update
from sqlalchemy.orm import Session

from lifegather.auth.store import Account
from lifegather.chat.models import Conversation, Turn
from lifegather.chat.service import ChatService
from lifegather.database import begin_snapshot
from lifegather.memory.models import Audit
from lifegather.memory.notes import NoteConflict
from lifegather.memory.service import MemoryError, MemoryService, fingerprint

FORMAT = "lifegather-conversation-deletion/1"


class ConversationPreview(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, revalidate_instances="always"
    )


class ConversationToken(ConversationPreview):
    preview_token: str = Field(pattern=r"^[a-f0-9]{64}$")


class ConversationDelete(ConversationToken):
    confirmed: StrictBool

    @model_validator(mode="after")
    def explicit(self) -> Self:
        if not self.confirmed:
            raise ValueError("Confirm permanent conversation deletion")
        return self


class ConversationPrivacy:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.memory = MemoryService(engine)

    @staticmethod
    def _preview_in(db: Session, actor: Account, identifier: str) -> dict[str, Any]:
        row = ChatService.owned(db, actor, identifier)
        # Public turn APIs append records and transition only pending -> terminal.
        # Counts and immutable per-state maxima detect those changes without reading
        # potentially large prompts/results, or materializing an entire transcript.
        groups = db.execute(
            select(
                Turn.state,
                func.count(Turn.id),
                func.max(Turn.id),
                func.max(Turn.created_at),
            )
            .where(Turn.user_id == actor.id, Turn.conversation_id == identifier)
            .group_by(Turn.state)
            .order_by(Turn.state)
        ).all()
        counts = {state: int(count) for state, count, _, _ in groups}
        return {
            "format": FORMAT,
            "id": row.id,
            "title": row.title,
            "turn_count": sum(counts.values()),
            "state_counts": counts,
            "pending_count": counts.get("pending", 0),
            "preview_token": fingerprint(
                [
                    actor.id,
                    row.id,
                    row.title,
                    row.created_at,
                    [list(group) for group in groups],
                ]
            ),
        }

    @staticmethod
    def _check(preview: dict[str, Any], token: ConversationToken) -> None:
        if preview["preview_token"] != token.preview_token:
            raise NoteConflict(
                "Conversation changed. Review it again before continuing."
            )

    def preview(self, actor: Account, identifier: str) -> dict[str, Any]:
        with Session(self.engine) as db:
            begin_snapshot(db)
            return self._preview_in(db, actor, identifier)

    def stop(
        self, actor: Account, identifier: str, value: ConversationToken
    ) -> dict[str, Any]:
        data = ConversationToken.model_validate(value)
        with self.memory._write() as db:
            preview = self._preview_in(db, actor, identifier)
            self._check(preview, data)
            stopped = preview["pending_count"]
            if stopped:
                db.execute(
                    update(Turn)
                    .where(
                        Turn.user_id == actor.id,
                        Turn.conversation_id == identifier,
                        Turn.state == "pending",
                    )
                    .values(
                        state="canceled",
                        result_json=json.dumps({"text": "Request stopped."}),
                    )
                )
                self.memory._audit(
                    db, actor, "chat_requests_stopped", identifier, self.memory.clock()
                )
            return {**self._preview_in(db, actor, identifier), "stopped_count": stopped}

    def delete(
        self, actor: Account, identifier: str, value: ConversationDelete
    ) -> dict[str, Any]:
        data = ConversationDelete.model_validate(value)
        with self.memory._write() as db:
            row = db.scalar(
                select(Conversation).where(
                    Conversation.user_id == actor.id, Conversation.id == identifier
                )
            )
            if row is None:
                tombstone = db.scalar(
                    select(Audit.id)
                    .where(
                        Audit.user_id == actor.id,
                        Audit.target_id == identifier,
                        Audit.operation == "conversation_deleted",
                    )
                    .limit(1)
                )
                if tombstone is None:
                    raise MemoryError("Conversation not found")
            else:
                preview = self._preview_in(db, actor, identifier)
                self._check(preview, data)
                if preview["pending_count"]:
                    raise MemoryError(
                        "Stop pending chat requests before deleting this conversation"
                    )
                db.execute(
                    delete(Turn).where(
                        Turn.user_id == actor.id, Turn.conversation_id == identifier
                    )
                )
                db.delete(row)
                self.memory._audit(
                    db, actor, "conversation_deleted", identifier, self.memory.clock()
                )
            return {"id": identifier, "deleted": True}
