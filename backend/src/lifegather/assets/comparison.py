"""One read snapshot for explicit comparison; never an identity or merge decision."""

import json
from typing import Any

from sqlalchemy import Engine, or_, select
from sqlalchemy.orm import Session

from lifegather.assets.batch import EvidenceMovePreview
from lifegather.assets.purchases import AssetPurchases, AssetPurchasesRead
from lifegather.auth.store import Account
from lifegather.database import begin_snapshot
from lifegather.maintenance.models import MaintenanceRevision, MaintenanceTask
from lifegather.memory.models import Alias, Assertion, Evidence
from lifegather.memory.notes import NoteService
from lifegather.memory.schemas import EntityView
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.photos.models import Photo, PhotoAsset
from lifegather.purchases.models import PurchaseEvidence
from lifegather.purchases.service import PurchaseEvidenceService
from lifegather.reconciliation.inventory import current_inventory
from lifegather.reconciliation.models import (
    Binding,
    Decision,
    Observation,
    Purchase,
    PurchaseLine,
)
from lifegather.reconciliation.schemas import DiscoveryInput

LIMITS = {
    "statements": 50,
    "evidence": 100,
    "aliases": 100,
    "photos": 40,
    "associations": 40,
    "purchase_evidence": 50,
    "receipt_lines": 40,
    "sources": 200,
}
MAX_BYTES = 30000


class RecordComparison(EvidenceMovePreview):
    """Two existing physical records; the input conveys no write authority."""


class RecordComparisonService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.memory = MemoryService(engine)

    def get(self, actor: Account, value: RecordComparison) -> dict[str, Any]:
        data = RecordComparison.model_validate(value)
        with Session(self.engine) as db:
            # All sections must describe the same committed state.
            begin_snapshot(db)
            return self._get_in(db, actor, data)

    def _get_in(
        self, db: Session, actor: Account, data: RecordComparison
    ) -> dict[str, Any]:
        entities = [
            self.memory._entity(db, actor, identifier)
            for identifier in (data.asset_id, data.target_asset_id)
        ]
        if any(entity.kind != "asset" for entity in entities):
            raise MemoryError("Choose two existing physical items")
        identifiers = [entity.id for entity in entities]
        result: dict[str, Any] = {
            "complete": True,
            "scope": "current-record-comparison; read only; no merge decision",
            "records": [
                {
                    **EntityView.model_validate(entity).model_dump(),
                    "in_inventory": bool(
                        db.scalar(
                            select(current_inventory(actor)).where(
                                type(entity).id == entity.id,
                                type(entity).user_id == actor.id,
                            )
                        )
                    ),
                }
                for entity in entities
            ],
            "limits": LIMITS,
            "counts": {},
            "limited_sections": [],
            "sections": {},
            "warnings": [],
        }

        def bounded(name: str, rows: list[Any]) -> list[Any]:
            result["counts"][name] = len(rows)
            if len(rows) > LIMITS[name]:
                result["limited_sections"].append(name)
            return rows[: LIMITS[name]]

        statements = bounded(
            "statements",
            list(
                db.scalars(
                    select(Assertion)
                    .where(
                        Assertion.user_id == actor.id,
                        Assertion.superseded_at.is_(None),
                        or_(
                            Assertion.subject_id.in_(identifiers),
                            Assertion.object_id.in_(identifiers),
                        ),
                    )
                    .order_by(Assertion.id)
                    .limit(LIMITS["statements"] + 1)
                )
            ),
        )
        evidence = bounded(
            "evidence",
            list(
                db.scalars(
                    select(Evidence)
                    .where(
                        Evidence.user_id == actor.id,
                        Evidence.fact_id.in_([row.id for row in statements]),
                    )
                    .order_by(Evidence.id)
                    .limit(LIMITS["evidence"] + 1)
                )
            ),
        )
        aliases = bounded(
            "aliases",
            list(
                db.scalars(
                    select(Alias)
                    .where(Alias.user_id == actor.id, Alias.entity_id.in_(identifiers))
                    .order_by(Alias.id)
                    .limit(LIMITS["aliases"] + 1)
                )
            ),
        )
        photos = bounded(
            "photos",
            list(
                db.execute(
                    select(PhotoAsset, Photo)
                    .join(Photo, Photo.id == PhotoAsset.photo_id)
                    .where(
                        PhotoAsset.user_id == actor.id,
                        Photo.user_id == actor.id,
                        PhotoAsset.asset_id.in_(identifiers),
                    )
                    .order_by(PhotoAsset.id)
                    .limit(LIMITS["photos"] + 1)
                )
            ),
        )
        associations = bounded(
            "associations",
            list(
                db.execute(
                    select(Binding, Decision, Observation)
                    .join(Decision, Decision.id == Binding.decision_id)
                    .join(Observation, Observation.id == Decision.observation_id)
                    .where(
                        Binding.user_id == actor.id,
                        Decision.user_id == actor.id,
                        Observation.user_id == actor.id,
                        Binding.asset_id.in_(identifiers),
                        Decision.superseded_at.is_(None),
                    )
                    .order_by(Binding.id)
                    .limit(LIMITS["associations"] + 1)
                )
            ),
        )
        line_ids = {
            observation.line_id
            for _, _, observation in associations
            if observation.line_id
        }
        lines = list(
            db.scalars(
                select(PurchaseLine).where(
                    PurchaseLine.user_id == actor.id, PurchaseLine.id.in_(line_ids)
                )
            )
        )
        purchase_ids = {line.purchase_id for line in lines}
        purchase_records = list(
            db.scalars(
                select(Purchase)
                .where(Purchase.user_id == actor.id, Purchase.id.in_(purchase_ids))
                .order_by(Purchase.id)
            )
        )
        purchase_rows = bounded(
            "purchase_evidence",
            list(
                db.scalars(
                    select(PurchaseEvidence)
                    .where(
                        PurchaseEvidence.user_id == actor.id,
                        PurchaseEvidence.purchase_id.in_(purchase_ids),
                        PurchaseEvidence.superseded_at.is_(None),
                        PurchaseEvidence.state == "active",
                    )
                    .order_by(PurchaseEvidence.id)
                    .limit(LIMITS["purchase_evidence"] + 1)
                )
            ),
        )
        receipt_rows: list[dict[str, Any]] = []
        purchases = AssetPurchases(self.engine)
        for identifier in identifiers:
            cursor = ""
            # At most twenty line associations per record; the existing next
            # cursor proves overflow without hiding omitted associations.
            for page_number in range(4):
                page = purchases._get_in(
                    db,
                    actor,
                    AssetPurchasesRead(asset_id=identifier, cursor=cursor),
                    original=True,
                )
                receipt_rows.extend(
                    {"asset_id": identifier, **row} for row in page["items"]
                )
                if not page["next_cursor"]:
                    break
                if page_number == 3:
                    result["limited_sections"].append("receipt_lines")
                    break
                cursor = page["next_cursor"]
        receipts = bounded("receipt_lines", receipt_rows)
        maintenance = list(
            db.execute(
                select(MaintenanceTask, MaintenanceRevision)
                .join(
                    MaintenanceRevision,
                    (MaintenanceRevision.user_id == MaintenanceTask.user_id)
                    & (MaintenanceRevision.task_id == MaintenanceTask.id),
                )
                .where(
                    MaintenanceTask.user_id == actor.id,
                    MaintenanceRevision.user_id == actor.id,
                    MaintenanceTask.entity_id.in_(identifiers),
                    MaintenanceRevision.superseded_at.is_(None),
                )
                .order_by(MaintenanceTask.id)
                .limit(21)
            )
        )
        # Keep the empty result contract identical for existing consolidation
        # receipts. Adding an empty section would invalidate old reversal tokens.
        if maintenance:
            result["limits"] = {**LIMITS, "maintenance": 20}
            result["counts"]["maintenance"] = len(maintenance)
            if len(maintenance) > 20:
                result["limited_sections"].append("maintenance")
        if result["limited_sections"]:
            return self._incomplete(result)
        sources = {entity.source_id for entity in entities}
        sources.update(row.source_id for row in aliases)
        sources.update(row.source_id for row in evidence)
        sources.update(photo.source_id for _, photo in photos if photo.source_id)
        sources.update(observation.source_id for _, _, observation in associations)
        sources.update(row.source_id for row in purchase_rows)
        sources.update(row.source_id for row in purchase_records)
        sources.update(row["source_id"] for row in receipts)
        sources.update(row.source_id for _, row in maintenance)
        bounded("sources", sorted(sources))
        if result["limited_sections"]:
            return self._incomplete(result)
        states = {}
        for source_id in sorted(sources):
            source = self.memory._source(db, actor, source_id)
            current = (
                NoteService._head(db, actor, NoteService._root(db, actor, source))
                if NoteService.is_note(source)
                else source.id
            )
            states[source_id] = {
                "current_source_id": current,
                "is_current": current == source_id,
            }
        source_views = [
            self.memory._view(db, actor, row).model_dump(mode="json")
            for row in statements
        ]
        for view in source_views:
            # JavaScript numbers cannot represent every Python integer exactly.
            # Keep the original literal display independent of JSON number parsing.
            value = view["value"]
            view["display_value"] = (
                value
                if isinstance(value, str)
                else "Unknown"
                if value is None
                else json.dumps(value, ensure_ascii=False)
            )
        neighbor_ids = {row.subject_id for row in statements} | {
            row.object_id for row in statements if row.object_id
        }
        result["references"] = [
            EntityView.model_validate(
                self.memory._entity(db, actor, identifier)
            ).model_dump()
            for identifier in sorted(neighbor_ids - set(identifiers))
        ]
        result["source_states"] = states
        result["purchases"] = [
            {
                "id": row.id,
                "retailer": row.retailer,
                "order_id": row.order_id,
                "source_id": row.source_id,
            }
            for row in purchase_records
        ]
        evidence_service = PurchaseEvidenceService(self.engine)
        result["sections"] = {
            "statements": source_views,
            "aliases": [
                {
                    "id": row.id,
                    "asset_id": row.entity_id,
                    "name": row.name,
                    "source_id": row.source_id,
                }
                for row in aliases
            ],
            "photos": [
                {
                    "link_id": link.id,
                    "asset_id": link.asset_id,
                    "id": photo.id,
                    "filename": photo.filename,
                    "purpose": photo.purpose,
                    "source_id": photo.source_id,
                    "deleted": photo.deleted_at is not None,
                    "updated_at": photo.updated_at,
                }
                for link, photo in photos
            ],
            "associations": [
                {
                    "asset_id": binding.asset_id,
                    "decision_id": decision.id,
                    "observation_id": observation.id,
                    "source_id": observation.source_id,
                    "line_id": observation.line_id,
                    "purchase_id": next(
                        (
                            line.purchase_id
                            for line in lines
                            if line.id == observation.line_id
                        ),
                        None,
                    ),
                    "unit": binding.unit + 1,
                    "quantity": (
                        discovery := DiscoveryInput.model_validate_json(
                            observation.payload
                        )
                    ).quantity,
                    "name": discovery.name,
                    "manufacturer": discovery.manufacturer,
                    "serial": discovery.serial,
                }
                for binding, decision, observation in associations
            ],
            "receipt_lines": receipts,
            "purchase_evidence": [
                evidence_service.view(db, actor, row) for row in purchase_rows
            ],
        }
        if maintenance:
            result["sections"]["maintenance"] = [
                {
                    "id": task.id,
                    "revision_id": row.id,
                    "asset_id": task.entity_id,
                    "title": row.title,
                    "due_on": row.due_on.isoformat() if row.due_on else None,
                    "timezone": row.timezone,
                    "state": row.state,
                    "completed_on": row.completed_on.isoformat()
                    if row.completed_on
                    else None,
                    "source_id": row.source_id,
                    "recorded_at": row.recorded_at,
                }
                for task, row in maintenance
            ]
        result["warnings"] = self._warnings(result)
        if len(json.dumps(result, ensure_ascii=False).encode()) > MAX_BYTES:
            result["limited_sections"].append("response_bytes")
            return self._incomplete(result)
        return result

    @staticmethod
    def _incomplete(result: dict[str, Any]) -> dict[str, Any]:
        result["complete"] = False
        result["sections"] = {}
        result["warnings"] = []
        result.pop("references", None)
        result.pop("source_states", None)
        result.pop("purchases", None)
        result["limited_sections"] = sorted(set(result["limited_sections"]))
        return result

    @staticmethod
    def _warnings(result: dict[str, Any]) -> list[dict[str, Any]]:
        warnings = []
        identifiers = {row["id"] for row in result["records"]}
        statements = result["sections"]["statements"]
        for fact in statements:
            if (
                fact["predicate"] == "replaced_by"
                and {fact["subject_id"], fact["object_id"]} == identifiers
            ):
                warnings.append(
                    {
                        "code": "replacement",
                        "message": (
                            "A current statement describes these as distinct "
                            "replacement items."
                        ),
                        "statement_ids": [fact["id"]],
                    }
                )
        predicates = {
            fact["predicate"]
            for fact in statements
            if fact["subject_id"] in identifiers
        }
        for predicate in sorted(predicates):
            group = [
                fact
                for fact in statements
                if fact["predicate"] == predicate
                and fact["subject_id"] in identifiers
                and fact["status"] != "unknown"
                and (fact["object_id"] is not None or fact["value"] is not None)
            ]
            conflicts = set()
            for left in group:
                for right in group:
                    if left["subject_id"] == right["subject_id"] or (
                        left["object_id"],
                        json.dumps(left["value"]),
                    ) == (right["object_id"], json.dumps(right["value"])):
                        continue
                    if (
                        left["valid_to"]
                        and right["valid_from"]
                        and left["valid_to"] <= right["valid_from"]
                    ) or (
                        right["valid_to"]
                        and left["valid_from"]
                        and right["valid_to"] <= left["valid_from"]
                    ):
                        continue
                    conflicts.update([left["id"], right["id"]])
            if conflicts:
                warnings.append(
                    {
                        "code": "statements_differ",
                        "predicate": predicate,
                        "statement_ids": sorted(conflicts),
                        "message": (
                            "Statements differ over overlapping or unknown dates. "
                            "Preserve both sources; identity is not established."
                        ),
                    }
                )
        associations = result["sections"]["associations"]
        claims = result["sections"]["purchase_evidence"]
        for purchase_id in sorted({claim["purchase_id"] for claim in claims}):
            totals = {
                (claim["currency"], claim["amount_minor"])
                for claim in claims
                if claim["purchase_id"] == purchase_id
                and claim["role"] in {"order", "receipt"}
                and claim["source_current"]
                and claim["amount_minor"] is not None
            }
            if len(totals) > 1:
                warnings.append(
                    {
                        "code": "purchase_totals_differ",
                        "purchase_id": purchase_id,
                        "message": (
                            "Current order/receipt totals disagree. Preserve each "
                            "source claim; do not add or allocate these amounts."
                        ),
                    }
                )
        for index, left in enumerate(associations):
            for right in associations[index + 1 :]:
                same = left["observation_id"] == right["observation_id"] or (
                    left["line_id"] and left["line_id"] == right["line_id"]
                )
                if (
                    left["asset_id"] != right["asset_id"]
                    and same
                    and left["unit"] != right["unit"]
                ):
                    warnings.append(
                        {
                            "code": "distinct_units",
                            "message": (
                                "These records represent different units of the same "
                                "receipt/discovery line. Keep physical units distinct."
                            ),
                            "observation_ids": sorted(
                                {left["observation_id"], right["observation_id"]}
                            ),
                        }
                    )
        return warnings
