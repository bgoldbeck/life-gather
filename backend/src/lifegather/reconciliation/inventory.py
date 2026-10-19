"""Shared current-world inventory predicates, correlated to a physical entity."""

from datetime import UTC, datetime

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.sql.elements import ColumnElement

from lifegather.assets.identity import same_identity
from lifegather.auth.store import Account
from lifegather.memory.models import Assertion, Entity
from lifegather.reconciliation.models import Binding, Decision


def current_ownership(
    actor: Account, value: bool, *, stated: bool = False
) -> ColumnElement[bool]:
    today = datetime.now(UTC).date()
    query = select(Assertion.id).where(
        Assertion.user_id == actor.id,
        same_identity(actor, Assertion.subject_id, Entity.id),
        Assertion.predicate == "owned",
        Assertion.value_json == ("true" if value else "false"),
        Assertion.superseded_at.is_(None),
        or_(Assertion.valid_from.is_(None), Assertion.valid_from <= today),
        or_(Assertion.valid_to.is_(None), Assertion.valid_to > today),
    )
    if stated:
        query = query.where(Assertion.status == "stated")
    return exists(query).correlate(Entity)


def current_inventory(actor: Account) -> ColumnElement[bool]:
    bound = exists(
        select(Binding.id)
        .join(Decision, Decision.id == Binding.decision_id)
        .where(
            Binding.user_id == actor.id,
            Decision.user_id == actor.id,
            same_identity(actor, Binding.asset_id, Entity.id),
            Decision.superseded_at.is_(None),
            Decision.outcome.in_(["create", "enrich"]),
        )
    ).correlate(Entity)
    return and_(
        or_(bound, current_ownership(actor, True, stated=True)),
        ~current_ownership(actor, False),
    )
