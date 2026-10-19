"""Bounded private asset browsing without changing evidence or ownership."""

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, and_, or_, select
from sqlalchemy.orm import Session

from lifegather.assets.identity import (
    canonical_id,
    identity_group,
    member_ids,
    secondary_ids,
)
from lifegather.assets.models import AssetAction, AssetConsolidation
from lifegather.auth.store import Account
from lifegather.memory.models import Entity
from lifegather.memory.schemas import EntityView
from lifegather.memory.service import MemoryError, MemoryService, normalized
from lifegather.reconciliation.inventory import current_inventory
from lifegather.reconciliation.models import Binding, Decision, Observation
from lifegather.reconciliation.schemas import DiscoveryInput


class AssetList(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str = Field(default="", max_length=200)
    cursor: str = Field(default="", max_length=36)
    include_history: bool = False
    limit: int = Field(default=25, ge=1, le=25)


class AssetRead(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    asset_id: str = Field(min_length=1, max_length=36)
    fact_cursor: str = Field(default="", max_length=36)
    decision_cursor: str = Field(default="", max_length=36)
    action_cursor: str = Field(default="", max_length=36)
    identity_cursor: str = Field(default="", max_length=36)
    limit: int = Field(default=25, ge=1, le=25)


class AssetService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.memory = MemoryService(engine)

    @staticmethod
    def active(actor: Account) -> Any:
        return current_inventory(actor)

    @staticmethod
    def action_result(row: AssetAction) -> dict[str, Any]:
        result: dict[str, Any] = json.loads(row.result_json)
        if row.operation in {"batch_move", "batch_restore"}:
            # The durable ledger retains reversal snapshots. Browse results need
            # only a summary, not repeated receipt passages and twenty-unit maps.
            return {
                "operation": row.operation,
                "source_id": row.source_id,
                "association_count": len(result["entries"]),
            }
        return result

    def list(self, actor: Account, value: AssetList) -> dict[str, Any]:
        data = AssetList.model_validate(value)
        secondary_entity = Entity.__table__.alias("secondary_entity")
        with Session(self.engine) as db:
            query = select(Entity, self.active(actor).label("in_inventory")).where(
                Entity.user_id == actor.id,
                Entity.kind == "asset",
                Entity.id > data.cursor,
                Entity.id.not_in(secondary_ids(actor)),
            )
            if not data.include_history:
                query = query.where(self.active(actor))
            if data.query.strip():
                query = query.where(
                    or_(
                        Entity.normalized_name.contains(
                            normalized(data.query), autoescape=True
                        ),
                        Entity.id.in_(
                            select(AssetConsolidation.primary_id)
                            .join(
                                secondary_entity,
                                secondary_entity.c.id
                                == AssetConsolidation.secondary_id,
                            )
                            .where(
                                AssetConsolidation.user_id == actor.id,
                                AssetConsolidation.superseded_at.is_(None),
                                secondary_entity.c.user_id == actor.id,
                                secondary_entity.c.normalized_name.contains(
                                    normalized(data.query), autoescape=True
                                ),
                            )
                        ),
                    )
                )
            rows = list(db.execute(query.order_by(Entity.id).limit(data.limit + 1)))
            return {
                "items": [
                    {
                        **EntityView.model_validate(row).model_dump(),
                        "in_inventory": bool(active),
                    }
                    for row, active in rows[: data.limit]
                ],
                "next_cursor": rows[data.limit - 1][0].id
                if len(rows) > data.limit
                else None,
            }

    def get(self, actor: Account, value: AssetRead) -> dict[str, Any]:
        data = AssetRead.model_validate(value)
        with Session(self.engine) as db:
            asset = self.memory._entity(db, actor, data.asset_id)
            if asset.kind != "asset":
                raise MemoryError("Asset not found")
            identifiers = member_ids(db, actor, asset.id)
            asset = self.memory._entity(db, actor, canonical_id(db, actor, asset.id))
            in_inventory = db.scalar(
                select(self.active(actor)).where(
                    Entity.id == asset.id, Entity.user_id == actor.id
                )
            )
            query = (
                select(Decision, Observation, Binding.unit)
                .join(Binding, Binding.decision_id == Decision.id)
                .join(Observation, Observation.id == Decision.observation_id)
                .where(
                    Binding.user_id == actor.id,
                    Binding.asset_id.in_(identifiers),
                    Decision.user_id == actor.id,
                )
            )
            if data.decision_cursor:
                previous = db.execute(
                    query.where(Decision.id == data.decision_cursor)
                ).first()
                if previous is None:
                    raise MemoryError("Invalid asset decision cursor")
                old = previous[0]
                query = query.where(
                    or_(
                        Decision.recorded_at < old.recorded_at,
                        and_(
                            Decision.recorded_at == old.recorded_at,
                            Decision.id < old.id,
                        ),
                    )
                )
            rows = list(
                db.execute(
                    query.order_by(
                        Decision.recorded_at.desc(), Decision.id.desc()
                    ).limit(data.limit + 1)
                )
            )
            decisions = []
            for decision, observation, unit in rows[: data.limit]:
                evidence = DiscoveryInput.model_validate_json(observation.payload)
                decisions.append(
                    {
                        "id": decision.id,
                        "observation_id": observation.id,
                        "outcome": decision.outcome,
                        "reason": decision.reason,
                        "recorded_at": decision.recorded_at,
                        "superseded_at": decision.superseded_at,
                        "source_id": observation.source_id,
                        "unit": unit,
                        "quantity": evidence.quantity,
                        "name": evidence.name,
                        "manufacturer": evidence.manufacturer,
                        "model": evidence.model,
                        "serial": evidence.serial,
                        "quote": evidence.quote,
                        "statement_kind": evidence.kind,
                    }
                )
            result = {
                "asset": EntityView.model_validate(asset).model_dump(),
                "in_inventory": bool(in_inventory),
                "decisions": decisions,
                "next_decision_cursor": rows[data.limit - 1][0].id
                if len(rows) > data.limit
                else None,
            }
            group = identity_group(db, actor, asset.id)
            result["consolidation"] = (
                None
                if group is None
                else {
                    "id": group.id,
                    "primary_id": group.primary_id,
                    "secondary_id": group.secondary_id,
                    "source_id": group.source_id,
                    "recorded_at": group.recorded_at,
                }
            )
            result["original_records"] = [
                EntityView.model_validate(
                    self.memory._entity(db, actor, identifier)
                ).model_dump()
                for identifier in identifiers
            ]
            identity_query = select(AssetConsolidation).where(
                AssetConsolidation.user_id == actor.id,
                or_(
                    AssetConsolidation.primary_id.in_(identifiers),
                    AssetConsolidation.secondary_id.in_(identifiers),
                ),
            )
            if data.identity_cursor:
                cursor = db.scalar(
                    identity_query.where(AssetConsolidation.id == data.identity_cursor)
                )
                if cursor is None:
                    raise MemoryError("Invalid consolidation history cursor")
                identity_query = identity_query.where(
                    or_(
                        AssetConsolidation.recorded_at < cursor.recorded_at,
                        and_(
                            AssetConsolidation.recorded_at == cursor.recorded_at,
                            AssetConsolidation.id < cursor.id,
                        ),
                    )
                )
            choices = list(
                db.scalars(
                    identity_query.order_by(
                        AssetConsolidation.recorded_at.desc(),
                        AssetConsolidation.id.desc(),
                    ).limit(data.limit + 1)
                )
            )
            result["identity_history"] = [
                {
                    "id": choice.id,
                    "primary_id": choice.primary_id,
                    "secondary_id": choice.secondary_id,
                    "primary_name": self.memory._entity(
                        db, actor, choice.primary_id
                    ).name,
                    "secondary_name": self.memory._entity(
                        db, actor, choice.secondary_id
                    ).name,
                    "source_id": choice.source_id,
                    "recorded_at": choice.recorded_at,
                    "superseded_at": choice.superseded_at,
                    "reverse_source_id": choice.reverse_source_id,
                }
                for choice in choices[: data.limit]
            ]
            result["next_identity_cursor"] = (
                choices[data.limit - 1].id if len(choices) > data.limit else None
            )
            actions_query = select(AssetAction).where(
                AssetAction.user_id == actor.id, AssetAction.asset_id == asset.id
            )
            latest = db.scalar(
                actions_query.order_by(
                    AssetAction.recorded_at.desc(), AssetAction.id.desc()
                ).limit(1)
            )
            result["action_head"] = latest.id if latest else ""
            # Incoming history is read-only context. The write head remains this
            # asset's own action chain, matching ActionService.latest.
            actions_query = select(AssetAction).where(
                AssetAction.user_id == actor.id,
                or_(
                    AssetAction.asset_id.in_(identifiers),
                    AssetAction.target_asset_id.in_(identifiers),
                ),
            )
            if data.action_cursor:
                old_action = db.scalar(
                    actions_query.where(AssetAction.id == data.action_cursor)
                )
                if old_action is None:
                    raise MemoryError("Invalid asset action cursor")
                actions_query = actions_query.where(
                    or_(
                        AssetAction.recorded_at < old_action.recorded_at,
                        and_(
                            AssetAction.recorded_at == old_action.recorded_at,
                            AssetAction.id < old_action.id,
                        ),
                    )
                )
            action_rows = list(
                db.scalars(
                    actions_query.order_by(
                        AssetAction.recorded_at.desc(), AssetAction.id.desc()
                    ).limit(data.limit + 1)
                )
            )
            result["actions"] = [
                {
                    "id": row.id,
                    "operation": row.operation,
                    "direction": "recorded_here"
                    if row.asset_id == asset.id
                    else "incoming",
                    "asset_id": row.asset_id,
                    "asset_name": self.memory._entity(db, actor, row.asset_id).name,
                    "target_asset_id": row.target_asset_id,
                    "target_asset_name": self.memory._entity(
                        db, actor, row.target_asset_id
                    ).name
                    if row.target_asset_id
                    else None,
                    "recorded_at": row.recorded_at,
                    "source_id": row.source_id,
                    "note": self.memory._source(db, actor, row.source_id).text,
                    "result": self.action_result(row),
                }
                for row in action_rows[: data.limit]
            ]
            result["next_action_cursor"] = (
                action_rows[data.limit - 1].id
                if len(action_rows) > data.limit
                else None
            )
        facts = self.memory.timeline(
            actor, data.asset_id, data.limit + 1, cursor=data.fact_cursor or None
        )
        with Session(self.engine) as db:
            result["facts"] = [
                {
                    **fact.model_dump(mode="json"),
                    "object_name": self.memory._entity(db, actor, fact.object_id).name
                    if fact.object_id
                    else None,
                }
                for fact in facts[: data.limit]
            ]
        result["next_fact_cursor"] = (
            facts[data.limit - 1].id if len(facts) > data.limit else None
        )
        return result
