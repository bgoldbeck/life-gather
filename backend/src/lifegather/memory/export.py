"""Bounded personal record portability, separate from installation backups."""

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, cast

from sqlalchemy import Connection, Engine, Table, select

from lifegather.assets.models import AssetAction, AssetConsolidation
from lifegather.auth.models import Base
from lifegather.auth.store import Account
from lifegather.chat.models import Conversation, Turn
from lifegather.documents.models import Document
from lifegather.maintenance.models import MaintenanceRevision, MaintenanceTask
from lifegather.memory.models import (
    Alias,
    Assertion,
    Audit,
    Entity,
    Episode,
    Evidence,
    NoteRevision,
)
from lifegather.photos.models import Photo, PhotoAsset
from lifegather.purchases.models import PurchaseEvidence
from lifegather.reconciliation.models import (
    Binding,
    Candidate,
    Decision,
    Observation,
    Purchase,
    PurchaseLine,
)
from lifegather.reconciliation.proposal_models import AssetProposal
from lifegather.reconciliation.receipt_models import ReceiptDetail, ReceiptProposal
from lifegather.version import __version__

FORMAT = "lifegather-records/3"
MAX_RECORDS = 10_000
MAX_BYTES = 16 * 1024 * 1024


class ExportLimitError(ValueError):
    """No complete download can be produced within the fixed limits."""


@dataclass(frozen=True)
class Projection:
    model: type[Base]
    fields: str

    @property
    def table(self) -> Table:
        return cast(Table, self.model.__table__)


# Frozen format contract: additions need explicit privacy review and tests.
# Never select an entire ORM row or infer exportability from a user_id column.
COLLECTIONS = (
    Projection(
        MaintenanceTask,
        "id entity_id source_id request_id fingerprint recorded_at",
    ),
    Projection(
        MaintenanceRevision,
        "id task_id previous_id title due_on timezone state completed_on source_id "
        "request_id fingerprint recorded_at superseded_at",
    ),
    Projection(
        AssetConsolidation,
        "id primary_id secondary_id source_id request_id fingerprint state_token "
        "recorded_at superseded_at reverse_source_id reverse_request_id "
        "reverse_fingerprint",
    ),
    Projection(
        Episode,
        "id source_key text source_type namespace external_id "
        "content_hash event_date recorded_at",
    ),
    Projection(
        Entity,
        "id name normalized_name kind source_id operation_key fingerprint recorded_at",
    ),
    Projection(Alias, "id entity_id name normalized_name source_id recorded_at"),
    Projection(
        Assertion,
        "id subject_id predicate object_id value_json status "
        "valid_from valid_to recorded_at superseded_at replaces_id operation_key "
        "fingerprint",
    ),
    Projection(Evidence, "id fact_id source_id quote recorded_at"),
    Projection(Audit, "id operation target_id recorded_at provenance_json"),
    Projection(
        NoteRevision,
        "id root_source_id previous_source_id source_id request_id "
        "fingerprint recorded_at",
    ),
    Projection(
        Purchase,
        "id identity_key retailer account_scope order_id source_id recorded_at",
    ),
    Projection(
        PurchaseLine,
        "id purchase_id line_key product_id quantity source_id recorded_at",
    ),
    Projection(
        Observation,
        "id source_id item_key payload fingerprint product_id "
        "line_id serial_key recorded_at",
    ),
    Projection(
        Decision,
        "id observation_id previous_id outcome reason request_key "
        "superseded_at recorded_at",
    ),
    Projection(
        Binding,
        "id decision_id unit asset_id ownership_fact_id product_fact_id recorded_at",
    ),
    Projection(Candidate, "id decision_id asset_id recorded_at"),
    Projection(
        AssetAction,
        "id asset_id target_asset_id previous_id source_id request_id "
        "fingerprint operation ownership_fact_id status_fact_id result_json "
        "recorded_at",
    ),
    Projection(
        AssetProposal,
        "id source_id recorded_at state proposed_json reviewed_json "
        "observation_id request_id fingerprint result_json reviewed_at",
    ),
    Projection(
        ReceiptProposal,
        "id source_id state proposed_json reviewed_json "
        "result_json request_id fingerprint recorded_at reviewed_at",
    ),
    Projection(
        ReceiptDetail,
        "id receipt_id source_id line_index revision total_minor "
        "currency money_quote purchase_date date_quote reason request_id "
        "fingerprint recorded_at",
    ),
    Projection(
        PurchaseEvidence,
        "id purchase_id source_id root_source_id revision "
        "previous_id superseded_at state role quote amount_minor currency "
        "money_quote occurred_on date_quote reason request_id fingerprint "
        "recorded_at",
    ),
    Projection(Conversation, "id title created_at"),
    Projection(
        Turn,
        "id conversation_id request_id mode text fingerprint state "
        "result_json created_at",
    ),
    Projection(
        Photo,
        "id content_hash filename mime purpose size width height "
        "preview_size source_id created_at updated_at deleted_at",
    ),
    Projection(PhotoAsset, "id photo_id asset_id recorded_at"),
    Projection(
        Document,
        "id content_hash filename size pages extracted_text format extraction_metadata "
        "text_truncated source_id created_at updated_at deleted_at",
    ),
)

EXCLUSIONS = (
    "account identity, authentication, sessions and stored credentials",
    "settings, connector configuration, scan/schedule state and AI extraction caches",
    "photo originals/previews and original PDF files (metadata/text only)",
    "search indexes and installation configuration",
)


def json_date(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError("Unsupported export value")


class RecordExport:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def download(self, actor: Account) -> bytes:
        """Build one complete owner-only snapshot in memory, or return no file."""
        # SQLite legacy mode needs a real BEGIN, not just SQLAlchemy autobegin.
        with self.engine.connect() as connection:
            connection.exec_driver_sql("BEGIN")
            return self.render_in(connection, actor)

    def render_in(
        self,
        connection: Connection,
        actor: Account,
        *,
        snapshot_at: datetime | None = None,
    ) -> bytes:
        """Render inside the caller's existing read snapshot without closing it."""
        if not connection.in_transaction():
            raise ValueError("Record rendering requires an active read snapshot")
        encoder = json.JSONEncoder(
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            default=json_date,
        )
        buffer = bytearray()

        def append(raw: str) -> None:
            encoded = raw.encode("utf-8")
            if len(buffer) + len(encoded) > MAX_BYTES:
                raise ExportLimitError(
                    "Record export exceeds the 16 MiB download limit"
                )
            buffer.extend(encoded)

        def encode(value: Any) -> None:
            for chunk in encoder.iterencode(value):
                append(chunk)

        counts: dict[str, int] = {}
        total = 0
        append('{"format":')
        encode(FORMAT)
        append(',"application_version":')
        encode(__version__)
        append(',"snapshot_at":')
        encode((snapshot_at or datetime.now(UTC)).isoformat())
        append(',"purpose":"personal record portability; not a restorable backup"')
        append(',"excluded":')
        encode(EXCLUSIONS)
        append(',"collections":{')
        for index, projection in enumerate(COLLECTIONS):
            table = projection.table
            columns = [table.c[field] for field in projection.fields.split()]
            if index:
                append(",")
            encode(table.name)
            append(":[")
            count = 0
            rows = connection.execute(
                select(*columns)
                .where(table.c.user_id == actor.id)
                .order_by(table.c.id)
                .limit(MAX_RECORDS - total + 1)
            ).mappings()
            for row in rows:
                if total >= MAX_RECORDS:
                    raise ExportLimitError(
                        "Record export exceeds the 10,000-record download limit"
                    )
                if count:
                    append(",")
                record = dict(row)
                # The legacy storage column is PDF-specific, not a page count
                # inferred for reflowable/tabular documents.
                if table.name == "documents" and record["format"] != "pdf":
                    record["pages"] = None
                encode(record)
                count += 1
                total += 1
            counts[table.name] = count
            append("]")
        append('},"counts":')
        encode(counts)
        append(',"total_records":')
        encode(total)
        append("}")
        return bytes(buffer)
