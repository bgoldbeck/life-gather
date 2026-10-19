from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lifegather.reconciliation.purchase_details import Currency, minor_amount


class Input(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, revalidate_instances="always"
    )


class EvidenceSave(Input):
    source_id: str = Field(min_length=1, max_length=36)
    purchase_id: str | None = Field(default=None, min_length=1, max_length=36)
    retailer: str | None = Field(default=None, min_length=1, max_length=100)
    account_scope: str | None = Field(default=None, min_length=1, max_length=100)
    order_id: str | None = Field(default=None, min_length=1, max_length=100)
    role: Literal["order", "receipt", "shipment", "payment"]
    quote: str = Field(min_length=1, max_length=2000)
    amount: str | None = Field(default=None, min_length=1, max_length=14)
    currency: Currency = "USD"
    money_quote: str | None = Field(default=None, min_length=1, max_length=500)
    occurred_on: str | None = Field(
        default=None, pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
    )
    date_quote: str | None = Field(default=None, min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=300)
    expected_head: str | None = Field(default=None, min_length=1, max_length=36)
    request_id: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def shape(self) -> Self:
        if self.purchase_id:
            if any((self.retailer, self.account_scope, self.order_id)):
                raise ValueError("Choose an existing purchase or an order reference")
        elif not all((self.retailer, self.account_scope, self.order_id)):
            raise ValueError(
                "Retailer, private account label and order ID are required"
            )
        if any(
            value is not None and not value.strip()
            for value in (
                self.retailer,
                self.account_scope,
                self.order_id,
                self.quote,
                self.reason,
                self.request_id,
            )
        ):
            raise ValueError("Evidence fields cannot be blank")
        if self.amount is not None:
            minor_amount(self.amount, self.currency)
        if (self.amount is None) != (self.money_quote is None):
            raise ValueError("An amount needs its supporting quote")
        if self.role == "shipment" and self.amount is not None:
            raise ValueError(
                "Shipment evidence does not record an order total or payment"
            )
        if (self.occurred_on is None) != (self.date_quote is None):
            raise ValueError("An event date needs its supporting quote")
        if self.occurred_on:
            date.fromisoformat(self.occurred_on)
        return self


class EvidenceWithdraw(Input):
    source_id: str = Field(min_length=1, max_length=36)
    expected_head: str = Field(min_length=1, max_length=36)
    reason: str = Field(min_length=1, max_length=300, pattern=r"\S")
    request_id: str = Field(min_length=1, max_length=100, pattern=r"\S")


class PurchasePage(Input):
    cursor: str = Field(default="", max_length=36)
    limit: int = Field(default=10, ge=1, le=20)


class PurchaseRead(Input):
    purchase_id: str = Field(min_length=1, max_length=36)
    after: str = Field(default="", max_length=36)
    limit: int = Field(default=5, ge=1, le=10)


class EvidenceHistory(Input):
    source_id: str = Field(min_length=1, max_length=36)
    before_revision: int = Field(default=0, ge=0)
