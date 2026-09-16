from decimal import Decimal, InvalidOperation
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

MetadataValue = Annotated[str, Field(min_length=1, max_length=200)]


class Amount(BaseModel):
    currency: str = Field(default="USD", min_length=3, max_length=3)
    value: str

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        currency = value.upper()
        if currency != "USD":
            raise ValueError("only USD is supported in the simulator")
        return currency

    @field_validator("value")
    @classmethod
    def validate_amount_value(cls, value: str) -> str:
        try:
            amount = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("amount must be a decimal string") from exc
        if amount <= 0:
            raise ValueError("amount must be greater than zero")
        exponent = amount.as_tuple().exponent
        if isinstance(exponent, int) and exponent < -2:
            raise ValueError("amount cannot have more than two decimal places")
        return f"{amount:.2f}"


class CustomerCreate(BaseModel):
    external_user_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)


class CustomerResponse(CustomerCreate):
    id: str


class BankAccountCreate(BaseModel):
    routing_number: str = Field(min_length=3, max_length=32)
    account_number: str = Field(min_length=4, max_length=32)
    account_type: str = Field(min_length=1, max_length=32)


class BankAccountResponse(BaseModel):
    id: str
    customer_id: str
    bank_name: str
    account_type: str
    last4: str
    verification_status: str


class TransferCreate(BaseModel):
    source: str = Field(min_length=1, max_length=64)
    destination: str = Field(min_length=1, max_length=64)
    amount: Amount
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)


class TransferResponse(BaseModel):
    id: str
    source: str
    destination: str
    amount: Amount
    metadata: dict[str, str]
    status: str
    return_code: str | None = None
    return_description: str | None = None


class ReturnTransferRequest(BaseModel):
    return_code: str = Field(min_length=3, max_length=3)


class WebhookEndpointCreate(BaseModel):
    url: str = Field(min_length=1, max_length=500)


class WebhookEndpointResponse(BaseModel):
    id: str
    url: str
    secret: str
    status: str


class ProviderEventResponse(BaseModel):
    id: str
    type: str
    transfer_id: str
    payload: dict[str, object]


class WebhookDeliveryResponse(BaseModel):
    id: str
    event_id: str
    endpoint_id: str
    attempt_number: int
    request_headers: dict[str, str]
    request_body: dict[str, object]
    response_status: int | None = None
    response_body: str | None = None
    error: str | None = None
