"""Explicit owner-scoped record snapshots, never global browser focus."""

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from lifegather.assets.identity import canonical_id, identity_group, member_ids
from lifegather.auth.store import Account
from lifegather.memory.models import Assertion
from lifegather.memory.service import MemoryError, MemoryService, fingerprint

PageName = Literal[
    "Overview",
    "Assets",
    "Profiles",
    "Maintenance",
    "Graph",
    "Memories",
    "Photos",
    "Documents",
    "Scans",
    "Purchases",
    "Review",
    "Settings",
]


class ContextRead(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, revalidate_instances="always"
    )
    page: PageName
    entity_id: str | None = Field(default=None, min_length=1, max_length=36)

    @model_validator(mode="after")
    def record_page(self) -> "ContextRead":
        if self.entity_id and self.page not in {"Assets", "Profiles", "Graph"}:
            raise ValueError("Record context belongs to Assets, Profiles or Graph")
        return self


class ContextRef(ContextRead):
    version: str = Field(default="", max_length=64, pattern=r"^(?:[a-f0-9]{64})?$")


class WorkspaceContexts:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.memory = MemoryService(engine)

    def read(self, actor: Account, value: ContextRead) -> dict[str, Any]:
        with Session(self.engine) as db:
            db.connection().exec_driver_sql("BEGIN")
            return self.read_in(db, actor, value)

    def read_in(
        self, db: Session, actor: Account, value: ContextRead
    ) -> dict[str, Any]:
        if not value.entity_id:
            return {
                "page": value.page,
                "entity_id": None,
                "name": None,
                "version": "",
                "fields": {},
            }
        entity = self.memory._entity(db, actor, value.entity_id)
        group = identity_group(db, actor, entity.id)
        identifiers = member_ids(db, actor, entity.id)
        entity = self.memory._entity(db, actor, canonical_id(db, actor, entity.id))
        rows = list(
            db.scalars(
                select(Assertion)
                .where(
                    Assertion.user_id == actor.id,
                    Assertion.subject_id.in_(identifiers),
                    Assertion.predicate.startswith("profile_", autoescape=True),
                    Assertion.superseded_at.is_(None),
                )
                .order_by(Assertion.predicate, Assertion.id)
                .limit(101)
            )
        )
        if len(rows) > 100:
            raise MemoryError(
                "Too many active profile details; review the profile first"
            )
        fields: dict[str, Any] = {}
        for row in rows:
            field = row.predicate.removeprefix("profile_")
            entry = fields.setdefault(field, {"count": 0, "statements": []})
            entry["count"] += 1
            if len(entry["statements"]) < 2:
                literal = json.loads(row.value_json) if row.value_json else None
                entry["statements"].append(
                    {
                        "id": row.id,
                        "value": literal[:300] if isinstance(literal, str) else literal,
                        "value_truncated": isinstance(literal, str)
                        and len(literal) > 300,
                        "status": row.status,
                    }
                )
        return {
            "page": value.page,
            "entity_id": entity.id,
            "name": entity.name,
            "kind": entity.kind,
            "version": fingerprint(
                [entity.id, entity.name, [row.id for row in rows]]
                + ([group.id] if group else [])
            ),
            "fields": fields,
        }
