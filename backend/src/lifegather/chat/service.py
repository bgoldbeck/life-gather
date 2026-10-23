"""Framework-independent conversations; models have read-only evidence access."""

import json
import time
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from lifegather.assets.actions import ActionService
from lifegather.auth.store import Account
from lifegather.chat.context import ContextRef, WorkspaceContexts
from lifegather.chat.models import Conversation, Turn, Usage
from lifegather.chat.provider_names import SUPPORTED_PROVIDERS
from lifegather.chat.research import ResearchScope
from lifegather.credentials.service import PrivateSettings
from lifegather.database import begin_serialized
from lifegather.mailboxes.scan import GmailScanConfig
from lifegather.memory.notes import NoteService
from lifegather.memory.origins import change_origin
from lifegather.memory.schemas import SourceInput, SourceView
from lifegather.memory.service import MemoryError, MemoryService, fingerprint
from lifegather.scans.service import ScanService

DAILY_REQUESTS = 20


class TurnInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, revalidate_instances="always"
    )
    request_id: str = Field(min_length=1, max_length=100)
    mode: Literal[
        "save",
        "search",
        "ask",
        "extract",
        "extract_photo",
        "extract_receipt",
        "extract_photo_receipt",
        "scan_email",
        "organize",
        "assistant",
        "research",
    ]
    source_id: str = Field(default="", max_length=36)
    photo_id: str = Field(default="", max_length=36)
    document_id: str = Field(default="", max_length=36)
    scan: GmailScanConfig | None = None
    context: ContextRef | None = None
    research: ResearchScope | None = None
    text: str = Field(min_length=1, max_length=4000)
    credential_id: str = Field(default="", max_length=36)
    model: str = Field(default="", max_length=100, pattern=r"^[a-zA-Z0-9._:-]*$")
    timezone: str = Field(default="", max_length=100)

    @model_validator(mode="after")
    def valid_text(self) -> "TurnInput":
        if self.timezone:
            if self.mode != "assistant":
                raise ValueError("Only the AI assistant accepts a request timezone")
            try:
                ZoneInfo(self.timezone)
            except (ValueError, ZoneInfoNotFoundError):
                raise ValueError("Choose an IANA timezone") from None
        if not self.text.strip():
            raise ValueError("Text cannot be blank")
        if self.mode == "scan_email" and self.scan is None:
            raise ValueError("Choose an email scan scope")
        if self.mode != "scan_email" and self.scan is not None:
            raise ValueError("Only email scan requests include scan scope")
        if (self.mode == "research") != (self.research is not None):
            raise ValueError("Only web research requests include research scope")
        if (
            self.research
            and self.research.share_record
            and not (self.context and self.context.entity_id)
        ):
            raise ValueError("Select a record before sharing its details")
        if self.mode in {
            "ask",
            "assistant",
            "extract",
            "extract_photo",
            "extract_receipt",
            "extract_photo_receipt",
            "research",
        } and (not self.credential_id or not self.model):
            raise ValueError("Choose an AI connection and model")
        if self.mode in {"extract", "extract_receipt"} and not self.source_id:
            raise ValueError("Choose a saved note first")
        if (
            self.mode in {"extract_photo", "extract_photo_receipt"}
            and not self.photo_id
        ):
            raise ValueError("Choose a photo first")
        if self.document_id and self.mode != "assistant":
            raise ValueError("Only the AI assistant reads an attached document")
        if self.mode == "assistant" and self.photo_id and self.document_id:
            raise ValueError("Attach one photo or one document")
        return self


def request_key(conversation_id: str, data: TurnInput) -> str:
    # Optional scope must not change fingerprints of already saved requests.
    excluded = (
        ({"source_id"} if not data.source_id else set())
        | ({"photo_id"} if not data.photo_id else set())
        | ({"document_id"} if not data.document_id else set())
        | ({"scan"} if data.scan is None else set())
        | ({"context"} if data.context is None else set())
        | ({"research"} if data.research is None else set())
        | ({"timezone"} if not data.timezone else set())
    )
    return fingerprint([conversation_id, data.model_dump(exclude=excluded)])


class SaveText(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, revalidate_instances="always"
    )
    text: str = Field(min_length=1, max_length=4000)
    request_id: str = Field(min_length=1, max_length=100)


def save_text(memory: MemoryService, actor: Account, data: SaveText) -> SourceView:
    data = SaveText.model_validate(data)
    with change_origin(method="user_statement"):
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
            begin_serialized(db)
            conversation = self.owned(db, actor, conversation_id)
            if data.context:
                WorkspaceContexts(self.engine).read_in(db, actor, data.context)
            # Preserve replay fingerprints for turns saved before extraction existed.
            key = request_key(conversation_id, data)
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

    def organize(
        self, actor: Account, conversation_id: str, value: TurnInput
    ) -> dict[str, Any] | None:
        from lifegather.chat.organizer import OrganizationAction, WorkspaceOrganizer

        data = TurnInput.model_validate(value)
        if data.mode != "organize":
            raise MemoryError("Choose the Assistant action")
        with self.memory._write() as db:
            self.owned(db, actor, conversation_id)
            row = db.scalar(
                select(Turn).where(
                    Turn.user_id == actor.id, Turn.request_id == data.request_id
                )
            )
            if row is None or row.fingerprint != request_key(conversation_id, data):
                raise MemoryError("Assistant request changed; start a new request")
            if row.state != "pending":
                return self.view(row)
            previous = db.scalar(
                select(Turn.result_json)
                .where(
                    Turn.user_id == actor.id,
                    Turn.conversation_id == conversation_id,
                    Turn.state == "complete",
                    Turn.id != row.id,
                )
                .order_by(Turn.created_at.desc(), Turn.id.desc())
                .limit(1)
            )
            awaiting = json.loads(previous).get("awaiting") if previous else None
            with change_origin(related_id=row.id):
                result = WorkspaceOrganizer(self.engine).execute_in(
                    db,
                    actor,
                    OrganizationAction(
                        request_id=data.request_id, text=data.text, context=data.context
                    ),
                    awaiting,
                )
            if result is None:
                return None
            row.result_json = json.dumps(result)
            row.state = "complete"
            db.flush()
            return self.view(row)

    def start_scan(
        self, actor: Account, conversation_id: str, value: TurnInput, scans: ScanService
    ) -> dict[str, Any]:
        """One authorized pending request, durable job and saved Chat result."""
        data = TurnInput.model_validate(value)
        if (
            data.mode != "scan_email"
            or data.scan is None
            or scans.engine is not self.engine
        ):
            raise MemoryError("Choose the connected email scan action")
        with self.memory._write() as db:
            self.owned(db, actor, conversation_id)
            row = db.scalar(
                select(Turn).where(
                    Turn.user_id == actor.id, Turn.request_id == data.request_id
                )
            )
            if row is None or row.fingerprint != request_key(conversation_id, data):
                raise MemoryError("Chat scan request changed; start a new request")
            if row.state != "pending":
                return self.view(row)
            run = scans.enqueue_in(
                db,
                actor,
                "gmail_import",
                data.scan.model_dump(),
                "chat:" + fingerprint([conversation_id, data.request_id]),
            )
            row.result_json = json.dumps(
                {
                    "text": (
                        "Email evidence scan queued. No AI extraction is enabled. "
                        "The scan continues after leaving Chat; open its progress "
                        "to inspect results or cancel."
                    ),
                    "scan_run_id": run["id"],
                    "scan_scope": data.scan.model_dump(),
                }
            )
            row.state = "complete"
            return self.view(row)

    def finish(
        self,
        actor: Account,
        turn_id: str,
        result: dict[str, Any],
        state: str = "complete",
    ) -> dict[str, Any]:
        with self.memory._write() as db:
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
            begin_serialized(db)
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
            begin_serialized(db)
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

    def source_metadata(self, actor: Account, source: SourceView) -> dict[str, Any]:
        """Shared provenance and current correction state for all recall paths."""
        from lifegather.documents.service import DocumentService
        from lifegather.maintenance.service import MaintenanceService
        from lifegather.photos.service import PhotoService

        result: dict[str, Any] = {
            "status": "corrected note; not independently verified"
            if source.namespace == "chat-note-correction"
            else "original statement; not independently verified"
        }
        photo = PhotoService(self.engine).source_photo(actor, source.id)
        if photo is not None:
            result["status"] = (
                "AI transcription or user correction of a photo; unverified"
            )
            result["photo"] = {
                "id": photo["id"],
                "deleted": photo["deleted_at"] is not None,
            }
        document = DocumentService(self.engine).source_document(actor, source.id)
        if document is not None:
            result["status"] = (
                f"user-reviewed {document.get('format', 'pdf').upper()} text; "
                "extraction/layout may be incomplete"
            )
            result["document"] = {
                "id": document["id"],
                "deleted": document["deleted_at"] is not None,
                "text_truncated": document["text_truncated"],
            }
        from lifegather.reconciliation.receipts import ReceiptService

        receipts = ReceiptService(self.engine)
        receipt_id = receipts.for_source(actor, source.id)
        if receipt_id is None:
            note = NoteService(self.engine).describe(actor, source.id)
            if note:
                receipt_id = receipts.for_source(actor, note["root_source_id"])
        if receipt_id:
            result["receipt_review_id"] = receipt_id
        context = ActionService(self.engine).source_context(actor, source.id)
        if context is not None:
            result["asset_context"] = context
        maintenance = MaintenanceService(self.engine).source_context(actor, source.id)
        if maintenance is not None:
            result["maintenance_context"] = maintenance
            result["status"] = (
                "current manual maintenance statement; not independently verified"
                if maintenance["is_current_revision"]
                else "historical maintenance statement; superseded revision"
            )
        return result

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

        def add(source: SourceView, metadata: dict[str, Any]) -> None:
            if len(sources) >= 8:
                return
            sources[source.id] = {
                "id": source.id,
                "text": source.text[:2000],
                "recorded_at": source.recorded_at,
                "event_date": source.event_date.isoformat()
                if source.event_date
                else None,
                **metadata,
            }

        for match in matches:
            identifier = match["id"]
            if match["kind"] == "entity":
                identifier = self.memory.get_entity(actor, identifier).source_id
            source = NoteService(self.engine).current(actor, identifier)
            metadata = self.source_metadata(actor, source)
            maintenance = metadata.get("maintenance_context")
            if maintenance and not maintenance["is_current_revision"]:
                current = self.memory.get_source(
                    actor, maintenance["current_source_id"]
                )
                add(current, self.source_metadata(actor, current))
            add(source, metadata)
            if len(sources) >= 8:
                break
        return list(sources.values())[:8]
