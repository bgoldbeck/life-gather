from typing import Literal, Self

from pydantic import BaseModel, Field, StrictInt, model_validator

from lifegather.memory.schemas import Input


class OrderRef(Input):
    retailer: str = Field(min_length=1, max_length=100)
    account_scope: str = Field(min_length=1, max_length=100)
    order_id: str = Field(min_length=1, max_length=100)
    line_id: str = Field(min_length=1, max_length=100)


class DiscoveryInput(Input):
    source_id: str = Field(min_length=1, max_length=36)
    item_key: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    manufacturer: str | None = Field(default=None, min_length=1, max_length=100)
    model: str | None = Field(default=None, min_length=1, max_length=100)
    serial: str | None = Field(default=None, min_length=1, max_length=100)
    order: OrderRef | None = None
    quantity: StrictInt = Field(ge=1, le=20)
    kind: Literal["purchase", "possession", "mention", "payment"]
    quote: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.serial and (not self.manufacturer or self.quantity != 1):
            raise ValueError("Serial identity needs manufacturer and one unit")
        if self.model and not self.manufacturer:
            raise ValueError("Product model needs manufacturer context")
        values = [self.name, self.item_key, self.manufacturer, self.model, self.serial]
        if self.order:
            values.extend(self.order.model_dump().values())
        if any(value is not None and not value.strip() for value in values):
            raise ValueError("Identity fields cannot be blank")
        return self


class DiscoveryView(BaseModel):
    id: str
    decision_id: str
    outcome: str
    reason: str
    asset_ids: list[str]
    candidate_ids: list[str]
    recorded_at: int
    superseded_at: int | None
    previous_decision_id: str | None
