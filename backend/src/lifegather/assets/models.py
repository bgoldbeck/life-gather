from sqlalchemy import ForeignKey, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from lifegather.auth.models import Base


class AssetAction(Base):
    __tablename__ = "asset_actions"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        UniqueConstraint("user_id", "request_id"),
        *[
            ForeignKeyConstraint(
                ["user_id", field], [table + ".user_id", table + ".id"]
            )
            for field, table in (
                ("asset_id", "memory_entities"),
                ("target_asset_id", "memory_entities"),
                ("source_id", "memory_sources"),
                ("previous_id", "asset_actions"),
                ("ownership_fact_id", "memory_facts"),
                ("status_fact_id", "memory_facts"),
            )
        ],
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    asset_id: Mapped[str] = mapped_column(index=True)
    target_asset_id: Mapped[str | None]
    previous_id: Mapped[str | None]
    source_id: Mapped[str]
    request_id: Mapped[str]
    fingerprint: Mapped[str]
    operation: Mapped[str]
    ownership_fact_id: Mapped[str | None]
    status_fact_id: Mapped[str | None]
    result_json: Mapped[str]
    recorded_at: Mapped[int]
