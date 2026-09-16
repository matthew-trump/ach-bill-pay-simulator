from enum import StrEnum


class TransferStatus(StrEnum):
    CREATED = "created"
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETURNED = "returned"
    CANCELED = "canceled"


class TransferTransitionError(ValueError):
    pass


ALLOWED_TRANSITIONS: dict[TransferStatus, set[TransferStatus]] = {
    TransferStatus.CREATED: {
        TransferStatus.PENDING,
        TransferStatus.FAILED,
        TransferStatus.CANCELED,
    },
    TransferStatus.PENDING: {
        TransferStatus.PROCESSING,
        TransferStatus.FAILED,
        TransferStatus.CANCELED,
    },
    TransferStatus.PROCESSING: {TransferStatus.SUCCEEDED, TransferStatus.FAILED},
    TransferStatus.SUCCEEDED: {TransferStatus.RETURNED},
    TransferStatus.FAILED: set(),
    TransferStatus.RETURNED: set(),
    TransferStatus.CANCELED: set(),
}


ADVANCE_TRANSITIONS: dict[TransferStatus, TransferStatus] = {
    TransferStatus.CREATED: TransferStatus.PENDING,
    TransferStatus.PENDING: TransferStatus.PROCESSING,
    TransferStatus.PROCESSING: TransferStatus.SUCCEEDED,
}


RETURN_CODES: dict[str, str] = {
    "R01": "Insufficient funds",
    "R02": "Account closed",
    "R03": "No account or unable to locate account",
    "R08": "Payment stopped",
    "R10": "Customer advises unauthorized entry",
}


def ensure_transition_allowed(current: TransferStatus, target: TransferStatus) -> None:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise TransferTransitionError(f"cannot transition transfer from {current} to {target}")


def next_advance_status(current: TransferStatus) -> TransferStatus:
    try:
        return ADVANCE_TRANSITIONS[current]
    except KeyError as exc:
        raise TransferTransitionError(f"cannot advance transfer from {current}") from exc
