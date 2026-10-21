"""Bounded template and supplied-value commands shared by UI and MCP."""

import re
from datetime import date
from typing import Literal, Self

from pydantic import Field, model_validator

from lifegather.memory.schemas import Input
from lifegather.profiles.service import RESERVED_CUSTOM_NAMES


class TemplateField(Input):
    id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    name: str = Field(min_length=1, max_length=48)
    system_field: Literal["vin"] | None = None
    retired: bool = False

    @model_validator(mode="after")
    def label(self) -> Self:
        self.name = self.name.strip()
        normalized = (
            re.sub(r"[\W_]+", "_", self.name, flags=re.UNICODE).strip("_").lower()
        )
        if not self.name or any(ord(char) < 32 for char in self.name):
            raise ValueError("Field names need visible single-line text")
        if self.system_field:
            if self.name != "VIN":
                raise ValueError("The standard VIN field keeps its name and meaning")
        elif normalized in RESERVED_CUSTOM_NAMES or normalized.startswith("profile_"):
            raise ValueError(
                "Use the existing standard field instead of a custom label"
            )
        return self


class TypeSave(Input):
    type_id: str | None = Field(default=None, max_length=36)
    expected_revision: str | None = Field(default=None, max_length=100)
    request_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    fields: list[TemplateField] = Field(default_factory=list, max_length=32)
    retired: bool = False

    @model_validator(mode="after")
    def shape(self) -> Self:
        self.name = self.name.strip()
        if not self.name or any(ord(char) < 32 for char in self.name):
            raise ValueError("Type names need visible single-line text")
        if bool(self.type_id) != bool(self.expected_revision):
            raise ValueError("Editing requires the current definition revision")
        names = [field.name.casefold() for field in self.fields]
        ids = [field.id for field in self.fields if field.id]
        if len(set(names)) != len(names) or len(set(ids)) != len(ids):
            raise ValueError("Field names and IDs must be unique within a type")
        return self


class TypeRead(Input):
    type_id: str = Field(min_length=1, max_length=36)
    cursor: str = Field(default="", max_length=36)


class TypeList(Input):
    include_retired: bool = False
    cursor: str = Field(default="", max_length=36)


class TypedAssetRead(Input):
    entity_id: str = Field(min_length=1, max_length=36)
    history: bool = False
    cursor: str = Field(default="", max_length=36)


class TypeAssign(Input):
    entity_id: str = Field(min_length=1, max_length=36)
    type_id: str = Field(min_length=1, max_length=36)
    request_id: str = Field(min_length=1, max_length=100)
    replaces_id: str | None = Field(default=None, min_length=1, max_length=36)


class FieldValue(Input):
    field_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    value: str | None = Field(max_length=500)
    text: str = Field(min_length=1, max_length=2000)
    valid_from: date | None = None
    valid_to: date | None = None

    @model_validator(mode="after")
    def sourced(self) -> Self:
        if self.valid_from and self.valid_to and self.valid_from >= self.valid_to:
            raise ValueError("End date must follow start date")
        if not self.text.strip() or (
            self.value is not None
            and (not self.value.strip() or self.value not in self.text)
        ):
            raise ValueError("The exact supplied value must appear in its evidence")
        return self


class TypeFieldSave(FieldValue):
    entity_id: str = Field(min_length=1, max_length=36)
    type_id: str = Field(min_length=1, max_length=36)
    request_id: str = Field(min_length=1, max_length=100)
    replaces_id: str | None = Field(default=None, min_length=1, max_length=36)
