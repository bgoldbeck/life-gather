"""Editable private templates, backed by shared sourced assertions and identity."""

import json
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import Engine, and_, or_, select
from sqlalchemy.orm import Session

from lifegather.assets.identity import canonical_id, member_ids
from lifegather.assets.type_models import AssetType, AssetTypeField, AssetTypeRevision
from lifegather.assets.type_schemas import TypeAssign, TypeFieldSave, TypeSave
from lifegather.auth.store import Account
from lifegather.memory.models import Assertion
from lifegather.memory.notes import NoteConflict
from lifegather.memory.schemas import FactInput, FactView, SourceInput
from lifegather.memory.service import MemoryError, MemoryService, fingerprint

STARTERS = (
    (
        "vehicle",
        "Vehicle",
        ("Year", "VIN", "Odometer with units", "Fuel or power type", "Tire size"),
    ),
    (
        "appliance",
        "Appliance",
        (
            "Appliance category",
            "Dimensions with units",
            "Power requirements",
            "Filter specification",
        ),
    ),
    (
        "electronics",
        "Electronics",
        ("Device category", "Capacity or storage", "Connectors", "Power requirements"),
    ),
    (
        "furniture",
        "Furniture",
        ("Dimensions with units", "Material", "Finish or color"),
    ),
    (
        "tools",
        "Tools & Equipment",
        (
            "Tool category",
            "Power source",
            "Battery specification",
            "Consumable specification",
        ),
    ),
)
PREFIX = "profile_template_"


def starter(
    actor: Account, key: str, name: str, labels: tuple[str, ...]
) -> dict[str, Any]:
    identifier = str(uuid5(NAMESPACE_URL, f"lifegather:{actor.id}:asset-type:{key}"))
    return {
        "id": identifier,
        "name": name,
        "description": "",
        "retired": False,
        "revision": str(uuid5(NAMESPACE_URL, identifier + ":seed:1")),
        "seed_key": key,
        "fields": [
            {
                "id": uuid5(NAMESPACE_URL, identifier + ":" + label).hex,
                "name": label,
                "system_field": "vin" if label == "VIN" else None,
                "retired": False,
            }
            for label in labels
        ],
    }


def predicate(field: dict[str, Any]) -> str:
    return "profile_vin" if field["system_field"] == "vin" else PREFIX + field["id"]


def compact_fact(fact: FactView) -> dict[str, Any]:
    result = fact.model_dump(mode="json")
    result["more_evidence"] = len(fact.evidence) > 5
    result["evidence"] = [{"source_id": row["source_id"]} for row in fact.evidence[:5]]
    return result


class AssetTypes:
    def __init__(self, engine: Engine) -> None:
        self.memory = MemoryService(engine)

    @staticmethod
    def _row(db: Session, actor: Account, identifier: str) -> AssetType | None:
        return db.scalar(
            select(AssetType).where(
                AssetType.user_id == actor.id, AssetType.id == identifier
            )
        )

    def _get(self, db: Session, actor: Account, identifier: str) -> dict[str, Any]:
        row = self._row(db, actor, identifier)
        if row is None:
            for key, name, labels in STARTERS:
                value = starter(actor, key, name, labels)
                if value["id"] == identifier:
                    return value
            raise MemoryError("Asset type not found")
        fields = list(
            db.scalars(
                select(AssetTypeField)
                .where(
                    AssetTypeField.user_id == actor.id,
                    AssetTypeField.type_id == identifier,
                )
                .order_by(AssetTypeField.position, AssetTypeField.id)
                .limit(32)
            )
        )
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "retired": row.retired,
            "revision": row.revision,
            "seed_key": row.seed_key,
            "fields": [
                {
                    "id": field.id,
                    "name": field.name,
                    "system_field": field.system_field,
                    "retired": field.retired,
                }
                for field in fields
            ],
        }

    def _materialize(
        self, db: Session, actor: Account, value: dict[str, Any]
    ) -> AssetType:
        row = self._row(db, actor, value["id"])
        if row is not None:
            return row
        row = AssetType(
            id=value["id"],
            user_id=actor.id,
            seed_key=value["seed_key"],
            name=value["name"],
            description=value["description"],
            retired=value["retired"],
            revision=value["revision"],
        )
        db.add(row)
        db.flush()
        for position, field in enumerate(value["fields"]):
            db.add(
                AssetTypeField(
                    user_id=actor.id, type_id=row.id, position=position, **field
                )
            )
        db.add(
            AssetTypeRevision(
                id=value["revision"],
                user_id=actor.id,
                type_id=row.id,
                previous_id=None,
                request_id="seed:" + row.id,
                fingerprint=fingerprint(value),
                definition_json=json.dumps(value),
                recorded_at=self.memory.clock(),
            )
        )
        db.flush()
        return row

    def list(
        self, actor: Account, include_retired: bool = False, cursor: str = ""
    ) -> dict[str, Any]:
        with Session(self.memory.engine) as db:
            db.connection().exec_driver_sql("BEGIN")
            rows = list(
                db.scalars(
                    select(AssetType)
                    .where(AssetType.user_id == actor.id)
                    .order_by(AssetType.id)
                    .limit(51)
                )
            )
            if len(rows) > 50:
                raise MemoryError("Asset type limit exceeded")
            # A restored archive keeps the starter rows saved under its original
            # account's IDs; list those instead of a second unsaved starter.
            saved = {row.seed_key for row in rows if row.seed_key}
            defaults = [
                value
                for value in (starter(actor, *item) for item in STARTERS)
                if value["seed_key"] not in saved
                or any(row.id == value["id"] for row in rows)
            ]
            identifiers = [value["id"] for value in defaults]
            identifiers.extend(row.id for row in rows if row.id not in identifiers)
            items = [self._get(db, actor, identifier) for identifier in identifiers]
            if cursor:
                if cursor not in identifiers:
                    raise MemoryError("Private asset type cursor not found")
                items = items[identifiers.index(cursor) + 1 :]
            items = [item for item in items if include_retired or not item["retired"]]
            page: list[dict[str, Any]] = []
            size = 0
            for item in items:
                item_bytes = len(json.dumps(item, ensure_ascii=False).encode("utf-8"))
                if len(page) >= 5 or (page and size + item_bytes > 24000):
                    break
                page.append(item)
                size += item_bytes
            return {
                "items": page,
                "next_cursor": page[-1]["id"] if len(page) < len(items) else None,
            }

    def get(self, actor: Account, identifier: str) -> dict[str, Any]:
        with Session(self.memory.engine) as db:
            db.connection().exec_driver_sql("BEGIN")
            return self._get(db, actor, identifier)

    def save(self, actor: Account, value: TypeSave) -> dict[str, Any]:
        data = TypeSave.model_validate(value)
        signature = fingerprint(data.model_dump(mode="json"))
        with self.memory._write() as db:
            replay = db.scalar(
                select(AssetTypeRevision).where(
                    AssetTypeRevision.user_id == actor.id,
                    AssetTypeRevision.request_id == data.request_id,
                )
            )
            if replay:
                if replay.fingerprint != signature:
                    raise NoteConflict(
                        "Request ID already used for a different definition"
                    )
                return json.loads(replay.definition_json)  # type: ignore[no-any-return]
            previous_id = None
            if data.type_id:
                current = self._get(db, actor, data.type_id)
                if current["revision"] != data.expected_revision:
                    raise NoteConflict(
                        "Asset type changed. Reload its definition before editing."
                    )
                row = self._materialize(db, actor, current)
                previous_id = row.revision
                fields = {field["id"]: field for field in current["fields"]}
                supplied = {field.id for field in data.fields if field.id}
                if supplied != set(fields):
                    raise MemoryError(
                        "Keep existing field IDs; retire fields instead of deleting"
                    )
                for field in data.fields:
                    if (
                        field.id
                        and field.system_field != fields[field.id]["system_field"]
                    ):
                        raise MemoryError("A field's standard meaning cannot change")
            else:
                count = list(
                    db.scalars(
                        select(AssetType.id)
                        .where(AssetType.user_id == actor.id)
                        .limit(46)
                    )
                )
                if len(count) >= 45:
                    raise MemoryError("Limit of 45 custom/saved types reached")
                if any(field.id for field in data.fields):
                    raise MemoryError("Copies and new types need new field IDs")
                row = AssetType(
                    id=str(uuid4()),
                    user_id=actor.id,
                    seed_key=None,
                    name=data.name,
                    description=data.description,
                    retired=data.retired,
                    revision="pending",
                )
                db.add(row)
                db.flush()
            row.name, row.description, row.retired = (
                data.name,
                data.description,
                data.retired,
            )
            row.revision = str(uuid4())
            for position, field in enumerate(data.fields):
                existing = db.get(AssetTypeField, field.id) if field.id else None
                if existing is None:
                    existing = AssetTypeField(
                        id=uuid4().hex,
                        user_id=actor.id,
                        type_id=row.id,
                        system_field=field.system_field,
                    )
                    db.add(existing)
                existing.name, existing.retired, existing.position = (
                    field.name,
                    field.retired,
                    position,
                )
            db.flush()
            result = self._get(db, actor, row.id)
            db.add(
                AssetTypeRevision(
                    id=row.revision,
                    user_id=actor.id,
                    type_id=row.id,
                    previous_id=previous_id,
                    request_id=data.request_id,
                    fingerprint=signature,
                    definition_json=json.dumps(result),
                    recorded_at=self.memory.clock(),
                )
            )
            self.memory._audit(
                db, actor, "asset_type_saved", row.id, self.memory.clock()
            )
            db.flush()
            return result

    def history(
        self, actor: Account, identifier: str, cursor: str = ""
    ) -> dict[str, Any]:
        with Session(self.memory.engine) as db:
            db.connection().exec_driver_sql("BEGIN")
            current = self._get(db, actor, identifier)
            query = select(AssetTypeRevision).where(
                AssetTypeRevision.user_id == actor.id,
                AssetTypeRevision.type_id == identifier,
            )
            if cursor:
                row = db.scalar(query.where(AssetTypeRevision.id == cursor))
                if row is None:
                    raise MemoryError("Definition history cursor not found")
                query = query.where(
                    or_(
                        AssetTypeRevision.recorded_at > row.recorded_at,
                        and_(
                            AssetTypeRevision.recorded_at == row.recorded_at,
                            AssetTypeRevision.id > row.id,
                        ),
                    )
                )
            rows = list(
                db.scalars(
                    query.order_by(
                        AssetTypeRevision.recorded_at, AssetTypeRevision.id
                    ).limit(2)
                )
            )
            return {
                "items": [
                    {
                        "id": row.id,
                        "recorded_at": row.recorded_at,
                        "definition": json.loads(row.definition_json),
                    }
                    for row in rows
                ]
                or (
                    [
                        {
                            "id": current["revision"],
                            "recorded_at": None,
                            "definition": current,
                        }
                    ]
                    if not cursor
                    else []
                ),
                "next_cursor": rows[-1].id if len(rows) == 2 else None,
            }

    def _asset(self, db: Session, actor: Account, identifier: str) -> str:
        entity = self.memory._entity(db, actor, identifier)
        if entity.kind != "asset":
            raise MemoryError("Choose a physical asset")
        return canonical_id(db, actor, identifier)

    def _assign_in(
        self, db: Session, actor: Account, data: TypeAssign
    ) -> dict[str, Any]:
        subject = self._asset(db, actor, data.entity_id)
        template = self._get(db, actor, data.type_id)
        operation = "asset-type-assign:" + data.request_id
        replay = db.scalar(
            select(Assertion).where(
                Assertion.user_id == actor.id, Assertion.operation_key == operation
            )
        )
        if replay and replay.subject_id in member_ids(db, actor, subject):
            subject = replay.subject_id
        if replay is None and template["retired"]:
            raise MemoryError("Retired types cannot be newly assigned")
        self._materialize(db, actor, template)
        if data.replaces_id:
            old = self.memory._assertion(db, actor, data.replaces_id)
            if (
                old.subject_id not in member_ids(db, actor, subject)
                or old.predicate != "profile_asset_type"
            ):
                raise MemoryError("Choose a type assignment from this asset")
            subject = old.subject_id
        elif replay is None:
            existing = db.scalar(
                select(Assertion.id)
                .where(
                    Assertion.user_id == actor.id,
                    Assertion.subject_id.in_(member_ids(db, actor, subject)),
                    Assertion.predicate == "profile_asset_type",
                    Assertion.superseded_at.is_(None),
                )
                .limit(1)
            )
            if existing:
                raise NoteConflict(
                    "Choose the previous assignment explicitly to change the asset type"
                )
        # Stable command content permits replay after a definition rename/retirement.
        source = self.memory._ingest_in(
            db,
            actor,
            SourceInput(
                text=f"I assign asset {data.entity_id} to asset type {data.type_id}.",
                namespace="asset-type-assignments",
                external_id=data.request_id,
            ),
        )
        fact = self.memory._put_fact_in(
            db,
            actor,
            FactInput(
                subject_id=subject,
                predicate="profile_asset_type",
                value=data.type_id,
                source_id=source.id,
                quote=source.text,
                operation_key=operation,
            ),
            data.replaces_id,
        )
        return compact_fact(fact)

    def assign(self, actor: Account, value: TypeAssign) -> dict[str, Any]:
        data = TypeAssign.model_validate(value)
        with self.memory._write() as db:
            return self._assign_in(db, actor, data)

    def _field_in(
        self,
        db: Session,
        actor: Account,
        data: TypeFieldSave,
        *,
        source_id: str | None = None,
    ) -> dict[str, Any]:
        subject = self._asset(db, actor, data.entity_id)
        template = self._get(db, actor, data.type_id)
        field = next(
            (item for item in template["fields"] if item["id"] == data.field_id), None
        )
        if field is None:
            raise MemoryError("Field not found in this private type")
        self._materialize(db, actor, template)
        key = "asset-type-field:" + data.request_id
        replay = db.scalar(
            select(Assertion).where(
                Assertion.user_id == actor.id, Assertion.operation_key == key
            )
        )
        if replay and replay.subject_id in member_ids(db, actor, subject):
            subject = replay.subject_id
        if data.replaces_id:
            old = self.memory._assertion(db, actor, data.replaces_id)
            if old.subject_id not in member_ids(
                db, actor, subject
            ) or old.predicate != predicate(field):
                raise MemoryError("Choose a correction from this asset and field")
            subject = old.subject_id
        elif replay is None:
            if field["retired"] or template["retired"]:
                raise MemoryError(
                    "Retired fields retain history but cannot accept new statements"
                )
            assigned = db.scalar(
                select(Assertion.id)
                .where(
                    Assertion.user_id == actor.id,
                    Assertion.subject_id.in_(member_ids(db, actor, subject)),
                    Assertion.predicate == "profile_asset_type",
                    Assertion.value_json == json.dumps(data.type_id),
                    Assertion.superseded_at.is_(None),
                )
                .limit(1)
            )
            if assigned is None:
                raise MemoryError("Assign this type before adding its field values")
        source = (
            self.memory._source(db, actor, source_id)
            if source_id
            else self.memory._ingest_in(
                db,
                actor,
                SourceInput(
                    text=(
                        f"Asset: {data.entity_id}\nType: {data.type_id}\n"
                        f"Field: {data.field_id}\n{data.text}"
                    ),
                    namespace="asset-type-fields",
                    external_id=data.request_id,
                ),
            )
        )
        fact = self.memory._put_fact_in(
            db,
            actor,
            FactInput(
                subject_id=subject,
                predicate=predicate(field),
                value=data.value,
                status="unknown" if data.value is None else "stated",
                source_id=source.id,
                quote=data.value or data.text[:500],
                operation_key=key,
                valid_from=data.valid_from,
                valid_to=data.valid_to,
            ),
            data.replaces_id,
        )
        return compact_fact(fact)

    def save_field(self, actor: Account, value: TypeFieldSave) -> dict[str, Any]:
        data = TypeFieldSave.model_validate(value)
        with self.memory._write() as db:
            return self._field_in(db, actor, data)

    def record(
        self, actor: Account, identifier: str, history: bool = False, cursor: str = ""
    ) -> dict[str, Any]:
        with Session(self.memory.engine) as db:
            db.connection().exec_driver_sql("BEGIN")
            subject = self._asset(db, actor, identifier)
            query = select(Assertion).where(
                Assertion.user_id == actor.id,
                Assertion.subject_id.in_(member_ids(db, actor, subject)),
                (Assertion.predicate.startswith(PREFIX, autoescape=True))
                | (Assertion.predicate == "profile_vin"),
            )
            if not history:
                query = query.where(Assertion.superseded_at.is_(None))
            query = self.memory._after(db, actor, subject, query, cursor or None)
            rows = list(
                db.scalars(
                    query.order_by(Assertion.recorded_at, Assertion.id).limit(25)
                )
            )
            facts: list[dict[str, Any]] = []
            size = 0
            delivered: list[Assertion] = []
            for row in rows:
                fact = compact_fact(self.memory._view(db, actor, row))
                byte_count = len(json.dumps(fact, ensure_ascii=False).encode("utf-8"))
                if facts and size + byte_count > 20000:
                    break
                facts.append(fact)
                delivered.append(row)
                size += byte_count
            assignment_rows = list(
                db.scalars(
                    select(Assertion)
                    .where(
                        Assertion.user_id == actor.id,
                        Assertion.subject_id.in_(member_ids(db, actor, subject)),
                        Assertion.predicate == "profile_asset_type",
                        Assertion.superseded_at.is_(None),
                    )
                    .order_by(Assertion.recorded_at, Assertion.id)
                    .limit(25)
                )
            )
            assignments = [
                compact_fact(self.memory._view(db, actor, row))
                for row in assignment_rows
            ]
            return {
                "entity_id": subject,
                "assignments": assignments,
                "facts": [
                    fact for fact in facts if fact["predicate"] != "profile_asset_type"
                ],
                "next_cursor": delivered[-1].id
                if delivered and (len(delivered) < len(rows) or len(rows) == 25)
                else None,
            }
