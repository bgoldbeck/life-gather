import hashlib
import json
import re
import time
import unicodedata
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import Engine, Select, and_, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from lifegather.assets.identity import canonical_id, member_ids, secondary_ids
from lifegather.auth.store import Account
from lifegather.memory.models import (
    Alias,
    Assertion,
    Audit,
    Entity,
    Episode,
    Evidence,
    NoteRevision,
)
from lifegather.memory.schemas import (
    EntityInput,
    EntityView,
    FactInput,
    FactView,
    SourceInput,
    SourceView,
)


class MemoryError(ValueError):
    """A bounded domain failure; no raw source data is included in the message."""


def normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def bounded(limit: int) -> int:
    if not 1 <= limit <= 100:
        raise MemoryError("Limit must be between 1 and 100")
    return limit


class MemoryService:
    def __init__(self, engine: Engine, clock: Callable[[], int] | None = None) -> None:
        self.engine = engine
        self.clock = clock or (lambda: time.time_ns() // 1000)

    @contextmanager
    def _write(self) -> Iterator[Session]:
        with Session(self.engine) as db:
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except IntegrityError:
                db.rollback()
                raise MemoryError("Memory write rejected by integrity checks") from None
            except Exception:
                db.rollback()
                raise

    @staticmethod
    def _source(db: Session, actor: Account, identifier: str) -> Episode:
        source = db.scalar(
            select(Episode)
            .where(Episode.user_id == actor.id, Episode.id == identifier)
            .limit(1)
        )
        if source is None:
            raise MemoryError("Source not found")
        return source

    @staticmethod
    def _entity(db: Session, actor: Account, identifier: str) -> Entity:
        entity = db.scalar(
            select(Entity)
            .where(Entity.user_id == actor.id, Entity.id == identifier)
            .limit(1)
        )
        if entity is None:
            raise MemoryError("Entity not found")
        return entity

    @staticmethod
    def _assertion(db: Session, actor: Account, identifier: str) -> Assertion:
        fact = db.scalar(
            select(Assertion)
            .where(Assertion.user_id == actor.id, Assertion.id == identifier)
            .limit(1)
        )
        if fact is None:
            raise MemoryError("Fact not found")
        return fact

    def _audit(
        self, db: Session, actor: Account, operation: str, target: str, now: int
    ) -> None:
        from lifegather.memory.origins import origin_json

        db.add(
            Audit(
                id=str(uuid4()),
                user_id=actor.id,
                operation=operation,
                target_id=target,
                recorded_at=now,
                provenance_json=origin_json(),
            )
        )

    @staticmethod
    def _index(
        db: Session, actor: Account, identifier: str, kind: str, body: str
    ) -> None:
        db.execute(
            text(
                "DELETE FROM memory_fts WHERE user_id=:owner "
                "AND record_id=:id AND kind=:kind"
            ),
            {"owner": actor.id, "id": identifier, "kind": kind},
        )
        db.execute(
            text(
                "INSERT INTO memory_fts(record_id,user_id,kind,body) "
                "VALUES (:id,:owner,:kind,:body)"
            ),
            {"owner": actor.id, "id": identifier, "kind": kind, "body": body},
        )

    def ingest(self, actor: Account, value: SourceInput) -> SourceView:
        with self._write() as db:
            return self._ingest_in(db, actor, value)

    def _ingest_in(
        self,
        db: Session,
        actor: Account,
        value: SourceInput,
        *,
        recorded_at: int | None = None,
    ) -> SourceView:
        data = SourceInput.model_validate(value)
        content_hash = hashlib.sha256(data.text.encode()).hexdigest()
        context = [data.source_type, data.namespace]
        key = fingerprint(
            context
            + (
                ["external", data.external_id]
                if data.external_id
                else ["content", content_hash, data.event_date]
            )
        )
        existing = db.scalar(
            select(Episode)
            .where(Episode.user_id == actor.id, Episode.source_key == key)
            .limit(1)
        )
        if existing is not None:
            if (
                existing.content_hash != content_hash
                or existing.event_date != data.event_date
            ):
                raise MemoryError(
                    "Source identity conflict: use a new source revision ID"
                )
            return SourceView.model_validate(existing)
        now = self.clock() if recorded_at is None else recorded_at
        source = Episode(
            id=str(uuid4()),
            user_id=actor.id,
            source_key=key,
            content_hash=content_hash,
            recorded_at=now,
            **data.model_dump(),
        )
        db.add(source)
        db.flush()
        self._index(db, actor, source.id, "source", source.text)
        self._audit(db, actor, "source_ingested", source.id, now)
        return SourceView.model_validate(source)

    def get_source(self, actor: Account, identifier: str) -> SourceView:
        with Session(self.engine) as db:
            return SourceView.model_validate(self._source(db, actor, identifier))

    def create_entity(self, actor: Account, value: EntityInput) -> EntityView:
        data = EntityInput.model_validate(value)
        with self._write() as db:
            return self._create_entity_in(db, actor, data)

    def _create_entity_in(
        self,
        db: Session,
        actor: Account,
        data: EntityInput,
        *,
        recorded_at: int | None = None,
    ) -> EntityView:
        signature = fingerprint(data.model_dump(mode="json"))
        source = self._source(db, actor, data.source_id)
        existing = db.scalar(
            select(Entity)
            .where(
                Entity.user_id == actor.id,
                Entity.operation_key == data.operation_key,
            )
            .limit(1)
        )
        if existing is not None:
            if existing.fingerprint != signature:
                raise MemoryError("Entity operation conflict")
            return EntityView.model_validate(existing)
        now = max(
            self.clock() if recorded_at is None else recorded_at, source.recorded_at
        )
        entity = Entity(
            id=str(uuid4()),
            user_id=actor.id,
            normalized_name=normalized(data.name),
            fingerprint=signature,
            recorded_at=now,
            **data.model_dump(),
        )
        db.add(entity)
        db.flush()
        self._index(db, actor, entity.id, "entity", entity.name)
        self._audit(db, actor, "entity_created", entity.id, now)
        return EntityView.model_validate(entity)

    def get_entity(
        self, actor: Account, identifier: str, *, known_at: int | None = None
    ) -> EntityView:
        with Session(self.engine) as db:
            self._entity(db, actor, identifier)
            identifier = member_ids(db, actor, identifier, known_at=known_at)[0]
            return EntityView.model_validate(self._entity(db, actor, identifier))

    def list_entities(
        self, actor: Account, cursor: str = "", limit: int = 25
    ) -> dict[str, Any]:
        bounded(limit)
        if len(cursor) > 36:
            raise MemoryError("Invalid cursor")
        with Session(self.engine) as db:
            rows = list(
                db.scalars(
                    select(Entity)
                    .where(
                        Entity.user_id == actor.id,
                        Entity.id > cursor,
                        Entity.id.not_in(secondary_ids(actor)),
                    )
                    .order_by(Entity.id)
                    .limit(limit + 1)
                )
            )
            return {
                "items": [EntityView.model_validate(row) for row in rows[:limit]],
                "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
            }

    def add_alias(
        self, actor: Account, entity_id: str, name: str, source_id: str
    ) -> None:
        if not name.strip() or len(name) > 200:
            raise MemoryError("Alias must contain 1 to 200 characters")
        label = normalized(name)
        with self._write() as db:
            entity = self._entity(db, actor, entity_id)
            source = self._source(db, actor, source_id)
            if label not in normalized(source.text):
                raise MemoryError("Alias must appear in its source text")
            exists = db.scalar(
                select(Alias.id)
                .where(
                    Alias.user_id == actor.id,
                    Alias.entity_id == entity_id,
                    Alias.normalized_name == label,
                    Alias.source_id == source_id,
                )
                .limit(1)
            )
            if exists is not None:
                return
            now = self.clock()
            db.add(
                Alias(
                    id=str(uuid4()),
                    user_id=actor.id,
                    entity_id=entity_id,
                    name=name,
                    normalized_name=label,
                    source_id=source_id,
                    recorded_at=now,
                )
            )
            db.flush()
            aliases = list(
                db.scalars(
                    select(Alias.name)
                    .where(Alias.user_id == actor.id, Alias.entity_id == entity_id)
                    .limit(101)
                )
            )
            if len(aliases) > 100:
                raise MemoryError("Alias limit reached")
            self._index(
                db, actor, entity_id, "entity", entity.name + "\n" + "\n".join(aliases)
            )
            self._audit(db, actor, "alias_added", entity_id, now)

    def find_entities(
        self, actor: Account, name: str, limit: int = 25
    ) -> list[EntityView]:
        bounded(limit)
        if not name.strip() or len(name) > 200:
            raise MemoryError("Invalid name")
        label = normalized(name)
        with Session(self.engine) as db:
            aliases = select(Alias.entity_id).where(
                Alias.user_id == actor.id, Alias.normalized_name == label
            )
            rows = list(
                db.scalars(
                    select(Entity)
                    .where(
                        Entity.user_id == actor.id,
                        or_(Entity.normalized_name == label, Entity.id.in_(aliases)),
                    )
                    .order_by(Entity.id)
                    .limit(limit * 2)
                )
            )
            canonical = sorted({canonical_id(db, actor, row.id) for row in rows})
            return [
                EntityView.model_validate(self._entity(db, actor, identifier))
                for identifier in canonical[:limit]
            ]

    @staticmethod
    def _view(
        db: Session, actor: Account, row: Assertion, known_at: int | None = None
    ) -> FactView:
        query = select(Evidence).where(
            Evidence.user_id == actor.id, Evidence.fact_id == row.id
        )
        if known_at is not None:
            query = query.where(Evidence.recorded_at <= known_at)
        evidence = list(db.scalars(query.order_by(Evidence.id).limit(100)))
        label = None
        display_value = None
        if row.predicate.startswith("profile_template_") and known_at is None:
            from lifegather.assets.type_models import AssetTypeField

            label = db.scalar(
                select(AssetTypeField.name).where(
                    AssetTypeField.user_id == actor.id,
                    AssetTypeField.id
                    == row.predicate.removeprefix("profile_template_"),
                )
            )
        if row.predicate == "profile_asset_type" and known_at is None:
            from lifegather.assets.type_models import AssetType

            label = "Asset type"
            display_value = db.scalar(
                select(AssetType.name).where(
                    AssetType.user_id == actor.id,
                    AssetType.id == json.loads(row.value_json or "null"),
                )
            )
        return FactView(
            label=label,
            display_value=display_value,
            id=row.id,
            subject_id=row.subject_id,
            predicate=row.predicate,
            object_id=row.object_id,
            value=json.loads(row.value_json) if row.value_json is not None else None,
            status=row.status,
            valid_from=row.valid_from,
            valid_to=row.valid_to,
            recorded_at=row.recorded_at,
            superseded_at=row.superseded_at,
            replaces_id=row.replaces_id,
            evidence=[
                {"source_id": item.source_id, "quote": item.quote} for item in evidence
            ],
        )

    def assert_fact(self, actor: Account, value: FactInput) -> FactView:
        return self._put_fact(actor, value, None)

    def attach_evidence(
        self, actor: Account, fact_id: str, source_id: str, quote: str | None = None
    ) -> None:
        with self._write() as db:
            fact = self._assertion(db, actor, fact_id)
            source = self._source(db, actor, source_id)
            if quote is not None and (
                not quote or len(quote) > 2000 or quote not in source.text
            ):
                raise MemoryError("Evidence quote must appear in its source")
            existing = db.scalar(
                select(Evidence)
                .where(
                    Evidence.user_id == actor.id,
                    Evidence.fact_id == fact_id,
                    Evidence.source_id == source_id,
                )
                .limit(1)
            )
            if existing is not None:
                if existing.quote != quote:
                    raise MemoryError("Evidence link conflict")
                return
            identifiers = list(
                db.scalars(
                    select(Evidence.id)
                    .where(
                        Evidence.user_id == actor.id,
                        Evidence.fact_id == fact_id,
                    )
                    .limit(100)
                )
            )
            if len(identifiers) >= 100:
                raise MemoryError("Evidence limit reached")
            now = max(self.clock(), fact.recorded_at, source.recorded_at)
            db.add(
                Evidence(
                    id=str(uuid4()),
                    user_id=actor.id,
                    fact_id=fact_id,
                    source_id=source_id,
                    quote=quote,
                    recorded_at=now,
                )
            )
            self._audit(db, actor, "evidence_attached", fact_id, now)

    def correct_fact(self, actor: Account, fact_id: str, value: FactInput) -> FactView:
        return self._put_fact(actor, value, fact_id)

    def _put_fact(
        self, actor: Account, value: FactInput, replaces: str | None
    ) -> FactView:
        data = FactInput.model_validate(value)
        with self._write() as db:
            return self._put_fact_in(db, actor, data, replaces)

    def _put_fact_in(
        self,
        db: Session,
        actor: Account,
        data: FactInput,
        replaces: str | None,
        *,
        recorded_at: int | None = None,
    ) -> FactView:
        signature = fingerprint([data.model_dump(mode="json"), replaces])
        self._entity(db, actor, data.subject_id)
        source = self._source(db, actor, data.source_id)
        if data.object_id is not None:
            self._entity(db, actor, data.object_id)
        if data.quote is not None and data.quote not in source.text:
            raise MemoryError("Evidence quote is not present in the original source")
        previous = self._assertion(db, actor, replaces) if replaces else None
        existing = db.scalar(
            select(Assertion)
            .where(
                Assertion.user_id == actor.id,
                Assertion.operation_key == data.operation_key,
            )
            .limit(1)
        )
        if existing is not None:
            if existing.fingerprint != signature:
                raise MemoryError("Fact operation conflict")
            return self._view(db, actor, existing)
        now = max(
            self.clock() if recorded_at is None else recorded_at, source.recorded_at
        )
        if previous is not None:
            if previous.superseded_at is not None:
                raise MemoryError("Fact already corrected; correct the current version")
            if (
                previous.subject_id != data.subject_id
                or previous.predicate != data.predicate
            ):
                raise MemoryError("Correction must preserve subject and predicate")
            now = max(now, previous.recorded_at + 1)
            previous.superseded_at = now
        fact = Assertion(
            id=str(uuid4()),
            user_id=actor.id,
            subject_id=data.subject_id,
            predicate=data.predicate,
            object_id=data.object_id,
            value_json=json.dumps(data.value) if data.object_id is None else None,
            status=data.status,
            valid_from=data.valid_from,
            valid_to=data.valid_to,
            recorded_at=now,
            superseded_at=None,
            replaces_id=replaces,
            operation_key=data.operation_key,
            fingerprint=signature,
        )
        db.add(fact)
        db.flush()
        sources: dict[str, str | None] = {}
        if previous is not None:
            old_evidence = list(
                db.scalars(
                    select(Evidence)
                    .where(
                        Evidence.user_id == actor.id,
                        Evidence.fact_id == previous.id,
                    )
                    .limit(100)
                )
            )
            sources.update({item.source_id: item.quote for item in old_evidence})
        sources[source.id] = data.quote
        if len(sources) > 100:
            raise MemoryError("Evidence limit reached")
        for source_id, quote in sources.items():
            db.add(
                Evidence(
                    id=str(uuid4()),
                    user_id=actor.id,
                    fact_id=fact.id,
                    source_id=source_id,
                    quote=quote,
                    recorded_at=now,
                )
            )
        self._audit(
            db,
            actor,
            "fact_corrected" if previous else "fact_asserted",
            fact.id,
            now,
        )
        db.flush()
        return self._view(db, actor, fact)

    def facts(
        self,
        actor: Account,
        entity_id: str,
        *,
        world_date: str | None = None,
        known_at: int | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> list[FactView]:
        bounded(limit)
        try:
            when = date.fromisoformat(world_date) if world_date is not None else None
        except ValueError:
            raise MemoryError("Invalid world date") from None
        if known_at is not None and known_at < 0:
            raise MemoryError("Invalid recorded timestamp")
        with Session(self.engine) as db:
            self._entity(db, actor, entity_id)
            identifiers = member_ids(db, actor, entity_id, known_at=known_at)
            query = select(Assertion).where(
                Assertion.user_id == actor.id, Assertion.subject_id.in_(identifiers)
            )
            if known_at is None:
                query = query.where(Assertion.superseded_at.is_(None))
            else:
                query = query.where(
                    Assertion.recorded_at <= known_at,
                    or_(
                        Assertion.superseded_at.is_(None),
                        Assertion.superseded_at > known_at,
                    ),
                )
            if when is not None:
                query = query.where(
                    Assertion.valid_from.is_not(None),
                    Assertion.valid_from <= when,
                    or_(Assertion.valid_to.is_(None), Assertion.valid_to > when),
                )
            query = self._after(
                db, actor, entity_id, query, cursor, identifiers=identifiers
            )
            return [
                self._view(db, actor, row, known_at)
                for row in db.scalars(
                    query.order_by(Assertion.recorded_at, Assertion.id).limit(limit)
                )
            ]

    def timeline(
        self,
        actor: Account,
        entity_id: str,
        limit: int = 100,
        *,
        cursor: str | None = None,
    ) -> list[FactView]:
        bounded(limit)
        with Session(self.engine) as db:
            self._entity(db, actor, entity_id)
            identifiers = member_ids(db, actor, entity_id)
            query = self._after(
                db,
                actor,
                entity_id,
                select(Assertion).where(
                    Assertion.user_id == actor.id, Assertion.subject_id.in_(identifiers)
                ),
                cursor,
            )
            return [
                self._view(db, actor, row)
                for row in db.scalars(
                    query.order_by(Assertion.recorded_at, Assertion.id).limit(limit)
                )
            ]

    def _after(
        self,
        db: Session,
        actor: Account,
        entity_id: str,
        query: Select[Assertion],
        cursor: str | None,
        *,
        identifiers: list[str] | None = None,
    ) -> Select[Assertion]:
        if cursor is None:
            return query
        if len(cursor) > 36:
            raise MemoryError("Invalid cursor")
        previous = self._assertion(db, actor, cursor)
        if previous.subject_id not in (identifiers or member_ids(db, actor, entity_id)):
            raise MemoryError("Invalid cursor")
        return query.where(
            or_(
                Assertion.recorded_at > previous.recorded_at,
                and_(
                    Assertion.recorded_at == previous.recorded_at,
                    Assertion.id > previous.id,
                ),
            )
        )

    def search(
        self, actor: Account, query: str, limit: int = 25
    ) -> list[dict[str, str]]:
        bounded(limit)
        if not query.strip() or len(query) > 200:
            raise MemoryError("Search requires 1 to 200 characters")
        words = re.findall(r"[^\W_]+", query, re.UNICODE)
        if not words or len(words) > 12:
            raise MemoryError("Search requires 1 to 12 words")
        match = " AND ".join('"' + word + '"' for word in words)
        with Session(self.engine) as db:
            matches = db.execute(
                text(
                    "SELECT record_id,kind FROM memory_fts "
                    "WHERE memory_fts MATCH :query "
                    "AND user_id=:owner AND NOT EXISTS ("
                    "SELECT 1 FROM memory_note_revisions r "
                    "WHERE r.user_id=memory_fts.user_id "
                    "AND r.previous_source_id=memory_fts.record_id "
                    "AND memory_fts.kind='source') "
                    "ORDER BY kind,record_id LIMIT :limit"
                ),
                {"query": match, "owner": actor.id, "limit": limit},
            ).all()
            results = []
            for identifier, kind in matches:
                if kind == "entity":
                    entity = self._entity(
                        db, actor, canonical_id(db, actor, identifier)
                    )
                    identifier = entity.id
                    label = entity.name
                else:
                    label = self._source(db, actor, identifier).text[:240]
                item = {"id": identifier, "kind": kind, "text": label}
                if item not in results:
                    results.append(item)
            return results

    def related(
        self, actor: Account, entity_id: str, *, depth: int = 1, limit: int = 50
    ) -> dict[str, Any]:
        bounded(limit)
        if depth not in {1, 2}:
            raise MemoryError("Graph depth must be 1 or 2")
        with Session(self.engine) as db:
            self._entity(db, actor, entity_id)
            identifiers = member_ids(db, actor, entity_id)
            visited, frontier = set(identifiers), set(identifiers)
            edges: dict[str, FactView] = {}
            truncated = False
            for _ in range(depth):
                rows = list(
                    db.scalars(
                        select(Assertion)
                        .where(
                            Assertion.user_id == actor.id,
                            Assertion.object_id.is_not(None),
                            Assertion.superseded_at.is_(None),
                            or_(
                                Assertion.subject_id.in_(frontier),
                                Assertion.object_id.in_(frontier),
                            ),
                            Assertion.id.not_in(list(edges)),
                        )
                        .order_by(Assertion.id)
                        .limit(limit - len(edges) + 1)
                    )
                )
                if len(rows) > limit - len(edges):
                    truncated = True
                next_frontier: set[str] = set()
                for row in rows[: limit - len(edges)]:
                    edges[row.id] = self._view(db, actor, row)
                    next_frontier.update(
                        {row.subject_id, row.object_id or row.subject_id}
                    )
                next_frontier = {
                    member
                    for identifier in next_frontier
                    for member in member_ids(db, actor, identifier)
                }
                next_frontier -= visited
                visited |= next_frontier
                frontier = next_frontier
                if not frontier or len(edges) == limit:
                    truncated = truncated or len(edges) == limit
                    break
            nodes = list(
                db.scalars(
                    select(Entity)
                    .where(Entity.user_id == actor.id, Entity.id.in_(visited))
                    .order_by(Entity.id)
                    .limit(201)
                )
            )
            canonical_nodes = sorted({canonical_id(db, actor, row.id) for row in nodes})
            return {
                "nodes": [
                    EntityView.model_validate(self._entity(db, actor, identifier))
                    for identifier in canonical_nodes
                ],
                "edges": [
                    edge.model_copy(
                        update={
                            "subject_id": canonical_id(db, actor, edge.subject_id),
                            "object_id": canonical_id(db, actor, edge.object_id)
                            if edge.object_id
                            else None,
                        }
                    )
                    for edge in edges.values()
                ],
                "identity_projection": [
                    {
                        "original_id": row.id,
                        "primary_id": canonical_id(db, actor, row.id),
                    }
                    for row in nodes
                    if canonical_id(db, actor, row.id) != row.id
                ],
                "truncated": truncated,
            }

    def export_page(
        self,
        actor: Account,
        collection: Literal[
            "sources",
            "entities",
            "aliases",
            "facts",
            "evidence",
            "audit",
            "note_revisions",
        ],
        cursor: str = "",
        limit: int = 100,
    ) -> dict[str, Any]:
        bounded(limit)
        models = {
            "sources": Episode,
            "entities": Entity,
            "aliases": Alias,
            "facts": Assertion,
            "evidence": Evidence,
            "audit": Audit,
            "note_revisions": NoteRevision,
        }
        if collection not in models or len(cursor) > 36:
            raise MemoryError("Invalid export page")
        table = models[collection].__table__
        with self.engine.connect() as connection:
            rows = list(
                connection.execute(
                    select(table)
                    .where(table.c.user_id == actor.id, table.c.id > cursor)
                    .order_by(table.c.id)
                    .limit(limit + 1)
                ).mappings()
            )
            return {
                "items": [
                    {
                        name: value.isoformat() if isinstance(value, date) else value
                        for name, value in row.items()
                        if name != "user_id"
                    }
                    for row in rows[:limit]
                ],
                "next_cursor": str(rows[limit - 1]["id"])
                if len(rows) > limit
                else None,
            }
