"""Erase one source (a Gmail connection or a finished scan) and what came from it.

Memory deletion keeps records made from a memory; account deletion removes
everything. Erasure deletes the source's rows and every row derived from them,
found by following the database's own foreign keys (read from pg_catalog, as
account deletion does) so new tables are covered without a list to maintain.
Records that a kept source also supports stay, attributed to that source.
"""

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from lifegather.auth.deletion import deletion_order
from lifegather.auth.store import Account
from lifegather.database import begin_serialized
from lifegather.mailboxes.models import Mailbox
from lifegather.memory.notes import NoteConflict
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.scans.models import ScanRun, ScanSchedule
from lifegather.storage.base import ObjectStorage, StorageError

SOURCE_ERASED = "source_erased"
ACTIVE = ("queued", "running")

# Foreign keys as (child, parent, child column paired with the parent's id,
# child column nullable, ON DELETE SET NULL), in the application schema.
LINKS = text(
    """
    SELECT child.relname, parent.relname, ca.attname, NOT ca.attnotnull,
           k.confdeltype = 'n'
    FROM pg_constraint k
    JOIN pg_class child ON child.oid = k.conrelid
    JOIN pg_class parent ON parent.oid = k.confrelid
    JOIN pg_namespace n ON n.oid = child.relnamespace
    CROSS JOIN LATERAL unnest(k.conkey, k.confkey) AS u(ck, pk)
    JOIN pg_attribute ca ON ca.attrelid = k.conrelid AND ca.attnum = u.ck
    JOIN pg_attribute pa ON pa.attrelid = k.confrelid AND pa.attnum = u.pk
    WHERE k.contype = 'f' AND n.nspname = current_schema() AND pa.attname = 'id'
      AND parent.relname <> 'users'
    """
)
COLUMNS = text(
    """
    SELECT table_name, column_name FROM information_schema.columns
    WHERE table_schema = current_schema() AND column_name IN ('id', 'superseded_at')
    """
)
# Nullable references whose row stays, with the reference cleared, when the
# referenced row is erased: the row stands on its own evidence. Every nullable
# self-reference (a revision chain) is also detached.
DETACHED = {
    ("scan_schedules", "last_run_id"),
    ("reconciliation_observations", "line_id"),
    ("reconciliation_bindings", "product_fact_id"),
}
# Kept sources that also support an entity, so it survives erasure of the
# source it was first created from.
SUPPORT = text(
    """
    SELECT entity, source FROM (
      SELECT f.subject_id AS entity, e.source_id AS source
      FROM memory_evidence e JOIN memory_facts f
        ON f.user_id = e.user_id AND f.id = e.fact_id
      WHERE e.user_id = :owner
      UNION ALL
      SELECT f.object_id, e.source_id FROM memory_evidence e JOIN memory_facts f
        ON f.user_id = e.user_id AND f.id = e.fact_id
      WHERE e.user_id = :owner AND f.object_id IS NOT NULL
      UNION ALL
      SELECT entity_id, source_id FROM memory_aliases WHERE user_id = :owner
      UNION ALL
      SELECT entity_id, source_id FROM maintenance_tasks WHERE user_id = :owner
      UNION ALL
      SELECT asset_id, source_id FROM asset_actions WHERE user_id = :owner
      UNION ALL
      SELECT product_id, source_id FROM reconciliation_observations
      WHERE user_id = :owner AND product_id IS NOT NULL
      UNION ALL
      SELECT product_id, source_id FROM reconciliation_lines
      WHERE user_id = :owner AND product_id IS NOT NULL
    ) support
    WHERE entity = ANY(:entities) AND NOT source = ANY(:erased)
    """
)
# Facts whose own evidence is all erased. A correction copies the evidence of
# the fact it replaces; only the sources it added are its own (all, if none).
UNSUPPORTED = text(
    """
    WITH touched AS (
      SELECT DISTINCT fact_id FROM memory_evidence
      WHERE user_id = :owner AND id = ANY(:evidence)
    ), ev AS (
      SELECT e.fact_id, e.id = ANY(:evidence) AS gone,
             EXISTS (SELECT 1 FROM memory_facts f JOIN memory_evidence p
                       ON p.user_id = f.user_id AND p.fact_id = f.replaces_id
                     WHERE f.user_id = :owner AND f.id = e.fact_id
                       AND p.source_id = e.source_id) AS inherited
      FROM memory_evidence e JOIN touched t ON t.fact_id = e.fact_id
      WHERE e.user_id = :owner
    )
    SELECT fact_id FROM ev WHERE NOT fact_id = ANY(:facts)
    GROUP BY fact_id
    HAVING CASE WHEN bool_or(NOT inherited)
                THEN bool_and(gone) FILTER (WHERE NOT inherited)
                ELSE bool_and(gone) END
    """
)
# Originals uploaded while one of the erased scans ran.
UPLOADED = text(
    """
    SELECT operation, target_id FROM memory_audit
    WHERE user_id = :owner
      AND operation IN ('document_uploaded', 'photo_uploaded')
      AND provenance_json IS NOT NULL
      AND (provenance_json::jsonb ->> 'related_id') = ANY(:runs)
    """
)


class ErasureTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["mailbox", "scan"]
    id: str = Field(min_length=1, max_length=36)


class ErasureConfirm(ErasureTarget):
    fingerprint: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class ErasureError(MemoryError):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Link:
    child: str
    parent: str
    column: str
    nullable: bool
    set_null: bool

    @property
    def detached(self) -> bool:
        return self.nullable and (
            self.child == self.parent or (self.child, self.column) in DETACHED
        )


@dataclass
class Plan:
    erased: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    # Entity id -> the kept source it is attributed to from now on.
    rehomed: dict[str, str] = field(default_factory=dict)
    files: set[str] = field(default_factory=set)
    counts: dict[str, int] = field(default_factory=dict)

    def fingerprint(self) -> str:
        parts = sorted(
            f"{table}:{identifier}"
            for table, ids in self.erased.items()
            for identifier in ids
        ) + sorted(f"kept:{e}:{s}" for e, s in self.rehomed.items())
        return hashlib.sha256("\n".join(parts).encode()).hexdigest()

    def ids(self) -> list[str]:
        return sorted({i for ids in self.erased.values() for i in ids})


def _array(values: set[str]) -> list[str]:
    return sorted(values)


class SourceErasure:
    """Framework-independent; HTTP is a thin authenticated adapter."""

    def __init__(self, engine: Engine, storage: ObjectStorage | None) -> None:
        self.engine = engine
        self.storage = storage
        self.memory = MemoryService(engine)

    # Seeds: the source's own rows.

    def _seeds(
        self, db: Session, actor: Account, target: ErasureTarget
    ) -> tuple[Plan, set[str]]:
        plan = Plan()
        if target.kind == "mailbox":
            mailbox = db.scalar(
                select(Mailbox).where(
                    Mailbox.user_id == actor.id, Mailbox.id == target.id
                )
            )
            if mailbox is None:
                raise ErasureError("Mailbox not found", 404)
            plan.erased["mailboxes"].add(mailbox.id)
            if mailbox.credential_id:
                plan.erased["credentials"].add(mailbox.credential_id)
            runs = list(
                db.scalars(
                    select(ScanRun).where(
                        ScanRun.user_id == actor.id,
                        ScanRun.resource_key == "gmail:" + mailbox.id,
                    )
                )
            )
            for schedule in db.scalars(
                select(ScanSchedule).where(ScanSchedule.user_id == actor.id)
            ):
                config = json.loads(schedule.config_json)
                if isinstance(config, dict) and config.get("mailbox_id") == mailbox.id:
                    plan.erased["scan_schedules"].add(schedule.id)
            plan.erased["memory_sources"].update(
                db.scalars(
                    text(
                        "SELECT id FROM memory_sources WHERE user_id = :owner "
                        "AND namespace LIKE 'gmail-%' AND namespace LIKE :suffix"
                    ),
                    {"owner": actor.id, "suffix": "%:" + mailbox.id},
                )
            )
        else:
            run = db.scalar(
                select(ScanRun).where(
                    ScanRun.user_id == actor.id, ScanRun.id == target.id
                )
            )
            if run is None:
                raise ErasureError("Scan not found", 404)
            runs = [run]
        if any(run.state in ACTIVE for run in runs):
            raise ErasureError(
                "A scan of this source is still running. Cancel it or wait for "
                "it to finish, then erase.",
                409,
            )
        run_ids = {run.id for run in runs}
        plan.erased["scan_runs"].update(run_ids)
        if run_ids:
            plan.erased["memory_sources"].update(
                db.scalars(
                    text(
                        "SELECT DISTINCT source_id FROM scan_run_items "
                        "WHERE user_id = :owner AND run_id = ANY(:runs) "
                        "AND source_id IS NOT NULL"
                    ),
                    {"owner": actor.id, "runs": _array(run_ids)},
                )
            )
            for operation, identifier in db.execute(
                UPLOADED, {"owner": actor.id, "runs": _array(run_ids)}
            ):
                table = "documents" if operation == "document_uploaded" else "photos"
                plan.erased[table].add(identifier)
        # A file's reviewed text or transcription goes with the file.
        for table in ("documents", "photos"):
            if plan.erased[table]:
                plan.erased["memory_sources"].update(
                    db.scalars(
                        text(
                            f"SELECT source_id FROM {table} WHERE user_id = :owner "
                            "AND id = ANY(:ids) AND source_id IS NOT NULL"
                        ),
                        {"owner": actor.id, "ids": _array(plan.erased[table])},
                    )
                )
        return plan, run_ids

    # Everything derived from the seeds.

    def plan(self, db: Session, actor: Account, target: ErasureTarget) -> Plan:
        plan, _ = self._seeds(db, actor, target)
        links = [Link(*row) for row in db.execute(LINKS)]
        columns: dict[str, set[str]] = defaultdict(set)
        for table, column in db.execute(COLUMNS):
            columns[table].add(column)
        owner = actor.id
        sources = plan.erased["memory_sources"]
        created = set(
            db.scalars(
                text(
                    "SELECT id FROM memory_entities WHERE user_id = :owner "
                    "AND source_id = ANY(:sources)"
                ),
                {"owner": owner, "sources": _array(sources)},
            )
        )
        if created:
            support: dict[str, list[str]] = defaultdict(list)
            for entity, source in db.execute(
                SUPPORT,
                {
                    "owner": owner,
                    "entities": _array(created),
                    "erased": _array(sources),
                },
            ):
                support[entity].append(source)
            for entity, kept in support.items():
                # The earliest kept source that supports it.
                plan.rehomed[entity] = db.execute(
                    text(
                        "SELECT id FROM memory_sources WHERE user_id = :owner "
                        "AND id = ANY(:ids) ORDER BY recorded_at, id LIMIT 1"
                    ),
                    {"owner": owner, "ids": sorted(set(kept))},
                ).scalar_one()
        changed = True
        while changed:
            changed = False
            for link in links:
                parents = plan.erased.get(link.parent)
                if (
                    not parents
                    or link.set_null
                    or link.detached
                    or "id" not in columns[link.child]
                ):
                    continue
                exempt = plan.erased[link.child]
                if link.child == "memory_entities":
                    exempt = exempt | set(plan.rehomed)
                found = set(
                    db.scalars(
                        text(
                            f'SELECT id FROM "{link.child}" WHERE user_id = :owner '
                            f'AND "{link.column}" = ANY(:parents) '
                            "AND NOT id = ANY(:exempt)"
                        ),
                        {
                            "owner": owner,
                            "parents": _array(parents),
                            "exempt": _array(exempt),
                        },
                    )
                )
                if found:
                    plan.erased[link.child].update(found)
                    changed = True
            unsupported = set(
                db.scalars(
                    UNSUPPORTED,
                    {
                        "owner": owner,
                        "facts": _array(plan.erased["memory_facts"]),
                        "evidence": _array(plan.erased["memory_evidence"]),
                    },
                )
            )
            if unsupported:
                plan.erased["memory_facts"].update(unsupported)
                changed = True
        plan.erased = defaultdict(
            set, {t: ids for t, ids in plan.erased.items() if ids}
        )
        self._describe(db, owner, plan)
        return plan

    def _describe(self, db: Session, owner: str, plan: Plan) -> None:
        def count(table: str) -> int:
            return len(plan.erased.get(table, ()))

        assets = 0
        if plan.erased.get("memory_entities"):
            assets = int(
                db.scalar(
                    text(
                        "SELECT count(*) FROM memory_entities WHERE user_id = :owner "
                        "AND id = ANY(:ids) AND kind = 'asset'"
                    ),
                    {"owner": owner, "ids": _array(plan.erased["memory_entities"])},
                )
                or 0
            )
        kept_assets = 0
        if plan.rehomed:
            kept_assets = int(
                db.scalar(
                    text(
                        "SELECT count(*) FROM memory_entities WHERE user_id = :owner "
                        "AND id = ANY(:ids) AND kind = 'asset'"
                    ),
                    {"owner": owner, "ids": sorted(plan.rehomed)},
                )
                or 0
            )
        for table, columns in (
            ("documents", ("original_key",)),
            ("photos", ("original_key", "preview_key")),
        ):
            if plan.erased.get(table):
                for row in db.execute(
                    text(
                        f"SELECT {', '.join(columns)} FROM {table} "
                        "WHERE user_id = :owner AND id = ANY(:ids)"
                    ),
                    {"owner": owner, "ids": _array(plan.erased[table])},
                ):
                    plan.files.update(key for key in row if key)
        plan.counts = {
            "memories": count("memory_sources"),
            "assets": assets,
            "other_records": count("memory_entities") - assets,
            "facts": count("memory_facts"),
            "purchases": count("reconciliation_purchases"),
            "suggestions": count("asset_proposals") + count("receipt_proposals"),
            "maintenance": count("maintenance_tasks"),
            "documents": count("documents"),
            "photos": count("photos"),
            "scans": count("scan_runs"),
            "schedules": count("scan_schedules"),
            "connections": count("mailboxes"),
            "kept_assets": kept_assets,
            "kept_records": len(plan.rehomed) - kept_assets,
        }

    def preview(self, actor: Account, value: ErasureTarget) -> dict[str, Any]:
        target = ErasureTarget.model_validate(value)
        with Session(self.engine) as db:
            plan = self.plan(db, actor, target)
        return {
            "kind": target.kind,
            "id": target.id,
            "counts": plan.counts,
            "fingerprint": plan.fingerprint(),
        }

    # Applying a plan.

    def _apply(self, db: Session, actor: Account, plan: Plan) -> int:
        owner = actor.id
        links = [Link(*row) for row in db.execute(LINKS)]
        columns: dict[str, set[str]] = defaultdict(set)
        for table, column in db.execute(COLUMNS):
            columns[table].add(column)
        for entity, source in sorted(plan.rehomed.items()):
            db.execute(
                text(
                    "UPDATE memory_entities SET source_id = :source "
                    "WHERE user_id = :owner AND id = :entity"
                ),
                {"owner": owner, "entity": entity, "source": source},
            )
        for link in links:
            parents = plan.erased.get(link.parent)
            if not parents or not link.detached:
                continue
            erased = _array(plan.erased.get(link.child, set()))
            ref = f'"{link.column}"'
            if link.child == link.parent and "superseded_at" in columns[link.child]:
                # A kept revision that an erased one replaced is current again,
                # unless a kept revision also replaced it.
                db.execute(
                    text(
                        f'UPDATE "{link.child}" p SET superseded_at = NULL '
                        "WHERE p.user_id = :owner AND NOT p.id = ANY(:erased) "
                        f'AND p.id IN (SELECT c.{ref} FROM "{link.child}" c '
                        "WHERE c.user_id = :owner AND c.id = ANY(:erased)) "
                        f'AND NOT EXISTS (SELECT 1 FROM "{link.child}" k '
                        f"WHERE k.user_id = :owner AND k.{ref} = p.id "
                        "AND NOT k.id = ANY(:erased))"
                    ),
                    {"owner": owner, "erased": erased},
                )
            db.execute(
                text(
                    f'UPDATE "{link.child}" SET {ref} = NULL WHERE user_id = :owner '
                    f"AND {ref} = ANY(:parents) AND NOT id = ANY(:erased)"
                ),
                {"owner": owner, "parents": _array(parents), "erased": erased},
            )
        rows = 0
        for table in deletion_order(db):
            if "id" in columns[table]:
                if plan.erased.get(table):
                    result = db.execute(
                        text(
                            f'DELETE FROM "{table}" WHERE user_id = :owner '
                            "AND id = ANY(:ids)"
                        ),
                        {"owner": owner, "ids": _array(plan.erased[table])},
                    )
                    rows += int(getattr(result, "rowcount", 0) or 0)
                continue
            # Tables without an id only ever reference other rows.
            for link in links:
                if (
                    link.child == table
                    and not link.set_null
                    and not link.detached
                    and plan.erased.get(link.parent)
                ):
                    result = db.execute(
                        text(
                            f'DELETE FROM "{table}" WHERE user_id = :owner '
                            f'AND "{link.column}" = ANY(:ids)'
                        ),
                        {"owner": owner, "ids": _array(plan.erased[link.parent])},
                    )
                    rows += int(getattr(result, "rowcount", 0) or 0)
        everything = plan.ids()
        for table, column in (
            ("memory_fts", "record_id"),
            ("memory_audit", "target_id"),
        ):
            db.execute(
                text(
                    f"DELETE FROM {table} WHERE user_id = :owner "
                    f"AND {column} = ANY(:ids)"
                ),
                {"owner": owner, "ids": everything},
            )
        return rows

    def erase(self, actor: Account, value: ErasureConfirm) -> dict[str, Any]:
        data = ErasureConfirm.model_validate(value)
        target = ErasureTarget(kind=data.kind, id=data.id)
        with Session(self.engine) as db:
            # Holds the writer lock while files go, so nothing new can link
            # to them; a storage failure rolls everything back.
            begin_serialized(db)
            plan = self.plan(db, actor, target)
            if plan.fingerprint() != data.fingerprint:
                raise NoteConflict(
                    "This source changed since the preview. Preview again."
                )
            if plan.files:
                if self.storage is None:
                    raise ErasureError(
                        "File storage is not configured; nothing was erased", 503
                    )
                try:
                    for key in sorted(plan.files):
                        self.storage.delete(key)
                except StorageError:
                    raise ErasureError(
                        "Could not delete stored files; nothing else was erased. "
                        "Try again.",
                        503,
                    ) from None
            rows = self._apply(db, actor, plan)
            self.memory._audit(db, actor, SOURCE_ERASED, data.id, self.memory.clock())
            db.commit()
        return {
            "erased": True,
            "kind": data.kind,
            "id": data.id,
            "counts": plan.counts,
            "rows": rows,
            "files": len(plan.files),
        }
