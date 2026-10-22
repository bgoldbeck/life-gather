"""Server-owned workflow attribution, independent of fact confidence and evidence."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChangeOrigin(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    interface: Literal["service", "web", "mcp", "worker", "scheduler"] = "service"
    initiator: Literal["unknown", "account_request", "scheduled", "external_client"] = (
        "unknown"
    )
    method: Literal[
        "unspecified",
        "manual_entry",
        "user_statement",
        "ai_extraction",
        "ai_inference",
        "ai_assistant",
        "import",
        "review",
        "correction",
    ] = "unspecified"
    provider: str | None = Field(default=None, max_length=64)
    model: str | None = Field(default=None, max_length=100)
    related_id: str | None = Field(default=None, max_length=36)


CURRENT_ORIGIN: ContextVar[ChangeOrigin | None] = ContextVar(
    "change_origin", default=None
)


@contextmanager
def change_origin(**changes: Any) -> Iterator[None]:
    value = ChangeOrigin.model_validate(
        {**(CURRENT_ORIGIN.get() or ChangeOrigin()).model_dump(), **changes}
    )
    token = CURRENT_ORIGIN.set(value)
    try:
        yield
    finally:
        CURRENT_ORIGIN.reset(token)


def origin_json() -> str:
    return (CURRENT_ORIGIN.get() or ChangeOrigin()).model_dump_json()
