"""Private bounded field timelines over original immutable facts and audits."""

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, and_, or_, select
from sqlalchemy.orm import Session

from lifegather.auth.store import Account
from lifegather.memory.models import Assertion, Audit
from lifegather.memory.origins import ChangeOrigin
from lifegather.memory.service import MemoryError, MemoryService


class FieldHistoryRead(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    entity_id: str = Field(min_length=1, max_length=36)
    field: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    cursor: str = Field(default="", max_length=36)
    limit: int = Field(default=5, ge=1, le=10)


def event_origin(
    db: Session, actor: Account, target: str, operations: tuple[str, ...]
) -> dict[str, Any] | None:
    value = db.scalar(
        select(Audit.provenance_json)
        .where(
            Audit.user_id == actor.id,
            Audit.target_id == target,
            Audit.operation.in_(operations),
        )
        .order_by(Audit.recorded_at, Audit.id)
        .limit(1)
    )
    return ChangeOrigin.model_validate_json(value).model_dump() if value else None


class FieldHistory:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.memory = MemoryService(engine)

    def get(self, actor: Account, value: FieldHistoryRead) -> dict[str, Any]:
        data = FieldHistoryRead.model_validate(value)
        with Session(self.engine) as db:
            db.connection().exec_driver_sql("BEGIN")
            entity = self.memory._entity(db, actor, data.entity_id)
            query = select(Assertion).where(
                Assertion.user_id == actor.id,
                Assertion.subject_id == entity.id,
                Assertion.predicate == data.field,
            )
            if data.cursor:
                cursor = self.memory._assertion(db, actor, data.cursor)
                if cursor.subject_id != entity.id or cursor.predicate != data.field:
                    raise MemoryError("Choose a cursor from this record and field")
                query = query.where(
                    or_(
                        Assertion.recorded_at > cursor.recorded_at,
                        and_(
                            Assertion.recorded_at == cursor.recorded_at,
                            Assertion.id > cursor.id,
                        ),
                    )
                )
            rows = list(
                db.scalars(
                    query.order_by(Assertion.recorded_at, Assertion.id).limit(
                        data.limit + 1
                    )
                )
            )
            items = []
            for row in rows[: data.limit]:
                view = self.memory._view(db, actor, row).model_dump(mode="json")
                previous = (
                    self.memory._assertion(db, actor, row.replaces_id)
                    if row.replaces_id
                    else None
                )
                evidence = []
                origin = event_origin(
                    db, actor, row.id, ("fact_asserted", "fact_corrected")
                )
                proposal_origin = (
                    event_origin(
                        db,
                        actor,
                        origin["related_id"],
                        ("asset_proposed", "receipt_proposed"),
                    )
                    if origin
                    and origin.get("method") == "review"
                    and origin.get("related_id")
                    else None
                )
                for entry in view["evidence"][:3]:
                    source = self.memory._source(db, actor, entry["source_id"])
                    quote = entry["quote"] or ""
                    evidence.append(
                        {
                            **entry,
                            "quote": quote[:400],
                            "quote_truncated": len(quote) > 400,
                            "source_type": source.source_type,
                            "source_origin": event_origin(
                                db, actor, source.id, ("source_ingested",)
                            ),
                        }
                    )
                items.append(
                    {
                        **view,
                        "evidence": evidence,
                        "more_evidence": len(view["evidence"]) > 3,
                        "previous": (
                            {
                                "id": previous.id,
                                "value": json.loads(previous.value_json)
                                if previous.value_json is not None
                                else None,
                                "object_id": previous.object_id,
                                "status": previous.status,
                            }
                            if previous
                            else None
                        ),
                        "origin": origin,
                        "proposal_origin": proposal_origin,
                    }
                )
            result = {
                "entity_id": entity.id,
                "field": data.field,
                "items": items,
                "next_cursor": rows[data.limit - 1].id
                if len(rows) > data.limit
                else None,
            }
            if len(json.dumps(result, ensure_ascii=False).encode()) > 32768:
                raise MemoryError(
                    "Field history exceeds the response limit; request a smaller page"
                )
            return result
