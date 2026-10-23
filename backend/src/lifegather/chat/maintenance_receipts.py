"""Recover accepted assistant outcomes without reinterpreting a retained task."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from lifegather.auth.store import Account
from lifegather.maintenance.models import MaintenanceRevision
from lifegather.maintenance.service import MaintenanceService
from lifegather.memory.service import MemoryError, fingerprint


def request_prefix(request_id: str) -> str:
    # 128-bit request identity plus the full 256-bit input fingerprint fits the
    # existing 100-character request column. Owner scope is enforced separately.
    return "am:" + fingerprint([request_id])[:32] + ":"


def maintenance_request_key(request_id: str, input_fingerprint: str) -> str:
    return request_prefix(request_id) + input_fingerprint


def revision_receipt(
    db: Session,
    actor: Account,
    service: MaintenanceService,
    revision: MaintenanceRevision,
) -> dict[str, Any]:
    task = service._task(db, actor, revision.task_id)
    target = service._target(db, actor, task.entity_id)
    recorded = service._revision(db, actor, revision)
    fields = {
        key: recorded[key]
        for key in (
            "title",
            "state",
            "due_on",
            "completed_on",
            "timezone",
        )
    }
    origin = recorded["origin"] or {}
    return {
        "text": (
            f"Recorded {fields['title']} for {target.name} as "
            f"{fields['state']}, as your statement."
        ),
        "provider": origin.get("provider"),
        "model": origin.get("model"),
        "changed_entity_id": target.id,
        "navigation": {"page": "Profiles", "entity_id": target.id, "name": target.name},
        "sources": [
            {
                "id": revision.source_id,
                "text": service.memory._source(db, actor, revision.source_id).text[
                    :2000
                ],
            }
        ],
        "maintenance": {"task_id": task.id, "revision_id": revision.id, **fields},
        "assistant": {"operation": "maintenance", "asset_id": target.id},
        "read_trace": [],
    }


def replay_maintenance(
    db: Session,
    actor: Account,
    service: MaintenanceService,
    request_id: str,
    input_fingerprint: str,
) -> dict[str, Any] | None:
    rows = list(
        db.scalars(
            select(MaintenanceRevision)
            .where(
                MaintenanceRevision.user_id == actor.id,
                MaintenanceRevision.request_id.startswith(request_prefix(request_id)),
            )
            .limit(2)
        )
    )
    if not rows:
        return None
    if len(rows) != 1 or rows[0].request_id != maintenance_request_key(
        request_id, input_fingerprint
    ):
        raise MemoryError("Request identity conflict; use a new request ID")
    # An ordinary user-supplied maintenance request ID cannot impersonate a
    # host-accepted assistant operation, even if it copies the namespace.
    view = service._revision(db, actor, rows[0])
    if not view["origin"] or view["origin"]["method"] != "ai_assistant":
        raise MemoryError("Request identity conflict; use a new request ID")
    result = revision_receipt(db, actor, service, rows[0])
    result["text"] = "This request was already recorded. " + result["text"]
    return result
