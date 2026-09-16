from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from billpay_api.ids import new_id
from billpay_api.persistence.models import LedgerAccount, LedgerEntry, LedgerTransaction

PLATFORM_SETTLEMENT_CASH = "ledger_platform_settlement_cash"
CUSTOMER_BILL_PAYMENT_LIABILITY = "ledger_customer_bill_payment_liability"
BILLER_SETTLEMENT_PAYABLE = "ledger_biller_settlement_payable"
PROVIDER_CLEARING = "ledger_provider_clearing"
FEES_REVENUE = "ledger_fees_revenue"
PAYMENT_LOSS_RECEIVABLE = "ledger_payment_loss_receivable"

LEDGER_ACCOUNT_DEFINITIONS: tuple[tuple[str, str, str, str], ...] = (
    (PLATFORM_SETTLEMENT_CASH, "Platform settlement cash", "asset", "debit"),
    (
        CUSTOMER_BILL_PAYMENT_LIABILITY,
        "Customer bill-payment liability",
        "liability",
        "credit",
    ),
    (BILLER_SETTLEMENT_PAYABLE, "Biller settlement payable", "liability", "credit"),
    (PROVIDER_CLEARING, "Provider clearing", "asset", "debit"),
    (FEES_REVENUE, "Fees revenue", "revenue", "credit"),
    (PAYMENT_LOSS_RECEIVABLE, "Payment loss/receivable", "asset", "debit"),
)


@dataclass(frozen=True)
class LedgerAccountBalance:
    account: LedgerAccount
    debit_cents: int
    credit_cents: int
    balance_cents: int


def ensure_ledger_accounts(session: Session) -> None:
    for account_id, name, account_type, normal_balance in LEDGER_ACCOUNT_DEFINITIONS:
        if session.get(LedgerAccount, account_id) is None:
            session.add(
                LedgerAccount(
                    id=account_id,
                    name=name,
                    account_type=account_type,
                    normal_balance=normal_balance,
                    status="active",
                )
            )


def post_funding_succeeded(
    *,
    session: Session,
    payment_order_id: str,
    payment_leg_id: str,
    amount: str,
) -> LedgerTransaction | None:
    return _post_balanced_transaction(
        session=session,
        payment_order_id=payment_order_id,
        transaction_type="funding_succeeded",
        description="Funding leg settled into platform settlement cash",
        source_type="payment_leg",
        source_id=f"{payment_leg_id}:funding_succeeded",
        entries=(
            (PLATFORM_SETTLEMENT_CASH, _amount_to_cents(amount), 0),
            (CUSTOMER_BILL_PAYMENT_LIABILITY, 0, _amount_to_cents(amount)),
        ),
    )


def post_delivery_succeeded(
    *,
    session: Session,
    payment_order_id: str,
    payment_leg_id: str,
    amount: str,
) -> LedgerTransaction | None:
    return _post_balanced_transaction(
        session=session,
        payment_order_id=payment_order_id,
        transaction_type="delivery_succeeded",
        description="Delivery leg relieved customer bill-payment liability",
        source_type="payment_leg",
        source_id=f"{payment_leg_id}:delivery_succeeded",
        entries=(
            (CUSTOMER_BILL_PAYMENT_LIABILITY, _amount_to_cents(amount), 0),
            (PLATFORM_SETTLEMENT_CASH, 0, _amount_to_cents(amount)),
        ),
    )


def ledger_transactions_for_payment(
    session: Session,
    payment_order_id: str,
) -> list[LedgerTransaction]:
    return list(
        session.scalars(
            select(LedgerTransaction)
            .where(LedgerTransaction.payment_order_id == payment_order_id)
            .order_by(LedgerTransaction.posted_at, LedgerTransaction.id)
        ).all()
    )


def ledger_entries_for_transaction(
    session: Session,
    ledger_transaction_id: str,
) -> list[LedgerEntry]:
    return list(
        session.scalars(
            select(LedgerEntry)
            .where(LedgerEntry.ledger_transaction_id == ledger_transaction_id)
            .order_by(LedgerEntry.id)
        ).all()
    )


def ledger_account_balances(session: Session) -> list[LedgerAccountBalance]:
    accounts = session.scalars(select(LedgerAccount).order_by(LedgerAccount.id)).all()
    entries = session.scalars(select(LedgerEntry)).all()
    totals: dict[str, tuple[int, int]] = {account.id: (0, 0) for account in accounts}
    for entry in entries:
        debit_cents, credit_cents = totals[entry.ledger_account_id]
        totals[entry.ledger_account_id] = (
            debit_cents + entry.debit_cents,
            credit_cents + entry.credit_cents,
        )
    return [
        LedgerAccountBalance(
            account=account,
            debit_cents=totals[account.id][0],
            credit_cents=totals[account.id][1],
            balance_cents=_normal_balance_cents(
                normal_balance=account.normal_balance,
                debit_cents=totals[account.id][0],
                credit_cents=totals[account.id][1],
            ),
        )
        for account in accounts
    ]


def unbalanced_ledger_transaction_ids(session: Session) -> list[str]:
    transactions = session.scalars(select(LedgerTransaction).order_by(LedgerTransaction.id)).all()
    unbalanced: list[str] = []
    for transaction in transactions:
        entries = ledger_entries_for_transaction(session, transaction.id)
        if sum(entry.debit_cents for entry in entries) != sum(
            entry.credit_cents for entry in entries
        ):
            unbalanced.append(transaction.id)
    return unbalanced


def _post_balanced_transaction(
    *,
    session: Session,
    payment_order_id: str,
    transaction_type: str,
    description: str,
    source_type: str,
    source_id: str,
    entries: tuple[tuple[str, int, int], ...],
) -> LedgerTransaction | None:
    existing = session.scalars(
        select(LedgerTransaction).where(
            LedgerTransaction.source_type == source_type,
            LedgerTransaction.source_id == source_id,
        )
    ).one_or_none()
    if existing is not None:
        return None

    if len(entries) < 2:
        raise ValueError("ledger transaction requires at least two entries")
    total_debits = sum(debit_cents for _, debit_cents, _ in entries)
    total_credits = sum(credit_cents for _, _, credit_cents in entries)
    if total_debits != total_credits:
        raise ValueError("ledger transaction must balance")
    if total_debits <= 0:
        raise ValueError("ledger transaction amount must be positive")

    ensure_ledger_accounts(session)
    transaction = LedgerTransaction(
        id=new_id("ltx"),
        payment_order_id=payment_order_id,
        transaction_type=transaction_type,
        description=description,
        source_type=source_type,
        source_id=source_id,
    )
    session.add(transaction)
    session.flush()
    for account_id, debit_cents, credit_cents in entries:
        if debit_cents < 0 or credit_cents < 0:
            raise ValueError("ledger entry amounts cannot be negative")
        if debit_cents > 0 and credit_cents > 0:
            raise ValueError("ledger entry cannot contain both debit and credit")
        session.add(
            LedgerEntry(
                id=new_id("le"),
                ledger_transaction_id=transaction.id,
                ledger_account_id=account_id,
                payment_order_id=payment_order_id,
                debit_cents=debit_cents,
                credit_cents=credit_cents,
            )
        )
    return transaction


def _amount_to_cents(amount: str) -> int:
    cents = (Decimal(amount) * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


def _normal_balance_cents(
    *,
    normal_balance: str,
    debit_cents: int,
    credit_cents: int,
) -> int:
    if normal_balance == "credit":
        return credit_cents - debit_cents
    return debit_cents - credit_cents
