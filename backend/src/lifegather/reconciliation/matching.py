"""Bounded identity matching: product similarity only produces candidates."""

from sqlalchemy import Select, and_, false, or_, select
from sqlalchemy.orm import Session

from lifegather.assets.identity import canonical_id, member_ids
from lifegather.auth.store import Account
from lifegather.memory.models import Alias, Assertion, Entity
from lifegather.memory.service import normalized
from lifegather.reconciliation.inventory import current_ownership
from lifegather.reconciliation.models import Binding, Decision, Observation
from lifegather.reconciliation.schemas import DiscoveryInput


class IdentityMatcher:
    @staticmethod
    def _active_bindings(actor: Account) -> Select[Binding, Observation]:
        return (
            select(Binding, Observation)
            .join(
                Decision,
                and_(
                    Decision.user_id == Binding.user_id,
                    Decision.id == Binding.decision_id,
                ),
            )
            .join(
                Observation,
                and_(
                    Observation.user_id == Decision.user_id,
                    Observation.id == Decision.observation_id,
                ),
            )
            .where(Binding.user_id == actor.id, Decision.superseded_at.is_(None))
        )

    def _weak_candidates(
        self,
        db: Session,
        actor: Account,
        observation: Observation,
        data: DiscoveryInput,
    ) -> list[str]:
        model_match = select(Assertion.subject_id).where(
            Assertion.user_id == actor.id,
            Assertion.predicate == "product_model",
            Assertion.object_id == observation.product_id,
            Assertion.superseded_at.is_(None),
        )
        aliases = select(Alias.entity_id).where(
            Alias.user_id == actor.id, Alias.normalized_name == normalized(data.name)
        )
        query = (
            select(Entity.id)
            .where(
                Entity.user_id == actor.id,
                Entity.kind == "asset",
                or_(
                    Entity.normalized_name == normalized(data.name),
                    Entity.id.in_(aliases),
                    Entity.id.in_(model_match) if observation.product_id else false(),
                ),
            )
            .order_by(Entity.id)
            .limit(101)
        )
        rows = list(db.scalars(query))
        # Preserve the overflow signal before collapsing equivalent records.
        return (
            rows
            if len(rows) > 100
            else sorted({canonical_id(db, actor, identifier) for identifier in rows})
        )

    def _choose(
        self,
        db: Session,
        actor: Account,
        observation: Observation,
        data: DiscoveryInput,
        line_conflict: bool,
    ) -> tuple[str, str, list[str], list[str]]:
        candidates = self._weak_candidates(db, actor, observation, data)
        if data.kind in {"payment", "mention"}:
            return (
                "review",
                "Source does not establish possession or item contents",
                [],
                candidates[:100],
            )
        if line_conflict:
            return (
                "review",
                "Order line product or quantity conflicts",
                [],
                candidates[:100],
            )
        if len(candidates) > 100:
            return (
                "review",
                "Candidate limit reached; narrow identity",
                [],
                candidates[:100],
            )
        serial_rows = (
            list(
                db.execute(
                    self._active_bindings(actor)
                    .where(Observation.serial_key == observation.serial_key)
                    .limit(101)
                )
            )
            if observation.serial_key
            else []
        )
        line_rows = (
            list(
                db.execute(
                    self._active_bindings(actor)
                    .where(Observation.line_id == observation.line_id)
                    .limit(101)
                )
            )
            if observation.line_id
            else []
        )
        if len(serial_rows) > 100 or len(line_rows) > 100:
            return "review", "Identity evidence limit reached", [], candidates[:100]
        targets: list[str] = []
        for unit in range(data.quantity):
            matches = {
                canonical_id(db, actor, binding.asset_id)
                for binding, _ in line_rows
                if binding.unit == unit
            }
            matches.update(
                canonical_id(db, actor, binding.asset_id) for binding, _ in serial_rows
            )
            if len(matches) > 1:
                return (
                    "review",
                    "Identifiers point to different physical items",
                    [],
                    sorted(set(candidates) | matches)[:100],
                )
            if matches:
                target = next(iter(matches))
                evidence_rows = list(
                    db.execute(
                        self._active_bindings(actor)
                        .where(Binding.asset_id.in_(member_ids(db, actor, target)))
                        .limit(101)
                    )
                )
                if len(evidence_rows) > 100:
                    return (
                        "review",
                        "Identity evidence limit reached",
                        [],
                        candidates[:100],
                    )
                if any(
                    (
                        observation.product_id
                        and other.product_id
                        and observation.product_id != other.product_id
                    )
                    or (
                        observation.serial_key
                        and other.serial_key
                        and observation.serial_key != other.serial_key
                    )
                    for _, other in evidence_rows
                ):
                    return (
                        "review",
                        "Serial or product context conflicts",
                        [],
                        sorted(set(candidates) | {target})[:100],
                    )
                targets.append(target)
        if targets:
            if len(targets) != data.quantity or len(set(targets)) != data.quantity:
                return (
                    "review",
                    "Incomplete or conflicting purchased-unit identity",
                    [],
                    candidates[:100],
                )
            excluded = db.scalar(
                select(Entity.id)
                .where(
                    Entity.user_id == actor.id,
                    Entity.id.in_(targets),
                    current_ownership(actor, False),
                )
                .limit(1)
            )
            if excluded:
                return (
                    "review",
                    "Existing ownership correction conflicts with this discovery",
                    [],
                    targets,
                )
            return (
                "enrich",
                "Matched order unit or manufacturer-scoped serial",
                targets,
                [],
            )
        if observation.serial_key or observation.line_id:
            historical = list(
                db.scalars(
                    select(Binding.asset_id)
                    .join(
                        Decision,
                        and_(
                            Decision.user_id == Binding.user_id,
                            Decision.id == Binding.decision_id,
                        ),
                    )
                    .join(
                        Observation,
                        and_(
                            Observation.user_id == Decision.user_id,
                            Observation.id == Decision.observation_id,
                        ),
                    )
                    .where(
                        Binding.user_id == actor.id,
                        or_(
                            Observation.serial_key == observation.serial_key
                            if observation.serial_key
                            else false(),
                            Observation.line_id == observation.line_id
                            if observation.line_id
                            else false(),
                        ),
                    )
                    .distinct()
                    .order_by(Binding.asset_id)
                    .limit(101)
                )
            )
            if historical:
                return (
                    "review",
                    "Known identity was previously corrected or excluded",
                    [],
                    sorted(
                        set(candidates)
                        | {
                            canonical_id(db, actor, identifier)
                            for identifier in historical
                        }
                    )[:100],
                )
        if candidates:
            # A different explicit order distinguishes purchased units only when all
            # same-product candidates already have an active order anchor.
            anchored = set(
                db.scalars(
                    self._active_bindings(actor)
                    .with_only_columns(Binding.asset_id)
                    .where(
                        Binding.asset_id.in_(
                            [
                                member
                                for identifier in candidates
                                for member in member_ids(db, actor, identifier)
                            ]
                        ),
                        Observation.line_id.is_not(None),
                    )
                    .distinct()
                    .limit(101)
                )
            )
            anchored = {canonical_id(db, actor, identifier) for identifier in anchored}
            if observation.line_id is None or set(candidates) - anchored:
                return (
                    "review",
                    "Product or name similarity does not establish physical identity",
                    [],
                    candidates,
                )
        return "create", "New sourced item; current ownership is inferred", [], []
