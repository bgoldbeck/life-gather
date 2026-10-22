"""Save cited web research sources to an asset, only on the user's explicit request.

The browser names a research reply, one of its cited URLs and an asset. Everything
kept (URL, title, page date, excerpts, research time) is copied from the stored
reply on the server, so a finding always matches what the user was shown.
"""

import json
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from lifegather.assets.identity import canonical_id, member_ids
from lifegather.auth.store import Account
from lifegather.chat.models import Turn
from lifegather.chat.research import IDENTITY_NOTE, web_url
from lifegather.findings.models import ResearchFinding
from lifegather.memory.service import MemoryError, MemoryService

MAX_FINDINGS = 100


class FindingSave(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str = Field(min_length=1, max_length=100)
    turn_id: str = Field(min_length=1, max_length=36)
    url: str = Field(min_length=1, max_length=2048)
    asset_id: str = Field(min_length=1, max_length=36)


class FindingsRead(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    asset_id: str = Field(min_length=1, max_length=36)


class FindingRemove(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    finding_id: str = Field(min_length=1, max_length=36)


def view(row: ResearchFinding) -> dict[str, Any]:
    return {
        "id": row.id,
        "asset_id": row.asset_id,
        "turn_id": row.turn_id,
        "question": row.question,
        "provider": row.provider,
        "model": row.model,
        "researched_at": row.researched_at,
        "url": row.url,
        "title": row.title,
        "published": row.published,
        "excerpt_kind": row.excerpt_kind,
        "excerpts": json.loads(row.excerpts_json),
        "recorded_at": row.recorded_at,
        "removed_at": row.removed_at,
        "identity_note": IDENTITY_NOTE,
    }


def cited_source(row: Turn, url: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """The completed reply's research block and its source for exactly this URL."""
    if row.mode != "research" or row.state != "complete":
        raise MemoryError("Choose a finished web research reply")
    result = json.loads(row.result_json)
    research = result.get("research") if isinstance(result, dict) else None
    if not isinstance(research, dict):
        raise MemoryError("Choose a finished web research reply")
    for source in research.get("sources") or []:
        if isinstance(source, dict) and source.get("url") == url:
            if web_url(url) is None:
                break
            return result, source
    raise MemoryError("That source is not cited in this research reply")


class FindingService:
    def __init__(self, memory: MemoryService) -> None:
        self.memory = memory

    def save(self, actor: Account, value: FindingSave) -> dict[str, Any]:
        data = FindingSave.model_validate(value)
        with self.memory._write() as db:
            replay = db.scalar(
                select(ResearchFinding).where(
                    ResearchFinding.user_id == actor.id,
                    ResearchFinding.request_id == data.request_id,
                )
            )
            if replay is not None:
                if (replay.turn_id, replay.url) != (data.turn_id, data.url):
                    raise MemoryError("Request ID was already used for another save")
                return view(replay) | {"already_saved": True}
            turn = db.scalar(
                select(Turn).where(Turn.user_id == actor.id, Turn.id == data.turn_id)
            )
            if turn is None:
                raise MemoryError("Message not found")
            result, source = cited_source(turn, data.url)
            asset = self.memory._entity(db, actor, data.asset_id)
            if asset.kind != "asset":
                raise MemoryError("Choose a physical asset")
            asset_id = canonical_id(db, actor, asset.id)
            existing = db.scalar(
                select(ResearchFinding).where(
                    ResearchFinding.user_id == actor.id,
                    ResearchFinding.asset_id.in_(member_ids(db, actor, asset_id)),
                    ResearchFinding.url == data.url,
                    ResearchFinding.removed_at.is_(None),
                )
            )
            if existing is not None:
                return view(existing) | {"already_saved": True}
            research = result["research"]
            excerpts = [
                text[:300]
                for text in source.get("excerpts") or []
                if isinstance(text, str)
            ][:3]
            published = source.get("published")
            now = self.memory.clock()
            row = ResearchFinding(
                id=str(uuid4()),
                user_id=actor.id,
                asset_id=asset_id,
                request_id=data.request_id,
                turn_id=turn.id,
                question=turn.text[:1000],
                provider=str(result.get("provider") or "")[:40],
                model=str(result.get("model") or "")[:200],
                researched_at=str(research.get("researched_at") or "")[:40],
                url=data.url,
                title=str(source.get("title") or data.url)[:200],
                published=published[:40] if isinstance(published, str) else None,
                excerpt_kind="answer"
                if source.get("excerpt_kind") == "answer"
                else "source",
                excerpts_json=json.dumps(excerpts, ensure_ascii=False),
                recorded_at=now,
                removed_at=None,
            )
            db.add(row)
            self.memory._audit(db, actor, "research_finding_saved", row.id, now)
            db.flush()
            return view(row) | {"already_saved": False}

    def remove(self, actor: Account, value: FindingRemove) -> dict[str, Any]:
        data = FindingRemove.model_validate(value)
        with self.memory._write() as db:
            row = db.scalar(
                select(ResearchFinding).where(
                    ResearchFinding.user_id == actor.id,
                    ResearchFinding.id == data.finding_id,
                )
            )
            if row is None:
                raise MemoryError("Finding not found")
            # Removing an already removed finding is a safe replay.
            if row.removed_at is None:
                row.removed_at = self.memory.clock()
                self.memory._audit(
                    db, actor, "research_finding_removed", row.id, row.removed_at
                )
            db.flush()
            return view(row)

    def for_asset(self, actor: Account, asset_id: str) -> dict[str, Any]:
        with Session(self.memory.engine) as db:
            asset = self.memory._entity(db, actor, asset_id)
            if asset.kind != "asset":
                raise MemoryError("Choose a physical asset")
            rows = db.scalars(
                select(ResearchFinding)
                .where(
                    ResearchFinding.user_id == actor.id,
                    ResearchFinding.asset_id.in_(
                        member_ids(db, actor, canonical_id(db, actor, asset.id))
                    ),
                    ResearchFinding.removed_at.is_(None),
                )
                .order_by(ResearchFinding.recorded_at.desc(), ResearchFinding.id)
                .limit(MAX_FINDINGS)
            )
            return {"items": [view(row) for row in rows]}
