"""Shared current identity projection; stored evidence always keeps original IDs."""

from typing import Any

from sqlalchemy import Select, and_, exists, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from lifegather.assets.models import AssetConsolidation
from lifegather.auth.store import Account


def identity_group(
    db: Session, actor: Account, identifier: str, *, known_at: int | None = None
) -> AssetConsolidation | None:
    query = select(AssetConsolidation).where(
        AssetConsolidation.user_id == actor.id,
        or_(
            AssetConsolidation.primary_id == identifier,
            AssetConsolidation.secondary_id == identifier,
        ),
    )
    if known_at is None:
        query = query.where(AssetConsolidation.superseded_at.is_(None))
    else:
        query = query.where(
            AssetConsolidation.recorded_at <= known_at,
            or_(
                AssetConsolidation.superseded_at.is_(None),
                AssetConsolidation.superseded_at > known_at,
            ),
        )
    return db.scalar(query.limit(1))


def canonical_id(db: Session, actor: Account, identifier: str) -> str:
    group = identity_group(db, actor, identifier)
    return group.primary_id if group else identifier


def member_ids(
    db: Session, actor: Account, identifier: str, *, known_at: int | None = None
) -> list[str]:
    group = identity_group(db, actor, identifier, known_at=known_at)
    return [group.primary_id, group.secondary_id] if group else [identifier]


def secondary_ids(actor: Account) -> Select[str]:
    return select(AssetConsolidation.secondary_id).where(
        AssetConsolidation.user_id == actor.id,
        AssetConsolidation.superseded_at.is_(None),
    )


def same_identity(actor: Account, left: Any, right: Any) -> ColumnElement[bool]:
    pair = exists(
        select(AssetConsolidation.id).where(
            AssetConsolidation.user_id == actor.id,
            AssetConsolidation.superseded_at.is_(None),
            or_(
                and_(
                    AssetConsolidation.primary_id == left,
                    AssetConsolidation.secondary_id == right,
                ),
                and_(
                    AssetConsolidation.secondary_id == left,
                    AssetConsolidation.primary_id == right,
                ),
            ),
        )
    )
    return or_(left == right, pair)
