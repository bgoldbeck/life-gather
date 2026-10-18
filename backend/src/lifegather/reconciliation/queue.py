"""One durable inbox over existing proposals and current identity decisions."""

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Engine, literal, select, union_all
from sqlalchemy.orm import Session

from lifegather.auth.store import Account
from lifegather.memory.notes import NoteConflict, NoteService
from lifegather.memory.service import MemoryError, MemoryService, fingerprint
from lifegather.reconciliation.models import Decision
from lifegather.reconciliation.proposal_models import AssetProposal
from lifegather.reconciliation.proposals import AssetExtraction, ProposalService
from lifegather.reconciliation.schemas import DiscoveryInput
from lifegather.reconciliation.service import ReconciliationService


class ReviewPage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["all", "proposals", "identities"] = "all"
    cursor: str = Field(default="", max_length=38, pattern=r"^(?:[dp]:[a-f0-9-]{36})?$")
    limit: int = Field(default=25, ge=1, le=25)


class IdentityRead(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    observation_id: str = Field(min_length=1, max_length=36)


class IdentityReview(IdentityRead):
    expected_decision_id: str = Field(min_length=1, max_length=36)
    action: Literal["new", "link", "dismiss"]
    asset_ids: list[str] = Field(default_factory=list, max_length=20)
    candidate_ids: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def choices(self) -> Self:
        if (self.action == "link") != bool(self.asset_ids):
            raise ValueError("Choose existing items only when linking")
        if any(
            not value or len(value) > 36
            for value in self.asset_ids + self.candidate_ids
        ):
            raise ValueError("Invalid item identifier")
        if len(set(self.asset_ids)) != len(self.asset_ids):
            raise ValueError("Each unit must be a distinct physical item")
        return self


class ReviewService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.memory = MemoryService(engine)
        self.reconcile = ReconciliationService(engine)
        self.proposals = ProposalService(engine)

    def list(self, actor: Account, value: ReviewPage) -> dict[str, Any]:
        data = ReviewPage.model_validate(value)
        proposals = select((literal("p:") + AssetProposal.id).label("key")).where(
            AssetProposal.user_id == actor.id, AssetProposal.state == "proposed"
        )
        identities = select(
            (literal("d:") + Decision.observation_id).label("key")
        ).where(
            Decision.user_id == actor.id,
            Decision.outcome == "review",
            Decision.superseded_at.is_(None),
        )
        query = (
            proposals
            if data.kind == "proposals"
            else identities
            if data.kind == "identities"
            else union_all(identities, proposals)
        ).subquery()
        with Session(self.engine) as db:
            keys = list(
                db.scalars(
                    select(query.c.key)
                    .where(query.c.key > data.cursor)
                    .order_by(query.c.key)
                    .limit(data.limit + 1)
                )
            )
            items = []
            for key in keys[: data.limit]:
                if key.startswith("p:"):
                    row = self.proposals._owned(db, actor, key[2:])
                    proposed = AssetExtraction.model_validate_json(row.proposed_json)
                    source = self.memory._source(db, actor, row.source_id)
                    items.append(
                        {
                            "key": key,
                            "kind": "proposal",
                            "id": row.id,
                            "name": proposed.candidate.name
                            if proposed.candidate
                            else "Unclear item",
                            "reason": proposed.explanation,
                            "source_id": source.id,
                            "recorded_at": row.recorded_at,
                        }
                    )
                else:
                    observation = self.reconcile._observation(db, actor, key[2:])
                    decision = self.reconcile._current(db, actor, key[2:])
                    payload = DiscoveryInput.model_validate_json(observation.payload)
                    items.append(
                        {
                            "key": key,
                            "kind": "identity",
                            "id": observation.id,
                            "name": payload.name,
                            "reason": decision.reason,
                            "source_id": payload.source_id,
                            "recorded_at": decision.recorded_at,
                        }
                    )
            return {
                "items": items,
                "next_cursor": keys[data.limit - 1] if len(keys) > data.limit else None,
            }

    def _detail(self, db: Session, actor: Account, identifier: str) -> dict[str, Any]:
        observation = self.reconcile._observation(db, actor, identifier)
        decision = self.reconcile._current(db, actor, identifier)
        payload = DiscoveryInput.model_validate_json(observation.payload)
        candidates, reliable = self.proposals._matches(db, actor, payload)
        outcome, _, targets, additional = self.reconcile.matcher._choose(
            db, actor, observation, payload, False
        )
        candidates = sorted(set(candidates + targets + additional))[:100]
        if outcome == "enrich":
            reliable = sorted(set(reliable + targets))
        return {
            "observation_id": identifier,
            "decision_id": decision.id,
            "outcome": decision.outcome,
            "reason": decision.reason,
            "observation": payload.model_dump(mode="json"),
            "candidates": [
                {"id": i, "name": self.memory._entity(db, actor, i).name}
                for i in candidates
            ],
            "reliable_ids": reliable,
        }

    def detail(self, actor: Account, identifier: str) -> dict[str, Any]:
        with Session(self.engine) as db:
            return self._detail(db, actor, identifier)

    def review(self, actor: Account, value: IdentityReview) -> dict[str, Any]:
        data = IdentityReview.model_validate(value)
        action: Literal["resolve", "dismiss"] = (
            "dismiss" if data.action == "dismiss" else "resolve"
        )
        targets = data.asset_ids if data.action == "link" else None
        with self.memory._write() as db:
            observation = self.reconcile._observation(db, actor, data.observation_id)
            old = self.reconcile._decision(db, actor, data.expected_decision_id)
            if old.observation_id != observation.id or old.outcome != "review":
                raise NoteConflict("Choose a pending identity review")
            # An exact replay remains safe even if subsequent evidence changed.
            successor = db.scalar(
                select(Decision).where(
                    Decision.user_id == actor.id, Decision.previous_id == old.id
                )
            )
            if successor:
                if successor.request_key != fingerprint([action, targets]):
                    raise NoteConflict("Review changed. Reload it before continuing.")
                return self.reconcile._view(db, actor, successor).model_dump(
                    mode="json"
                )
            if data.action != "dismiss":
                payload = DiscoveryInput.model_validate_json(observation.payload)
                source = self.memory._source(db, actor, payload.source_id)
                if NoteService.is_note(source):
                    self.proposals._source(db, actor, source.id)
                detail = self._detail(db, actor, observation.id)
                candidates = sorted(c["id"] for c in detail["candidates"])
                if sorted(data.candidate_ids) != candidates:
                    raise NoteConflict(
                        "Possible duplicates changed. Reload this review."
                    )
                if data.action == "new" and detail["reliable_ids"]:
                    raise MemoryError(
                        "An identifier matches an existing item; review that item"
                    )
                if data.action == "link" and not set(data.asset_ids) <= set(candidates):
                    raise MemoryError(
                        "Choose existing candidate items from this review"
                    )
            return self.reconcile._change_in(
                db, actor, observation.id, old.id, action, targets
            ).model_dump(mode="json")
