import re
from datetime import date
from typing import Annotated, Any, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictStr,
    model_validator,
)


def calendar_date(value: Any) -> date | None:
    if value is None or type(value) is date:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return date.fromisoformat(value)
    raise ValueError("Supply an ISO calendar date or explicit unknown")


CalendarDate = Annotated[date | None, BeforeValidator(calendar_date)]
TaskState = Literal["open", "completed", "canceled"]


class Input(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, revalidate_instances="always"
    )


class MaintenanceFields(Input):
    title: StrictStr = Field(min_length=1, max_length=200)
    due_on: CalendarDate
    timezone: StrictStr = Field(min_length=1, max_length=100)
    state: TaskState = "open"
    completed_on: CalendarDate = None
    text: StrictStr = Field(min_length=1, max_length=4000)
    request_id: StrictStr = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def valid(self) -> Self:
        if (
            not self.title.strip()
            or not self.text.strip()
            or not self.request_id.strip()
        ):
            raise ValueError(
                "Task title, source statement and request ID cannot be blank"
            )
        try:
            ZoneInfo(self.timezone)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("Choose an IANA timezone") from None
        if self.state != "completed" and self.completed_on is not None:
            raise ValueError("A completion date requires completed state")
        return self


class MaintenanceCreate(MaintenanceFields):
    entity_id: StrictStr = Field(min_length=1, max_length=36)


class MaintenanceRead(Input):
    task_id: str = Field(min_length=1, max_length=36)


class MaintenanceChange(MaintenanceFields):
    task_id: StrictStr = Field(min_length=1, max_length=36)
    state_token: StrictStr = Field(pattern=r"^[a-f0-9]{64}$")


class MaintenancePage(Input):
    entity_id: str | None = Field(default=None, min_length=1, max_length=36)
    state: TaskState | Literal["all"] = "open"
    cursor: str = Field(default="", max_length=512)
    limit: int = Field(default=10, ge=1, le=20)


class MaintenanceHistory(MaintenanceRead):
    cursor: str = Field(default="", max_length=36)
    limit: int = Field(default=5, ge=1, le=10)
