"""Explicit manual inventory declarations using shared physical identity rules."""

import json
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from lifegather.assets.type_schemas import FieldValue, TypeAssign, TypeFieldSave
from lifegather.assets.types import AssetTypes
from lifegather.auth.store import Account
from lifegather.memory.history import event_origin
from lifegather.memory.models import Assertion, Entity
from lifegather.memory.notes import NoteConflict
from lifegather.memory.origins import change_origin
from lifegather.memory.schemas import FactInput, SourceInput
from lifegather.memory.service import MemoryError, MemoryService, fingerprint
from lifegather.reconciliation.inventory import current_ownership
from lifegather.reconciliation.proposals import ProposalService
from lifegather.reconciliation.schemas import DiscoveryInput
from lifegather.reconciliation.service import ReconciliationService


class ManualAssetFields(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, revalidate_instances="always"
    )
    name: str = Field(min_length=1, max_length=200)
    manufacturer: str | None = Field(default=None, min_length=1, max_length=100)
    model: str | None = Field(default=None, min_length=1, max_length=100)
    serial: str | None = Field(default=None, min_length=1, max_length=100)
    notes: str = Field(default="", max_length=2000)
    ownership_confirmed: StrictBool
    type_id: str | None = Field(default=None, min_length=1, max_length=36)
    type_revision: str | None = Field(default=None, min_length=1, max_length=100)
    type_values: list[FieldValue] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def declaration(self) -> Self:
        if (
            sum(len(value.text) + len(value.value or "") for value in self.type_values)
            > 12000
        ):
            raise ValueError("Template values and evidence exceed the entry limit")
        if bool(self.type_id) != bool(self.type_revision) or (
            self.type_values and not self.type_id
        ):
            raise ValueError(
                "Typed entry requires a selected type and current revision"
            )
        if len({value.field_id for value in self.type_values}) != len(self.type_values):
            raise ValueError("Supply each template field only once")
        if not self.ownership_confirmed:
            raise ValueError("Confirm current ownership to add inventory")
        if any(
            value is not None and (not value.strip() or "\n" in value or "\r" in value)
            for value in (self.name, self.manufacturer, self.model, self.serial)
        ):
            raise ValueError("Identity fields need nonblank single-line values")
        if (self.model or self.serial) and not self.manufacturer:
            raise ValueError("Supply manufacturer context for model or serial")
        return self

    def quote(self) -> str:
        lines = ["Manual asset entry", f"Name: {self.name}"]
        for field in ("manufacturer", "model", "serial"):
            if value := getattr(self, field):
                lines.append(f"{field.title()}: {value}")
        return "\n".join([*lines, "Ownership: I currently own this item."])

    def discovery(self, source_id: str) -> DiscoveryInput:
        return DiscoveryInput(
            source_id=source_id,
            item_key="manual-asset",
            name=self.name,
            manufacturer=self.manufacturer,
            model=self.model,
            serial=self.serial,
            kind="possession",
            quantity=1,
            quote=self.quote(),
        )


class ManualAssetCreate(ManualAssetFields):
    request_id: str = Field(min_length=1, max_length=100)
    action: Literal["new", "link"] = "new"
    asset_id: str | None = Field(default=None, min_length=1, max_length=36)
    candidate_ids: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def choice(self) -> Self:
        if (self.action == "link") != (self.asset_id is not None):
            raise ValueError("Choose a target only when linking an existing asset")
        if len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise ValueError("Duplicate candidate identifiers")
        return self


class ManualAssets:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.memory = MemoryService(engine)
        self.reconcile = ReconciliationService(engine)
        self.proposals = ProposalService(engine)
        self.types = AssetTypes(engine)

    def check_type(self, db: Session, actor: Account, data: ManualAssetFields) -> None:
        if data.type_id:
            template = self.types._get(db, actor, data.type_id)
            if template["retired"] or template["revision"] != data.type_revision:
                raise NoteConflict(
                    "Asset type changed or retired. Reload the type before saving."
                )
            active = {
                field["id"] for field in template["fields"] if not field["retired"]
            }
            if any(value.field_id not in active for value in data.type_values):
                raise MemoryError("Choose active fields from the selected private type")

    def matches(
        self, db: Session, actor: Account, fields: ManualAssetFields
    ) -> tuple[list[str], list[str]]:
        candidates, reliable = self.proposals._matches(
            db, actor, fields.discovery("preview")
        )
        if len(candidates) >= 100:
            raise NoteConflict(
                "Too many possible matches; narrow the name or identifiers"
            )
        return candidates, reliable

    @staticmethod
    def excluded(db: Session, actor: Account, identifier: str) -> bool:
        return (
            db.scalar(
                select(Entity.id)
                .where(
                    Entity.id == identifier,
                    Entity.user_id == actor.id,
                    current_ownership(actor, False),
                )
                .limit(1)
            )
            is not None
        )

    def preview(self, actor: Account, value: ManualAssetFields) -> dict[str, Any]:
        data = ManualAssetFields.model_validate(value)
        with Session(self.engine) as db:
            db.connection().exec_driver_sql("BEGIN")
            self.check_type(db, actor, data)
            candidates, reliable = self.matches(db, actor, data)
            return {
                "candidates": [
                    {
                        "id": identifier,
                        "name": self.memory._entity(db, actor, identifier).name,
                        "can_link": not self.excluded(db, actor, identifier),
                    }
                    for identifier in candidates
                ],
                "reliable_ids": reliable,
            }

    def result(
        self, db: Session, actor: Account, source_id: str, asset_id: str, created: bool
    ) -> dict[str, Any]:
        asset = self.memory._entity(db, actor, asset_id)
        return {
            "asset": {"id": asset.id, "name": asset.name},
            "source_id": source_id,
            "created": created,
        }

    def save(self, actor: Account, value: ManualAssetCreate) -> dict[str, Any]:
        data = ManualAssetCreate.model_validate(value)
        with self.memory._write() as db, change_origin(method="manual_entry"):
            source = self.memory._ingest_in(
                db,
                actor,
                SourceInput(
                    text=(
                        f"{data.quote()}\nNotes:\n{data.notes}\n"
                        f"Identity choice: {data.action}\n"
                        f"Target: {data.asset_id or 'new item'}"
                        + (
                            "\nAsset type input:\n"
                            + json.dumps(
                                {
                                    "type_id": data.type_id,
                                    "type_revision": data.type_revision,
                                    "type_values": [
                                        item.model_dump(mode="json")
                                        for item in data.type_values
                                    ],
                                },
                                sort_keys=True,
                                ensure_ascii=False,
                            )
                            if data.type_id
                            else ""
                        )
                    ),
                    namespace="manual-assets",
                    external_id=data.request_id,
                ),
            )
            saved = event_origin(db, actor, source.id, ("manual_asset_saved",))
            if saved and saved.get("related_id"):
                return self.result(
                    db, actor, source.id, saved["related_id"], data.action == "new"
                )
            candidates, reliable = self.matches(db, actor, data)
            self.check_type(db, actor, data)
            if sorted(data.candidate_ids) != candidates:
                raise NoteConflict(
                    "Possible matches changed. Check duplicates again before saving."
                )
            if data.action == "new" and reliable:
                raise NoteConflict(
                    "This identifier already matches an item; use that existing asset"
                )
            if data.action == "link":
                if data.asset_id not in candidates or (
                    reliable and data.asset_id not in reliable
                ):
                    raise NoteConflict(
                        "Choose a matching item from the current duplicate check"
                    )
                assert data.asset_id is not None
                if self.excluded(db, actor, data.asset_id):
                    raise NoteConflict(
                        "This item has an ownership correction. "
                        "Update ownership in its details first."
                    )
            discovery = self.reconcile._discover_in(
                db, actor, data.discovery(source.id), ownership_status="stated"
            )
            if discovery.outcome == "review" or (
                data.action == "link" and discovery.asset_ids != [data.asset_id]
            ):
                discovery = self.reconcile._change_in(
                    db,
                    actor,
                    discovery.id,
                    discovery.decision_id,
                    "resolve",
                    [data.asset_id] if data.asset_id else None,
                    ownership_status="stated",
                )
            asset_id = discovery.asset_ids[0]
            if data.type_id:
                from lifegather.assets.identity import member_ids

                assignments = list(
                    db.scalars(
                        select(Assertion)
                        .where(
                            Assertion.user_id == actor.id,
                            Assertion.subject_id.in_(member_ids(db, actor, asset_id)),
                            Assertion.predicate == "profile_asset_type",
                            Assertion.superseded_at.is_(None),
                        )
                        .limit(3)
                    )
                )
                if not assignments:
                    self.types._assign_in(
                        db,
                        actor,
                        TypeAssign(
                            entity_id=asset_id,
                            type_id=data.type_id,
                            request_id="manual:" + fingerprint(data.request_id),
                        ),
                    )
                elif any(
                    row.value_json != json.dumps(data.type_id) for row in assignments
                ):
                    raise NoteConflict(
                        "Different type. Change it explicitly in asset details first."
                    )
                for field_value in data.type_values:
                    self.types._field_in(
                        db,
                        actor,
                        TypeFieldSave(
                            entity_id=asset_id,
                            type_id=data.type_id,
                            request_id="manual:"
                            + fingerprint([data.request_id, field_value.field_id]),
                            **field_value.model_dump(),
                        ),
                    )
            for field in ("manufacturer", "model", "serial"):
                if entry := getattr(data, field):
                    self.memory._put_fact_in(
                        db,
                        actor,
                        FactInput(
                            subject_id=asset_id,
                            predicate="profile_" + field,
                            value=entry,
                            source_id=source.id,
                            quote=f"{field.title()}: {entry}",
                            operation_key=f"manual:{data.request_id}:{field}",
                        ),
                        None,
                    )
            with change_origin(related_id=asset_id):
                self.memory._audit(
                    db, actor, "manual_asset_saved", source.id, self.memory.clock()
                )
            db.flush()
            return self.result(db, actor, source.id, asset_id, data.action == "new")
