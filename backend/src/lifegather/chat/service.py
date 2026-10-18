"""Framework-independent conversations; models have read-only evidence access."""

import json
import time
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from lifegather.assets.actions import ActionService
from lifegather.auth.store import Account
from lifegather.chat.models import Conversation, Turn, Usage
from lifegather.chat.provider_names import SUPPORTED_PROVIDERS
from lifegather.credentials.service import PrivateSettings
from lifegather.memory.notes import NoteService
from lifegather.memory.schemas import SourceInput, SourceView
from lifegather.memory.service import MemoryError, MemoryService, fingerprint

DAILY_REQUESTS = 20


class TurnInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, revalidate_instances="always"
    )
    request_id: str = Field(min_length=1, max_length=100)
    mode: Literal[
        "save", "search", "ask", "extract", "extract_photo", "extract_receipt"
    ]
    source_id: str = Field(default="", max_length=36)
    photo_id: str = Field(default="", max_length=36)
    text: str = Field(min_length=1, max_length=4000)
    credential_id: str = Field(default="", max_length=36)
    model: str = Field(default="", max_length=100, pattern=r"^[a-zA-Z0-9._:-]*$")

    @model_validator(mode="after")
    def valid_text(self) -> "TurnInput":
        if not self.text.strip():
            raise ValueError("Text cannot be blank")
        if self.mode in {"ask", "extract", "extract_photo", "extract_receipt"} and (
            not self.credential_id or not self.model
        ):
            raise ValueError("Choose an AI connection and model")
        if self.mode in {"extract", "extract_receipt"} and not self.source_id:
            raise ValueError("Choose a saved note first")
        if self.mode == "extract_photo" and not self.photo_id:
            raise ValueError("Choose a photo first")
        return self


class SaveText(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, revalidate_instances="always"
    )
    text: str = Field(min_length=1, max_length=4000)
    request_id: str = Field(min_length=1, max_length=100)


def save_text(memory: MemoryService, actor: Account, data: SaveText) -> SourceView:
    data = SaveText.model_validate(data)
    return memory.ingest(
        actor,
        SourceInput(
            text=data.text,
            source_type="conversation",
            namespace="chat-memory",
            external_id=data.request_id,
        ),
    )


class ChatService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.memory = MemoryService(engine)

    @staticmethod
    def owned(db: Session, actor: Account, identifier: str) -> Conversation:
        row = db.scalar(
            select(Conversation).where(
                Conversation.user_id == actor.id,
                Conversation.id == identifier,
            )
        )
        if row is None:
            raise MemoryError("Conversation not found")
        return row

    def create(self, actor: Account) -> dict[str, Any]:
        with Session(self.engine) as db, db.begin():
            row = Conversation(
                id=str(uuid4()),
                user_id=actor.id,
                title="New conversation",
                created_at=time.time_ns() // 1000,
            )
            db.add(row)
            db.flush()
            return {"id": row.id, "title": row.title}

    def conversations(self, actor: Account, cursor: str = "") -> dict[str, Any]:
        with Session(self.engine) as db:
            rows = list(
                db.scalars(
                    select(Conversation)
                    .where(
                        Conversation.user_id == actor.id,
                        Conversation.id > cursor,
                    )
                    .order_by(Conversation.id)
                    .limit(26)
                )
            )
            return {
                "items": [{"id": r.id, "title": r.title} for r in rows[:25]],
                "next_cursor": rows[24].id if len(rows) > 25 else None,
            }

    @staticmethod
    def view(row: Turn) -> dict[str, Any]:
        state = row.state
        if state == "pending" and time.time_ns() // 1000 - row.created_at > 120_000_000:
            state = "interrupted"
        return {
            "id": row.id,
            "request_id": row.request_id,
            "text": row.text,
            "mode": row.mode,
            "state": state,
            "result": json.loads(row.result_json),
        }

    def turns(
        self, actor: Account, conversation_id: str, cursor: str = ""
    ) -> dict[str, Any]:
        with Session(self.engine) as db:
            self.owned(db, actor, conversation_id)
            query = select(Turn).where(
                Turn.user_id == actor.id, Turn.conversation_id == conversation_id
            )
            if cursor:
                previous = db.scalar(query.where(Turn.id == cursor))
                if previous is None:
                    raise MemoryError("Invalid cursor")
                query = query.where(
                    (Turn.created_at > previous.created_at)
                    | ((Turn.created_at == previous.created_at) & (Turn.id > cursor))
                )
            rows = list(db.scalars(query.order_by(Turn.created_at, Turn.id).limit(26)))
            return {
                "items": [self.view(r) for r in rows[:25]],
                "next_cursor": rows[24].id if len(rows) > 25 else None,
            }

    def begin(
        self, actor: Account, conversation_id: str, data: TurnInput
    ) -> tuple[dict[str, Any], bool]:
        data = TurnInput.model_validate(data)
        with Session(self.engine) as db:
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            conversation = self.owned(db, actor, conversation_id)
            # Preserve replay fingerprints for turns saved before extraction existed.
            key = fingerprint(
                [
                    conversation_id,
                    data.model_dump(
                        exclude=({"source_id"} if not data.source_id else set())
                        | ({"photo_id"} if not data.photo_id else set())
                    ),
                ]
            )
            existing = db.scalar(
                select(Turn).where(
                    Turn.user_id == actor.id, Turn.request_id == data.request_id
                )
            )
            if existing is not None:
                if existing.fingerprint != key:
                    raise MemoryError("Request identity conflict; use a new request ID")
                return self.view(existing), False
            if db.scalar(
                select(Turn.id)
                .where(
                    Turn.user_id == actor.id,
                    Turn.state == "pending",
                    Turn.created_at > time.time_ns() // 1000 - 120_000_000,
                )
                .limit(1)
            ):
                raise MemoryError("Another request is still running")
            row = Turn(
                id=str(uuid4()),
                user_id=actor.id,
                conversation_id=conversation_id,
                request_id=data.request_id,
                mode=data.mode,
                text=data.text,
                fingerprint=key,
                state="pending",
                result_json="{}",
                created_at=time.time_ns() // 1000,
            )
            if conversation.title == "New conversation":
                conversation.title = data.text[:60]
            db.add(row)
            db.flush()
            result = self.view(row)
            db.commit()
            return result, True

    def finish(
        self,
        actor: Account,
        turn_id: str,
        result: dict[str, Any],
        state: str = "complete",
    ) -> dict[str, Any]:
        with Session(self.engine) as db, db.begin():
            row = db.scalar(
                select(Turn).where(Turn.user_id == actor.id, Turn.id == turn_id)
            )
            if row is None:
                raise MemoryError("Message not found")
            if row.state == "pending":
                row.result_json, row.state = json.dumps(result), state
            return self.view(row)

    def recent(self, actor: Account, conversation_id: str) -> list[dict[str, Any]]:
        with Session(self.engine) as db:
            self.owned(db, actor, conversation_id)
            rows = list(
                db.scalars(
                    select(Turn)
                    .where(
                        Turn.user_id == actor.id,
                        Turn.conversation_id == conversation_id,
                    )
                    .order_by(Turn.created_at.desc(), Turn.id.desc())
                    .limit(4)
                )
            )
            return [self.view(row) for row in reversed(rows)]

    def cancel(self, actor: Account, request_id: str) -> dict[str, Any]:
        with Session(self.engine) as db:
            row = db.scalar(
                select(Turn).where(
                    Turn.user_id == actor.id,
                    Turn.request_id == request_id,
                )
            )
            if row is None:
                raise MemoryError("Message not found")
            identifier = row.id
        return self.finish(actor, identifier, {"text": "Request stopped."}, "canceled")

    def provider_name(
        self, actor: Account, vault: PrivateSettings, credential_id: str
    ) -> str:
        with Session(self.engine) as db:
            credential = vault._owned(db, actor, credential_id)
            if (
                credential.kind != "ai"
                or credential.provider not in SUPPORTED_PROVIDERS
            ):
                raise MemoryError("Select a supported AI connection")
            return credential.provider

    def reserve(
        self, actor: Account, vault: PrivateSettings, credential_id: str
    ) -> tuple[str, str]:
        if not vault.preferences(actor):
            raise MemoryError("Enable external AI access in Settings before asking AI")
        self.provider_name(actor, vault, credential_id)
        secret = vault.read_secret(actor, credential_id)
        day = datetime.now(UTC).date().isoformat()
        with Session(self.engine) as db:
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            usage = db.get(Usage, (actor.id, day))
            if usage is None:
                usage = Usage(
                    user_id=actor.id,
                    day=day,
                    requests=0,
                    input_tokens=0,
                    output_tokens=0,
                )
                db.add(usage)
            if usage.requests >= DAILY_REQUESTS:
                raise MemoryError("Daily limit reached (20 AI questions per UTC day)")
            usage.requests += 1
            db.commit()
        return secret, day

    def record_usage(
        self, actor: Account, day: str, input_tokens: int, output_tokens: int
    ) -> None:
        with Session(self.engine) as db:
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            usage = db.get(Usage, (actor.id, day))
            if usage is None:
                raise MemoryError("Usage reservation not found")
            usage.input_tokens += input_tokens
            usage.output_tokens += output_tokens
            db.commit()

    def usage(self, actor: Account) -> dict[str, Any]:
        day = datetime.now(UTC).date().isoformat()
        with Session(self.engine) as db:
            row = db.get(Usage, (actor.id, day))
            return {
                "day": day,
                "requests": row.requests if row else 0,
                "limit": DAILY_REQUESTS,
                "input_tokens": row.input_tokens if row else 0,
                "output_tokens": row.output_tokens if row else 0,
            }

    def evidence(self, actor: Account, query: str) -> list[dict[str, Any]]:
        matches = self.memory.search(actor, query, 8)
        actions = ActionService(self.engine)
        original_ids = []
        entity_ids = []
        for match in matches:
            if match["kind"] == "entity":
                entity_ids.append(match["id"])
                original_ids.append(
                    self.memory.get_entity(actor, match["id"]).source_id
                )
            else:
                original_ids.append(match["id"])
                metadata = NoteService(self.engine).describe(actor, match["id"])
                if metadata:
                    original_ids.append(metadata["root_source_id"])
        action_ids = actions.related_sources(actor, original_ids, entity_ids)
        matches = [
            {"kind": "source", "id": identifier} for identifier in action_ids
        ] + matches
        sources: dict[str, Any] = {}
        for match in matches:
            identifier = match["id"]
            if match["kind"] == "entity":
                identifier = self.memory.get_entity(actor, identifier).source_id
            source = NoteService(self.engine).current(actor, identifier)
            identifier = source.id
            sources[identifier] = {
                "id": identifier,
                "text": source.text[:2000],
                "recorded_at": source.recorded_at,
                "event_date": source.event_date.isoformat()
                if source.event_date
                else None,
                "status": "corrected note; not independently verified"
                if source.namespace == "chat-note-correction"
                else "original statement; not independently verified",
            }
            from lifegather.photos.service import PhotoService

            photo = PhotoService(self.engine).source_photo(actor, identifier)
            if photo is not None:
                sources[identifier]["status"] = (
                    "AI transcription or user correction of a photo; unverified"
                )
                sources[identifier]["photo"] = {
                    "id": photo["id"],
                    "deleted": photo["deleted_at"] is not None,
                }
            from lifegather.documents.service import DocumentService

            document = DocumentService(self.engine).source_document(actor, identifier)
            if document is not None:
                sources[identifier]["status"] = (
                    "user-reviewed PDF text; extraction/layout may be incomplete"
                )
                sources[identifier]["document"] = {
                    "id": document["id"],
                    "deleted": document["deleted_at"] is not None,
                    "text_truncated": document["text_truncated"],
                }
            # Preserve exact user text; attach authenticated item-selection context
            # so short corrections such as "I sold it" remain attributable.
            context = actions.source_context(actor, identifier)
            if context is not None:
                sources[identifier]["asset_context"] = context
        return list(sources.values())[:8]
