"""Bounded receipt reads through current physical-item evidence bindings."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, func, literal, select
from sqlalchemy.orm import Session

from lifegather.auth.store import Account
from lifegather.memory.service import MemoryError
from lifegather.reconciliation.models import Binding, Decision, Observation
from lifegather.reconciliation.purchase_details import PurchaseDetails
from lifegather.reconciliation.receipt_models import ReceiptDetail, ReceiptProposal


class AssetPurchasesRead(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    asset_id: str = Field(min_length=1, max_length=36)
    cursor: str = Field(
        default="", max_length=38, pattern=r"^(?:[a-f0-9-]{36}:[0-7])?$"
    )
    limit: int = Field(default=5, ge=1, le=5)


class AssetPurchases:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.details = PurchaseDetails(engine)

    def get(self, actor: Account, value: AssetPurchasesRead) -> dict[str, Any]:
        data = AssetPurchasesRead.model_validate(value)
        with Session(self.engine) as db:
            return self._get_in(db, actor, data)

    def _get_in(
        self, db: Session, actor: Account, data: AssetPurchasesRead
    ) -> dict[str, Any]:
        asset = self.details.receipts.memory._entity(db, actor, data.asset_id)
        if asset.kind != "asset":
            raise MemoryError("Asset not found")
        key = (
            ReceiptProposal.id + literal(":") + func.substr(Observation.item_key, -1, 1)
        )
        query = (
            select(
                ReceiptProposal,
                Observation.item_key,
                Binding.unit,
                key.label("cursor"),
            )
            .join(Observation, Observation.source_id == ReceiptProposal.source_id)
            .join(Decision, Decision.observation_id == Observation.id)
            .join(Binding, Binding.decision_id == Decision.id)
            .where(
                ReceiptProposal.user_id == actor.id,
                ReceiptProposal.state == "accepted",
                Observation.user_id == actor.id,
                Decision.user_id == actor.id,
                Binding.user_id == actor.id,
                Binding.asset_id == asset.id,
                Decision.superseded_at.is_(None),
                Decision.outcome.in_(["create", "enrich"]),
                Observation.item_key.in_([f"receipt-line-{i}" for i in range(8)]),
                func.json_extract(Observation.payload, "$.kind") == "purchase",
                key > data.cursor,
            )
        )
        rows = list(db.execute(query.order_by(key).limit(data.limit + 1)))
        items = []
        for receipt, item_key, unit, cursor in rows[: data.limit]:
            index = int(item_key[-1])
            _, choice = self.details.context(db, actor, receipt.id, index)
            latest = db.scalar(
                self.details.query(actor, receipt.id, index)
                .order_by(ReceiptDetail.revision.desc())
                .limit(1)
            )
            current_source = True
            try:
                self.details.receipts.source(db, actor, receipt.source_id)
            except MemoryError:
                current_source = False
            items.append(
                {
                    "key": cursor,
                    "receipt_id": receipt.id,
                    "index": index,
                    "source_id": receipt.source_id,
                    "name": choice.fields.name,
                    "quantity": choice.fields.quantity,
                    "unit": unit + 1,
                    "source_current": current_source,
                    "claim": self.details.view(latest) if latest else None,
                }
            )
        return {
            "asset_id": asset.id,
            "items": items,
            "next_cursor": rows[data.limit - 1][3] if len(rows) > data.limit else None,
        }
