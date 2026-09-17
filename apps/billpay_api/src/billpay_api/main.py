from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from billpay_api.persistence.database import BillpayDatabase
from billpay_api.persistence.models import (
    BankAccount,
    Bill,
    Biller,
    BillerAccount,
    PaymentLeg,
    PaymentOrder,
    ProviderEventInbox,
    ReconciliationException,
    ReconciliationRun,
    User,
)
from billpay_api.providers.mock_ach import MockAchProviderClient
from billpay_api.providers.types import AchProvider
from billpay_api.schemas import (
    BankAccountResponse,
    BillerAccountResponse,
    BillerResponse,
    BillResponse,
    DevOverviewResponse,
    LedgerAccountBalanceResponse,
    LedgerInvariantResponse,
    PaymentOrderCreate,
    PaymentOrderResponse,
    ProviderEventInboxResponse,
    ProviderEventIngestResponse,
    ReconciliationExceptionResponse,
    ReconciliationRunResponse,
    SeedResponse,
    UserResponse,
)
from billpay_api.services.ledger import (
    ensure_ledger_accounts,
    ledger_account_balances,
    unbalanced_ledger_transaction_ids,
)
from billpay_api.services.payments import (
    create_payment_order,
    ingest_provider_event,
    payment_order_response,
)
from billpay_api.services.reconciliation import (
    list_reconciliation_exceptions,
    list_reconciliation_runs,
    run_reconciliation,
)
from billpay_api.services.seed import ensure_seed_data
from billpay_api.settings import settings


def create_app(
    *,
    database_url: str | None = None,
    provider: AchProvider | None = None,
) -> FastAPI:
    billpay_db = BillpayDatabase(database_url or settings.database_url)
    ach_provider = provider or MockAchProviderClient(
        base_url=settings.provider_base_url,
        api_key=settings.provider_api_key,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        billpay_db.create_all()
        yield

    app = FastAPI(title="ACH Bill Pay Simulator API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:3500", "http://localhost:3500"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.billpay_db = billpay_db
    app.state.ach_provider = ach_provider

    def get_session() -> Iterator[Session]:
        yield from billpay_db.session()

    def get_provider() -> AchProvider:
        return ach_provider

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name}

    @app.post("/dev/seed", response_model=SeedResponse)
    def seed(session: Session = Depends(get_session)) -> SeedResponse:
        return ensure_seed_data(session)

    @app.get("/dev/overview", response_model=DevOverviewResponse)
    def dev_overview(session: Session = Depends(get_session)) -> DevOverviewResponse:
        users = session.scalars(select(User).order_by(User.id)).all()
        bank_accounts = session.scalars(select(BankAccount).order_by(BankAccount.id)).all()
        billers = session.scalars(select(Biller).order_by(Biller.id)).all()
        biller_accounts = session.scalars(select(BillerAccount).order_by(BillerAccount.id)).all()
        bills = session.scalars(select(Bill).order_by(Bill.due_date, Bill.id)).all()
        payment_orders = session.scalars(
            select(PaymentOrder).order_by(PaymentOrder.created_at.desc(), PaymentOrder.id)
        ).all()
        return DevOverviewResponse(
            users=[
                UserResponse(id=user.id, email=user.email, name=user.name, status=user.status)
                for user in users
            ],
            bank_accounts=[
                BankAccountResponse(
                    id=account.id,
                    user_id=account.user_id,
                    bank_name=account.bank_name,
                    account_type=account.account_type,
                    last4=account.last4,
                    verification_status=account.verification_status,
                )
                for account in bank_accounts
            ],
            billers=[
                BillerResponse(id=biller.id, name=biller.name, status=biller.status)
                for biller in billers
            ],
            biller_accounts=[
                BillerAccountResponse(
                    id=account.id,
                    user_id=account.user_id,
                    biller_id=account.biller_id,
                    customer_reference=account.customer_reference,
                    display_mask=account.display_mask,
                    nickname=account.nickname,
                )
                for account in biller_accounts
            ],
            bills=[
                BillResponse(
                    id=bill.id,
                    biller_account_id=bill.biller_account_id,
                    amount=bill.amount,
                    due_date=bill.due_date.isoformat(),
                    description=bill.description,
                    status=bill.status,
                )
                for bill in bills
            ],
            payment_orders=[payment_order_response(session, order) for order in payment_orders],
        )

    @app.post("/v1/payment-orders", response_model=PaymentOrderResponse)
    async def submit_payment_order(
        payload: PaymentOrderCreate,
        session: Session = Depends(get_session),
        provider: AchProvider = Depends(get_provider),
    ) -> PaymentOrderResponse:
        try:
            return await create_payment_order(
                session=session,
                provider=provider,
                payload=payload,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get("/v1/payment-orders/{payment_order_id}", response_model=PaymentOrderResponse)
    def get_payment_order(
        payment_order_id: str,
        session: Session = Depends(get_session),
    ) -> PaymentOrderResponse:
        order = session.get(PaymentOrder, payment_order_id)
        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="payment order not found",
            )
        return payment_order_response(session, order)

    @app.post("/v1/provider-events", response_model=ProviderEventIngestResponse)
    async def receive_provider_event(
        request: Request,
        session: Session = Depends(get_session),
        provider: AchProvider = Depends(get_provider),
    ) -> ProviderEventIngestResponse:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="event payload must be an object",
            )
        return await ingest_provider_event(session=session, provider=provider, payload=payload)

    @app.get("/v1/provider-events", response_model=list[ProviderEventInboxResponse])
    def list_provider_events(
        session: Session = Depends(get_session),
    ) -> list[ProviderEventInboxResponse]:
        events = session.scalars(
            select(ProviderEventInbox).order_by(ProviderEventInbox.received_at.desc())
        ).all()
        return [_provider_event_response(session, event) for event in events]

    @app.get("/v1/ledger/accounts", response_model=list[LedgerAccountBalanceResponse])
    def list_ledger_accounts(
        session: Session = Depends(get_session),
    ) -> list[LedgerAccountBalanceResponse]:
        ensure_ledger_accounts(session)
        session.commit()
        return [
            LedgerAccountBalanceResponse(
                id=balance.account.id,
                name=balance.account.name,
                account_type=balance.account.account_type,
                normal_balance=balance.account.normal_balance,
                debit_cents=balance.debit_cents,
                credit_cents=balance.credit_cents,
                balance_cents=balance.balance_cents,
            )
            for balance in ledger_account_balances(session)
        ]

    @app.get("/v1/ledger/invariants", response_model=LedgerInvariantResponse)
    def get_ledger_invariants(
        session: Session = Depends(get_session),
    ) -> LedgerInvariantResponse:
        unbalanced = unbalanced_ledger_transaction_ids(session)
        return LedgerInvariantResponse(
            balanced=len(unbalanced) == 0,
            unbalanced_transaction_ids=unbalanced,
        )

    @app.post("/v1/reconciliation-runs", response_model=ReconciliationRunResponse)
    async def create_reconciliation_run(
        session: Session = Depends(get_session),
        provider: AchProvider = Depends(get_provider),
    ) -> ReconciliationRunResponse:
        run = await run_reconciliation(session=session, provider=provider)
        return _reconciliation_run_response(run)

    @app.get("/v1/reconciliation-runs", response_model=list[ReconciliationRunResponse])
    def get_reconciliation_runs(
        session: Session = Depends(get_session),
    ) -> list[ReconciliationRunResponse]:
        return [_reconciliation_run_response(run) for run in list_reconciliation_runs(session)]

    @app.get(
        "/v1/reconciliation-exceptions",
        response_model=list[ReconciliationExceptionResponse],
    )
    def get_reconciliation_exceptions(
        session: Session = Depends(get_session),
    ) -> list[ReconciliationExceptionResponse]:
        return [
            _reconciliation_exception_response(exception)
            for exception in list_reconciliation_exceptions(session)
        ]

    return app


def _reconciliation_run_response(run: ReconciliationRun) -> ReconciliationRunResponse:
    return ReconciliationRunResponse(
        id=run.id,
        status=run.status,
        checked_payment_legs=run.checked_payment_legs,
        checked_provider_transfers=run.checked_provider_transfers,
        exception_count=run.exception_count,
    )


def _reconciliation_exception_response(
    exception: ReconciliationException,
) -> ReconciliationExceptionResponse:
    return ReconciliationExceptionResponse(
        id=exception.id,
        reconciliation_run_id=exception.reconciliation_run_id,
        exception_type=exception.exception_type,
        severity=exception.severity,
        payment_order_id=exception.payment_order_id,
        payment_leg_id=exception.payment_leg_id,
        provider_transfer_id=exception.provider_transfer_id,
        description=exception.description,
        details=exception.details_json,
        status=exception.status,
    )


def _provider_event_response(
    session: Session,
    event: ProviderEventInbox,
) -> ProviderEventInboxResponse:
    payment_leg_id: str | None = None
    try:
        data = event.payload_json.get("data")
        if isinstance(data, dict):
            transfer = data.get("transfer")
            if isinstance(transfer, dict):
                transfer_id = transfer.get("id")
                if transfer_id is not None:
                    leg = session.scalars(
                        select(PaymentLeg).where(
                            PaymentLeg.provider_transfer_id == str(transfer_id)
                        )
                    ).one_or_none()
                    if leg is not None:
                        payment_leg_id = leg.id
    except AttributeError:
        payment_leg_id = None
    return ProviderEventInboxResponse(
        id=event.id,
        provider_event_id=event.provider_event_id,
        event_type=event.event_type,
        payment_leg_id=payment_leg_id,
        processed=event.processed_at is not None,
        processing_error=event.processing_error,
    )


app = create_app()
