"""Bounded explicit workspace commands. No model output or document instructions."""

import re
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, func, or_, select
from sqlalchemy.orm import Session

from lifegather.auth.store import Account
from lifegather.chat.context import ContextRef, WorkspaceContexts
from lifegather.memory.models import Alias, Assertion, Entity, Episode, Evidence
from lifegather.memory.notes import NoteConflict
from lifegather.memory.origins import change_origin
from lifegather.memory.service import MemoryError, MemoryService, fingerprint
from lifegather.profiles.service import ProfileChange, ProfileField, ProfileService

PREFIX = r"(?:(?:please|can you|could you|i want to|i'd like to|i would like to)\s+)*"
NAVIGATE = re.compile(
    r"^"
    + PREFIX
    + r"(?:open|show|edit)(?:\s+me)?\s+(?:(?:my|the|our)\s+)?(.{1,200}?)\s*[.!?]?$",
    re.I,
)
EDIT = re.compile(
    r"^" + PREFIX + r"(?:add|set|update|change|record)\s+(?:(?:the|a|an|its|my)\s+)?"
    r"(vin(?: number)?|serial(?: number)?|manufacturer|model|paint|"
    r"filter dimensions|maintenance|specification)"
    r"(?:(?:\s+(?:to|as|is)\s+|\s*[:=]\s*)(.+))?\s*$",
    re.I,
)
HELP = (
    "I can open an item or save a supplied profile detail. "
    "Try ‘Edit my F150’, then ‘Set VIN to …’. "
    "Choose Ask AI for broader questions."
)


class OrganizationAction(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, revalidate_instances="always"
    )
    request_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=4000)
    context: ContextRef | None = None


def compact(value: Any) -> Any:
    return func.replace(
        func.replace(func.replace(func.lower(value), "-", ""), " ", ""), "_", ""
    )


class WorkspaceOrganizer:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.memory = MemoryService(engine)
        self.contexts = WorkspaceContexts(engine)
        self.profiles = ProfileService(engine)

    def run(self, actor: Account, value: OrganizationAction) -> dict[str, Any]:
        data = OrganizationAction.model_validate(value)
        with self.memory._write() as db:
            return self.execute_in(db, actor, data) or {"text": HELP}

    def execute_in(
        self,
        db: Session,
        actor: Account,
        data: OrganizationAction,
        awaiting: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        snapshot = (
            self.contexts.read_in(db, actor, data.context) if data.context else None
        )
        text = data.text.strip()
        if match := NAVIGATE.fullmatch(text):
            name = re.sub(r"[-\s_]", "", match[1].rstrip(".!?").lower())
            if not name:
                return {"text": "Which item would you like to open?"}
            rows = list(
                db.scalars(
                    select(Entity)
                    .outerjoin(
                        Alias,
                        (Alias.entity_id == Entity.id) & (Alias.user_id == actor.id),
                    )
                    .where(
                        Entity.user_id == actor.id,
                        Entity.kind == "asset",
                        or_(
                            compact(Entity.name).contains(name, autoescape=True),
                            compact(Alias.normalized_name).contains(
                                name, autoescape=True
                            ),
                        ),
                    )
                    .distinct()
                    .order_by(Entity.id)
                    .limit(6)
                )
            )
            if not rows:
                return {
                    "text": "I couldn't find that asset in your records. "
                    "Try its saved name."
                }
            if len(rows) != 1:
                return {
                    "text": "Which physical item do you mean? "
                    "Choose one before editing."
                    if len(rows) <= 5
                    else "There are too many matches. Use a more specific saved name.",
                    "choices": [{"id": row.id, "name": row.name} for row in rows[:5]],
                }
            row = rows[0]
            return {
                "text": f"Opening {row.name}. What would you like to change?",
                "navigation": {"page": "Assets", "entity_id": row.id, "name": row.name},
            }
        edit = EDIT.fullmatch(text)
        if edit:
            field = edit[1].lower().replace(" number", "").replace(" ", "_")
            value = edit[2]
        elif (
            awaiting
            and re.fullmatch(r"[A-Za-z0-9]{17}", text)
            and awaiting.get("field") == "vin"
            and snapshot
            and awaiting.get("entity_id") == snapshot["entity_id"]
        ):
            field, value = "vin", text
            if awaiting.get("version") != snapshot["version"]:
                raise NoteConflict(
                    "The selected record changed. "
                    "Check its current details before editing."
                )
        else:
            return None
        if not snapshot or not snapshot["entity_id"]:
            return {
                "text": "Open the item you want to edit first, or say ‘Edit my F150’."
            }
        if snapshot["kind"] not in {"asset", "place"}:
            raise MemoryError("Select an asset or home profile before editing details")
        ref = {key: snapshot[key] for key in ("page", "entity_id", "version")}
        if not value:
            return {
                "text": (
                    f"What {field.replace('_', ' ')} should I record for "
                    f"{snapshot['name']}? Supply the exact value; I won't guess."
                ),
                "awaiting": {**ref, "field": field},
                "context": {**ref, "name": snapshot["name"]},
            }
        if len(value) > 500:
            return {"text": "Profile details accept at most 500 characters."}
        operation_key = "workspace:" + fingerprint([data.request_id])
        existing = db.scalar(
            select(Assertion)
            .where(
                Assertion.user_id == actor.id,
                Assertion.operation_key == "profile-fact:" + operation_key,
            )
            .limit(1)
        )
        if existing:
            if (
                existing.subject_id != snapshot["entity_id"]
                or existing.predicate != "profile_" + field
            ):
                raise NoteConflict(
                    "This request already belongs to another record or field"
                )
            view = self.memory._view(db, actor, existing)
            if view.value != value:
                raise NoteConflict("This request already saved another statement")
        else:
            if not data.context or data.context.version != snapshot["version"]:
                raise NoteConflict(
                    "The selected record changed. Refresh its context before editing."
                )
            if field == "vin" and not re.fullmatch(r"[A-Za-z0-9]{17}", value):
                return {
                    "text": "Chat VIN edits accept 17 letters/digits. "
                    "Supply the exact VIN, or use Profiles "
                    "for another identifier format.",
                    "awaiting": {**ref, "field": field},
                }
            details = snapshot["fields"].get(field, {"count": 0, "statements": []})
            if details["count"] > 1:
                raise NoteConflict(
                    "Multiple current statements need review. "
                    "Use the profile to choose which to correct."
                )
            replaces = details["statements"][0]["id"] if details["count"] else None
            with change_origin(method="correction" if replaces else "user_statement"):
                view = self.profiles._save_in(
                    db,
                    actor,
                    ProfileChange(
                        entity_id=snapshot["entity_id"],
                        field=cast(ProfileField, field),
                        value=value,
                        text=data.text,
                        operation_key=operation_key,
                        replaces_id=replaces,
                    ),
                )
        source = db.scalar(
            select(Episode)
            .join(Evidence, Evidence.source_id == Episode.id)
            .where(
                Episode.user_id == actor.id,
                Evidence.user_id == actor.id,
                Evidence.fact_id == view.id,
                Episode.namespace == "profile-facts",
                Episode.external_id == operation_key,
            )
            .limit(1)
        )
        if source is None or source.text != data.text:
            raise NoteConflict("This request already saved another statement")
        if data.context:
            ref["version"] = data.context.version
        return {
            "text": (
                f"Saved {field.replace('_', ' ')} for {snapshot['name']} "
                "as your statement."
            ),
            "changed_entity_id": snapshot["entity_id"],
            "profile_fact_id": view.id,
            "sources": [{"id": source.id, "text": source.text}],
            "context": {**ref, "name": snapshot["name"]},
        }
