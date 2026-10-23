"""Bounded, user-stated maintenance operations sharing the chat transaction."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from lifegather.chat.assistant_dates import stated_date
from lifegather.chat.context import ContextRead
from lifegather.chat.models import Turn
from lifegather.maintenance.schemas import (
    MaintenanceChange,
    MaintenanceCreate,
    MaintenancePage,
)
from lifegather.maintenance.service import MaintenanceService
from lifegather.memory.notes import NoteConflict
from lifegather.memory.origins import change_origin
from lifegather.memory.service import fingerprint

if TYPE_CHECKING:
    from lifegather.chat.assistant import AssistantRunner


class MaintenanceField(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    field: Literal["title", "state", "due_on", "completed_on"]
    value: str | None = Field(max_length=200)
    quote: str = Field(min_length=1, max_length=500)


class MaintenanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    intent_quote: str = Field(min_length=1, max_length=500)
    changes: list[MaintenanceField] = Field(min_length=1, max_length=4)


class AssistantMaintenance:
    def __init__(self, runner: AssistantRunner) -> None:
        self.runner = runner
        self.service = MaintenanceService(runner.engine)
        self.known: dict[str, dict[str, Any]] = {}
        self.reads: dict[str, dict[str, Any]] = {}
        self.limited_assets: set[str] = set()
        self.date_contexts: dict[str, dict[str, str]] = {}
        self.date_context: dict[str, str] | None = None
        self.date_timezone: str | None = None
        if runner.pending:
            self.limited_assets = set(
                runner.pending.get("maintenance_limited_assets", [])[:20]
            )
            self.known = {
                item["id"]: item
                for item in runner.pending.get("maintenance_known", [])[:20]
            }
            origin_ids = {item["id"] for item in runner.origins}
            self.date_contexts = {
                key: value
                for key, value in runner.pending.get(
                    "maintenance_date_contexts", {}
                ).items()
                if key in origin_ids
            }
        if runner.timezone:
            with Session(runner.engine) as db:
                created = db.scalar(
                    select(Turn.created_at).where(
                        Turn.user_id == runner.actor.id,
                        Turn.id == runner.turn_id,
                    )
                )
            if created is not None:
                local = datetime.fromtimestamp(created / 1_000_000, UTC).astimezone(
                    ZoneInfo(runner.timezone)
                )
                self.date_context = {
                    "today": local.date().isoformat(),
                    "timezone": runner.timezone,
                }
                self.date_contexts[runner.turn_id] = self.date_context

    def list_tasks(self, asset_id: str | None) -> dict[str, Any]:
        runner = self.runner
        identifier = runner._known(asset_id)
        runner.read(identifier)
        page = self.service.list(
            runner.actor, MaintenancePage(entity_id=identifier, state="all", limit=20)
        )
        items = []
        limited = page["next_cursor"] is not None
        for item in page["items"]:
            if item["id"] not in self.known and len(self.known) >= 20:
                limited = True
                continue
            observed = {
                "id": item["id"],
                "asset_id": item["target"]["id"],
                "state_token": item["state_token"],
                "title": item["revision"]["title"],
            }
            self.known.setdefault(item["id"], observed)
            items.append({**observed, "revision": item["revision"]})
        if limited:
            self.limited_assets.add(
                runner.known[identifier].get("canonical_id", identifier)
            )
        return {"items": items, "limited": limited}

    def read(self, task_id: str | None) -> dict[str, Any]:
        from lifegather.chat.assistant import StepError

        if not task_id or task_id not in self.known:
            raise StepError("Unknown maintenance task. List this asset's tasks first.")
        result = self.service.get(self.runner.actor, task_id)
        self.reads[task_id] = result
        return result

    def pending(self) -> dict[str, Any]:
        return {
            "maintenance_known": list(self.known.values())[:20],
            "maintenance_date_contexts": self.date_contexts,
            "maintenance_limited_assets": sorted(self.limited_assets),
        }

    def choices(self, identifiers: list[str]) -> list[dict[str, str]]:
        return [
            {
                "id": i,
                "name": f"{self.known[i]['title']} (task {i[:8]})",
                "asset_id": self.known[i]["asset_id"],
            }
            for i in dict.fromkeys(identifiers)
        ]

    def _intent(self, quote: str) -> bool:
        """Require a direct request/statement, rather than an embedded command."""
        from lifegather.chat.assistant import mentions

        blocked = (
            r"\s*(?:no\b|nope\b|never\s?mind\b|forget it\b|stop\b|"
            r"what\b|why\b|when\b|where\b|how\b|should\b|did\b|if\b|suppose\b)"
        )
        if re.match(blocked, self.runner.text, re.I) or re.search(
            r"\b(don't|do not|cancel (?:that |this )?request)\b", self.runner.text, re.I
        ):
            return False
        direct = (
            r"\s*(?:(?:for|on)\b[^,\n]{1,200},\s*)?"
            r"(?:(?:please|can you|could you|would you)\s+)?"
            r"(?:(?:I(?:'ve| have)?|we(?:'ve| have)?)\s+)?"
            r"(?:add|create|record|log|schedule|plan|mark|complete[ds]?|"
            r"cancel(?:ed|led)?|reopen|correct|change[ds]?|replace[ds]?|"
            r"finish(?:ed)?|did|done|serviced|performed)\b"
        )
        messages = (
            [self.runner.text]
            if re.match(direct, self.runner.text, re.I)
            else [i["text"] for i in self.runner.origins]
        )
        for message in messages:
            if not mentions(message, quote):
                continue
            if re.search(r"\b(don't|do not|never|not yet)\b", message, re.I):
                continue
            if re.match(
                r"\s*(what|why|when|where|how|should|did|if|suppose)\b", message, re.I
            ):
                continue
            if re.match(direct, message, re.I):
                return True
        return False

    def _changes(self, item: MaintenanceRequest) -> dict[str, str | None]:
        from lifegather.chat.assistant import StepError, contains, mentions

        evidence = self.runner.evidence
        if not self._intent(item.intent_quote) or not re.search(
            r"\b(add|create|record|log|schedule|plan|mark|complete[ds]?|cancel(?:ed)?|"
            r"reopen|correct|change[ds]?|replace[ds]?|finish(?:ed)?|did|done)\b",
            item.intent_quote,
            re.I,
        ):
            raise StepError("Use the user's explicit maintenance request, or clarify.")
        changes: dict[str, str | None] = {}
        for entry in item.changes:
            if entry.field in changes or not mentions(evidence, entry.quote):
                raise StepError(
                    "Supply each task field once with the user's exact words."
                )
            value = entry.value
            if entry.field == "title":
                if not value or not contains(entry.quote, value):
                    raise StepError(
                        "The task title must appear exactly in the user's words."
                    )
            elif entry.field == "state":
                states = {
                    "open": r"\b(open|reopen|plan|schedule|add|create)\b",
                    "completed": (
                        r"\b(complete[ds]?|finished|done|changed|replaced|"
                        r"serviced|performed|did)\b"
                    ),
                    "canceled": r"\b(cancel(?:ed|led)?|cancel)\b",
                }
                if value not in states or not re.search(
                    states[value], entry.quote, re.I
                ):
                    raise StepError("Task state must be explicitly stated by the user.")
            else:
                messages = [
                    *self.runner.origins,
                    {"id": self.runner.turn_id, "text": self.runner.text},
                ]
                context = next(
                    (
                        self.date_contexts.get(message["id"])
                        for message in reversed(messages)
                        if mentions(message["text"], entry.quote)
                    ),
                    None,
                )
                anchor = date.fromisoformat(context["today"]) if context else None
                try:
                    value = stated_date(value, entry.quote, anchor)
                except ValueError as error:
                    raise StepError(str(error)) from None
                if context and value is not None:
                    self.date_timezone = context["timezone"]
            changes[entry.field] = value
        return changes

    def write(
        self,
        asset_id: str | None,
        task_id: str | None,
        item: MaintenanceRequest | None,
        *,
        create: bool,
    ) -> dict[str, Any]:
        from lifegather.chat.assistant import StepError

        runner = self.runner
        identifier = runner._known(asset_id)
        if item is None:
            raise StepError("Supply the maintenance request.")
        changes = self._changes(item)
        expected = runner.known[identifier].get("version")
        if not expected:
            raise StepError("Read the asset before changing its maintenance.")
        target_id = runner.known[identifier].get("canonical_id", identifier)
        if not runner.selected or runner.selected["id"] != target_id:
            same_name = {
                entry.get("canonical_id", key)
                for key, entry in runner.known.items()
                if entry["name"].casefold()
                == runner.known[identifier]["name"].casefold()
            }
            if len(same_name) > 1:
                raise StepError(
                    "Several assets share that name. "
                    "Ask the user to open the specific asset."
                )
        previous: dict[str, Any] | None = None
        if not create:
            if not task_id or task_id not in self.reads:
                raise StepError("Read the maintenance task before revising it.")
            previous = self.reads[task_id]
            if previous["state_token"] != self.known[task_id]["state_token"]:
                raise NoteConflict("Maintenance task changed; reload it and ask again.")
            from lifegather.chat.assistant import mentions

            matching = [
                task
                for task in self.known.values()
                if task["asset_id"] == self.known[task_id]["asset_id"]
            ]
            if (
                not mentions(runner.evidence, previous["revision"]["title"])
                and (task_id[:8] not in runner.evidence)
                and not (
                    len(matching) == 1
                    and re.search(r"\b(that|this|it)\b", runner.evidence, re.I)
                )
            ):
                raise StepError("The user did not identify this task; clarify first.")
            same_title = [
                i
                for i, task in self.known.items()
                if task["asset_id"] == self.known[task_id]["asset_id"]
                and task["title"].casefold() == self.known[task_id]["title"].casefold()
            ]
            if len(same_title) > 1 and task_id[:8] not in runner.evidence:
                raise StepError(
                    "Several tasks share that title. "
                    "Clarify with the task choices first."
                )
            if target_id in self.limited_assets and task_id[:8] not in runner.evidence:
                raise StepError(
                    "The task list was limited; ask for an explicit task choice."
                )
        elif task_id:
            raise StepError("A new task cannot reuse a task ID.")
        fields: dict[str, Any] = {
            key: previous["revision"][key] if previous else default
            for key, default in {
                "title": "",
                "state": "open",
                "due_on": None,
                "completed_on": None,
                "timezone": self.date_timezone or runner.timezone or "UTC",
            }.items()
        }
        fields.update(changes)
        if fields["state"] != "completed":
            if changes.get("completed_on") is not None:
                raise StepError("A completion date needs completed state.")
            fields["completed_on"] = None
        runner.active()
        with runner.manual.memory._write() as db:
            row = runner._turn(db)
            snapshot = runner.contexts.read_in(
                db, runner.actor, ContextRead(page="Assets", entity_id=identifier)
            )
            if snapshot["version"] != expected:
                raise NoteConflict("Asset changed since it was read; ask again.")
            target = snapshot["entity_id"]
            data: dict[str, Any] = {
                **fields,
                "text": runner.evidence,
                "request_id": "assistant-maintenance:"
                + fingerprint([runner.request_id]),
            }
            try:
                with change_origin(
                    method="ai_assistant",
                    provider=runner.provider,
                    model=runner.model,
                    related_id=runner.turn_id,
                ):
                    if create:
                        saved = self.service.create_in(
                            db,
                            runner.actor,
                            MaintenanceCreate(entity_id=target, **data),
                        )
                    else:
                        assert previous is not None and task_id is not None
                        if previous["target"]["id"] != target:
                            raise StepError("This task belongs to another asset.")
                        saved = self.service.revise_in(
                            db,
                            runner.actor,
                            MaintenanceChange(
                                task_id=task_id,
                                state_token=self.known[task_id]["state_token"],
                                **data,
                            ),
                        )
            except ValidationError:
                raise StepError(
                    "Invalid task fields or source statement. Ask for a nonblank title "
                    "and valid dates in a concise request (at most 4,000 characters)."
                ) from None
            task = self.service._task(db, runner.actor, saved["id"])
            revision = self.service._head(db, runner.actor, task)
            result = self._receipt(
                db, target, snapshot["name"], saved, fields, revision.source_id
            )
            runner._commit(db, row, result)
            return result

    def _receipt(
        self,
        db: Session,
        asset_id: str,
        name: str,
        saved: dict[str, str],
        fields: dict[str, Any],
        source_id: str,
    ) -> dict[str, Any]:
        runner = self.runner
        return {
            "text": (
                f"Recorded {fields['title']} for {name} as "
                f"{fields['state']}, as your statement."
            ),
            "provider": runner.provider,
            "model": runner.model,
            "changed_entity_id": asset_id,
            "navigation": {"page": "Profiles", "entity_id": asset_id, "name": name},
            "sources": [{"id": source_id, "text": runner._source_text(db, source_id)}],
            "maintenance": {
                "task_id": saved["id"],
                "revision_id": saved["revision_id"],
                **fields,
            },
            "assistant": {"operation": "maintenance", "asset_id": asset_id},
            "read_trace": runner.trace,
        }
