from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol


class TransferStatus(StrEnum):
    CREATED = "created"
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETURNED = "returned"
    CANCELED = "canceled"


@dataclass(frozen=True)
class BankAccountRef:
    provider_account_id: str
    bank_name: str
    account_type: str
    last4: str
    verification_status: str


@dataclass(frozen=True)
class TransferResult:
    provider_transfer_id: str
    status: TransferStatus
    return_code: str | None = None


class AchProvider(Protocol):
    async def create_transfer(
        self,
        *,
        source_account_id: str,
        destination_account_id: str,
        amount: Decimal,
        idempotency_key: str,
        metadata: dict[str, str],
    ) -> TransferResult: ...
