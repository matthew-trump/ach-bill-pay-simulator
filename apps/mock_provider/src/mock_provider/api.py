from collections.abc import Callable, Iterator

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from mock_provider.ids import new_id
from mock_provider.models import BankAccount, Customer, IdempotencyRecord, Transfer
from mock_provider.schemas import (
    BankAccountCreate,
    BankAccountResponse,
    CustomerCreate,
    CustomerResponse,
    ReturnTransferRequest,
    TransferCreate,
    TransferResponse,
)
from mock_provider.services import (
    canonical_request_body,
    hash_request_body,
    response_from_transfer,
    transition_transfer,
)
from mock_provider.state_machine import (
    RETURN_CODES,
    TransferStatus,
    TransferTransitionError,
    next_advance_status,
)


def make_v1_router(
    *,
    get_session: Callable[[], Iterator[Session]],
    api_key: str,
) -> APIRouter:
    router = APIRouter(prefix="/v1", dependencies=[Depends(_require_bearer(api_key))])

    @router.post("/customers", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
    def create_customer(
        payload: CustomerCreate,
        session: Session = Depends(get_session),
    ) -> Customer:
        customer = Customer(id=new_id("cus"), **payload.model_dump())
        session.add(customer)
        session.commit()
        session.refresh(customer)
        return customer

    @router.get("/customers/{customer_id}", response_model=CustomerResponse)
    def get_customer(customer_id: str, session: Session = Depends(get_session)) -> Customer:
        return _get_customer_or_404(session, customer_id)

    @router.post(
        "/customers/{customer_id}/bank-accounts",
        response_model=BankAccountResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_bank_account(
        customer_id: str,
        payload: BankAccountCreate,
        session: Session = Depends(get_session),
    ) -> BankAccount:
        _get_customer_or_404(session, customer_id)
        account = BankAccount(
            id=new_id("ba"),
            customer_id=customer_id,
            bank_name="Fictional Test Bank",
            account_type=payload.account_type,
            last4=payload.account_number[-4:],
            verification_status="unverified",
        )
        session.add(account)
        session.commit()
        session.refresh(account)
        return account

    @router.get("/bank-accounts/{bank_account_id}", response_model=BankAccountResponse)
    def get_bank_account(
        bank_account_id: str,
        session: Session = Depends(get_session),
    ) -> BankAccount:
        return _get_bank_account_or_404(session, bank_account_id)

    @router.post("/bank-accounts/{bank_account_id}/verify", response_model=BankAccountResponse)
    def verify_bank_account(
        bank_account_id: str,
        session: Session = Depends(get_session),
    ) -> BankAccount:
        account = _get_bank_account_or_404(session, bank_account_id)
        account.verification_status = "verified"
        session.commit()
        session.refresh(account)
        return account

    @router.post("/transfers", response_model=TransferResponse, status_code=status.HTTP_201_CREATED)
    def create_transfer(
        payload: TransferCreate,
        response: Response,
        idempotency_key: str = Header(alias="Idempotency-Key"),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        _get_bank_account_or_404(session, payload.source)
        _get_bank_account_or_404(session, payload.destination)

        endpoint = "/v1/transfers"
        client_id = "development"
        canonical_body = canonical_request_body(payload)
        request_hash = hash_request_body(canonical_body)
        existing = session.scalars(
            select(IdempotencyRecord).where(
                IdempotencyRecord.client_id == client_id,
                IdempotencyRecord.method == "POST",
                IdempotencyRecord.endpoint == endpoint,
                IdempotencyRecord.idempotency_key == idempotency_key,
            )
        ).one_or_none()
        if existing is not None:
            if existing.request_hash != request_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="idempotency key reused with different request body",
                )
            response.status_code = existing.response_status
            return existing.response_body

        transfer = Transfer(
            id=new_id("tr"),
            source=payload.source,
            destination=payload.destination,
            amount_currency=payload.amount.currency,
            amount_value=payload.amount.value,
            metadata_json=payload.metadata,
            status=TransferStatus.CREATED,
        )
        session.add(transfer)
        body = response_from_transfer(transfer).model_dump()
        session.add(
            IdempotencyRecord(
                client_id=client_id,
                method="POST",
                endpoint=endpoint,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_status=status.HTTP_201_CREATED,
                response_body=body,
                canonical_request=canonical_body,
            )
        )
        session.commit()
        return body

    @router.get("/transfers/{transfer_id}", response_model=TransferResponse)
    def get_transfer(transfer_id: str, session: Session = Depends(get_session)) -> TransferResponse:
        return response_from_transfer(_get_transfer_or_404(session, transfer_id))

    @router.get("/transfers", response_model=list[TransferResponse])
    def list_transfers(session: Session = Depends(get_session)) -> list[TransferResponse]:
        transfers = session.scalars(select(Transfer).order_by(Transfer.created_at)).all()
        return [response_from_transfer(transfer) for transfer in transfers]

    @router.post("/transfers/{transfer_id}/cancel", response_model=TransferResponse)
    def cancel_transfer(
        transfer_id: str,
        session: Session = Depends(get_session),
    ) -> TransferResponse:
        transfer = _get_transfer_or_404(session, transfer_id)
        transition_transfer(transfer, TransferStatus.CANCELED)
        session.commit()
        session.refresh(transfer)
        return response_from_transfer(transfer)

    return router


def make_sandbox_router(get_session: Callable[[], Iterator[Session]]) -> APIRouter:
    router = APIRouter(prefix="/_sandbox")

    @router.post("/transfers/{transfer_id}/advance", response_model=TransferResponse)
    def advance_transfer(
        transfer_id: str,
        session: Session = Depends(get_session),
    ) -> TransferResponse:
        transfer = _get_transfer_or_404(session, transfer_id)
        try:
            target = next_advance_status(TransferStatus(transfer.status))
        except TransferTransitionError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        transition_transfer(transfer, target)
        session.commit()
        session.refresh(transfer)
        return response_from_transfer(transfer)

    @router.post("/transfers/{transfer_id}/fail", response_model=TransferResponse)
    def fail_transfer(
        transfer_id: str,
        session: Session = Depends(get_session),
    ) -> TransferResponse:
        transfer = _get_transfer_or_404(session, transfer_id)
        transition_transfer(transfer, TransferStatus.FAILED)
        session.commit()
        session.refresh(transfer)
        return response_from_transfer(transfer)

    @router.post("/transfers/{transfer_id}/return", response_model=TransferResponse)
    def return_transfer(
        transfer_id: str,
        payload: ReturnTransferRequest,
        session: Session = Depends(get_session),
    ) -> TransferResponse:
        return_code = payload.return_code.upper()
        if return_code not in RETURN_CODES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="unknown return code",
            )
        transfer = _get_transfer_or_404(session, transfer_id)
        transition_transfer(transfer, TransferStatus.RETURNED)
        transfer.return_code = return_code
        transfer.return_description = RETURN_CODES[return_code]
        session.commit()
        session.refresh(transfer)
        return response_from_transfer(transfer)

    return router


def _require_bearer(api_key: str) -> Callable[[str | None], None]:
    def dependency(authorization: str | None = Header(default=None)) -> None:
        if authorization != f"Bearer {api_key}":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")

    return dependency


def _get_customer_or_404(session: Session, customer_id: str) -> Customer:
    customer = session.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="customer not found")
    return customer


def _get_bank_account_or_404(session: Session, bank_account_id: str) -> BankAccount:
    account = session.get(BankAccount, bank_account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="bank account not found")
    return account


def _get_transfer_or_404(session: Session, transfer_id: str) -> Transfer:
    transfer = session.get(Transfer, transfer_id)
    if transfer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="transfer not found")
    return transfer
