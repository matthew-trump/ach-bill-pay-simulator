from hashlib import sha256
from json import dumps

from fastapi import HTTPException, status

from mock_provider.models import Transfer
from mock_provider.schemas import Amount, TransferCreate, TransferResponse
from mock_provider.state_machine import (
    TransferStatus,
    TransferTransitionError,
    ensure_transition_allowed,
)


def canonical_request_body(payload: TransferCreate) -> str:
    return dumps(
        payload.model_dump(by_alias=True, exclude_none=True, round_trip=True),
        separators=(",", ":"),
        sort_keys=True,
    )


def hash_request_body(canonical_body: str) -> str:
    return sha256(canonical_body.encode("utf-8")).hexdigest()


def response_from_transfer(transfer: Transfer) -> TransferResponse:
    return TransferResponse(
        id=transfer.id,
        source=transfer.source,
        destination=transfer.destination,
        amount=Amount(currency=transfer.amount_currency, value=transfer.amount_value),
        metadata=transfer.metadata_json,
        status=transfer.status,
        return_code=transfer.return_code,
        return_description=transfer.return_description,
    )


def transition_transfer(transfer: Transfer, target: TransferStatus) -> None:
    try:
        ensure_transition_allowed(TransferStatus(transfer.status), target)
    except TransferTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    transfer.status = target
