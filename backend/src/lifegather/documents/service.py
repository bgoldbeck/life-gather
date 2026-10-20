"""Owner-scoped original documents, extraction review and immutable source links."""

import hashlib
import json
from collections.abc import Callable
from typing import Any, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from lifegather.auth.store import Account
from lifegather.documents.extractor import MAX_BYTES, extract_document
from lifegather.documents.formats import MIMES, PreviewOptions
from lifegather.documents.models import Document
from lifegather.memory.notes import NoteConflict, NoteService
from lifegather.memory.schemas import SourceInput
from lifegather.memory.service import MemoryError, MemoryService


class DocumentRead(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    document_id: str = Field(min_length=1, max_length=36)


class DocumentPage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    cursor: str = Field(default="", max_length=36)
    limit: int = Field(default=25, ge=1, le=25)


class DocumentText(DocumentRead):
    model_config = ConfigDict(
        extra="forbid", strict=True, revalidate_instances="always"
    )
    text: str = Field(min_length=1, max_length=4000)
    expected_updated_at: int = Field(ge=0)

    @model_validator(mode="after")
    def nonempty(self) -> Self:
        if not self.text.strip():
            raise ValueError("Reviewed text cannot be blank")
        return self


class DocumentDelete(DocumentRead):
    expected_updated_at: int = Field(ge=0)


class DocumentPreview(DocumentRead, PreviewOptions):
    pass


class DocumentService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.memory = MemoryService(engine)

    @staticmethod
    def owned(db: Session, actor: Account, identifier: str) -> Document:
        row = db.scalar(
            select(Document)
            .where(Document.user_id == actor.id, Document.id == identifier)
            .limit(1)
        )
        if row is None:
            raise MemoryError("Document not found")
        return row

    @staticmethod
    def view(row: Document, *, include_text: bool = True) -> dict[str, Any]:
        return {
            "id": row.id,
            "filename": row.filename,
            "format": row.format,
            "mime": MIMES.get(row.format, "application/octet-stream"),
            "extraction_metadata": json.loads(row.extraction_metadata),
            "size": row.size,
            "pages": row.pages if row.format == "pdf" else None,
            "text_truncated": row.text_truncated,
            "source_id": row.source_id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "deleted_at": row.deleted_at,
            **({"extracted_text": row.extracted_text} if include_text else {}),
        }

    def list(self, actor: Account, value: DocumentPage | None = None) -> dict[str, Any]:
        data = DocumentPage.model_validate(value or DocumentPage())
        with Session(self.engine) as db:
            rows = list(
                db.scalars(
                    select(Document)
                    .where(
                        Document.user_id == actor.id,
                        Document.deleted_at.is_(None),
                        Document.id > data.cursor,
                    )
                    .order_by(Document.id)
                    .limit(data.limit + 1)
                )
            )
            return {
                "items": [
                    self.view(row, include_text=False) for row in rows[: data.limit]
                ],
                "next_cursor": rows[data.limit - 1].id
                if len(rows) > data.limit
                else None,
            }

    def get(self, actor: Account, identifier: str) -> dict[str, Any]:
        with Session(self.engine) as db:
            return self.view(self.owned(db, actor, identifier))

    def binary(self, actor: Account, identifier: str) -> bytes:
        with Session(self.engine) as db:
            row = self.owned(db, actor, identifier)
            if row.deleted_at is not None or row.original is None:
                raise MemoryError("Original document was deleted")
            return row.original

    def upload(
        self,
        actor: Account,
        raw: bytes,
        filename: str,
        active: Callable[[], None] | None = None,
        options: PreviewOptions | None = None,
    ) -> dict[str, Any]:
        if (
            not filename
            or len(filename) > 200
            or filename.rsplit(".", 1)[-1].lower() not in MIMES
            or any(ord(c) < 32 or c in "/\\" for c in filename)
            or len(raw) > MAX_BYTES
        ):
            raise MemoryError("Choose a supported document of at most 8 MiB")
        extension = filename.rsplit(".", 1)[-1].lower()
        digest = hashlib.sha256(raw).hexdigest()
        with Session(self.engine) as db:
            existing = db.scalar(
                select(Document)
                .where(
                    Document.user_id == actor.id,
                    Document.content_hash == digest,
                    Document.deleted_at.is_(None),
                )
                .limit(1)
            )
            if existing is not None:
                return self.view(existing)
        try:
            extracted = extract_document(raw, extension, options or PreviewOptions())
        except Exception:
            raise MemoryError(
                "Document could not be read within its limits; "
                "check format, encoding and selection"
            ) from None
        with self.memory._write() as db:
            if active:
                active()
            existing = db.scalar(
                select(Document)
                .where(
                    Document.user_id == actor.id,
                    Document.content_hash == digest,
                    Document.deleted_at.is_(None),
                )
                .limit(1)
            )
            if existing is not None:
                return self.view(existing)
            count, size = db.execute(
                select(
                    func.count(Document.id), func.coalesce(func.sum(Document.size), 0)
                ).where(Document.user_id == actor.id, Document.deleted_at.is_(None))
            ).one()
            if count >= 200 or size + len(raw) > 256 * 1024 * 1024:
                raise MemoryError("Private document storage quota reached")
            now = self.memory.clock()
            row = Document(
                id=str(uuid4()),
                user_id=actor.id,
                content_hash=digest,
                filename=filename,
                format=extension,
                extraction_metadata=json.dumps(extracted.metadata, ensure_ascii=False),
                size=len(raw),
                pages=extracted.pages,
                extracted_text=extracted.text,
                text_truncated=extracted.truncated,
                original=raw,
                source_id=None,
                created_at=now,
                updated_at=now,
                deleted_at=None,
            )
            db.add(row)
            db.flush()
            self.memory._audit(db, actor, "document_uploaded", row.id, now)
            return self.view(row)

    def preview(self, actor: Account, value: DocumentPreview) -> dict[str, Any]:
        data = DocumentPreview.model_validate(value)
        with Session(self.engine) as db:
            row = self.owned(db, actor, data.document_id)
            if row.deleted_at is not None or row.original is None:
                raise MemoryError("Original document was deleted")
            extension, raw = row.format, row.original
        try:
            return extract_document(
                raw,
                extension,
                PreviewOptions.model_validate(data.model_dump(exclude={"document_id"})),
            ).model_dump()
        except Exception:
            raise MemoryError(
                "Preview failed; check encoding, delimiter and worksheet/range limits"
            ) from None

    def save_text(self, actor: Account, value: DocumentText) -> dict[str, Any]:
        data = DocumentText.model_validate(value)
        with self.memory._write() as db:
            row = self.owned(db, actor, data.document_id)
            if row.deleted_at is not None:
                raise MemoryError("Document was deleted")
            if row.source_id:
                if self.memory._source(db, actor, row.source_id).text != data.text:
                    raise NoteConflict(
                        "Text was already saved. Correct the saved source instead."
                    )
                return self.view(row)
            if row.updated_at != data.expected_updated_at:
                raise NoteConflict("Document changed. Reload before saving.")
            source = self.memory._ingest_in(
                db,
                actor,
                SourceInput(
                    text=data.text,
                    source_type="import",
                    namespace="pdf-memory"
                    if row.format == "pdf"
                    else "document-memory",
                    external_id=row.id,
                ),
            )
            row.source_id = source.id
            row.updated_at = max(self.memory.clock(), row.updated_at + 1)
            self.memory._audit(
                db, actor, "document_text_reviewed", row.id, row.updated_at
            )
            db.flush()
            return self.view(row)

    def delete(self, actor: Account, value: DocumentDelete) -> dict[str, Any]:
        data = DocumentDelete.model_validate(value)
        with self.memory._write() as db:
            row = self.owned(db, actor, data.document_id)
            if row.deleted_at is None:
                if row.updated_at != data.expected_updated_at:
                    raise NoteConflict("Document changed. Reload before deleting.")
                row.deleted_at = self.memory.clock()
                row.updated_at = max(row.deleted_at, row.updated_at + 1)
                row.original = None
                row.extracted_text = ""
                self.memory._audit(
                    db, actor, "document_deleted", row.id, row.deleted_at
                )
            return self.view(row)

    def source_document(self, actor: Account, source_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as db:
            source = self.memory._source(db, actor, source_id)
            root = NoteService._root(db, actor, source)
            row = db.scalar(
                select(Document)
                .where(Document.user_id == actor.id, Document.source_id == root)
                .limit(1)
            )
            return self.view(row, include_text=False) if row else None
