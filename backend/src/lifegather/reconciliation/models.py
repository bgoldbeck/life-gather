from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from lifegather.auth.models import Base


def link(column: str, table: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["user_id", column], [table + ".user_id", table + ".id"]
    )


class Record(Base):
    __abstract__ = True
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    recorded_at: Mapped[int]


class Purchase(Record):
    __tablename__ = "reconciliation_purchases"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        UniqueConstraint("user_id", "identity_key"),
        link("source_id", "memory_sources"),
    )
    identity_key: Mapped[str]
    retailer: Mapped[str]
    account_scope: Mapped[str]
    order_id: Mapped[str]
    source_id: Mapped[str]


class PurchaseLine(Record):
    __tablename__ = "reconciliation_lines"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        UniqueConstraint("user_id", "purchase_id", "line_key"),
        link("purchase_id", "reconciliation_purchases"),
        link("product_id", "memory_entities"),
        link("source_id", "memory_sources"),
        CheckConstraint("quantity BETWEEN 1 AND 20"),
    )
    purchase_id: Mapped[str]
    line_key: Mapped[str]
    product_id: Mapped[str | None]
    quantity: Mapped[int]
    source_id: Mapped[str]


class Observation(Record):
    __tablename__ = "reconciliation_observations"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        UniqueConstraint("user_id", "source_id", "item_key"),
        link("source_id", "memory_sources"),
        link("product_id", "memory_entities"),
        link("line_id", "reconciliation_lines"),
    )
    source_id: Mapped[str]
    item_key: Mapped[str]
    payload: Mapped[str]
    fingerprint: Mapped[str]
    product_id: Mapped[str | None]
    line_id: Mapped[str | None]
    serial_key: Mapped[str | None] = mapped_column(index=True)


class Decision(Record):
    __tablename__ = "reconciliation_decisions"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        link("observation_id", "reconciliation_observations"),
        link("previous_id", "reconciliation_decisions"),
        CheckConstraint("outcome IN ('create','enrich','review','dismissed')"),
        Index(
            "uq_reconciliation_current",
            "user_id",
            "observation_id",
            unique=True,
            postgresql_where=text("superseded_at IS NULL"),
        ),
    )
    observation_id: Mapped[str]
    previous_id: Mapped[str | None]
    outcome: Mapped[str]
    reason: Mapped[str]
    request_key: Mapped[str]
    superseded_at: Mapped[int | None]


class Binding(Record):
    __tablename__ = "reconciliation_bindings"
    __table_args__ = (
        UniqueConstraint("user_id", "decision_id", "unit"),
        link("decision_id", "reconciliation_decisions"),
        link("asset_id", "memory_entities"),
        link("ownership_fact_id", "memory_facts"),
        link("product_fact_id", "memory_facts"),
        CheckConstraint("unit BETWEEN 0 AND 19"),
    )
    decision_id: Mapped[str]
    unit: Mapped[int]
    asset_id: Mapped[str]
    ownership_fact_id: Mapped[str]
    product_fact_id: Mapped[str | None]


class Candidate(Record):
    __tablename__ = "reconciliation_candidates"
    __table_args__ = (
        UniqueConstraint("user_id", "decision_id", "asset_id"),
        link("decision_id", "reconciliation_decisions"),
        link("asset_id", "memory_entities"),
    )
    decision_id: Mapped[str]
    asset_id: Mapped[str]
