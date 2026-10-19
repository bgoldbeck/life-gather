"""Typed, server-registered scan sources; no dynamic user/plugin execution."""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from lifegather.auth.store import Account
from lifegather.memory.schemas import SourceInput
from lifegather.memory.service import MemoryError


class ScanPage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    cursor: str = Field(default="", max_length=36)


class ScanRead(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    run_id: str = Field(min_length=1, max_length=36)
    after: int = Field(default=0, ge=0, le=50)


@dataclass(frozen=True)
class PreparedScan:
    resource_key: str
    config: dict[str, Any]


@dataclass(frozen=True)
class ScanEvidence:
    key: str
    source: SourceInput | None
    label: str
    reason: str = ""
    metadata: dict[str, str | int | bool] = field(default_factory=dict)


@dataclass(frozen=True)
class ScanBatch:
    items: list[ScanEvidence]
    next_cursor: dict[str, Any] | None
    truncated: bool = False


@dataclass
class ScanContext:
    actor: Account
    run_id: str
    check: Callable[[], None]
    state: dict[str, Any] = field(default_factory=dict)


class ScanHandler(Protocol):
    @property
    def key(self) -> str: ...
    @property
    def title(self) -> str: ...
    @property
    def permissions(self) -> tuple[str, ...]: ...
    @property
    def config_model(self) -> type[BaseModel]: ...

    def prepare(self, actor: Account, config: BaseModel) -> PreparedScan: ...

    def authorize(
        self, db: Session, actor: Account, config: dict[str, Any]
    ) -> None: ...

    async def step(
        self, context: ScanContext, config: dict[str, Any], cursor: dict[str, Any]
    ) -> ScanBatch: ...


class ScanRegistry:
    def __init__(self, handlers: Sequence[ScanHandler]) -> None:
        self.handlers: dict[str, ScanHandler] = {}
        for handler in handlers:
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,49}", handler.key):
                raise ValueError("Invalid registered scan key")
            if handler.key in self.handlers:
                raise ValueError("Duplicate registered scan key")
            self.handlers[handler.key] = handler

    def get(self, key: str) -> ScanHandler:
        if key not in self.handlers:
            raise MemoryError("This scan source is unavailable")
        return self.handlers[key]

    def normalize(self, key: str, config: dict[str, Any]) -> BaseModel:
        try:
            return self.get(key).config_model.model_validate(config)
        except ValidationError:
            raise MemoryError("Invalid scan scope or options") from None

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "key": h.key,
                "title": h.title,
                "permissions": list(h.permissions),
                "schema": h.config_model.model_json_schema(),
            }
            for h in self.handlers.values()
        ]
