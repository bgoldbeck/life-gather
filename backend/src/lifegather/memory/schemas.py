from datetime import date
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    model_validator,
)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", revalidate_instances="always")


class SourceInput(Input):
    text: str = Field(min_length=1, max_length=20000)
    source_type: Literal[
        "manual", "conversation", "email", "receipt", "statement", "web", "import"
    ] = "manual"
    namespace: str = Field(default="local", min_length=1, max_length=100)
    external_id: str | None = Field(default=None, min_length=1, max_length=300)
    event_date: date | None = None

    @model_validator(mode="after")
    def nonempty(self) -> Self:
        if not self.text.strip():
            raise ValueError("Source text cannot be blank")
        return self


class EntityInput(Input):
    name: str = Field(min_length=1, max_length=200)
    kind: Literal[
        "asset", "person", "place", "organization", "event", "product", "other"
    ]
    source_id: str = Field(min_length=1, max_length=36)
    operation_key: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def nonempty(self) -> Self:
        if not self.name.strip():
            raise ValueError("Entity name cannot be blank")
        return self


class FactInput(Input):
    subject_id: str = Field(min_length=1, max_length=36)
    predicate: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    object_id: str | None = Field(default=None, min_length=1, max_length=36)
    value: StrictStr | StrictBool | StrictInt | None = None
    status: Literal["stated", "verified", "inferred", "unknown"] = "stated"
    source_id: str = Field(min_length=1, max_length=36)
    quote: str | None = Field(default=None, min_length=1, max_length=2000)
    valid_from: date | None = None
    valid_to: date | None = None
    operation_key: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def valid_fact(self) -> Self:
        if (self.object_id is not None) == ("value" in self.model_fields_set):
            raise ValueError(
                "Supply either object_id or value, including explicit null"
            )
        if isinstance(self.value, str) and len(self.value) > 2000:
            raise ValueError("Literal text is too long")
        if self.valid_from and self.valid_to and self.valid_from >= self.valid_to:
            raise ValueError("valid_to must follow valid_from")
        return self


class SourceView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    text: str
    source_type: str
    namespace: str
    external_id: str | None
    content_hash: str
    event_date: date | None
    recorded_at: int


class EntityView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    kind: str
    source_id: str
    recorded_at: int


class FactView(BaseModel):
    id: str
    subject_id: str
    predicate: str
    object_id: str | None
    value: str | bool | int | None
    status: str
    valid_from: date | None
    valid_to: date | None
    recorded_at: int
    superseded_at: int | None
    replaces_id: str | None
    evidence: list[dict[str, str | None]]
