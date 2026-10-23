"""Bounded saved research context; never evidence or authorization for a write."""

from typing import Any

from lifegather.auth.store import Account
from lifegather.chat.research import IDENTITY_NOTE
from lifegather.findings.service import FindingService
from lifegather.memory.service import MemoryService

MAX_RESEARCH_FINDINGS = 5


class AssistantResearch:
    def __init__(self, memory: MemoryService, actor: Account) -> None:
        self.service = FindingService(memory)
        self.actor = actor
        self.citations: dict[str, dict[str, Any]] = {}
        self.read_assets: set[str] = set()
        self.limited = False

    def read(self, asset_id: str, name: str) -> dict[str, Any]:
        result: dict[str, Any] = {
            "asset_id": asset_id,
            "items": [],
            "limited": self.limited,
            "identity_note": IDENTITY_NOTE,
        }
        if asset_id in self.read_assets:
            return result | {"already_read": True}
        # The domain service owns account isolation, active filtering and current
        # physical identity membership. Never read findings by a model-given ID.
        rows = self.service.for_asset(self.actor, asset_id)["items"]
        self.read_assets.add(asset_id)
        unseen = [row for row in rows if row["id"] not in self.citations]
        room = MAX_RESEARCH_FINDINGS - len(self.citations)
        self.limited |= len(unseen) > room
        items = []
        for row in unseen[:room]:
            item = {
                "id": row["id"],
                "citation": len(self.citations) + 1,
                "asset_id": asset_id,
                "asset_name": name[:200],
                "url": row["url"],
                "title": row["title"][:200],
                "published": row["published"],
                "researched_at": row["researched_at"],
                "recorded_at": row["recorded_at"],
                "excerpt_kind": row["excerpt_kind"],
                "excerpts": [text[:300] for text in row["excerpts"][:3]],
            }
            self.citations[item["id"]] = item
            items.append(item)
        return result | {"items": items, "limited": self.limited}

    def receipt(self) -> dict[str, Any]:
        if not self.read_assets:
            return {}
        return {
            "saved_research": list(self.citations.values()),
            "saved_research_limited": self.limited,
        }
