"""Sourced home/vehicle details on existing memory records, without model calls."""

from datetime import date
from typing import Any, Literal, Self

from pydantic import Field, model_validator
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from lifegather.auth.store import Account
from lifegather.memory.models import Assertion
from lifegather.memory.schemas import (
    EntityInput,
    EntityView,
    FactInput,
    FactView,
    Input,
    SourceInput,
)
from lifegather.memory.service import MemoryError, MemoryService

ProfileField = Literal[
    "manufacturer",
    "model",
    "serial",
    "vin",
    "filter_dimensions",
    "paint",
    "maintenance",
    "specification",
]


class ProfileRead(Input):
    entity_id: str = Field(min_length=1, max_length=36)
    history: bool = False
    cursor: str | None = Field(default=None, max_length=36)


class ProfileCreate(Input):
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["home", "vehicle"]
    text: str = Field(min_length=1, max_length=4000)
    operation_key: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def nonempty(self) -> Self:
        if not self.name.strip() or not self.text.strip():
            raise ValueError("Name and source statement cannot be blank")
        return self


class ProfileChange(Input):
    entity_id: str = Field(min_length=1, max_length=36)
    field: ProfileField
    value: str | None = Field(max_length=500)
    text: str = Field(min_length=1, max_length=4000)
    status: Literal["stated", "inferred", "unknown"] = "stated"
    valid_from: date | None = None
    valid_to: date | None = None
    replaces_id: str | None = Field(default=None, min_length=1, max_length=36)
    operation_key: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def sourced(self) -> Self:
        if not self.text.strip() or (
            self.value is not None
            and (not self.value.strip() or self.value not in self.text)
        ):
            raise ValueError("The exact value must appear in the source text")
        if (self.status == "unknown") != (self.value is None):
            raise ValueError(
                "Unknown requires null; supplied values need stated or inferred status"
            )
        if self.valid_from and self.valid_to and self.valid_from >= self.valid_to:
            raise ValueError("End date must follow start date")
        return self


class ProfileService:
    def __init__(self, engine: Engine) -> None:
        self.memory = MemoryService(engine)

    def create(self, actor: Account, value: ProfileCreate) -> EntityView:
        data = ProfileCreate.model_validate(value)
        with self.memory._write() as db:
            source = self.memory._ingest_in(
                db,
                actor,
                SourceInput(
                    text=(
                        f"Record name: {data.name}\n"
                        f"Profile kind: {data.kind}\n{data.text}"
                    ),
                    namespace="profiles",
                    external_id=data.operation_key,
                ),
            )
            entity = self.memory._create_entity_in(
                db,
                actor,
                EntityInput(
                    name=data.name,
                    kind="place" if data.kind == "home" else "asset",
                    source_id=source.id,
                    operation_key="profile:" + data.operation_key,
                ),
            )
            self.memory._put_fact_in(
                db,
                actor,
                FactInput(
                    subject_id=entity.id,
                    predicate="profile_kind",
                    value=data.kind,
                    source_id=source.id,
                    quote=f"Profile kind: {data.kind}",
                    operation_key="profile-kind:" + data.operation_key,
                ),
                None,
            )
            return entity

    def save(self, actor: Account, value: ProfileChange) -> FactView:
        data = ProfileChange.model_validate(value)
        with self.memory._write() as db:
            entity = self.memory._entity(db, actor, data.entity_id)
            if entity.kind not in {"asset", "place"}:
                raise MemoryError("Profiles require an asset or place record")
            source = self.memory._ingest_in(
                db,
                actor,
                SourceInput(
                    text=data.text,
                    namespace="profile-facts",
                    external_id=data.operation_key,
                ),
            )
            return self.memory._put_fact_in(
                db,
                actor,
                FactInput(
                    subject_id=entity.id,
                    predicate="profile_" + data.field,
                    value=data.value,
                    status=data.status,
                    source_id=source.id,
                    quote=data.value or data.text[:500],
                    valid_from=data.valid_from,
                    valid_to=data.valid_to,
                    operation_key="profile-fact:" + data.operation_key,
                ),
                data.replaces_id,
            )

    def get(
        self,
        actor: Account,
        entity_id: str,
        *,
        history: bool = False,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        with Session(self.memory.engine) as db:
            entity = self.memory._entity(db, actor, entity_id)
            if entity.kind not in {"asset", "place"}:
                raise MemoryError("Profiles require an asset or place record")
            query = select(Assertion).where(
                Assertion.user_id == actor.id,
                Assertion.subject_id == entity.id,
                Assertion.predicate.startswith("profile_", autoescape=True),
            )
            if not history:
                query = query.where(Assertion.superseded_at.is_(None))
            query = self.memory._after(db, actor, entity.id, query, cursor)
            rows = list(
                db.scalars(
                    query.order_by(Assertion.recorded_at, Assertion.id).limit(25)
                )
            )
            return {
                "entity": EntityView.model_validate(entity),
                "facts": [self.memory._view(db, actor, row) for row in rows],
                "next_cursor": rows[-1].id if len(rows) == 25 else None,
            }
