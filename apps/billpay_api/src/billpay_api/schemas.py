from pydantic import BaseModel, Field


class SeedResponse(BaseModel):
    user_id: str
    funding_account_id: str
    bill_id: str


class PaymentOrderCreate(BaseModel):
    user_id: str
    bill_id: str
    funding_account_id: str
    idempotency_key: str = Field(min_length=1, max_length=200)
    authorization_text: str = Field(min_length=1)


class PaymentLegResponse(BaseModel):
    id: str
    leg_type: str
    provider_transfer_id: str
    status: str
    return_code: str | None = None


class PaymentOrderResponse(BaseModel):
    id: str
    user_id: str
    bill_id: str
    funding_account_id: str
    amount: str
    status: str
    idempotency_key: str
    legs: list[PaymentLegResponse]


class ProviderEventIngestResponse(BaseModel):
    provider_event_id: str
    duplicate: bool
    processed: bool
    payment_leg_id: str | None = None
