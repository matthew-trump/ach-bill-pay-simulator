from pydantic import BaseModel, Field


class SeedResponse(BaseModel):
    user_id: str
    funding_account_id: str
    bill_id: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    status: str


class BankAccountResponse(BaseModel):
    id: str
    user_id: str
    bank_name: str
    account_type: str
    last4: str
    verification_status: str


class BillerResponse(BaseModel):
    id: str
    name: str
    status: str


class BillerAccountResponse(BaseModel):
    id: str
    user_id: str
    biller_id: str
    customer_reference: str
    display_mask: str
    nickname: str


class BillResponse(BaseModel):
    id: str
    biller_account_id: str
    amount: str
    due_date: str
    description: str
    status: str


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


class LedgerEntryResponse(BaseModel):
    id: str
    ledger_account_id: str
    debit_cents: int
    credit_cents: int


class LedgerTransactionResponse(BaseModel):
    id: str
    payment_order_id: str
    transaction_type: str
    description: str
    source_type: str
    source_id: str
    entries: list[LedgerEntryResponse]


class PaymentOrderResponse(BaseModel):
    id: str
    user_id: str
    bill_id: str
    funding_account_id: str
    amount: str
    status: str
    idempotency_key: str
    legs: list[PaymentLegResponse]
    ledger_transactions: list[LedgerTransactionResponse]


class ProviderEventIngestResponse(BaseModel):
    provider_event_id: str
    duplicate: bool
    processed: bool
    payment_leg_id: str | None = None


class ProviderEventInboxResponse(BaseModel):
    id: str
    provider_event_id: str
    event_type: str
    payment_leg_id: str | None = None
    processed: bool
    processing_error: str | None = None


class DevOverviewResponse(BaseModel):
    users: list[UserResponse]
    bank_accounts: list[BankAccountResponse]
    billers: list[BillerResponse]
    biller_accounts: list[BillerAccountResponse]
    bills: list[BillResponse]
    payment_orders: list[PaymentOrderResponse]


class LedgerAccountBalanceResponse(BaseModel):
    id: str
    name: str
    account_type: str
    normal_balance: str
    debit_cents: int
    credit_cents: int
    balance_cents: int


class LedgerInvariantResponse(BaseModel):
    balanced: bool
    unbalanced_transaction_ids: list[str]


class ReconciliationRunResponse(BaseModel):
    id: str
    status: str
    checked_payment_legs: int
    checked_provider_transfers: int
    exception_count: int


class ReconciliationExceptionResponse(BaseModel):
    id: str
    reconciliation_run_id: str
    exception_type: str
    severity: str
    payment_order_id: str | None = None
    payment_leg_id: str | None = None
    provider_transfer_id: str | None = None
    description: str
    details: dict[str, object]
    status: str
