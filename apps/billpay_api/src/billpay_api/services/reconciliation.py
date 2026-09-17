from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from billpay_api.ids import new_id
from billpay_api.persistence.models import (
    LedgerTransaction,
    PaymentLeg,
    PaymentOrder,
    ReconciliationException,
    ReconciliationRun,
)
from billpay_api.providers.types import AchProvider, ProviderTransfer
from billpay_api.services.ledger import (
    ledger_transactions_for_payment,
    unbalanced_ledger_transaction_ids,
)


async def run_reconciliation(
    *,
    session: Session,
    provider: AchProvider,
) -> ReconciliationRun:
    provider_transfers = await provider.list_transfers()
    provider_by_id = {
        transfer.provider_transfer_id: transfer for transfer in provider_transfers
    }
    legs = session.scalars(select(PaymentLeg).order_by(PaymentLeg.id)).all()
    leg_by_provider_transfer_id = {leg.provider_transfer_id: leg for leg in legs}

    run = ReconciliationRun(
        id=new_id("recon"),
        status="running",
        checked_payment_legs=len(legs),
        checked_provider_transfers=len(provider_transfers),
    )
    session.add(run)
    session.flush()

    exceptions: list[ReconciliationException] = []
    for leg in legs:
        provider_transfer = provider_by_id.get(leg.provider_transfer_id)
        if provider_transfer is None:
            exceptions.append(
                _exception(
                    run=run,
                    exception_type="internal_leg_missing_provider_transfer",
                    severity="critical",
                    description=(
                        "Internal payment leg references a provider transfer that does not exist."
                    ),
                    payment_order_id=leg.payment_order_id,
                    payment_leg_id=leg.id,
                    provider_transfer_id=leg.provider_transfer_id,
                    details={"leg_status": leg.status},
                )
            )
            continue
        exceptions.extend(_compare_leg_to_provider(run, leg, provider_transfer))

    for provider_transfer in provider_transfers:
        if provider_transfer.provider_transfer_id not in leg_by_provider_transfer_id:
            exceptions.append(
                _exception(
                    run=run,
                    exception_type="provider_transfer_missing_internal_leg",
                    severity="critical",
                    description=(
                        "Provider transfer does not have a corresponding internal payment leg."
                    ),
                    provider_transfer_id=provider_transfer.provider_transfer_id,
                    details={
                        "provider_status": provider_transfer.status,
                        "provider_amount": f"{provider_transfer.amount:.2f}",
                    },
                )
            )

    orders = session.scalars(select(PaymentOrder).order_by(PaymentOrder.id)).all()
    for order in orders:
        order_legs = [leg for leg in legs if leg.payment_order_id == order.id]
        transactions = ledger_transactions_for_payment(session, order.id)
        exceptions.extend(_ledger_exceptions_for_order(run, order, order_legs, transactions))
        exceptions.extend(_late_return_exceptions_for_order(run, order, order_legs))

    for transaction_id in unbalanced_ledger_transaction_ids(session):
        exceptions.append(
            _exception(
                run=run,
                exception_type="unbalanced_ledger_transaction",
                severity="critical",
                description="Ledger transaction debits and credits do not balance.",
                details={"ledger_transaction_id": transaction_id},
            )
        )

    session.add_all(exceptions)
    run.exception_count = len(exceptions)
    run.status = "completed"
    run.completed_at = datetime.now(UTC)
    session.commit()
    return run


def list_reconciliation_runs(session: Session) -> list[ReconciliationRun]:
    return list(
        session.scalars(
            select(ReconciliationRun).order_by(ReconciliationRun.started_at.desc())
        ).all()
    )


def list_reconciliation_exceptions(
    session: Session,
    *,
    unresolved_only: bool = True,
) -> list[ReconciliationException]:
    statement = select(ReconciliationException).order_by(
        ReconciliationException.created_at.desc(),
        ReconciliationException.id,
    )
    if unresolved_only:
        statement = statement.where(ReconciliationException.status == "open")
    return list(session.scalars(statement).all())


def _compare_leg_to_provider(
    run: ReconciliationRun,
    leg: PaymentLeg,
    provider_transfer: ProviderTransfer,
) -> list[ReconciliationException]:
    exceptions: list[ReconciliationException] = []
    if leg.status != provider_transfer.status:
        exceptions.append(
            _exception(
                run=run,
                exception_type="status_mismatch",
                severity="warning",
                description="Internal payment leg status differs from provider transfer status.",
                payment_order_id=leg.payment_order_id,
                payment_leg_id=leg.id,
                provider_transfer_id=leg.provider_transfer_id,
                details={
                    "leg_status": leg.status,
                    "provider_status": provider_transfer.status,
                },
            )
        )
    if Decimal(leg.amount) != provider_transfer.amount:
        exceptions.append(
            _exception(
                run=run,
                exception_type="amount_mismatch",
                severity="critical",
                description="Internal payment leg amount differs from provider transfer amount.",
                payment_order_id=leg.payment_order_id,
                payment_leg_id=leg.id,
                provider_transfer_id=leg.provider_transfer_id,
                details={
                    "leg_amount": leg.amount,
                    "provider_amount": f"{provider_transfer.amount:.2f}",
                },
            )
        )
    return exceptions


def _ledger_exceptions_for_order(
    run: ReconciliationRun,
    order: PaymentOrder,
    legs: list[PaymentLeg],
    transactions: list[LedgerTransaction],
) -> list[ReconciliationException]:
    exceptions: list[ReconciliationException] = []
    transaction_types = [transaction.transaction_type for transaction in transactions]
    expected_by_leg_status = {
        "funding": ("succeeded", "funding_succeeded"),
        "delivery": ("succeeded", "delivery_succeeded"),
    }
    for leg_type, (success_status, transaction_type) in expected_by_leg_status.items():
        leg = next((candidate for candidate in legs if candidate.leg_type == leg_type), None)
        if leg is None or leg.status != success_status:
            continue
        count = transaction_types.count(transaction_type)
        if count == 0:
            exceptions.append(
                _exception(
                    run=run,
                    exception_type="missing_ledger_posting",
                    severity="critical",
                    description="Succeeded payment leg is missing its expected ledger posting.",
                    payment_order_id=order.id,
                    payment_leg_id=leg.id,
                    provider_transfer_id=leg.provider_transfer_id,
                    details={"expected_transaction_type": transaction_type},
                )
            )
        elif count > 1:
            exceptions.append(
                _exception(
                    run=run,
                    exception_type="duplicate_ledger_posting",
                    severity="critical",
                    description=(
                        "Payment order has duplicate ledger postings for the same leg outcome."
                    ),
                    payment_order_id=order.id,
                    payment_leg_id=leg.id,
                    provider_transfer_id=leg.provider_transfer_id,
                    details={
                        "transaction_type": transaction_type,
                        "posting_count": count,
                    },
                )
            )
    return exceptions


def _late_return_exceptions_for_order(
    run: ReconciliationRun,
    order: PaymentOrder,
    legs: list[PaymentLeg],
) -> list[ReconciliationException]:
    funding_leg = next((leg for leg in legs if leg.leg_type == "funding"), None)
    delivery_leg = next((leg for leg in legs if leg.leg_type == "delivery"), None)
    if funding_leg is None or delivery_leg is None:
        return []
    if funding_leg.status == "returned" and delivery_leg.status == "succeeded":
        return [
            _exception(
                run=run,
                exception_type="returned_funding_after_completed_delivery",
                severity="critical",
                description="Funding returned after delivery already completed.",
                payment_order_id=order.id,
                payment_leg_id=funding_leg.id,
                provider_transfer_id=funding_leg.provider_transfer_id,
                details={
                    "payment_status": order.status,
                    "funding_return_code": funding_leg.return_code,
                    "delivery_leg_id": delivery_leg.id,
                },
            )
        ]
    return []


def _exception(
    *,
    run: ReconciliationRun,
    exception_type: str,
    severity: str,
    description: str,
    details: dict[str, object],
    payment_order_id: str | None = None,
    payment_leg_id: str | None = None,
    provider_transfer_id: str | None = None,
) -> ReconciliationException:
    return ReconciliationException(
        id=new_id("rex"),
        reconciliation_run_id=run.id,
        exception_type=exception_type,
        severity=severity,
        payment_order_id=payment_order_id,
        payment_leg_id=payment_leg_id,
        provider_transfer_id=provider_transfer_id,
        description=description,
        details_json=details,
        status="open",
    )
