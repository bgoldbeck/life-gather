"""A bounded read-only plan over the same domain services exposed through MCP."""

import json
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from lifegather.assets.purchases import AssetPurchases, AssetPurchasesRead
from lifegather.assets.service import AssetRead, AssetService
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
        self,
        actor: Account,
        value: RecallPlan,
        *,
        max_bytes: int = 24000,
        pinned_entity_id: str | None = None,
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
                **self.chat.source_metadata(actor, source),
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
        groups = (
            [[memory.get_entity(actor, pinned_entity_id)]] if pinned_entity_id else []
        )
        groups.extend(
            memory.find_entities(actor, name, 3) for name in plan.entity_names
        )
        for matches in groups:
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
                detail = (
                    AssetService(memory.engine).get(
                        actor, AssetRead(asset_id=entity.id, limit=3)
                    )
                    if entity.kind == "asset"
                    else None
                )
                corrections = []
                if detail is not None:
                    for action in detail["actions"]:
                        if add_source(action["source_id"]):
                            corrections.append(
                                {
                                    "action_id": action["id"],
                                    "source_id": action["source_id"],
                                    "operation": action["operation"],
                                    "direction": action["direction"],
                                    "recorded_at": action["recorded_at"],
                                }
                            )
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
                    "purchases": [],
                    "purchases_limited": False,
                    "corrections": corrections,
                    "corrections_limited": bool(
                        detail
                        and (
                            detail["next_action_cursor"]
                            or len(corrections) < len(detail["actions"])
                        )
                    ),
                }
                if detail is not None:
                    record["in_inventory"] = detail["in_inventory"]
                    record["inventory_status"] = (
                        "inferred membership; not verified ownership"
                    )
                    trace.append(
                        {
                            "tool": "asset_detail",
                            "count": len(corrections),
                            "limited": record["corrections_limited"],
                        }
                    )
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
                if entity.kind == "asset":
                    page = AssetPurchases(memory.engine).get(
                        actor, AssetPurchasesRead(asset_id=entity.id, limit=3)
                    )
                    for purchase in page["items"]:
                        if add_source(purchase["source_id"]):
                            claim = purchase["claim"]
                            record["purchases"].append(
                                {
                                    **purchase,
                                    "detail_status": "not_recorded"
                                    if claim is None
                                    else "withdrawn"
                                    if claim["line_total"] is None
                                    and claim["purchase_date"] is None
                                    else "recorded",
                                    "scope": "whole line total; all units",
                                    "receipt_line_key": purchase["key"],
                                    "status": "unverified source claim"
                                    if purchase["source_current"]
                                    else "historical: corrected or deleted source",
                                }
                            )
                    record["purchases_limited"] = page[
                        "next_cursor"
                    ] is not None or len(record["purchases"]) < len(page["items"])
                    trace.append(
                        {
                            "tool": "asset_purchases",
                            "count": len(record["purchases"]),
                            "limited": record["purchases_limited"],
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
                record["facts_limited"]
                or record["connections_limited"]
                or record["purchases_limited"]
                or record["corrections_limited"]
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
                    if record["connections"]
                    or record["facts"]
                    or record["purchases"]
                    or record["corrections"]
                ),
                None,
            )
            if removable is not None:
                if removable["connections"]:
                    removable["connections"].pop()
                    removable["connections_limited"] = True
                elif removable["facts"]:
                    removable["facts"].pop()
                    removable["facts_limited"] = True
                elif removable["purchases"]:
                    removable["purchases"].pop()
                    removable["purchases_limited"] = True
                else:
                    removable["corrections"].pop()
                    removable["corrections_limited"] = True
            elif records:
                records.pop()
            elif result["evidence"]:
                result["evidence"].pop()
            else:
                result["read_trace"].pop()
        return result
