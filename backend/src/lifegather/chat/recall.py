"""A bounded read-only plan over the same domain services exposed through MCP."""

import json
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from lifegather.auth.store import Account
from lifegather.chat.service import ChatService
from lifegather.memory.notes import NoteService
from lifegather.memory.schemas import FactView


class RecallPlan(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, revalidate_instances="always"
    )
    query: str = Field(min_length=1, max_length=200)
    entity_names: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(
        max_length=2
    )
    include_connections: bool


class RecallTools:
    def __init__(self, chat: ChatService) -> None:
        self.chat = chat

    def collect(
        self, actor: Account, value: RecallPlan, *, max_bytes: int = 24000
    ) -> dict[str, Any]:
        if not 1200 <= max_bytes <= 24000:
            raise ValueError("Invalid recall context budget")
        plan = RecallPlan.model_validate(value)
        memory = self.chat.memory
        sources: dict[str, dict[str, Any]] = {}
        records: list[dict[str, Any]] = []
        trace: list[dict[str, Any]] = []
        truncated = False

        def add_source(identifier: str) -> bool:
            if identifier in sources:
                return True
            if len(sources) >= 8:
                return False
            source = memory.get_source(actor, identifier)
            text = source.text.encode()[:1200].decode(errors="ignore")
            current = NoteService(memory.engine).current(actor, identifier)
            sources[identifier] = {
                "id": source.id,
                "text": text,
                "text_truncated": text != source.text,
                "recorded_at": source.recorded_at,
                "event_date": source.event_date.isoformat()
                if source.event_date
                else None,
                "status": "original source; not independently verified",
                "current_note_source_id": current.id,
                "has_later_note_correction": current.id != source.id,
            }
            if current.id != source.id and len(sources) < 8:
                add_source(current.id)
            return True

        def sourced(fact: FactView) -> dict[str, Any] | None:
            evidence = [
                entry
                for entry in fact.evidence[:2]
                if add_source(str(entry["source_id"]))
            ]
            if not evidence:
                return None
            result = fact.model_dump(mode="json")
            result["evidence"] = [
                {
                    "source_id": entry["source_id"],
                    "quote": entry["quote"][:400] if entry["quote"] else None,
                    "quote_truncated": bool(
                        entry["quote"] and len(entry["quote"]) > 400
                    ),
                }
                for entry in evidence
            ]
            return result

        seen: set[str] = set()
        for name in plan.entity_names:
            matches = memory.find_entities(actor, name, 3)
            trace.append(
                {
                    "tool": "memory_find_entities",
                    "count": len(matches),
                    "limited": len(matches) == 3,
                }
            )
            for entity in matches:
                if entity.id in seen:
                    continue
                if len(records) >= 2:
                    truncated = True
                    break
                seen.add(entity.id)
                add_source(entity.source_id)
                facts = memory.facts(actor, entity.id, limit=8)
                record: dict[str, Any] = {
                    "entity": entity.model_dump(),
                    "ambiguous_name": len(matches) > 1,
                    "facts": [
                        item for fact in facts if (item := sourced(fact)) is not None
                    ],
                    "facts_limited": len(facts) == 8,
                    "connections": [],
                    "nodes": [],
                    "connections_limited": False,
                }
                record["facts_limited"] = record["facts_limited"] or len(
                    record["facts"]
                ) < len(facts)
                trace.append(
                    {
                        "tool": "memory_get_entity",
                        "count": len(record["facts"]),
                        "limited": record["facts_limited"],
                    }
                )
                if plan.include_connections:
                    related = memory.related(actor, entity.id, depth=1, limit=6)
                    record["connections"] = [
                        item
                        for fact in related["edges"]
                        if (item := sourced(fact)) is not None
                    ]
                    record["nodes"] = [node.model_dump() for node in related["nodes"]]
                    record["connections_limited"] = related["truncated"] or len(
                        record["connections"]
                    ) < len(related["edges"])
                    trace.append(
                        {
                            "tool": "memory_related",
                            "count": len(record["connections"]),
                            "limited": related["truncated"],
                        }
                    )
                records.append(record)
        for source in self.chat.evidence(actor, plan.query):
            if add_source(source["id"]):
                for key in ("asset_context", "photo", "document", "status"):
                    if key in source:
                        sources[source["id"]][key] = source[key]
        trace.append(
            {
                "tool": "memory_search",
                "count": len(sources),
                "limited": len(sources) == 8,
            }
        )
        result: dict[str, Any] = {
            "records": records,
            "evidence": list(sources.values()),
            "read_trace": trace,
            "truncated": truncated
            or len(sources) == 8
            or any(
                record["facts_limited"] or record["connections_limited"]
                for record in records
            ),
        }
        # Never truncate a literal fact into a different apparent value. Omit entire
        # facts/connections or records when the serialized context reaches its cap.
        while len(json.dumps(result, ensure_ascii=False).encode()) > max_bytes:
            result["truncated"] = True
            removable = next(
                (
                    record
                    for record in reversed(records)
                    if record["connections"] or record["facts"]
                ),
                None,
            )
            if removable is not None:
                if removable["connections"]:
                    removable["connections"].pop()
                    removable["connections_limited"] = True
                else:
                    removable["facts"].pop()
                    removable["facts_limited"] = True
            elif records:
                records.pop()
            else:
                result["evidence"].pop()
        return result
